"""
AIRA Python Checker
Performs static analysis of Python source files for AI-induced failure patterns.
"""

import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Finding:
    check_id: str
    check_name: str
    severity: str  # HIGH | MEDIUM | LOW
    file: str
    line: int
    description: str
    snippet: Optional[str] = None


class PythonChecker:
    """
    Analyzes Python source files for all 15 AIRA checks.
    Returns a list of Finding objects.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        self.lines = self.source.splitlines()
        try:
            self.tree = ast.parse(self.source)
            self.parse_ok = True
            self.parse_error = None
        except SyntaxError as exc:
            self.tree = None
            self.parse_ok = False
            self.parse_error = exc
        self.findings: List[Finding] = []

    def run(self) -> List[Finding]:
        if not self.parse_ok:
            line = getattr(self.parse_error, "lineno", 1) or 1
            message = getattr(self.parse_error, "msg", "invalid syntax")
            self._add(
                "SCANNER",
                "SCANNER ERROR",
                "HIGH",
                line,
                f"Could not parse Python file: {message}. Fix syntax before relying on scan results.",
            )
            return self.findings
        self._check_broad_exception_suppression()
        self._check_success_integrity()
        self._check_audit_integrity()
        self._check_bypass_paths()
        self._check_ambiguous_returns()
        self._check_background_tasks()
        self._check_environment_safety()
        self._check_startup_integrity()
        self._check_determinism()
        self._check_confidence_misrepresentation()
        self._check_idempotency()
        self._check_fallback_scatter()
        return self.findings

    def _snippet(self, lineno: int) -> str:
        idx = lineno - 1
        return self.lines[idx].strip() if 0 <= idx < len(self.lines) else ""

    def _add(self, check_id, check_name, severity, line, description):
        self.findings.append(Finding(
            check_id=check_id,
            check_name=check_name,
            severity=severity,
            file=self.filepath,
            line=line,
            description=description,
            snippet=self._snippet(line)
        ))

    # ── CHECK 3: Broad Exception Suppression ─────────────────────
    def _check_broad_exception_suppression(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # Bare except or except Exception
            is_broad = (
                node.type is None or
                (isinstance(node.type, ast.Name) and node.type.id == "Exception") or
                (isinstance(node.type, ast.Attribute) and node.type.attr == "Exception")
            )
            if not is_broad:
                continue

            # Check if handler re-raises or just logs/passes
            body_types = [type(s).__name__ for s in node.body]
            has_raise = any(isinstance(s, ast.Raise) for s in ast.walk(ast.Module(body=node.body, type_ignores=[])))
            has_only_pass = body_types == ["Pass"]
            has_only_log = all(
                isinstance(s, (ast.Expr, ast.Pass)) for s in node.body
            ) and not has_raise

            if has_only_pass:
                self._add("C03", "BROAD EXCEPTION SUPPRESSION", "HIGH",
                          node.lineno,
                          "Bare except/Exception handler with only 'pass' — failure silently swallowed")
            elif has_only_log and not has_raise:
                self._add("C03", "BROAD EXCEPTION SUPPRESSION", "HIGH",
                          node.lineno,
                          "Broad exception handler that logs but does not re-raise — failure semantics lost")
            elif is_broad and not has_raise:
                self._add("C03", "BROAD EXCEPTION SUPPRESSION", "MEDIUM",
                          node.lineno,
                          "Broad exception handler does not re-raise — verify failure is intentionally absorbed")

    # ── CHECK 1: Success Integrity ────────────────────────────────
    def _check_success_integrity(self):
        """Flag try blocks in functions that return success-like values after catching errors."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                # Look for return True / return {"status": "ok"} / return success_obj inside handler
                for child in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
                    if isinstance(child, ast.Return):
                        val = child.value
                        # return True
                        if isinstance(val, ast.Constant) and val.value is True:
                            self._add("C01", "SUCCESS INTEGRITY", "HIGH",
                                      getattr(child, 'lineno', node.lineno),
                                      "Exception handler returns True — may misrepresent success after failure")
                        # return {"status": "ok"} or similar dict with success key
                        if isinstance(val, ast.Dict):
                            for k in val.keys:
                                if isinstance(k, ast.Constant) and str(k.value).lower() in ("status", "success", "ok", "result"):
                                    self._add("C01", "SUCCESS INTEGRITY", "HIGH",
                                              getattr(child, 'lineno', node.lineno),
                                              "Exception handler returns success-shaped dict — verify this is intentional")

    # ── CHECK 2: Audit / Evidence Integrity ──────────────────────
    def _check_audit_integrity(self):
        """Flag audit/log writes inside try/except that only log on failure."""
        audit_keywords = {"audit", "evidence", "log_event", "write_audit", "record_event",
                          "audit_write", "flush", "persist_audit", "commit_audit"}
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Try):
                continue
            # Check if try body contains audit-related calls
            try_calls = []
            for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if isinstance(child, ast.Call):
                    func = child.func
                    name = ""
                    if isinstance(func, ast.Attribute):
                        name = func.attr
                    elif isinstance(func, ast.Name):
                        name = func.id
                    if any(kw in name.lower() for kw in audit_keywords):
                        try_calls.append((name, getattr(child, 'lineno', node.lineno)))

            if not try_calls:
                continue

            # Check handlers — do they swallow?
            for handler in node.handlers:
                has_raise = any(isinstance(s, ast.Raise)
                                for s in ast.walk(ast.Module(body=handler.body, type_ignores=[])))
                if not has_raise:
                    for call_name, call_line in try_calls:
                        self._add("C02", "AUDIT / EVIDENCE INTEGRITY", "HIGH",
                                  call_line,
                                  f"Audit operation '{call_name}' inside try/except that does not re-raise — evidence loss possible")

    # ── CHECK 5: Bypass / Override Paths ─────────────────────────
    def _check_bypass_paths(self):
        bypass_patterns = [
            r'\btesting_bypass\b', r'\bskip_router\b', r'\bforce_model_output\b',
            r'\ballow_degraded\b', r'\bbypass_governance\b', r'\bskip_validation\b',
            r'\bskip_audit\b', r'\bdisable_checks\b', r'\bforce_pass\b'
        ]
        for i, line in enumerate(self.lines, start=1):
            for pattern in bypass_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add("C05", "BYPASS / OVERRIDE PATHS", "HIGH",
                              i, f"Potential governance bypass flag detected: '{line.strip()}'")

    # ── CHECK 6: Ambiguous Return Contracts ───────────────────────
    def _check_ambiguous_returns(self):
        """Flag functions that return None in multiple semantically different contexts."""
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            none_returns = []
            for child in ast.walk(node):
                if child is node:
                    continue
                if isinstance(child, ast.Return):
                    val = child.value
                    if val is None or (isinstance(val, ast.Constant) and val.value is None):
                        none_returns.append(getattr(child, 'lineno', node.lineno))
            # Multiple None returns in same function = likely semantic overload
            if len(none_returns) >= 2:
                self._add("C06", "AMBIGUOUS RETURN CONTRACTS", "MEDIUM",
                          node.lineno,
                          f"Function '{node.name}' returns None in {len(none_returns)} locations — "
                          f"caller may not distinguish failure vs absence vs disabled (lines: {none_returns})")

    # ── CHECK 8: Unsupervised Background Tasks ────────────────────
    def _check_background_tasks(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in ("create_task", "ensure_future"):
                # Check if result is assigned or awaited (supervision signal)
                lineno = getattr(node, 'lineno', 0)
                self._add("C08", "UNSUPERVISED BACKGROUND TASKS", "MEDIUM",
                          lineno,
                          f"'{name}()' call — verify task result is supervised and failure surfaces to health monitoring")

    # ── CHECK 9: Environment-Dependent Safety ─────────────────────
    def _check_environment_safety(self):
        env_patterns = [
            r'\bif\s+.*(?:debug|dev|staging|test|development).*:',
            r'\bENV\s*[!=]=\s*["\'](?:dev|development|staging|test)',
            r'\bENVIRONMENT\s*[!=]=\s*["\'](?:dev|development|staging)',
            r'(?:skip|disable|bypass|relax).*(?:valid|check|auth|security)',
        ]
        for i, line in enumerate(self.lines, start=1):
            for pattern in env_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add("C09", "ENVIRONMENT-DEPENDENT SAFETY", "HIGH",
                              i, f"Possible environment-conditional safety logic: '{line.strip()}'")

    # ── CHECK 10: Startup Integrity ───────────────────────────────
    def _check_startup_integrity(self):
        startup_keywords = {"startup", "initialize", "init", "setup", "bootstrap", "on_startup"}
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(kw in node.name.lower() for kw in startup_keywords):
                continue
            # Look for try/except that logs but continues
            for child in ast.walk(node):
                if isinstance(child, ast.ExceptHandler):
                    has_raise = any(isinstance(s, ast.Raise)
                                    for s in ast.walk(ast.Module(body=child.body, type_ignores=[])))
                    has_sys_exit = any(
                        isinstance(s, ast.Call) and
                        isinstance(getattr(s, 'func', None), ast.Attribute) and
                        s.func.attr in ("exit", "_exit")
                        for s in ast.walk(ast.Module(body=child.body, type_ignores=[]))
                    )
                    if not has_raise and not has_sys_exit:
                        self._add("C10", "STARTUP INTEGRITY", "HIGH",
                                  child.lineno,
                                  f"Startup function '{node.name}' catches exception without halting — "
                                  "system may run in partially invalid state")

    # ── CHECK 11: Deterministic Reasoning Drift ───────────────────
    def _check_determinism(self):
        non_determinism_patterns = [
            r'\btemperature\s*=\s*(?:0?\.\d*[1-9]\d*|[1-9]\d*(?:\.\d+)?)',
            r'"temperature"\s*:\s*(?:0?\.\d*[1-9]\d*|[1-9]\d*(?:\.\d+)?)',
            r"'temperature'\s*:\s*(?:0?\.\d*[1-9]\d*|[1-9]\d*(?:\.\d+)?)",
        ]
        for i, line in enumerate(self.lines, start=1):
            for pattern in non_determinism_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add("C11", "DETERMINISTIC REASONING DRIFT", "HIGH",
                              i, f"Non-zero temperature detected in model call — "
                                 f"verify this is not a commit or governance decision path: '{line.strip()}'")

    # ── CHECK 13: Confidence Misrepresentation ────────────────────
    def _check_confidence_misrepresentation(self):
        """Flag functions returning results without confidence/certainty metadata."""
        confidence_terms = {"confidence", "is_confident", "certainty", "is_verified",
                            "score", "probability", "is_cached", "is_default", "is_estimated"}
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Heuristic: function name suggests it produces a result/prediction/assessment
            result_names = {"predict", "assess", "evaluate", "score", "classify",
                            "recommend", "decide", "infer", "generate", "resolve"}
            if not any(kw in node.name.lower() for kw in result_names):
                continue
            # Check if any return includes confidence metadata
            returns = [c for c in ast.walk(node) if isinstance(c, ast.Return) and c is not node]
            has_confidence = False
            for ret in returns:
                src = ast.unparse(ret) if hasattr(ast, 'unparse') else ""
                if any(term in src.lower() for term in confidence_terms):
                    has_confidence = True
                    break
            if not has_confidence and returns:
                self._add("C13", "CONFIDENCE MISREPRESENTATION", "MEDIUM",
                          node.lineno,
                          f"Function '{node.name}' returns result without confidence/certainty metadata — "
                          "caller cannot distinguish verified result from estimate or default")

    # ── CHECK 15: Retry / Idempotency Assumption Drift ───────────
    def _check_idempotency(self):
        retry_patterns = [
            r'\bretry\b', r'\bbackoff\b', r'\btenacity\b',
            r'for\s+\w+\s+in\s+range\s*\(.*attempt',
            r'while.*attempt', r'@retry', r'@backoff'
        ]
        write_patterns = [
            r'\b(?:insert|create|write|commit|publish|send|post|charge|submit)\b'
        ]
        idempotency_patterns = [
            r'\bidempotency_key\b', r'\bidempotent\b', r'\bdedup\b',
            r'\bdeduplicate\b', r'\bif_not_exists\b'
        ]

        for i, line in enumerate(self.lines, start=1):
            is_retry = any(re.search(p, line, re.IGNORECASE) for p in retry_patterns)
            if not is_retry:
                continue
            # Look at surrounding 10 lines for write ops without idempotency
            window_start = max(0, i - 5)
            window_end = min(len(self.lines), i + 10)
            window = "\n".join(self.lines[window_start:window_end])
            has_write = any(re.search(p, window, re.IGNORECASE) for p in write_patterns)
            has_idempotency = any(re.search(p, window, re.IGNORECASE) for p in idempotency_patterns)
            if has_write and not has_idempotency:
                self._add("C15", "RETRY / IDEMPOTENCY ASSUMPTION DRIFT", "HIGH",
                          i,
                          f"Retry logic near write operation without idempotency key — "
                          f"double-write/commit risk: '{line.strip()}'")

    # ── CHECK 4: Fallback Scatter ─────────────────────────────────
    def _check_fallback_scatter(self):
        fallback_patterns = [
            r'\bfallback\b', r'\bdegraded\b', r'\bbest.?effort\b',
            r'\bfallback_mode\b', r'\buse_fallback\b'
        ]
        for i, line in enumerate(self.lines, start=1):
            for pattern in fallback_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add("C04", "DISTRIBUTED FALLBACK / DEGRADED EXECUTION", "LOW",
                              i, f"Fallback/degraded logic detected — verify centralized governance: '{line.strip()}'")
