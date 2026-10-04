"""Shared natural-language temporal interpretation without domain or mutation authority."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.temporal import TemporalValueError, normalize_iso_date
from odyssey_core.temporal_resolution import (
    TemporalResolution,
    TemporalResolutionKind,
    parse_temporal_resolution,
    temporal_resolution_json_schema,
)

TEMPORAL_INTERPRETER_MODEL = "gpt-6-luna"
TEMPORAL_INTERPRETER_REASONING_EFFORT = "low"
TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS = 512
TEMPORAL_INTERPRETER_TIMEOUT_SECONDS = 30.0
TEMPORAL_INTERPRETER_KINDS = tuple(TemporalResolutionKind)
TEMPORAL_INTERPRETER_MAX_ITEMS = 8


class TemporalInterpreterError(ValueError):
    """Report unavailable, malformed, or unsafe temporal interpretation."""


class ResponsesClient(Protocol):
    """Describe the injected Responses API subset used by Temporal."""

    responses: Any


@dataclass(frozen=True, slots=True)
class TemporalMention:
    """Bind one exact source span to one normalized temporal resolution."""

    temporal_text: str
    resolution: TemporalResolution

    def __post_init__(self) -> None:
        if not isinstance(self.temporal_text, str) or not self.temporal_text.strip():
            raise TemporalInterpreterError("Temporal wording must be non-empty")
        if not isinstance(self.resolution, TemporalResolution):
            raise TemporalInterpreterError("Temporal resolution is invalid")


@dataclass(frozen=True, slots=True)
class TemporalInterpretation:
    """Carry every material temporal mention in one unchanged routed source."""

    source_text: str
    mentions: tuple[TemporalMention, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise TemporalInterpreterError("Temporal source must be non-empty")
        if (
            not isinstance(self.mentions, tuple)
            or not self.mentions
            or len(self.mentions) > TEMPORAL_INTERPRETER_MAX_ITEMS
            or not all(isinstance(item, TemporalMention) for item in self.mentions)
        ):
            raise TemporalInterpreterError("Temporal mentions are invalid")
        cursor = 0
        for mention in self.mentions:
            position = self.source_text.find(mention.temporal_text, cursor)
            if position < 0:
                raise TemporalInterpreterError("Temporal wording is not grounded in source order")
            cursor = position + len(mention.temporal_text)

    def core_domain_interpretation(self) -> DomainInterpretation:
        """Project exact dates/date-times into bounded evidence consumed directly by Core."""
        evidence: list[DomainEvidence] = []
        for mention in self.mentions:
            if mention.resolution.kind is TemporalResolutionKind.EXACT_DATE:
                value = mention.resolution.exact_date
            elif mention.resolution.kind is TemporalResolutionKind.EXACT_DATETIME:
                value = mention.resolution.exact_datetime
            else:
                raise TemporalInterpreterError("Temporal resolution is not an exact Core anchor")
            if value is None:
                raise TemporalInterpreterError("Temporal exact value is unavailable")
            evidence.append(
                DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, mention.temporal_text, value)
            )
        return DomainInterpretation(
            capability_id="temporal",
            source_text=self.source_text,
            intent="TEMPORAL_RESOLUTION",
            evidence=tuple(evidence),
        )

    def kinds(self) -> tuple[TemporalResolutionKind, ...]:
        """Return source-ordered resolution kinds for runtime capability checks."""
        return tuple(item.resolution.kind for item in self.mentions)


def _temporal_mention_json_schema() -> dict[str, Any]:
    """Return one closed provider item for a grounded temporal mention."""
    return {
        "type": "object",
        "properties": {
            "temporal_text": {"type": "string"},
            "temporal": temporal_resolution_json_schema(allowed_kinds=TEMPORAL_INTERPRETER_KINDS),
        },
        "required": ["temporal_text", "temporal"],
        "additionalProperties": False,
    }


def temporal_interpretation_json_schema() -> dict[str, Any]:
    """Return Temporal's closed ordered multi-mention provider contract."""
    return {
        "type": "object",
        "properties": {
            "mentions": {
                "type": "array",
                "minItems": 1,
                "maxItems": TEMPORAL_INTERPRETER_MAX_ITEMS,
                "items": _temporal_mention_json_schema(),
            }
        },
        "required": ["mentions"],
        "additionalProperties": False,
    }


def parse_temporal_interpretation(
    payload: Mapping[str, Any], source_text: str, *, timezone: str
) -> TemporalInterpretation:
    """Validate ordered untrusted Temporal provider results against their exact source."""
    if not isinstance(payload, Mapping) or set(payload) != {"mentions"}:
        raise TemporalInterpreterError("Temporal interpretation fields are invalid")
    raw_mentions = payload["mentions"]
    if (
        not isinstance(raw_mentions, list)
        or not raw_mentions
        or len(raw_mentions) > TEMPORAL_INTERPRETER_MAX_ITEMS
    ):
        raise TemporalInterpreterError("Temporal mentions are invalid")
    mentions: list[TemporalMention] = []
    for raw in raw_mentions:
        if not isinstance(raw, Mapping) or set(raw) != {"temporal_text", "temporal"}:
            raise TemporalInterpreterError("Temporal mention fields are invalid")
        temporal_text = raw["temporal_text"]
        if not isinstance(temporal_text, str):
            raise TemporalInterpreterError("Temporal wording is invalid")
        try:
            resolution = parse_temporal_resolution(
                raw["temporal"], allowed_kinds=TEMPORAL_INTERPRETER_KINDS, timezone=timezone
            )
        except TemporalValueError as error:
            raise TemporalInterpreterError("Temporal resolution is invalid") from error
        mentions.append(TemporalMention(temporal_text, resolution))
    return TemporalInterpretation(source_text, tuple(mentions))


def render_temporal_prompt(current_context: Mapping[str, str]) -> str:
    """Render only date/time resolution instructions and explicit runtime clock context."""
    if set(current_context) != {"date", "time", "timezone"} or not all(
        isinstance(value, str) and value.strip() for value in current_context.values()
    ):
        raise TemporalInterpreterError("Temporal current context is invalid")
    try:
        normalize_iso_date(current_context["date"])
    except TemporalValueError as error:
        raise TemporalInterpreterError("Temporal current date is invalid") from error
    return (
        "You are Odyssey Temporal, a shared lower-level date/time resolver. Interpret only temporal "
        "wording in the exact current user source. Never classify the user's domain, choose a target, "
        "resolve an entity, decide where knowledge belongs, or emit a mutation. Return every material "
        "temporal mention needed to preserve the source meaning, in source order. Each temporal_text "
        "must be the exact non-empty substring whose temporal meaning that item resolves. Do not merge "
        "independent temporal mentions, omit one because another exists, or duplicate an item. A single "
        "compound interval is one DATE_RANGE item. Use EXACT_DATE for one calendar date without a "
        "required clock time, EXACT_DATETIME for one precise local instant, DATE_RANGE for a bounded "
        "calendar interval using a half-open range_end_exclusive, and UNSPECIFIED only when that temporal "
        "wording cannot be normalized safely. For relative wording, use only the supplied current date, "
        "time, and timezone. Never invent a different temporal phrase. Return only the strict JSON object.\n"
        + json.dumps(dict(current_context), ensure_ascii=False, separators=(",", ":"))
    )


class OpenAITemporalInterpreter:
    """Resolve one routed temporal source with one bounded model call and no retries."""

    def __init__(self, client: ResponsesClient, current_context: Mapping[str, str]) -> None:
        self._client = client
        self._current_context = dict(current_context)
        self.model = TEMPORAL_INTERPRETER_MODEL
        self.reasoning_effort = TEMPORAL_INTERPRETER_REASONING_EFFORT
        self.last_call = False
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        self.last_error_category = None

    @classmethod
    def from_environment(cls, current_context: Mapping[str, str]) -> OpenAITemporalInterpreter:
        """Build the shared resolver with SDK retries disabled."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise TemporalInterpreterError("OPENAI_API_KEY is required for Temporal interpretation")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise TemporalInterpreterError(
                "Install the OpenAI SDK for Temporal interpretation"
            ) from error
        return cls(
            OpenAI(max_retries=0, timeout=TEMPORAL_INTERPRETER_TIMEOUT_SECONDS), current_context
        )

    def interpret(
        self, source_text: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> TemporalInterpretation:
        """Resolve one exact routed source; prior context never supplies current temporal wording."""
        del conversation_context
        if not isinstance(source_text, str) or not source_text.strip():
            raise TemporalInterpreterError("Temporal source must be non-empty")
        prompt = render_temporal_prompt(self._current_context)
        self.last_call = True
        try:
            response = self._client.responses.create(
                model=TEMPORAL_INTERPRETER_MODEL,
                reasoning={"effort": TEMPORAL_INTERPRETER_REASONING_EFFORT},
                store=False,
                max_output_tokens=TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": source_text},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_temporal_interpretation",
                        "strict": True,
                        "schema": temporal_interpretation_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:120]
            raise TemporalInterpreterError("Temporal provider call failed") from error

        self.last_usage = getattr(response, "usage", None)
        self.last_response_id = getattr(response, "id", None)
        self.last_provider_status = getattr(response, "status", None)
        if self.last_provider_status != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise TemporalInterpreterError("Temporal provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            self.last_error_category = "MalformedTemporalJSON"
            raise TemporalInterpreterError("Temporal provider returned malformed output") from error
        try:
            return parse_temporal_interpretation(
                payload, source_text, timezone=self._current_context["timezone"]
            )
        except TemporalInterpreterError:
            self.last_error_category = "LocalTemporalValidationError"
            raise
