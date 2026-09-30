"""Bounded Core-owned presentation evidence for an identity clarification."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CLARIFICATION_CANDIDATES = 4
MAX_CLARIFICATION_LABEL_CHARS = 160
MAX_CLARIFICATION_EVIDENCE_CHARS = 320
MAX_CLARIFICATION_REFERENCE_CHARS = 240


@dataclass(frozen=True, slots=True)
class ClarificationCandidateEvidence:
    """Describe one current canonical option without model prose or retrieval metadata."""

    id: str
    label: str
    note_type: str
    evidence: str

    def __post_init__(self) -> None:
        """Reject unsafe or unbounded candidate presentation fields."""
        if (
            not self.id
            or not self.label.strip()
            or len(self.label) > MAX_CLARIFICATION_LABEL_CHARS
            or not self.note_type.strip()
            or not self.evidence.strip()
            or len(self.evidence) > MAX_CLARIFICATION_EVIDENCE_CHARS
        ):
            raise ValueError("clarification candidate evidence is invalid")


@dataclass(frozen=True, slots=True)
class ClarificationPresentation:
    """Carry the requested wording and two to four grounded canonical options."""

    requested_reference: str
    candidates: tuple[ClarificationCandidateEvidence, ...]

    def __post_init__(self) -> None:
        """Keep the diagnostic small, unique, and safe for public projection."""
        if (
            not self.requested_reference.strip()
            or len(self.requested_reference) > MAX_CLARIFICATION_REFERENCE_CHARS
            or not 1 < len(self.candidates) <= MAX_CLARIFICATION_CANDIDATES
            or len({candidate.id for candidate in self.candidates}) != len(self.candidates)
        ):
            raise ValueError("clarification presentation is invalid")

    @property
    def explanation(self) -> str:
        """Return deterministic wording derived only from the requested reference."""
        return (
            f"No puedo identificar con seguridad a “{self.requested_reference}”. "
            "He encontrado estas posibilidades en tus notas."
        )
