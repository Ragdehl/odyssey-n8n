"""Events domain-only groundwork; not yet registered or writable."""

from .interpretation import (
    EventInterpretation,
    EventInterpretationError,
    EventOperation,
    EventTemporalMention,
    EventTemporalRole,
)
from .proposal import validate_event_proposal

__all__ = [
    "EventInterpretation",
    "EventInterpretationError",
    "EventOperation",
    "EventTemporalMention",
    "EventTemporalRole",
    "validate_event_proposal",
]
