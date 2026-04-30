from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


IntentScope = Literal["all", "building", "unit", "device"]


@dataclass(slots=True)
class IntentEntities:
    site_id: str | None = None
    building: str | None = None
    unit: str | None = None
    device: str | None = None
    scope: IntentScope = "all"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "IntentEntities":
        source = payload or {}
        scope = source.get("scope") or "all"
        if scope not in {"all", "building", "unit", "device"}:
            raise ValueError(f"Invalid intent scope: {scope!r}")
        return cls(
            site_id=source.get("site_id"),
            building=source.get("building"),
            unit=source.get("unit"),
            device=source.get("device"),
            scope=scope,
        )


@dataclass(slots=True)
class IntentSchema:
    intent: str
    entities: IntentEntities = field(default_factory=IntentEntities)
    confidence: float = 0.0
    ambiguous: bool = False
    clarification_needed: str | None = None
    raw: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"Intent confidence must be between 0.0 and 1.0, got {self.confidence!r}")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntentSchema":
        if not isinstance(payload, dict):
            raise ValueError("Intent payload must be a dictionary")
        intent = payload.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("Intent payload requires a non-empty 'intent' string")
        confidence = payload.get("confidence", 0.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Intent confidence must be numeric, got {confidence!r}") from exc
        ambiguous = bool(payload.get("ambiguous", False))
        clarification_needed = payload.get("clarification_needed")
        if clarification_needed is not None and not isinstance(clarification_needed, str):
            raise ValueError("Intent clarification_needed must be a string or null")
        raw = payload.get("raw")
        if not isinstance(raw, str):
            raise ValueError("Intent payload requires a 'raw' string")
        return cls(
            intent=intent.strip(),
            entities=IntentEntities.from_dict(payload.get("entities")),
            confidence=confidence_value,
            ambiguous=ambiguous,
            clarification_needed=clarification_needed,
            raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
