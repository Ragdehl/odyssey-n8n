"""Bounded conversational entry and post-failure interpretation for Odyssey.

This module is NOT an alternative router, answerer, identity resolver or writer.
Its model outputs are untrusted UX hints only. Production execution remains
unchanged until a versioned, live-validated composition adapter explicitly adopts
this gateway.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from odyssey_apps.router import ROUTER_MODEL, ROUTER_REASONING_EFFORT
from odyssey_core.local_conversations import LocalConversationStore

CHAT_GATE_MAX_INPUT_CHARS = 4_096
CHAT_GATE_MAX_TOPIC_CHARS = 120
CHAT_GATE_MAX_OUTPUT_TOKENS = 320
CHAT_GATE_TIMEOUT_SECONDS = 30.0
ERROR_GUIDANCE_MAX_OUTPUT_TOKENS = 550


class ConversationGateError(ValueError):
    """Reject malformed model output and untrusted execution instructions."""


class ConversationMode(StrEnum):
    """Closed UX modes; ERROR is post-execution only."""

    ROUTER = "ROUTER"
    CHAT = "CHAT"
    CONTEXT = "CONTEXT"
    ERROR = "ERROR"


class ContextScope(StrEnum):
    """Describe retrieval needs without choosing canonical identities."""

    NONE = "NONE"
    RECENT = "RECENT"
    HISTORY = "HISTORY"


class RecoveryHint(StrEnum):
    """Only suggestions; NONE of these authorizes a retry or mutation."""

    EXPLAIN = "EXPLAIN"
    ASK_USER = "ASK_USER"
    REVIEW_RETRY = "REVIEW_RETRY"


class GuidanceKind(StrEnum):
    """Finite, vetted recovery guidance; LLM cannot write arbitrary claims."""

    SPECIFY_IDENTITY = "SPECIFY_IDENTITY"
    SPECIFY_DATE = "SPECIFY_DATE"
    CLARIFY_REQUEST = "CLARIFY_REQUEST"
    RETRY_LATER = "RETRY_LATER"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


_GUIDANCE_TEXT = {
    GuidanceKind.SPECIFY_IDENTITY: "¿Puedes indicar el nombre de la persona o la tarea a la que te refieres?",
    GuidanceKind.SPECIFY_DATE: "¿Puedes concretar el día o la fecha de la que estás hablando?",
    GuidanceKind.CLARIFY_REQUEST: "¿Puedes reformular la parte que quieres que Odyssey interprete?",
    GuidanceKind.RETRY_LATER: "Ha habido una dificultad técnica. Antes de repetir la operación, comprueba el resultado de la solicitud.",
    GuidanceKind.UNSUPPORTED: "Esa operación podría necesitar una función de Odyssey que todavía no está disponible.",
    GuidanceKind.UNKNOWN: "No he podido verificar la causa exacta del problema. Puedes darme algún detalle más.",
}


@dataclass(frozen=True, slots=True)
class ConversationState:
    """Compact hints from a previously authenticated conversation only."""

    active_topic: str = ""
    pending_clarification: bool = False
    last_status: str = ""

    def __post_init__(self) -> None:
        """Reject unbounded or invented status vocabularies."""
        if (
            not isinstance(self.active_topic, str)
            or len(self.active_topic) > CHAT_GATE_MAX_TOPIC_CHARS
            or not isinstance(self.pending_clarification, bool)
            or self.last_status not in ("", "completed", "partial", "needs_attention", "failed")
        ):
            raise ConversationGateError("Invalid compact conversation state")


@dataclass(frozen=True, slots=True)
class ConversationDecision:
    """Non-executable preliminary intent classification."""

    mode: ConversationMode
    context_scope: ContextScope

    def __post_init__(self) -> None:
        """A pre-request decision can never choose ERROR or invent work."""
        if self.mode is ConversationMode.ERROR:
            raise ConversationGateError("ERROR mode requires verified post-execution diagnostics")
        if self.mode is ConversationMode.CONTEXT and self.context_scope is ContextScope.NONE:
            raise ConversationGateError("Context mode requires bounded retrieval")
        if (
            self.mode is not ConversationMode.CONTEXT
            and self.context_scope is not ContextScope.NONE
        ):
            raise ConversationGateError("Only context mode may request more history")


@dataclass(frozen=True, slots=True)
class VerifiedFailure:
    """Trusted execution receipt, not a user-supplied model instruction."""

    request_id: str
    status: str
    reason_code: str
    written_count: int | None

    def __post_init__(self) -> None:
        """Keep diagnostic evidence finite and never assume zero writes."""
        if (
            not isinstance(self.request_id, str)
            or not self.request_id
            or len(self.request_id) > 128
            or not isinstance(self.reason_code, str)
            or not self.reason_code
            or len(self.reason_code) > 100
            or self.status not in ("failed", "partial", "needs_attention")
            or (
                self.written_count is not None
                and (
                    type(self.written_count) is not int
                    or self.written_count < 0
                    or self.written_count > 64
                )
            )
        ):
            raise ConversationGateError("Invalid verified failure receipt")


@dataclass(frozen=True, slots=True)
class ErrorAdvice:
    """Model selects a vetted recovery strategy; never emits executable text."""

    guidance_kind: GuidanceKind
    hint: RecoveryHint
    retry_authorized: bool = False

    def __post_init__(self) -> None:
        """Never allow output model to claim permission for retries."""
        if (
            not isinstance(self.guidance_kind, GuidanceKind)
            or not isinstance(self.hint, RecoveryHint)
            or self.retry_authorized is not False
        ):
            raise ConversationGateError("Invalid error explanation")

    def user_message(self, receipt: VerifiedFailure) -> str:
        """Render status and guidance only from verified data and vetted text."""
        if not isinstance(receipt, VerifiedFailure):
            raise ConversationGateError("Verified result required")
        if receipt.written_count is None:
            prefix = "No puedo confirmar todavía qué parte de la solicitud se ha guardado. "
        elif receipt.written_count > 0:
            prefix = "Odyssey ha guardado parte de la información. "
        else:
            prefix = "Odyssey no tiene escrituras confirmadas para esta solicitud. "
        return prefix + _GUIDANCE_TEXT[self.guidance_kind]


class ResponsesClient(Protocol):
    """Reuse the minimal Responses client surface from the existing Router."""

    responses: Any


def decision_schema() -> dict[str, Any]:
    """Use the same strict Responses JSON schema discipline as Router."""
    return {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    mode.value for mode in ConversationMode if mode is not ConversationMode.ERROR
                ],
            },
            "context_scope": {"type": "string", "enum": [scope.value for scope in ContextScope]},
        },
        "required": ["mode", "context_scope"],
        "additionalProperties": False,
    }


def error_advice_schema() -> dict[str, Any]:
    """Bound post-result UX guidance to hints, never execution commands."""
    return {
        "type": "object",
        "properties": {
            "guidance_kind": {"type": "string", "enum": [kind.value for kind in GuidanceKind]},
            "hint": {"type": "string", "enum": [hint.value for hint in RecoveryHint]},
        },
        "required": ["guidance_kind", "hint"],
        "additionalProperties": False,
    }


def parse_decision(payload: Mapping[str, Any]) -> ConversationDecision:
    """Reject unrecognized keys and invalid mode/context combinations."""
    if not isinstance(payload, Mapping) or set(payload) != {"mode", "context_scope"}:
        raise ConversationGateError("Invalid conversation decision keys")
    try:
        return ConversationDecision(
            ConversationMode(payload["mode"]), ContextScope(payload["context_scope"])
        )
    except (TypeError, ValueError) as error:
        raise ConversationGateError("Invalid conversation decision") from error


def parse_error_advice(payload: Mapping[str, Any]) -> ErrorAdvice:
    """Parse a human-facing suggestion without admitting a retry flag."""
    if not isinstance(payload, Mapping) or set(payload) != {"guidance_kind", "hint"}:
        raise ConversationGateError("Invalid error advice keys")
    try:
        return ErrorAdvice(GuidanceKind(payload["guidance_kind"]), RecoveryHint(payload["hint"]))
    except (TypeError, ValueError) as error:
        raise ConversationGateError("Invalid error advice") from error


def read_recent_continuity(
    decision: ConversationDecision, store: LocalConversationStore, request_id: str
) -> tuple[dict[str, str], ...]:
    """Reuse actor-rooted transcript history, never new identity or hidden summaries.

    The caller must resolve the actor first, via the existing runtime resolver.
    Older-history indexing and topic summarization require their own verified
    retrieval contract; they do not silently fall back to the most recent turns.
    """
    if (
        not isinstance(decision, ConversationDecision)
        or decision.mode is not ConversationMode.CONTEXT
    ):
        raise ConversationGateError("Context retrieval requires a validated CONTEXT decision")
    if not isinstance(store, LocalConversationStore):
        raise ConversationGateError("Actor-bound LocalConversationStore required")
    if decision.context_scope is ContextScope.HISTORY:
        raise ConversationGateError("Historical context retrieval has not been authorized yet")
    if not isinstance(request_id, str) or not request_id:
        raise ConversationGateError("Request ID required for self-exclusion")
    try:
        return tuple(store.recent_context(exclude_request_id=request_id))
    except (ValueError, OSError) as error:
        raise ConversationGateError("Recent conversation retrieval failed") from error


CLASSIFY_INSTRUCTIONS = (
    "You are Odyssey's NON-EXECUTING conversational front door. Classify the "
    "current user's purpose, never resolve note identities, infer a participant, "
    "rewrite source text, plan a mutation, or answer. ROUTER means the text "
    "contains information or instructions for Odyssey's existing Router/Apps/Core; "
    "CHAT means a conversation, help question or explanation without a request "
    "to read/write personal knowledge; CONTEXT means conversational continuity "
    "or pending clarification cannot be safely resolved without authenticated "
    "previous turns. Choose context_scope RECENT for recent continuity and HISTORY "
    "only for clearly older references. An active topic is a hypothesis, not fact. "
    "When a message includes any save/mutate intent, ROUTER takes precedence "
    "unless its referenced scope is missing, then choose CONTEXT. When uncertain "
    "whether to save or merely converse, choose CONTEXT. Never emit ERROR; errors "
    "are interpreted only after a verified Odyssey result."
)

ERROR_INSTRUCTIONS = (
    "You select one VETTED recovery guidance category from a VERIFIED Odyssey "
    "execution receipt. Never write free text, resolve identities, infer writes, "
    "name notes, issue commands, choose retry parameters, or change the original "
    "request. SPECIFY_IDENTITY requests a named target; SPECIFY_DATE asks for a "
    "specific day; CLARIFY_REQUEST asks to reformulate; RETRY_LATER suggests "
    "the user inspect the receipt and later try again; UNSUPPORTED indicates a "
    "missing capability; UNKNOWN is the safe fallback when reason is opaque. "
    "EXPLAIN, ASK_USER and REVIEW_RETRY are NON-EXECUTABLE suggestions only: "
    "no automatic retries or repairs are authorized. "
    "Use UNKNOWN for unrecognized reason codes. Never infer that no data "
    "was written; independent verified evidence controls that statement."
)


class OpenAIConversationGateway:
    """Two small Luna call modes sharing the already accepted provider pattern."""

    def __init__(self, client: ResponsesClient) -> None:
        """Inject a minimal provider for deterministic tests and composition."""
        self.client = client
        self.model = ROUTER_MODEL
        self.reasoning_effort = ROUTER_REASONING_EFFORT

    @classmethod
    def from_environment(cls) -> OpenAIConversationGateway:
        """Use the same protected runtime environment expectations as Router."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise ConversationGateError("OpenAI provider environment is unavailable")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise ConversationGateError("OpenAI SDK unavailable") from error
        return cls(OpenAI(max_retries=0, timeout=CHAT_GATE_TIMEOUT_SECONDS))

    def _complete(
        self,
        *,
        schema: dict[str, Any],
        name: str,
        system: str,
        data: Mapping[str, object],
        max_tokens: int,
    ) -> Mapping[str, Any]:
        """One fail-closed Responses call; never mutate or log source content."""
        try:
            response = self.client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                store=False,
                max_output_tokens=max_tokens,
                input=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": name,
                        "strict": True,
                        "schema": schema,
                    }
                },
            )
            if getattr(response, "status", None) != "completed":
                raise ConversationGateError("Conversation model did not finish")
            payload = json.loads(response.output_text)
        except ConversationGateError:
            raise
        except Exception as error:
            raise ConversationGateError("Conversation provider response failed") from error
        if not isinstance(payload, dict):
            raise ConversationGateError("Conversation provider output must be an object")
        return payload

    def classify(self, original_message: str, state: ConversationState) -> ConversationDecision:
        """Use only exact current source and compact untrusted continuity hints."""
        if (
            not isinstance(original_message, str)
            or not original_message.strip()
            or len(original_message) > CHAT_GATE_MAX_INPUT_CHARS
            or not isinstance(state, ConversationState)
        ):
            raise ConversationGateError("Invalid input to conversational classifier")
        response = self._complete(
            schema=decision_schema(),
            name="odyssey_conversation_decision",
            system=CLASSIFY_INSTRUCTIONS,
            data={
                "original_message": original_message,
                "active_topic_hint": state.active_topic,
                "pending_clarification": state.pending_clarification,
                "last_status": state.last_status,
            },
            max_tokens=CHAT_GATE_MAX_OUTPUT_TOKENS,
        )
        return parse_decision(response)

    def explain_error(self, receipt: VerifiedFailure) -> ErrorAdvice:
        """Use verified status/code only, without passing the raw execution graph."""
        if not isinstance(receipt, VerifiedFailure):
            raise ConversationGateError("Verified failure receipt required")
        response = self._complete(
            schema=error_advice_schema(),
            name="odyssey_error_guidance",
            system=ERROR_INSTRUCTIONS,
            data={
                "status": receipt.status,
                "reason_code": receipt.reason_code,
                "write_evidence": (
                    "UNKNOWN"
                    if receipt.written_count is None
                    else "SOME"
                    if receipt.written_count > 0
                    else "ZERO_CONFIRMED"
                ),
            },
            max_tokens=ERROR_GUIDANCE_MAX_OUTPUT_TOKENS,
        )
        return parse_error_advice(response)
