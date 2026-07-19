"""Deterministic status/outcome normalization for ErrorSignal graph edges."""

from __future__ import annotations

from typing import Any, Dict, Optional


def status_class(code: Any) -> Optional[str]:
    if not isinstance(code, int) or code < 100 or code > 599:
        return None
    return f"{code // 100}xx"


def status_mapping(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a normalized status mapping for a return signal, if observable."""
    if signal.get("kind") != "return":
        return None
    outcome = signal.get("outcome") or {}
    kind = outcome.get("kind")
    mapping: Dict[str, Any] = {
        "outcome_kind": kind or "unknown",
        "success_state": outcome.get("success_state", "unknown"),
    }
    code = outcome.get("value") if kind == "status_code" else None
    fields = outcome.get("fields") or {}
    if code is None:
        code = fields.get("status_code", fields.get("code"))
    if isinstance(code, int):
        mapping["status_code"] = code
        mapping["status_class"] = status_class(code)
    status = fields.get("status")
    if status is not None:
        mapping["status"] = status
    if kind in {"status_code", "success", "failure", "error", "error_object", "success_object"}:
        return mapping
    if mapping["success_state"] != "unknown" or code is not None or status is not None:
        return mapping
    return None
