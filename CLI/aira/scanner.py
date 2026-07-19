"""
AIRA Scanner — Core orchestrator.

Supports:
- static scanning via language-specific checkers
- optional provider-assisted LLM scans
- hybrid mode that merges static and LLM findings
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    from aira.checkers.js_checker import JSChecker
    from aira.checkers.python_checker import PythonChecker
    from aira.checkers.test_coverage_checker import scan_test_files
    from aira.finding_metadata import enrich_finding
    from aira.llm import LLMConfig, LLMRoutingError, run_llm_json_audit
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from aira.checkers.js_checker import JSChecker
    from aira.checkers.python_checker import PythonChecker
    from aira.checkers.test_coverage_checker import scan_test_files
    from aira.finding_metadata import enrich_finding
    from aira.llm import LLMConfig, LLMRoutingError, run_llm_json_audit

from aira import __version__

CHECKS = {
    "C01": ("success_integrity", "SUCCESS INTEGRITY"),
    "C02": ("audit_integrity", "AUDIT / EVIDENCE INTEGRITY"),
    "C03": ("exception_handling", "BROAD EXCEPTION SUPPRESSION"),
    "C04": ("fallback_control", "DISTRIBUTED FALLBACK / DEGRADED EXECUTION"),
    "C05": ("bypass_controls", "BYPASS / OVERRIDE PATHS"),
    "C06": ("return_contracts", "AMBIGUOUS RETURN CONTRACTS"),
    "C07": ("logic_consistency", "PARALLEL LOGIC DRIFT"),
    "C08": ("background_tasks", "UNSUPERVISED BACKGROUND TASKS"),
    "C09": ("environment_safety", "ENVIRONMENT-DEPENDENT SAFETY"),
    "C10": ("startup_integrity", "STARTUP INTEGRITY"),
    "C11": ("determinism", "DETERMINISTIC REASONING DRIFT"),
    "C12": ("lineage", "SOURCE-TO-OUTPUT LINEAGE"),
    "C13": ("confidence_representation", "CONFIDENCE MISREPRESENTATION"),
    "C14": ("test_coverage_symmetry", "TEST COVERAGE ASYMMETRY"),
    "C15": ("idempotency_safety", "RETRY / IDEMPOTENCY ASSUMPTION DRIFT"),
}
CHECK_ID_BY_KEY = {key: check_id for check_id, (key, _) in CHECKS.items()}
CHECK_NAME_BY_KEY = {key: label for _, (key, label) in CHECKS.items()}

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}


class ScanTargetError(ValueError):
    """Raised when a path cannot be scanned (missing, wrong type, no matching files, etc.)."""


def supported_extensions_hint() -> str:
    """Comma-separated list of file extensions scanned in static/hybrid modes."""
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


def validate_scan_target(path: Path) -> None:
    """
    Validate that ``path`` can be scanned before starting work.

    Raises:
        ScanTargetError: If the path is missing, not a file/directory, or a single file with an unsupported extension.
    """
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise ScanTargetError(f"Cannot resolve path {path}: {exc}") from exc

    if not resolved.exists():
        raise ScanTargetError(
            f"Path does not exist or is not reachable: {resolved}. "
            "Check the spelling, symlinks, and filesystem permissions."
        )
    if not resolved.is_file() and not resolved.is_dir():
        raise ScanTargetError(f"Not a file or directory: {resolved}")

    if resolved.is_file():
        ext = resolved.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ScanTargetError(
                f"Unsupported file type for single-file scan ({ext or 'no extension'}). "
                f"Supported extensions: {supported_extensions_hint()}. "
                "Scan a directory to include multiple languages, or convert/add a supported source file."
            )


def describe_empty_scan_result(scanner: "AIRAScanner", files_scanned: int) -> Optional[str]:
    """If ``files_scanned`` is zero, return a user-facing explanation; otherwise ``None``."""
    if files_scanned > 0:
        return None
    if scanner.target.is_file():
        if scanner.is_target_excluded_from_static_scan():
            return (
                "The scan target file matches an --exclude pattern, so nothing was analyzed. "
                "Remove or narrow --exclude patterns to include this file."
            )
        return (
            "No files were analyzed. If you see this message, report it as a bug; "
            "the CLI should reject unsupported single-file targets before scanning."
        )
    return (
        f"No scannable source files found under {scanner.target}. "
        f"Supported extensions: {supported_extensions_hint()}. "
        "The tree may contain only unsupported file types, or --exclude may be filtering all matches."
    )


SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", "dist", "build", ".tox", "coverage", ".mypy_cache",
}

LLM_SYSTEM_PROMPT = (
    f"You are AIRA — the AI-Induced Risk Audit scanner v{__version__}. "
    "You audit code for truthful failure handling. Return JSON only."
)


class AIRAScannerError(RuntimeError):
    """Base error for scanner failures that should be shown cleanly by the CLI."""


class ScannerInputError(AIRAScannerError, ValueError):
    """Raised when the requested scan target or options cannot produce a valid scan."""


class ScannerExecutionError(AIRAScannerError):
    """Raised when scanning starts but an operational dependency fails."""


@dataclass
class ScanResult:
    target: str
    scanned_at: str
    files_scanned: int
    findings_total: int
    check_results: Dict[str, str]
    findings: List[Dict[str, Any]]
    summary: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


def _default_check_results(files_scanned: int, *, coverage_complete: Optional[bool] = None) -> Dict[str, str]:
    if coverage_complete is None:
        coverage_complete = files_scanned > 0
    results: Dict[str, str] = {}
    for check_id, (key, _) in CHECKS.items():
        if not coverage_complete or check_id in {"C07", "C12"}:
            results[key] = "UNKNOWN"
        else:
            results[key] = "PASS"
    return results


def _artifact_counts(files_scanned: int, values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    supplied = values or {}
    discovered = int(supplied.get("files_discovered", files_scanned) or 0)
    analyzed = int(supplied.get("files_analyzed", files_scanned) or 0)
    partial = int(supplied.get("files_partial", 0) or 0)
    failed = int(supplied.get("files_failed", 0) or 0)
    omitted = int(supplied.get("files_omitted", 0) or 0)
    if discovered <= 0:
        completeness = "unavailable"
    elif analyzed == discovered and partial == 0 and failed == 0 and omitted == 0:
        completeness = "complete"
    elif analyzed == 0 and partial == 0 and failed + omitted >= discovered:
        completeness = "failed"
    else:
        completeness = "partial"
    return {
        "files_discovered": discovered,
        "files_analyzed": analyzed,
        "files_partial": partial,
        "files_failed": failed,
        "files_omitted": omitted,
        "scan_completeness": completeness,
    }


def _summarize(
    findings: List[Dict[str, Any]],
    check_results: Dict[str, str],
    files_scanned: int,
    artifact_counts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    high = sum(1 for finding in findings if finding.get("severity") == "HIGH")
    medium = sum(1 for finding in findings if finding.get("severity") == "MEDIUM")
    low = sum(1 for finding in findings if finding.get("severity") == "LOW")
    return {
        "files_scanned": files_scanned,
        **_artifact_counts(files_scanned, artifact_counts),
        "findings_total": len(findings),
        "by_severity": {
            "HIGH": high,
            "MEDIUM": medium,
            "LOW": low,
        },
        "checks_failed": sum(1 for value in check_results.values() if value == "FAIL"),
        "checks_passed": sum(1 for value in check_results.values() if value == "PASS"),
        "checks_unknown": sum(1 for value in check_results.values() if value == "UNKNOWN"),
        "requires_human_review": ["logic_consistency (C07)", "lineage (C12)"],
    }


def _normalize_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    normalized = []
    for finding in findings:
        item = {
            "check_id": finding.get("check_id", "C00"),
            "check_name": finding.get("check_name", "UNSPECIFIED"),
            "severity": finding.get("severity", "LOW") if finding.get("severity") in {"HIGH", "MEDIUM", "LOW"} else "LOW",
            "file": finding.get("file", ""),
            "line": _coerce_line_number(finding.get("line", 0)),
            "description": str(finding.get("description", "")),
            "snippet": str(finding.get("snippet", "") or ""),
        }
        for optional_key in (
            "boundary_type",
            "context",
            "evidence",
            "fingerprint_version",
            "fingerprint",
            "semantic_fingerprint",
            "location_fingerprint",
        ):
            if optional_key in finding:
                item[optional_key] = finding[optional_key]
        normalized.append(enrich_finding(item))
    return sorted(normalized, key=lambda item: (severity_rank.get(item["severity"], 3), item["file"], item["line"], item["check_id"]))


def _coerce_line_number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_result(
    target: Path,
    files_scanned: int,
    findings: List[Dict[str, Any]],
    check_results: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    artifact_counts: Optional[Dict[str, Any]] = None,
) -> ScanResult:
    normalized_findings = _normalize_findings(findings)
    final_check_results = check_results or _default_check_results(files_scanned)
    summary = _summarize(
        normalized_findings,
        final_check_results,
        files_scanned,
        artifact_counts=artifact_counts,
    )
    return ScanResult(
        target=str(target),
        scanned_at=datetime.now(timezone.utc).isoformat(),
        files_scanned=files_scanned,
        findings_total=len(normalized_findings),
        check_results=final_check_results,
        findings=normalized_findings,
        summary=summary,
        metadata=metadata or {},
    )


def _merge_check_status(left: str, right: str) -> str:
    if "FAIL" in {left, right}:
        return "FAIL"
    if "PASS" in {left, right}:
        return "PASS"
    return "UNKNOWN"


def merge_scan_results(primary: ScanResult, secondary: ScanResult, mode: str) -> ScanResult:
    merged_findings = primary.findings + secondary.findings
    deduped = {}
    for finding in merged_findings:
        key = (
            finding.get("check_id"),
            finding.get("file"),
            finding.get("line"),
            finding.get("description"),
        )
        deduped[key] = finding

    merged_checks = {
        key: _merge_check_status(primary.check_results.get(key, "UNKNOWN"), secondary.check_results.get(key, "UNKNOWN"))
        for _, (key, _) in CHECKS.items()
    }
    metadata = {
        "mode": mode,
        "sources": [primary.metadata, secondary.metadata],
    }
    discovered = max(
        int(primary.summary.get("files_discovered", primary.files_scanned)),
        int(secondary.summary.get("files_discovered", secondary.files_scanned)),
    )
    analyzed = max(
        int(primary.summary.get("files_analyzed", primary.files_scanned)),
        int(secondary.summary.get("files_analyzed", secondary.files_scanned)),
    )
    fully_analyzed = discovered > 0 and analyzed >= discovered
    merged_artifact_counts = {
        "files_discovered": discovered,
        "files_analyzed": min(analyzed, discovered),
        "files_partial": 0 if fully_analyzed else max(
            int(primary.summary.get("files_partial", 0)),
            int(secondary.summary.get("files_partial", 0)),
        ),
        "files_failed": 0 if fully_analyzed else max(
            int(primary.summary.get("files_failed", 0)),
            int(secondary.summary.get("files_failed", 0)),
        ),
        "files_omitted": 0 if fully_analyzed else max(
            int(primary.summary.get("files_omitted", 0)),
            int(secondary.summary.get("files_omitted", 0)),
        ),
    }
    return _build_result(
        Path(primary.target),
        max(primary.files_scanned, secondary.files_scanned),
        list(deduped.values()),
        check_results=merged_checks,
        metadata=metadata,
        artifact_counts=merged_artifact_counts,
    )


class AIRAScanner:
    def __init__(self, target: str, exclude_dirs: Optional[List[str]] = None):
        self.target = Path(target).resolve()
        self.exclude_patterns = tuple(item.strip() for item in (exclude_dirs or []) if item.strip())

    def is_target_excluded_from_static_scan(self) -> bool:
        """Whether the scan root path is excluded by built-in skips or user --exclude patterns."""
        return self._is_excluded_path(self.target)

    def scan(self, mode: str = "static", llm_config: Optional[LLMConfig] = None) -> ScanResult:
        if mode not in {"static", "llm", "hybrid"}:
            raise ScannerInputError(f"Unsupported scan mode: {mode}")
        self._files_to_scan()

        if mode == "static":
            return self._scan_static()
        if mode == "llm":
            return self._scan_llm(llm_config or LLMConfig())

        static_result = self._scan_static()
        try:
            llm_result = self._scan_llm(llm_config or LLMConfig())
        except LLMRoutingError as exc:
            static_result.metadata = {
                **static_result.metadata,
                "mode": "hybrid",
                "llm_fallback": "static_only",
                "notes": [f"LLM scan unavailable: {exc}"],
            }
            return static_result

        return merge_scan_results(static_result, llm_result, mode="hybrid")

    def _scan_static(self) -> ScanResult:
        findings: List[Dict[str, Any]] = []
        files = self._files_to_scan()
        artifacts: List[Dict[str, Any]] = []
        for filepath in files:
            file_findings, artifact = self._scan_static_file(filepath)
            findings.extend(file_findings)
            artifacts.append(artifact)

        capability_gaps: Dict[str, List[str]] = {}
        if self.target.is_dir():
            _, test_findings = scan_test_files(str(self.target), is_excluded=self._is_excluded_path)
            for finding in test_findings:
                normalized = dict(finding)
                if normalized.get("file"):
                    normalized["file"] = self._display_path(Path(normalized["file"]))
                findings.append(self._enrich_display_finding(normalized))
            test_analysis_failures = sorted({
                self._display_path(Path(str(finding.get("file"))))
                for finding in test_findings
                if finding.get("check_id") == "SCANNER" and finding.get("file")
            })
            if test_analysis_failures:
                capability_gaps["test_coverage_symmetry"] = test_analysis_failures

        failed_checks = {finding["check_id"] for finding in findings if str(finding.get("check_id", "")).startswith("C")}
        status_counts = {
            status: sum(1 for artifact in artifacts if artifact.get("status") == status)
            for status in ("analyzed", "partial", "failed", "omitted")
        }
        files_discovered = len(files)
        coverage_complete = status_counts["analyzed"] == files_discovered
        check_results = _default_check_results(
            files_discovered,
            coverage_complete=coverage_complete,
        )
        for check_id, (key, _) in CHECKS.items():
            if check_id in failed_checks:
                check_results[key] = "FAIL"
        for check_key in capability_gaps:
            if check_results.get(check_key) != "FAIL":
                check_results[check_key] = "UNKNOWN"

        return _build_result(
            self.target,
            status_counts["analyzed"],
            findings,
            check_results=check_results,
            metadata={
                "mode": "static",
                "engine": "static",
                "artifacts": artifacts,
                "capability_gaps": capability_gaps,
            },
            artifact_counts={
                "files_discovered": files_discovered,
                "files_analyzed": status_counts["analyzed"],
                "files_partial": status_counts["partial"],
                "files_failed": status_counts["failed"],
                "files_omitted": status_counts["omitted"],
            },
        )

    def _scan_static_file(self, filepath: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        ext = filepath.suffix.lower()
        lang = SUPPORTED_EXTENSIONS.get(ext)
        display_path = self._display_path(filepath)
        if not lang:
            return [], {
                "path": display_path,
                "language": "unsupported",
                "status": "omitted",
                "parser": "unsupported",
            }

        try:
            checker = PythonChecker(str(filepath)) if lang == "python" else JSChecker(str(filepath))
            findings = [
                enrich_finding(
                    {
                        "check_id": item.check_id,
                        "check_name": item.check_name,
                        "severity": item.severity,
                        "file": display_path,
                        "line": item.line,
                        "description": item.description,
                        "snippet": item.snippet or "",
                    },
                    source=checker.source,
                    source_path=filepath,
                    language=lang,
                )
                for item in checker.run()
            ]
            if lang == "python":
                status = "analyzed" if checker.parse_ok else "failed"
                parser = "python_ast" if checker.parse_ok else "python_ast_failed"
                reason = "" if checker.parse_ok else str(checker.parse_error or "Python parser failure")
            else:
                status = "analyzed" if checker.parse_ok else "partial"
                parser = "esprima" if checker.parse_ok else "lexical_fallback"
                reason = "" if checker.parse_ok else "JavaScript/TypeScript parser unavailable or unsupported syntax"
            artifact = {
                "path": display_path,
                "language": lang,
                "status": status,
                "parser": parser,
            }
            if reason:
                artifact["reason"] = reason
            return findings, artifact
        except OSError as exc:
            return [self._scanner_error_finding(filepath, f"Unable to read file: {exc}")], {
                "path": display_path,
                "language": lang,
                "status": "failed",
                "parser": "unavailable",
                "reason": f"Unable to read file: {exc}",
            }
        except Exception as exc:
            return [self._scanner_error_finding(filepath, f"Scanner failed on file: {exc}")], {
                "path": display_path,
                "language": lang,
                "status": "failed",
                "parser": "failed",
                "reason": f"Scanner failed on file: {exc}",
            }

    def _scanner_error_finding(self, filepath: Path, description: str, line: int = 0) -> Dict[str, Any]:
        return enrich_finding({
            "check_id": "SCANNER",
            "check_name": "SCANNER ERROR",
            "severity": "HIGH",
            "file": self._display_path(filepath),
            "line": line,
            "description": f"{description}. Fix this file or exclude it before relying on scan results.",
            "snippet": "",
        }, source_path=filepath)

    def _source_path_for_display_path(self, display_path: str) -> Optional[Path]:
        if not display_path:
            return self.target if self.target.is_file() else None
        canonical = self._canonical_artifact_path(display_path)
        if not canonical:
            return None
        candidate = Path(canonical)
        if self.target.is_file():
            return self.target if canonical == self.target.name else None
        root = self.target.resolve()
        resolved = (root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError:
            return None
        return resolved if resolved.is_file() else None

    @staticmethod
    def _canonical_artifact_path(value: Any) -> Optional[str]:
        raw = str(value or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if PureWindowsPath(raw).is_absolute():
            return None
        candidate = PurePosixPath(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None
        parts = [part for part in candidate.parts if part not in {"", "."}]
        if not parts:
            return ""
        return PurePosixPath(*parts).as_posix()

    def _validated_model_artifact(
        self,
        value: Any,
        allowed_artifacts: set,
    ) -> Tuple[Optional[str], Optional[str]]:
        canonical = self._canonical_artifact_path(value)
        if canonical is None:
            return None, "noncanonical_artifact_path"
        if not canonical:
            return "", None
        if canonical not in allowed_artifacts:
            return None, "artifact_not_in_manifest"
        return canonical, None

    def _enrich_display_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        source_path = self._source_path_for_display_path(str(finding.get("file") or ""))
        language = SUPPORTED_EXTENSIONS.get(source_path.suffix.lower()) if source_path else None
        return enrich_finding(finding, source_path=source_path, language=language)

    def _files_to_scan(self) -> List[Path]:
        if not self.target.exists():
            raise ScannerInputError(f"Path not found: {self.target}")
        if self.target.is_file():
            if self._is_excluded_path(self.target):
                raise ScannerInputError(
                    f"Target is excluded by built-in skip directories or configured --exclude patterns: {self.target}"
                )
            if self.target.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ScannerInputError(
                    f"Unsupported file type for scan: {self.target}. Supported extensions: {supported_extensions_hint()}"
                )
            return [self.target]
        if not self.target.is_dir():
            raise ScannerInputError(f"Target must be a file or directory: {self.target}")

        files = self._iter_supported_files()
        if not files:
            raise ScannerInputError(
                f"No supported source files found in directory: {self.target}. "
                f"Supported extensions: {supported_extensions_hint()}. "
                "Check the path and --exclude patterns."
            )
        return files

    def _display_path(self, filepath: Path) -> str:
        if self.target.is_file():
            return filepath.name
        return str(filepath.relative_to(self.target))

    def _relative_path(self, filepath: Path) -> str:
        if self.target.is_file():
            base = self.target.parent
        else:
            base = self.target
        try:
            return filepath.resolve().relative_to(base).as_posix()
        except ValueError:
            return filepath.name

    def _matches_exclude_pattern(self, filepath: Path, pattern: str) -> bool:
        normalized = pattern.strip().replace("\\", "/").rstrip("/")
        if not normalized:
            return False

        relative_path = self._relative_path(filepath)
        basename = filepath.name

        if basename == normalized or relative_path == normalized:
            return True
        if fnmatch.fnmatchcase(basename, normalized) or fnmatch.fnmatchcase(relative_path, normalized):
            return True
        if "/" not in normalized and not any(ch in normalized for ch in "*?[]"):
            return normalized in filepath.parts
        if "/" in normalized and relative_path.endswith(f"/{normalized}"):
            return True
        return False

    def _is_excluded_path(self, filepath: Path) -> bool:
        for skip_dir in SKIP_DIRS:
            if skip_dir in filepath.parts:
                return True
        return any(self._matches_exclude_pattern(filepath, pattern) for pattern in self.exclude_patterns)

    def _iter_supported_files(self) -> List[Path]:
        files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.target):
            current_dir = Path(dirpath)
            dirnames[:] = [name for name in dirnames if not self._is_excluded_path(current_dir / name)]
            for filename in filenames:
                filepath = current_dir / filename
                if self._is_excluded_path(filepath):
                    continue
                if filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(filepath)
        return sorted(files)

    def _scan_llm(self, llm_config: LLMConfig) -> ScanResult:
        combined_source, files_scanned, truncated, artifacts = self._build_llm_input(llm_config.max_context_chars)
        prompt = self._build_llm_prompt(combined_source)
        response = run_llm_json_audit(llm_config, LLM_SYSTEM_PROMPT, prompt)
        result = self._normalize_llm_result(
            response,
            files_scanned,
            truncated,
            llm_config,
            artifacts=artifacts,
        )
        return result

    def _build_llm_input(self, max_context_chars: int) -> Tuple[str, int, bool, List[Dict[str, Any]]]:
        files = self._files_to_scan()
        sections: List[str] = []
        artifacts: List[Dict[str, Any]] = []
        total_chars = 0
        truncated = False
        files_included = 0

        for file_index, filepath in enumerate(files):
            rel_path = filepath.name if self.target.is_file() else str(filepath.relative_to(self.target))
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise ScannerExecutionError(f"Unable to read {rel_path}: {exc}") from exc
            section = f"# FILE: {rel_path}\n{content}\n"
            if total_chars + len(section) <= max_context_chars:
                sections.append(section)
                total_chars += len(section)
                files_included += 1
                artifacts.append({
                    "path": rel_path,
                    "language": SUPPORTED_EXTENSIONS.get(filepath.suffix.lower(), "unknown"),
                    "status": "analyzed",
                    "parser": "llm_input",
                })
                continue

            remaining = max_context_chars - total_chars
            if remaining > 0:
                snippet = section[:remaining]
                sections.append(f"{snippet}\n[...truncated for size...]\n")
                files_included += 1
                artifacts.append({
                    "path": rel_path,
                    "language": SUPPORTED_EXTENSIONS.get(filepath.suffix.lower(), "unknown"),
                    "status": "partial",
                    "parser": "llm_input",
                    "reason": "Input truncated by max_context_chars",
                })
            truncated = True
            for omitted_path in files[file_index + 1 if remaining > 0 else file_index:]:
                omitted_rel_path = omitted_path.name if self.target.is_file() else str(omitted_path.relative_to(self.target))
                artifacts.append({
                    "path": omitted_rel_path,
                    "language": SUPPORTED_EXTENSIONS.get(omitted_path.suffix.lower(), "unknown"),
                    "status": "omitted",
                    "parser": "llm_input",
                    "reason": "Omitted after max_context_chars was exhausted",
                })
            break

        return "\n".join(sections), files_included, truncated, artifacts

    def _build_llm_prompt(self, combined_source: str) -> str:
        return f"""Analyze the following code snapshot with AIRA v{__version__}.

Return ONLY valid JSON in this exact structure:
{{
  "ai_failure_audit": {{
    "success_integrity": "PASS|FAIL|UNKNOWN",
    "audit_integrity": "PASS|FAIL|UNKNOWN",
    "exception_handling": "PASS|FAIL|UNKNOWN",
    "fallback_control": "PASS|FAIL|UNKNOWN",
    "bypass_controls": "PASS|FAIL|UNKNOWN",
    "return_contracts": "PASS|FAIL|UNKNOWN",
    "logic_consistency": "UNKNOWN",
    "background_tasks": "PASS|FAIL|UNKNOWN",
    "environment_safety": "PASS|FAIL|UNKNOWN",
    "startup_integrity": "PASS|FAIL|UNKNOWN",
    "determinism": "PASS|FAIL|UNKNOWN",
    "lineage": "UNKNOWN",
    "confidence_representation": "PASS|FAIL|UNKNOWN",
    "test_coverage_symmetry": "PASS|FAIL|UNKNOWN",
    "idempotency_safety": "PASS|FAIL|UNKNOWN"
  }},
  "findings": [
    {{
      "check_id": "C01",
      "check_name": "SUCCESS INTEGRITY",
      "severity": "HIGH|MEDIUM|LOW",
      "file": "relative/path.py",
      "line": 42,
      "description": "Specific grounded violation",
      "snippet": "optional code snippet"
    }}
  ]
}}

Rules:
- Keep C07 and C12 as UNKNOWN.
- Include only grounded findings.
- Use the file headers in the input for file attribution.
- If an exact file or line is unclear, use an empty file and line 0.

Code snapshot:

{combined_source}
"""

    def _normalize_llm_result(
        self,
        response: Dict[str, Any],
        files_scanned: int,
        truncated: bool,
        llm_config: LLMConfig,
        *,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> ScanResult:
        try:
            raw = json.loads(response["text"])
        except Exception as exc:
            raise LLMRoutingError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise LLMRoutingError("LLM returned JSON that is not an object.")

        raw_checks = raw.get("ai_failure_audit") or {}
        if not isinstance(raw_checks, dict):
            raw_checks = {}
        artifact_manifest = artifacts or []
        files_discovered = len(artifact_manifest) or files_scanned
        status_counts = {
            status: sum(1 for artifact in artifact_manifest if artifact.get("status") == status)
            for status in ("analyzed", "partial", "failed", "omitted")
        }
        coverage_complete = (
            files_discovered > 0
            and status_counts["analyzed"] == files_discovered
            and not truncated
        )
        check_results = _default_check_results(files_scanned, coverage_complete=False)
        for _, (key, _) in CHECKS.items():
            value = raw_checks.get(key)
            if value == "FAIL":
                check_results[key] = value
            elif value == "PASS" and coverage_complete:
                check_results[key] = value
            elif value == "UNKNOWN":
                check_results[key] = value
        check_results["logic_consistency"] = "UNKNOWN"
        check_results["lineage"] = "UNKNOWN"

        findings = []
        rejected_findings = []
        allowed_artifacts = {
            str(artifact.get("path") or "")
            for artifact in artifact_manifest
            if artifact.get("status") in {"analyzed", "partial"}
        }
        for item in raw.get("findings", []) if isinstance(raw.get("findings"), list) else []:
            if not isinstance(item, dict):
                continue
            check_id = item.get("check_id", "")
            normalized_check_id = check_id or CHECK_ID_BY_KEY.get(item.get("check_key", ""), "C00")
            if normalized_check_id in {"C07", "C12"}:
                continue
            artifact, rejection_reason = self._validated_model_artifact(
                item.get("file", ""),
                allowed_artifacts,
            )
            if rejection_reason:
                rejected_findings.append({
                    "file": str(item.get("file") or ""),
                    "check_id": str(normalized_check_id or ""),
                    "reason": rejection_reason,
                })
                continue
            check_name = item.get("check_name") or CHECKS.get(check_id, ("", "UNSPECIFIED"))[1]
            findings.append({
                "check_id": normalized_check_id,
                "check_name": check_name,
                "severity": item.get("severity", "LOW"),
                "file": artifact or "",
                "line": _coerce_line_number(item.get("line", 0)),
                "description": str(item.get("description", "")),
                "snippet": str(item.get("snippet", "") or ""),
            })
        findings = [self._enrich_display_finding(finding) for finding in findings]
        failed_checks = {
            str(finding.get("check_id") or "").upper()
            for finding in findings
            if str(finding.get("check_id") or "").upper() in CHECKS
        }
        for check_id in failed_checks:
            check_results[CHECKS[check_id][0]] = "FAIL"

        return _build_result(
            self.target,
            status_counts["analyzed"],
            findings,
            check_results=check_results,
            metadata={
                "mode": "llm",
                "provider": response.get("provider"),
                "model": response.get("model"),
                "configured_provider": llm_config.provider,
                "truncated": truncated,
                "engine": "llm",
                "artifacts": artifact_manifest,
                "capability_gaps": {
                    "llm_input_coverage": [
                        artifact["path"]
                        for artifact in artifact_manifest
                        if artifact.get("status") != "analyzed"
                    ]
                } if not coverage_complete else {},
                "rejected_findings_count": len(rejected_findings),
                "rejected_findings": rejected_findings,
            },
            artifact_counts={
                "files_discovered": files_discovered,
                "files_analyzed": status_counts["analyzed"],
                "files_partial": status_counts["partial"],
                "files_failed": status_counts["failed"],
                "files_omitted": status_counts["omitted"],
            },
        )


def result_to_yaml(result: ScanResult) -> str:
    doc = {
        "aira_scan": {
            "version": __version__,
            "target": result.target,
            "scanned_at": result.scanned_at,
            "summary": result.summary,
            "metadata": result.metadata,
            "ai_failure_audit": result.check_results,
            "findings": result.findings,
        }
    }
    return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)


def result_to_json(result: ScanResult) -> str:
    return json.dumps({
        "aira_scan": {
            "version": __version__,
            "target": result.target,
            "scanned_at": result.scanned_at,
            "summary": result.summary,
            "metadata": result.metadata,
            "ai_failure_audit": result.check_results,
            "findings": result.findings,
        }
    }, indent=2)
