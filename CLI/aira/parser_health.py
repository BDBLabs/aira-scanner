"""Parser capability records for the error-signal inventory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ParserHealth:
    """Truthful, per-artifact parser coverage.

    ``status`` is one of ``analyzed``, ``partial``, ``failed``, or ``omitted``.
    Lexical recovery is always partial because it cannot authorize structural
    absence claims.
    """

    parser: str
    parser_version: str
    status: str
    structural: bool
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, [], "")}
