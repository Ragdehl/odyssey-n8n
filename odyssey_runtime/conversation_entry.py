"""C1–C3 read-only interpretation seam for one trusted, actor-scoped delivery.

The runtime retains sole execution, transcript and E3 mutation authority.
This module never writes notes, persists chat, or executes a clarification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from odyssey_core.local_conversations import LocalConversationStore
from odyssey_runtime.conversation_chat import (
    ChatPurpose,
    ChatReply,
    answer_chat,
    answer_standalone_chat,
)
from odyssey_runtime.conversation_continuity import (
    ContextHandoff,
    prepare_context_handoff,
    propose_after_context,
)
from odyssey_runtime.conversation_gateway import (
    ContextScope,
    ConversationGateError,
    ConversationMode,
    ConversationState,
    FollowupIntent,
    OpenAIConversationGateway,
)


@dataclass(frozen=True, slots=True)
class ConversationEntry:
    """Typed non-executable decision. A missing reply never implies a write."""

    route: str
    reply: ChatReply | None = None

    def __post_init__(self) -> None:
        if self.route not in {"ROUTER", "CHAT", "CLARIFY"}:
            raise ConversationGateError("Invalid conversation entry route")
        if (self.route == "CHAT") != (self.reply is not None):
            raise ConversationGateError("Chat reply must match route")


def _bounded_second_pass(turns: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    """Preserve exact prior evidence while bounding provider call and JSON overhead."""
    import json

    window = turns[-16:]
    while window and len(json.dumps(window, ensure_ascii=False).encode("utf-8")) > 4096:
        window = window[1:]
    return window


def evaluate_conversation_entry(
    gateway: OpenAIConversationGateway,
    store: LocalConversationStore,
    *,
    original_message: str,
    request_id: str,
    now: datetime,
    deployed_capabilities: frozenset[str],
) -> ConversationEntry:
    """Classify once, optionally reclassify once, then reply or defer to Core.

    The caller must first check durable same-ID delivery and pending Core
    clarifications under the same actor lock; it must then separately persist
    the user turn and return the reply via the existing n8n finalizer.
    """
    if (
        not isinstance(gateway, OpenAIConversationGateway)
        or not isinstance(store, LocalConversationStore)
        or not isinstance(now, datetime)
        or now.tzinfo is None
    ):
        raise ConversationGateError("Trusted conversation entry inputs required")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ConversationGateError("Trusted delivery ID required")
    store.load_or_create_main(now=now.isoformat())
    last_status = ""
    page = store.load_main_page(limit=1)
    if page["turns"]:
        final = page["turns"][-1]
        if final["role"] == "assistant" and final.get("status") in {
            "completed",
            "partial",
            "needs_attention",
            "failed",
        }:
            last_status = final["status"]
    state = ConversationState(last_status=last_status)
    decision = gateway.classify(original_message, state)
    if decision.mode is ConversationMode.ROUTER:
        return ConversationEntry("ROUTER")
    if decision.mode is ConversationMode.CHAT:
        reply = answer_standalone_chat(
            gateway,
            original_message=original_message,
            deployed_capabilities=deployed_capabilities,
        )
        return ConversationEntry("CHAT", reply)
    if decision.context_scope not in {ContextScope.RECENT, ContextScope.HISTORY}:
        raise ConversationGateError("Invalid context request")
    handoff: ContextHandoff = prepare_context_handoff(
        decision,
        store,
        original_message=original_message,
        current_request_id=request_id,
        now=now,
    )
    assessment = gateway.classify_after_context(
        original_message,
        state,
        _bounded_second_pass(
            tuple({"role": turn.role, "text": turn.text} for turn in handoff.prior_turns)
        ),
    )
    proposal = propose_after_context(assessment, handoff)
    if proposal.intent is FollowupIntent.ROUTER:
        return ConversationEntry("ROUTER")
    if proposal.intent is FollowupIntent.CLARIFY:
        return ConversationEntry("CLARIFY")
    reply = answer_chat(
        gateway,
        original_message=original_message,
        purpose=ChatPurpose.PRIOR_CONVERSATION,
        previous_turns=tuple(turn for turn in handoff.prior_turns[-8:] if len(turn.text) <= 1000),
    )
    return ConversationEntry("CHAT", reply)
