"""Generic handoff from specialized applications back to the Core planner.

Applications may interpret only their own domain and attach bounded evidence. They do not
construct Core targets, facts, identities, RequestPlans, or mutation instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .temporal import TemporalAnchor, TemporalValueError

TEMPORAL_REFERENCE_EVIDENCE = "temporal_reference"
DOMAIN_PROPERTY_SET_PREFIX = "property."
DOMAIN_PROPERTY_REMOVE_PREFIX = "property_remove."
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_INTENT = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class DomainEvidence:
    """Carry one grounded normalized value produced by a specialized application."""

    kind: str
    source_text: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or _IDENTIFIER.fullmatch(self.kind) is None:
            raise ValueError("domain evidence kind is invalid")
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise ValueError("domain evidence source text is invalid")
        if not isinstance(self.value, str) or not self.value.strip() or len(self.value) > 256:
            raise ValueError("domain evidence value is invalid")
        if self.kind == TEMPORAL_REFERENCE_EVIDENCE:
            try:
                anchor = TemporalAnchor.from_value(self.value)
            except TemporalValueError as error:
                raise ValueError("temporal domain evidence is invalid") from error
            if anchor.value != self.value:
                raise ValueError("temporal domain evidence must be canonical")

    def to_payload(self) -> dict[str, str]:
        """Return the bounded prompt-safe representation of this evidence item."""
        return {"kind": self.kind, "source_text": self.source_text, "value": self.value}

    def temporal_anchor(self) -> TemporalAnchor:
        """Return this temporal evidence as a validated semantic coordinate."""
        if self.kind != TEMPORAL_REFERENCE_EVIDENCE:
            raise ValueError("domain evidence is not temporal")
        try:
            return TemporalAnchor.from_value(self.value)
        except TemporalValueError as error:
            raise ValueError("temporal domain evidence is invalid") from error


@dataclass(frozen=True, slots=True)
class DomainInterpretation:
    """Describe only application-specialized interpretation for one exact routed source."""

    capability_id: str
    source_text: str
    intent: str
    evidence: tuple[DomainEvidence, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability_id, str)
            or _IDENTIFIER.fullmatch(self.capability_id) is None
        ):
            raise ValueError("domain capability ID is invalid")
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise ValueError("domain interpretation source is invalid")
        if not isinstance(self.intent, str) or _INTENT.fullmatch(self.intent) is None:
            raise ValueError("domain interpretation intent is invalid")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, DomainEvidence) for item in self.evidence
        ):
            raise ValueError("domain interpretation evidence is invalid")
        if len(self.evidence) > 16:
            raise ValueError("domain interpretation evidence is too large")
        non_temporal = tuple(
            item for item in self.evidence if item.kind != TEMPORAL_REFERENCE_EVIDENCE
        )
        if len(non_temporal) != len(set(non_temporal)):
            raise ValueError("domain interpretation evidence is duplicate")
        if any(item.source_text not in self.source_text for item in self.evidence):
            raise ValueError("domain evidence is not grounded in routed source")

    def to_prompt_payload(self) -> dict[str, object]:
        """Return bounded evidence for Core planning without granting mutation authority."""
        return {
            "capability_id": self.capability_id,
            "intent": self.intent,
            "evidence": [item.to_payload() for item in self.evidence],
        }

    def temporal_references(self) -> tuple[DomainEvidence, ...]:
        """Return exact date/date-time evidence that may anchor Core writes."""
        return tuple(item for item in self.evidence if item.kind == TEMPORAL_REFERENCE_EVIDENCE)

    def property_evidence(self) -> tuple[DomainEvidence, ...]:
        """Return app-normalized property evidence without interpreting its business meaning."""
        return tuple(
            item
            for item in self.evidence
            if item.kind.startswith(DOMAIN_PROPERTY_SET_PREFIX)
            or item.kind.startswith(DOMAIN_PROPERTY_REMOVE_PREFIX)
        )
