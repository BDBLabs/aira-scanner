"""
AIRA research submission helpers for CLI/CI usage.

This path is intentionally aggregate-only:
- no source code
- no file-level findings
- no snippets
- no raw target paths
"""

from __future__ import annotations

import json
import os
import re
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from aira import __version__ as AIRA_VERSION
from aira.scanner import CHECKS


BASELINE_FIELD_ORDER = (
    "Submitted At",
    "Checks JSON",
    "High Count",
    "Medium Count",
    "Low Count",
    "Total Findings",
    "Checks Failed",
    "Engine",
    "Source",
)

OPTIONAL_FIELD_ORDER = (
    "Check Count JSON",
    "Check Severity JSON",
    "Checks Passed",
    "Checks Unknown",
    "Files Scanned",
    "Scan Mode",
    "Provider",
    "Model",
    "Target Kind",
    "CI Workflow",
    "CI Run ID",
    "CI Ref",
)

UNKNOWN_FIELD_RE = re.compile(r'Unknown field name:\s*"?(?P<field>[^"]+)"?')
VALID_RESEARCH_BACKENDS = {"supabase", "jsonl", "airtable", "none"}
DEFAULT_HOSTED_RESEARCH_BACKEND = "supabase"
RESEARCH_BACKEND_ORDER = ("supabase", "jsonl", "airtable")
VALID_ATTRIBUTION_CLASSES = {"explicit_ai", "suspected_ai", "human_baseline", "unknown"}
VALID_SOURCE_KINDS = {"repo", "directory", "dataset_file", "dataset_repo", "ci_run", "manual"}
VALID_CHECK_STATUSES = {"PASS", "FAIL", "UNKNOWN"}
DEFAULT_SCORING_VERSION = "fti-v1"
CHECK_IDS = tuple(CHECKS.keys())
FTI_V1_WEIGHTS_BY_KEY = {
    "success_integrity": 3,
    "audit_integrity": 3,
    "exception_handling": 3,
    "confidence_representation": 3,
    "fallback_control": 2,
    "bypass_controls": 2,
    "return_contracts": 2,
    "determinism": 2,
    "idempotency_safety": 2,
    "logic_consistency": 1,
    "background_tasks": 1,
    "environment_safety": 1,
    "startup_integrity": 1,
    "lineage": 1,
    "test_coverage_symmetry": 1,
}
FTI_V1_TOTAL_WEIGHT = sum(FTI_V1_WEIGHTS_BY_KEY.values())


class ResearchSubmissionError(RuntimeError):
    """Raised when aggregate research submission fails."""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _env(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _non_empty_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _normalize_status(value: Any) -> str:
    normalized = str(value or "UNKNOWN").upper()
    return normalized if normalized in VALID_CHECK_STATUSES else "UNKNOWN"


def _canonicalize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _submission_option(submission_options: Optional[Dict[str, Any]], key: str, *env_names: str) -> Optional[str]:
    if submission_options:
        direct = submission_options.get(key)
        direct_str = _non_empty_str(str(direct)) if direct is not None else None
        if direct_str:
            return direct_str
    return _env(*env_names)


def _normalize_attribution_class(value: Optional[str]) -> str:
    normalized = _non_empty_str(value) or "unknown"
    if normalized not in VALID_ATTRIBUTION_CLASSES:
        raise ResearchSubmissionError(
            "Invalid attribution_class "
            f"'{normalized}'. Use one of: explicit_ai, suspected_ai, human_baseline, unknown."
        )
    return normalized


def _normalize_source_kind(value: Optional[str]) -> Optional[str]:
    normalized = _non_empty_str(value)
    if not normalized:
        return None
    if normalized not in VALID_SOURCE_KINDS:
        raise ResearchSubmissionError(
            "Invalid source_kind "
            f"'{normalized}'. Use one of: repo, directory, dataset_file, dataset_repo, ci_run, manual."
        )
    return normalized


def _normalize_scoring_version(value: Optional[str]) -> str:
    normalized = _non_empty_str(value) or DEFAULT_SCORING_VERSION
    if normalized != DEFAULT_SCORING_VERSION:
        raise ResearchSubmissionError(
            f"Unsupported scoring_version '{normalized}'. Only fti-v1 is currently supported."
        )
    return normalized


def infer_research_source(explicit_source: Optional[str] = None) -> str:
    if explicit_source:
        return explicit_source
    if _env("GITHUB_REPOSITORY"):
        return f"github:{_env('GITHUB_REPOSITORY')}"
    if _env("CI"):
        return "ci"
    return "aira-cli"


def infer_research_backend(explicit_backend: Optional[str] = None) -> str:
    requested = (explicit_backend or _env("AIRA_RESEARCH_BACKEND", "RESEARCH_BACKEND") or "").strip().lower()
    if requested:
        return requested
    if _env("SUPABASE_URL") and _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"):
        return "supabase"
    if _env("AIRA_RESEARCH_JSONL", "RESEARCH_JSONL"):
        return "jsonl"
    if _env("AIRTABLE_BASE_ID") and _env("AIRTABLE_TOKEN"):
        return "airtable"
    return "none"


def _is_valid_backend(name: str) -> bool:
    return name in VALID_RESEARCH_BACKENDS


def _airtable_target() -> tuple[Optional[str], str, Optional[str]]:
    return (
        _env("AIRTABLE_BASE_ID"),
        _env("AIRTABLE_TABLE") or "Submissions",
        _env("AIRTABLE_TOKEN"),
    )


def _supabase_target() -> tuple[Optional[str], str, Optional[str]]:
    return (
        (_env("SUPABASE_URL") or "").rstrip("/") or None,
        _env("SUPABASE_TABLE") or "aira_submissions",
        _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"),
    )


def _supabase_checks_table() -> str:
    return _env("SUPABASE_CHECKS_TABLE") or "aira_submission_checks"


def _jsonl_target() -> Optional[Path]:
    raw = _env("AIRA_RESEARCH_JSONL", "RESEARCH_JSONL")
    return Path(raw).expanduser() if raw else None


def airtable_config_snapshot() -> Dict[str, Any]:
    base_id, table, token = _airtable_target()
    return {
        "configured": bool(base_id and token),
        "base_id_configured": bool(base_id),
        "table": table,
        "token_configured": bool(token),
    }


def supabase_config_snapshot() -> Dict[str, Any]:
    url, table, key = _supabase_target()
    return {
        "configured": bool(url and key),
        "url_configured": bool(url),
        "table": table,
        "checks_table": _supabase_checks_table(),
        "key_configured": bool(key),
    }


def jsonl_config_snapshot() -> Dict[str, Any]:
    path = _jsonl_target()
    return {
        "configured": path is not None,
        "path": str(path) if path else "",
    }


def research_backend_snapshot(explicit_backend: Optional[str] = None) -> Dict[str, Any]:
    backend = infer_research_backend(explicit_backend)
    snapshot: Dict[str, Any] = {
        "backend": backend,
        "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
        "backend_order": list(RESEARCH_BACKEND_ORDER),
        "legacy_fallback_backend": "airtable",
    }
    if not _is_valid_backend(backend):
        snapshot.update({"configured": False, "invalid_backend": True})
        return snapshot
    if backend == "supabase":
        snapshot.update(supabase_config_snapshot())
    elif backend == "jsonl":
        snapshot.update(jsonl_config_snapshot())
    elif backend == "airtable":
        snapshot.update(airtable_config_snapshot())
        snapshot["legacy_fallback"] = True
    else:
        snapshot.update({"configured": False})
    return snapshot


def _engine_label(result) -> str:
    metadata = result.metadata or {}
    provider = metadata.get("provider") or metadata.get("engine")
    model = metadata.get("model")
    if provider and model:
        return f"{provider}:{model}"
    if provider:
        return str(provider)
    return str(metadata.get("mode", "static"))


def normalize_checks_json(raw: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    data = raw or {}
    normalized: Dict[str, str] = {}
    for check_id, (key, _) in CHECKS.items():
        normalized[key] = _normalize_status(data.get(key, data.get(check_id)))
    return normalized


def build_check_finding_counts(result) -> Dict[str, int]:
    counts: Dict[str, int] = {check_id: 0 for check_id in CHECK_IDS}
    for finding in result.findings or []:
        check_id = str(finding.get("check_id") or "UNSPECIFIED").upper()
        counts[check_id] = counts.get(check_id, 0) + 1
    return counts


def build_check_severity_counts(result) -> Dict[str, Dict[str, int]]:
    severity_counts: Dict[str, Dict[str, int]] = {
        check_id: {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "TOTAL": 0}
        for check_id in CHECK_IDS
    }
    for finding in result.findings or []:
        check_id = str(finding.get("check_id") or "UNSPECIFIED").upper()
        if check_id not in severity_counts:
            severity_counts[check_id] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "TOTAL": 0}
        severity = str(finding.get("severity") or "LOW").upper()
        if severity not in {"HIGH", "MEDIUM", "LOW"}:
            severity = "LOW"
        severity_counts[check_id][severity] += 1
        severity_counts[check_id]["TOTAL"] += 1
    return severity_counts


def build_submission_check_rows(
    checks_json: Dict[str, str],
    check_count_json: Dict[str, int],
    check_severity_json: Dict[str, Dict[str, int]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for check_id, (key, label) in CHECKS.items():
        severity = check_severity_json.get(check_id, {})
        rows.append(
            {
                "check_id": check_id,
                "check_key": key,
                "check_name": label,
                "status": _normalize_status(checks_json.get(key)),
                "weight": FTI_V1_WEIGHTS_BY_KEY[key],
                "finding_count": _normalize_int(check_count_json.get(check_id)),
                "high_count": _normalize_int(severity.get("HIGH")),
                "medium_count": _normalize_int(severity.get("MEDIUM")),
                "low_count": _normalize_int(severity.get("LOW")),
            }
        )
    return rows


def compute_fti_v1(checks_or_rows: Any) -> float:
    rows: List[Dict[str, Any]]
    if isinstance(checks_or_rows, list):
        rows = checks_or_rows
    else:
        rows = build_submission_check_rows(normalize_checks_json(checks_or_rows), {}, {})
    failed_weight = sum(row["weight"] for row in rows if row.get("status") == "FAIL")
    score = 100 - ((failed_weight / FTI_V1_TOTAL_WEIGHT) * 100)
    return round(score, 2)


def risk_level_for_fti(score: float) -> str:
    if score >= 85.0:
        return "LOW_RISK"
    if score >= 65.0:
        return "MODERATE_RISK"
    if score >= 40.0:
        return "HIGH_RISK"
    return "CRITICAL_RISK"


def _infer_source_kind(
    explicit_source_kind: Optional[str],
    source_id: Optional[str],
    source: str,
    target_kind: str,
) -> str:
    explicit = _normalize_source_kind(explicit_source_kind)
    if explicit:
        return explicit
    if _env("GITHUB_RUN_ID") or _env("GITHUB_WORKFLOW"):
        return "ci_run"
    if source.startswith("github:"):
        return "repo"
    if source_id and "/" in source_id:
        return "repo"
    if target_kind == "directory":
        return "directory"
    if target_kind == "file":
        return "dataset_file"
    return "manual"


def _resolve_sample_name(
    requested_sample_name: Optional[str],
    source_kind: str,
    source_id: Optional[str],
    source: str,
    target_name: Optional[str],
    fallback_seed: str,
) -> str:
    explicit = _non_empty_str(requested_sample_name)
    if explicit:
        return explicit
    if source_id:
        return source_id
    if source.startswith("github:"):
        return source.split("github:", 1)[1]
    if source_kind in {"repo", "dataset_repo"} and _non_empty_str(source):
        return source
    if target_name:
        return target_name
    return f"adhoc:{_sha256_hex(fallback_seed)[:16]}"


def _build_fingerprint_payload(record: Dict[str, Any], submission_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "attribution_class": record["attribution_class"],
        "checks_failed": record["checks_failed"],
        "checks_json": record["checks_json"],
        "checks_passed": record["checks_passed"],
        "checks_unknown": record["checks_unknown"],
        "ci_ref": record["ci_ref"],
        "ci_run_id": record["ci_run_id"],
        "ci_workflow": record["ci_workflow"],
        "engine": record["engine"],
        "files_scanned": record["files_scanned"],
        "high_count": record["high_count"],
        "language": record["language"],
        "low_count": record["low_count"],
        "medium_count": record["medium_count"],
        "metadata_json": record["metadata_json"],
        "model": record["model"],
        "provider": record["provider"],
        "ruleset_version": record["ruleset_version"],
        "sample_name": record["sample_name"],
        "sample_version": record["sample_version"],
        "scanner_name": record["scanner_name"],
        "scanner_version": record["scanner_version"],
        "scan_mode": record["scan_mode"],
        "scoring_version": record["scoring_version"],
        "source": record["source"],
        "source_id": record["source_id"],
        "source_kind": record["source_kind"],
        "submission_checks": [
            {
                "check_id": row["check_id"],
                "status": row["status"],
                "weight": row["weight"],
                "finding_count": row["finding_count"],
                "high_count": row["high_count"],
                "medium_count": row["medium_count"],
                "low_count": row["low_count"],
            }
            for row in submission_checks
        ],
        "target_kind": record["target_kind"],
        "total_findings": record["total_findings"],
    }


def _build_persisted_payload(record: Dict[str, Any], submission_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "attribution_class": record["attribution_class"],
        "check_count_json": record["check_count_json"],
        "check_severity_json": record["check_severity_json"],
        "checks_failed": record["checks_failed"],
        "checks_json": record["checks_json"],
        "checks_passed": record["checks_passed"],
        "checks_unknown": record["checks_unknown"],
        "ci_ref": record["ci_ref"],
        "ci_run_id": record["ci_run_id"],
        "ci_workflow": record["ci_workflow"],
        "engine": record["engine"],
        "files_scanned": record["files_scanned"],
        "fti_score": record["fti_score"],
        "high_count": record["high_count"],
        "language": record["language"],
        "low_count": record["low_count"],
        "medium_count": record["medium_count"],
        "metadata_json": record["metadata_json"],
        "model": record["model"],
        "parent_record_sha256": record["parent_record_sha256"],
        "provider": record["provider"],
        "risk_level": record["risk_level"],
        "ruleset_version": record["ruleset_version"],
        "sample_name": record["sample_name"],
        "sample_version": record["sample_version"],
        "scanner_name": record["scanner_name"],
        "scanner_version": record["scanner_version"],
        "scan_mode": record["scan_mode"],
        "scoring_version": record["scoring_version"],
        "source": record["source"],
        "source_id": record["source_id"],
        "source_kind": record["source_kind"],
        "submission_checks": [
            {
                "check_id": row["check_id"],
                "check_name": row["check_name"],
                "status": row["status"],
                "weight": row["weight"],
                "finding_count": row["finding_count"],
                "high_count": row["high_count"],
                "medium_count": row["medium_count"],
                "low_count": row["low_count"],
            }
            for row in submission_checks
        ],
        "submission_fingerprint": record["submission_fingerprint"],
        "submitted_at": record["submitted_at"],
        "target_kind": record["target_kind"],
        "total_findings": record["total_findings"],
    }


def build_baseline_submission_fields(result, source: Optional[str] = None) -> Dict[str, Any]:
    summary = result.summary or {}
    checks = result.check_results or {}
    return {
        "Submitted At": datetime.now(timezone.utc).isoformat(),
        "Checks JSON": json.dumps(checks, sort_keys=True),
        "High Count": int((summary.get("by_severity") or {}).get("HIGH", 0)),
        "Medium Count": int((summary.get("by_severity") or {}).get("MEDIUM", 0)),
        "Low Count": int((summary.get("by_severity") or {}).get("LOW", 0)),
        "Total Findings": int(summary.get("findings_total", 0)),
        "Checks Failed": int(summary.get("checks_failed", 0)),
        "Engine": _engine_label(result),
        "Source": infer_research_source(source),
    }


def build_optional_submission_fields(result) -> Dict[str, Any]:
    summary = result.summary or {}
    metadata = result.metadata or {}
    target_kind = "directory"
    try:
        target_kind = "file" if Path(result.target).is_file() else "directory"
    except OSError:
        pass

    fields = {
        "Check Count JSON": json.dumps(build_check_finding_counts(result), sort_keys=True),
        "Check Severity JSON": json.dumps(build_check_severity_counts(result), sort_keys=True),
        "Checks Passed": int(summary.get("checks_passed", 0)),
        "Checks Unknown": int(summary.get("checks_unknown", 0)),
        "Files Scanned": int(summary.get("files_scanned", 0)),
        "Scan Mode": str(metadata.get("mode", "static")),
        "Provider": str(metadata.get("provider") or metadata.get("engine") or "static"),
        "Model": str(metadata.get("model") or ""),
        "Target Kind": target_kind,
    }

    if _env("GITHUB_WORKFLOW"):
        fields["CI Workflow"] = _env("GITHUB_WORKFLOW")
    if _env("GITHUB_RUN_ID"):
        fields["CI Run ID"] = _env("GITHUB_RUN_ID")
    if _env("GITHUB_REF_NAME"):
        fields["CI Ref"] = _env("GITHUB_REF_NAME")

    return fields


def build_aggregate_submission_fields(result, source: Optional[str] = None) -> Dict[str, Any]:
    return {
        **build_baseline_submission_fields(result, source=source),
        **build_optional_submission_fields(result),
    }


def build_submission_bundle(
    result,
    source: Optional[str] = None,
    submission_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = result.summary or {}
    metadata = result.metadata or {}
    target_kind = "directory"
    try:
        target_kind = "file" if Path(result.target).is_file() else "directory"
    except OSError:
        pass
    source_label = infer_research_source(source)
    source_id = _submission_option(submission_options, "source_id", "AIRA_SOURCE_ID", "RESEARCH_SOURCE_ID")
    source_kind = _infer_source_kind(
        _submission_option(submission_options, "source_kind", "AIRA_SOURCE_KIND", "RESEARCH_SOURCE_KIND"),
        source_id,
        source_label,
        target_kind,
    )
    scanner_version = (
        _submission_option(submission_options, "scanner_version", "AIRA_SCANNER_VERSION", "RESEARCH_SCANNER_VERSION")
        or AIRA_VERSION
    )
    ruleset_version = (
        _submission_option(submission_options, "ruleset_version", "AIRA_RULESET_VERSION", "RESEARCH_RULESET_VERSION")
        or scanner_version
    )
    scoring_version = _normalize_scoring_version(
        _submission_option(submission_options, "scoring_version", "AIRA_SCORING_VERSION")
    )
    checks_json = normalize_checks_json(result.check_results or {})
    check_count_json = build_check_finding_counts(result)
    check_severity_json = build_check_severity_counts(result)
    submission_checks = build_submission_check_rows(checks_json, check_count_json, check_severity_json)
    fti_score = compute_fti_v1(submission_checks)
    fingerprint_seed = _canonicalize(
        {
            "checks_json": checks_json,
            "ci_ref": _env("GITHUB_REF_NAME"),
            "ci_run_id": _env("GITHUB_RUN_ID"),
            "ci_workflow": _env("GITHUB_WORKFLOW"),
            "metadata_json": metadata,
            "source": source_label,
            "source_id": source_id,
            "source_kind": source_kind,
            "target_kind": target_kind,
        }
    )
    sample_name = _resolve_sample_name(
        _submission_option(submission_options, "sample_name", "AIRA_SAMPLE_NAME", "RESEARCH_SAMPLE_NAME"),
        source_kind,
        source_id,
        source_label,
        _non_empty_str(Path(result.target).name),
        fingerprint_seed,
    )
    sample_version = _submission_option(
        submission_options, "sample_version", "AIRA_SAMPLE_VERSION", "RESEARCH_SAMPLE_VERSION"
    ) or "v1"
    record = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "source": source_label,
        "language": metadata.get("language"),
        "engine": _engine_label(result),
        "scan_mode": metadata.get("mode", "static"),
        "provider": metadata.get("provider") or metadata.get("engine"),
        "model": metadata.get("model"),
        "target_kind": target_kind,
        "files_scanned": int(summary.get("files_scanned", 0)),
        "high_count": int((summary.get("by_severity") or {}).get("HIGH", 0)),
        "medium_count": int((summary.get("by_severity") or {}).get("MEDIUM", 0)),
        "low_count": int((summary.get("by_severity") or {}).get("LOW", 0)),
        "total_findings": int(summary.get("findings_total", 0)),
        "checks_failed": sum(1 for row in submission_checks if row["status"] == "FAIL"),
        "checks_passed": sum(1 for row in submission_checks if row["status"] == "PASS"),
        "checks_unknown": sum(1 for row in submission_checks if row["status"] == "UNKNOWN"),
        "checks_json": checks_json,
        "check_count_json": check_count_json,
        "check_severity_json": check_severity_json,
        "ci_workflow": _env("GITHUB_WORKFLOW"),
        "ci_run_id": _env("GITHUB_RUN_ID"),
        "ci_ref": _env("GITHUB_REF_NAME"),
        "metadata_json": metadata,
        "sample_name": sample_name,
        "sample_version": sample_version,
        "attribution_class": _normalize_attribution_class(
            _submission_option(
                submission_options, "attribution_class", "AIRA_ATTRIBUTION_CLASS", "RESEARCH_ATTRIBUTION_CLASS"
            )
        ),
        "source_id": source_id,
        "source_kind": source_kind,
        "scanner_name": _submission_option(submission_options, "scanner_name", "AIRA_SCANNER_NAME") or "aira",
        "scanner_version": scanner_version,
        "ruleset_version": ruleset_version,
        "scoring_version": scoring_version,
        "fti_score": fti_score,
        "risk_level": risk_level_for_fti(fti_score),
        "parent_record_sha256": None,
    }
    record["submission_fingerprint"] = _sha256_hex(_canonicalize(_build_fingerprint_payload(record, submission_checks)))
    return {
        "record": record,
        "submission_checks": submission_checks,
    }


def finalize_submission_bundle(
    bundle: Dict[str, Any],
    parent_record_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    record = {
        **bundle["record"],
        "parent_record_sha256": parent_record_sha256,
    }
    record["record_sha256"] = _sha256_hex(_canonicalize(_build_persisted_payload(record, bundle["submission_checks"])))
    return {
        "record": record,
        "submission_checks": bundle["submission_checks"],
    }


def build_structured_submission_record(
    result,
    source: Optional[str] = None,
    submission_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return finalize_submission_bundle(
        build_submission_bundle(result, source=source, submission_options=submission_options)
    )["record"]


def _airtable_url(base_id: str, table: str, query: str = "") -> str:
    url = f"https://api.airtable.com/v0/{parse.quote(base_id)}/{parse.quote(table)}"
    if query:
        return f"{url}?{query}"
    return url


def _supabase_url(base_url: str, table: str, query: str = "") -> str:
    url = f"{base_url}/rest/v1/{parse.quote(table)}"
    if query:
        return f"{url}?{query}"
    return url


def _decode_error_message(raw: str, exc: error.HTTPError) -> str:
    try:
        parsed = json.loads(raw or "{}")
        err = parsed.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or raw or exc)
        if err:
            return str(err)
    except Exception:
        pass
    return raw or str(exc)


def _airtable_request_json(
    method: str,
    url: str,
    token: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 15,
) -> Dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ResearchSubmissionError(_decode_error_message(raw, exc), status_code=exc.code) from exc
    except error.URLError as exc:
        raise ResearchSubmissionError(f"Airtable request failed: {exc.reason}") from exc


def _supabase_request_json(
    method: str,
    url: str,
    key: str,
    *,
    payload: Optional[Any] = None,
    prefer: str = "return=representation",
    timeout_seconds: int = 15,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw or "[]")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw or "{}")
            message = parsed.get("message") or parsed.get("error_description") or parsed.get("error") or raw
        except Exception:
            message = raw or str(exc)
        raise ResearchSubmissionError(f"Supabase request failed: {message}", status_code=exc.code) from exc
    except error.URLError as exc:
        raise ResearchSubmissionError(f"Supabase request failed: {exc.reason}") from exc


def _supabase_fetch_submission_by_fingerprint(
    base_url: str,
    table: str,
    key: str,
    fingerprint: str,
    *,
    timeout_seconds: int = 15,
) -> Optional[Dict[str, Any]]:
    url = _supabase_url(
        base_url,
        table,
        query=parse.urlencode({"select": "*", "submission_fingerprint": f"eq.{fingerprint}", "limit": 1}),
    )
    data = _supabase_request_json("GET", url, key, timeout_seconds=timeout_seconds)
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


def _supabase_fetch_latest_parent(
    base_url: str,
    table: str,
    key: str,
    *,
    sample_name: str,
    sample_version: str,
    timeout_seconds: int = 15,
) -> Optional[Dict[str, Any]]:
    url = _supabase_url(
        base_url,
        table,
        query=parse.urlencode(
            {
                "select": "id,record_sha256",
                "sample_name": f"eq.{sample_name}",
                "sample_version": f"eq.{sample_version}",
                "order": "submitted_at.desc,created_at.desc",
                "limit": 1,
            }
        ),
    )
    data = _supabase_request_json("GET", url, key, timeout_seconds=timeout_seconds)
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


def _supabase_insert_submission_checks(
    base_url: str,
    key: str,
    *,
    submission_id: str,
    submission_checks: List[Dict[str, Any]],
    timeout_seconds: int = 15,
) -> Any:
    if not submission_checks:
        return []
    payload = [
        {
            "submission_id": submission_id,
            "check_id": row["check_id"],
            "check_name": row["check_name"],
            "status": row["status"],
            "weight": row["weight"],
            "finding_count": row["finding_count"],
            "high_count": row["high_count"],
            "medium_count": row["medium_count"],
            "low_count": row["low_count"],
        }
        for row in submission_checks
    ]
    url = _supabase_url(
        base_url,
        _supabase_checks_table(),
        query=parse.urlencode({"on_conflict": "submission_id,check_id"}),
    )
    return _supabase_request_json(
        "POST",
        url,
        key,
        payload=payload,
        prefer="resolution=ignore-duplicates,return=representation",
        timeout_seconds=timeout_seconds,
    )


def _extract_unknown_field(message: str) -> Optional[str]:
    match = UNKNOWN_FIELD_RE.search(message)
    if not match:
        return None
    return match.group("field")


def check_airtable_connection(timeout_seconds: int = 10) -> Dict[str, Any]:
    snapshot = airtable_config_snapshot()
    if not snapshot["configured"]:
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": "AIRTABLE_BASE_ID and AIRTABLE_TOKEN are not configured.",
        }

    base_id, table, token = _airtable_target()
    assert base_id is not None and token is not None
    url = _airtable_url(base_id, table, query=parse.urlencode({"maxRecords": 1}))

    try:
        _airtable_request_json("GET", url, token, timeout_seconds=timeout_seconds)
        return {
            **snapshot,
            "ok": True,
            "reachable": True,
            "message": "Airtable connection verified.",
        }
    except ResearchSubmissionError as exc:
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": str(exc),
            "status_code": exc.status_code,
        }


def check_supabase_connection(timeout_seconds: int = 10) -> Dict[str, Any]:
    snapshot = supabase_config_snapshot()
    if not snapshot["configured"]:
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are not configured.",
        }

    base_url, table, key = _supabase_target()
    assert base_url is not None and key is not None
    url = _supabase_url(base_url, table, query=parse.urlencode({"select": "submitted_at", "limit": 1}))

    try:
        _supabase_request_json("GET", url, key, timeout_seconds=timeout_seconds)
        return {
            **snapshot,
            "ok": True,
            "reachable": True,
            "message": "Supabase connection verified.",
        }
    except ResearchSubmissionError as exc:
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": str(exc),
            "status_code": exc.status_code,
        }


def check_jsonl_connection() -> Dict[str, Any]:
    snapshot = jsonl_config_snapshot()
    if not snapshot["configured"]:
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": "AIRA_RESEARCH_JSONL is not configured.",
        }

    path = _jsonl_target()
    assert path is not None
    parent = path.parent
    if not parent.exists():
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": f"Research JSONL directory does not exist: {parent}",
        }
    if not os.access(parent, os.W_OK):
        return {
            **snapshot,
            "ok": False,
            "reachable": False,
            "message": f"Research JSONL directory is not writable: {parent}",
        }
    return {
        **snapshot,
        "ok": True,
        "reachable": True,
        "message": "JSONL research sink is writable.",
    }


def _submit_aggregate_research_airtable(result, source: Optional[str] = None, timeout_seconds: int = 15) -> Dict[str, Any]:
    base_id, table, token = _airtable_target()
    if not base_id or not token:
        raise ResearchSubmissionError(
            "AIRTABLE_BASE_ID and AIRTABLE_TOKEN must be configured for research submission."
        )

    baseline_fields = build_baseline_submission_fields(result, source=source)
    optional_fields = build_optional_submission_fields(result)
    dropped_optional_fields = []
    url = _airtable_url(base_id, table)

    while True:
        fields = {**baseline_fields, **optional_fields}
        try:
            response = _airtable_request_json(
                "POST",
                url,
                token,
                payload={"fields": fields},
                timeout_seconds=timeout_seconds,
            )
            response["submitted_fields"] = sorted(fields)
            response["dropped_optional_fields"] = dropped_optional_fields
            return response
        except ResearchSubmissionError as exc:
            unknown_field = _extract_unknown_field(str(exc))
            if exc.status_code != 422 or not unknown_field:
                raise ResearchSubmissionError(f"Airtable submission failed: {exc}", status_code=exc.status_code) from exc
            if unknown_field not in optional_fields:
                raise ResearchSubmissionError(
                    f"Airtable submission failed: required field '{unknown_field}' is missing from the table.",
                    status_code=exc.status_code,
                ) from exc

            optional_fields.pop(unknown_field, None)
            dropped_optional_fields.append(unknown_field)


def _submit_aggregate_research_supabase(
    result,
    source: Optional[str] = None,
    timeout_seconds: int = 15,
    submission_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_url, table, key = _supabase_target()
    if not base_url or not key:
        raise ResearchSubmissionError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured for research submission."
        )

    bundle = build_submission_bundle(result, source=source, submission_options=submission_options)
    existing = _supabase_fetch_submission_by_fingerprint(
        base_url,
        table,
        key,
        bundle["record"]["submission_fingerprint"],
        timeout_seconds=timeout_seconds,
    )
    if existing and existing.get("id"):
        _supabase_insert_submission_checks(
            base_url,
            key,
            submission_id=existing["id"],
            submission_checks=bundle["submission_checks"],
            timeout_seconds=timeout_seconds,
        )
        return {
            "backend": "supabase",
            "id": existing.get("id"),
            "duplicate": True,
            "record": existing,
        }

    parent = _supabase_fetch_latest_parent(
        base_url,
        table,
        key,
        sample_name=bundle["record"]["sample_name"],
        sample_version=bundle["record"]["sample_version"],
        timeout_seconds=timeout_seconds,
    )
    finalized = finalize_submission_bundle(bundle, parent_record_sha256=(parent or {}).get("record_sha256"))
    response = _supabase_request_json(
        "POST",
        _supabase_url(base_url, table, query=parse.urlencode({"on_conflict": "submission_fingerprint"})),
        key,
        payload=[finalized["record"]],
        prefer="resolution=ignore-duplicates,return=representation",
        timeout_seconds=timeout_seconds,
    )
    inserted = response[0] if isinstance(response, list) and response else None
    if not inserted:
        inserted = _supabase_fetch_submission_by_fingerprint(
            base_url,
            table,
            key,
            finalized["record"]["submission_fingerprint"],
            timeout_seconds=timeout_seconds,
        )
    if not inserted or not inserted.get("id"):
        raise ResearchSubmissionError("Supabase submission did not return a persisted record.")
    _supabase_insert_submission_checks(
        base_url,
        key,
        submission_id=inserted["id"],
        submission_checks=finalized["submission_checks"],
        timeout_seconds=timeout_seconds,
    )
    return {
        "backend": "supabase",
        "id": inserted.get("id"),
        "duplicate": False,
        "record": inserted,
    }


def _submit_aggregate_research_jsonl(
    result,
    source: Optional[str] = None,
    submission_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    path = _jsonl_target()
    if path is None:
        raise ResearchSubmissionError("AIRA_RESEARCH_JSONL must be configured for JSONL research submission.")

    finalized = finalize_submission_bundle(
        build_submission_bundle(result, source=source, submission_options=submission_options)
    )
    record_id = str(uuid.uuid4())
    payload = {"id": record_id, **finalized["record"], "submission_checks": finalized["submission_checks"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
    return {
        "backend": "jsonl",
        "id": record_id,
        "path": str(path),
    }


def check_research_connection(timeout_seconds: int = 10, backend: Optional[str] = None) -> Dict[str, Any]:
    selected = infer_research_backend(backend)
    if not _is_valid_backend(selected):
        return {
            "backend": selected,
            "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
            "backend_order": list(RESEARCH_BACKEND_ORDER),
            "legacy_fallback_backend": "airtable",
            "configured": False,
            "ok": False,
            "reachable": False,
            "invalid_backend": True,
            "message": f"Unknown research backend '{selected}'. Use one of: supabase, jsonl, airtable.",
        }
    if selected == "supabase":
        return {
            "backend": "supabase",
            "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
            "backend_order": list(RESEARCH_BACKEND_ORDER),
            "legacy_fallback_backend": "airtable",
            **check_supabase_connection(timeout_seconds=timeout_seconds),
        }
    if selected == "jsonl":
        return {
            "backend": "jsonl",
            "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
            "backend_order": list(RESEARCH_BACKEND_ORDER),
            "legacy_fallback_backend": "airtable",
            **check_jsonl_connection(),
        }
    if selected == "airtable":
        snapshot = check_airtable_connection(timeout_seconds=timeout_seconds)
        if snapshot.get("ok"):
            snapshot["message"] = "Airtable connection verified. This backend is supported only as a legacy compatibility fallback."
        return {
            "backend": "airtable",
            "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
            "backend_order": list(RESEARCH_BACKEND_ORDER),
            "legacy_fallback_backend": "airtable",
            "legacy_fallback": True,
            **snapshot,
        }
    return {
        "backend": "none",
        "preferred_backend": DEFAULT_HOSTED_RESEARCH_BACKEND,
        "backend_order": list(RESEARCH_BACKEND_ORDER),
        "legacy_fallback_backend": "airtable",
        "configured": False,
        "ok": False,
        "reachable": False,
        "message": "No research backend is configured. Supabase is the preferred hosted backend.",
    }


def submit_aggregate_research(
    result,
    source: Optional[str] = None,
    timeout_seconds: int = 15,
    backend: Optional[str] = None,
    submission_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    selected = infer_research_backend(backend)
    if not _is_valid_backend(selected):
        raise ResearchSubmissionError(
            f"Unknown research backend '{selected}'. Use one of: supabase, jsonl, airtable."
        )
    if selected == "supabase":
        return _submit_aggregate_research_supabase(
            result,
            source=source,
            timeout_seconds=timeout_seconds,
            submission_options=submission_options,
        )
    if selected == "jsonl":
        return _submit_aggregate_research_jsonl(result, source=source, submission_options=submission_options)
    if selected == "airtable":
        response = _submit_aggregate_research_airtable(result, source=source, timeout_seconds=timeout_seconds)
        response["backend"] = "airtable"
        response["legacy_fallback"] = True
        return response
    raise ResearchSubmissionError(
        "No research backend is configured. Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY, "
        "AIRA_RESEARCH_JSONL, or AIRTABLE_BASE_ID + AIRTABLE_TOKEN. Supabase is the preferred hosted backend."
    )
