"""Scoped, paginated conversation history for Odyssey C2.

Reads only the already actor-resolved LocalConversationStore. No new database,
summaries, inferred identities, writes, or LLM calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from odyssey_core.conversations import ConversationError
from odyssey_core.local_conversations import LocalConversationStore
from odyssey_runtime.conversation_gateway import (
    ContextScope,
    ConversationDecision,
    ConversationGateError,
    ConversationMode,
    FollowupAssessment,
    FollowupIntent,
    ReferentEvidence,
)

HISTORY_DAYS = 30
HISTORY_MAX_TURNS = 48
HISTORY_MAX_BYTES = 12_288
HISTORY_PAGE_SIZE = 32
HISTORY_MAX_PAGES = 8
RECENT_MAX_TURNS = 16
RECENT_MAX_BYTES = 4_096


@dataclass(frozen=True, slots=True)
class HistoricalTurn:
    """Verifiable original turn with bounded source identity and timestamp."""

    request_id: str
    role: str
    text: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ContextHandoff:
    """Unchanged source plus read-only continuity evidence, not an executable plan."""

    original_message: str
    source_request_id: str
    prior_turns: tuple[HistoricalTurn, ...]
    context_scope: ContextScope

    def as_routing_context(self, *, max_turns: int = 8) -> tuple[dict[str, str], ...]:
        """Return bounded evidence only; existing Router still owns scope/validation."""
        if type(max_turns) is not int or not 1 <= max_turns <= 8:
            raise ConversationGateError("Router context limit is invalid")
        return tuple(
            {"role": turn.role, "text": turn.text} for turn in self.prior_turns[-max_turns:]
        )


def _parse_time(value: object) -> datetime:
    """Require timezone-aware timestamps, never infer naive local clock times."""
    if not isinstance(value, str):
        raise ConversationGateError("Conversation timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ConversationGateError("Conversation timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConversationGateError("Conversation timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _trusted_turn(raw: object) -> HistoricalTurn:
    """Reduce stored turn to a verified provenance-bearing source excerpt."""
    if not isinstance(raw, dict) or raw.get("role") not in ("user", "assistant"):
        raise ConversationGateError("Conversation turn is invalid")
    identifier = raw.get("request_id")
    content = raw.get("text")
    if (
        not isinstance(identifier, str)
        or not identifier
        or len(identifier) > 128
        or not isinstance(content, str)
        or not content.strip()
    ):
        raise ConversationGateError("Conversation turn source is invalid")
    _parse_time(raw.get("created_at"))
    return HistoricalTurn(identifier, raw["role"], content, raw["created_at"])


def read_historical_continuity(
    store: LocalConversationStore,
    *,
    current_request_id: str,
    now: datetime,
    max_days: int = HISTORY_DAYS,
    max_turns: int = HISTORY_MAX_TURNS,
    max_bytes: int = HISTORY_MAX_BYTES,
) -> tuple[HistoricalTurn, ...]:
    """Page back at most 30 days/48 turns/12 KB from existing actor-scoped history.

    This bounds real context *retrieval*, not chat summarization or semantic
    relevancy; original turns retain their IDs and immutable timestamps.
    """
    if not isinstance(store, LocalConversationStore):
        raise ConversationGateError("Actor-bound transcript store required")
    if not isinstance(current_request_id, str) or not current_request_id.strip():
        raise ConversationGateError("Current request ID required")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ConversationGateError("Offset-aware current time required")
    if type(max_days) is not int or not 1 <= max_days <= HISTORY_DAYS:
        raise ConversationGateError("History age window is invalid")
    if (
        type(max_turns) is not int
        or not 1 <= max_turns <= HISTORY_MAX_TURNS
        or type(max_bytes) is not int
        or not 1 <= max_bytes <= HISTORY_MAX_BYTES
    ):
        raise ConversationGateError("History bounds are invalid")
    upper = now.astimezone(UTC)
    cutoff = upper - timedelta(days=max_days)
    cursor: str | None = None
    newest_first: list[HistoricalTurn] = []
    size = 0
    try:
        for _ in range(HISTORY_MAX_PAGES):
            page = store.load_main_page(limit=HISTORY_PAGE_SIZE, before=cursor)
            turns = page["turns"]
            if not isinstance(turns, list):
                raise ConversationGateError("Transcript page is invalid")
            exhausted = False
            for raw in reversed(turns):
                turn = _trusted_turn(raw)
                moment = _parse_time(turn.created_at)
                # Chunk append order is not guaranteed to be date order:
                # an old inserted turn may precede an eligible one.
                if moment < cutoff or moment > upper or turn.request_id == current_request_id:
                    continue
                cost = len(
                    json.dumps({"role": turn.role, "text": turn.text}, ensure_ascii=False).encode(
                        "utf-8"
                    )
                )
                if len(newest_first) >= max_turns or size + cost > max_bytes:
                    exhausted = True
                    break
                newest_first.append(turn)
                size += cost
            if exhausted or not page["has_older"]:
                break
            cursor = page.get("before")
            if not isinstance(cursor, str) or not cursor:
                raise ConversationGateError("Historical cursor is invalid")
    except (ConversationError, OSError, KeyError, TypeError) as error:
        raise ConversationGateError("Historical context is unavailable") from error
    return tuple(reversed(newest_first))


def prepare_context_handoff(
    decision: ConversationDecision,
    store: LocalConversationStore,
    *,
    original_message: str,
    current_request_id: str,
    now: datetime,
) -> ContextHandoff:
    """Resolve CONTEXT request without modifying source or selecting identities."""
    if not isinstance(original_message, str) or not original_message.strip():
        raise ConversationGateError("Exact original message required")
    if (
        not isinstance(decision, ConversationDecision)
        or decision.mode is not ConversationMode.CONTEXT
    ):
        raise ConversationGateError("Only a CONTEXT decision can request history")
    if decision.context_scope is ContextScope.RECENT:
        # Read the original stored request IDs and times directly. Never
        # reconstruct provenance by matching repeated role/text strings.
        turns = read_historical_continuity(
            store,
            current_request_id=current_request_id,
            now=now,
            max_turns=RECENT_MAX_TURNS,
            max_bytes=RECENT_MAX_BYTES,
        )
    elif decision.context_scope is ContextScope.HISTORY:
        turns = read_historical_continuity(store, current_request_id=current_request_id, now=now)
    else:
        raise ConversationGateError("Invalid context scope")
    return ContextHandoff(original_message, current_request_id, turns, decision.context_scope)


@dataclass(frozen=True, slots=True)
class ConversationHandoffProposal:
    """Read-only downstream intent, with no entity or write authority."""

    intent: FollowupIntent
    original_message: str
    request_id: str
    recent_context: tuple[dict[str, str], ...]
    referent_evidence: ReferentEvidence

    @property
    def write_authorized(self) -> bool:
        """Only Core/E3 may make this decision after canonical validation."""
        return False


def propose_after_context(
    assessment: FollowupAssessment, handoff: ContextHandoff
) -> ConversationHandoffProposal:
    """Make a bounded Router/Chat/clarification *proposal*, never execute.

    ROUTER carries the exact original source plus at most eight prior turn
    quotations. All references are unverified; a missing group is NOT a
    reason to suppress the save intent in the conversational layer.
    """
    if not isinstance(assessment, FollowupAssessment) or not isinstance(handoff, ContextHandoff):
        raise ConversationGateError("Trusted typed handoff and intent required")
    if (
        not handoff.original_message.strip()
        or len(handoff.original_message) > 4096
        or not handoff.source_request_id
    ):
        raise ConversationGateError("Invalid handoff source")
    return ConversationHandoffProposal(
        intent=assessment.intent,
        original_message=handoff.original_message,
        request_id=handoff.source_request_id,
        recent_context=handoff.as_routing_context(),
        referent_evidence=ReferentEvidence.UNVERIFIED,
    )
