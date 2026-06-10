"""
AIRA research — JSONL backend.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from aira.research.base import (
    ResearchSubmissionError,
    _env,
)
from aira.research.helpers import (
    build_submission_bundle,
    finalize_submission_bundle,
)


def _jsonl_target() -> Optional[Path]:
    raw = _env("AIRA_RESEARCH_JSONL", "RESEARCH_JSONL")
    return Path(raw).expanduser() if raw else None


def jsonl_config_snapshot() -> Dict[str, Any]:
    path = _jsonl_target()
    return {
        "configured": path is not None,
        "path": str(path) if path else "",
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


def _submit_aggregate_research_jsonl(
    result: Any,
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