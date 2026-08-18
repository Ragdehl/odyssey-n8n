"""Contextual entity-resolution contracts and the narrow OpenAI provider boundary."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

OUTCOMES = frozenset({"RESOLVED", "AMBIGUOUS", "UNRESOLVED"})
SOL_FEW_SHOT_PROMPT_CACHE_KEY = "odyssey:contextual-resolution:sol-few-shot-v1"


class ContextualResolutionError(RuntimeError):
    """Indicate that a contextual reasoner failed or returned an unsafe decision."""


class ContextualProviderError(ContextualResolutionError):
    """Indicate a transport or provider-service failure rather than a model decision failure."""


@dataclass(frozen=True, slots=True)
class ContextualCandidate:
    """Carry the minimum supplied evidence for one contextual-resolution candidate.

    Attributes:
        id: Stable Odyssey identifier accepted in a resolved decision.
        evidence: Synthetic or production-derived textual identity evidence.
    """

    id: str
    evidence: str


@dataclass(frozen=True, slots=True)
class ContextualResolutionRequest:
    """Describe one reference and its already-retrieved candidate set.

    Attributes:
        reference: The contextual entity wording to resolve.
        context: Surrounding text that may disambiguate the reference.
        entity_type: Canonical expected entity type.
        candidates: Phase 10 candidate evidence, in retrieval order.
    """

    reference: str
    context: str
    entity_type: str
    candidates: tuple[ContextualCandidate, ...]


@dataclass(frozen=True, slots=True)
class ContextualResolutionDecision:
    """Represent a decision accepted by deterministic Odyssey Core validation."""

    outcome: str
    id: str | None


@dataclass(frozen=True, slots=True)
class ContextualResolutionExample:
    """Pair one pre-existing calibration request with its frozen valid decision.

    Attributes:
        request: Label-free contextual evidence shown as a user turn.
        decision: Frozen answer shown as the corresponding assistant turn.
    """

    request: ContextualResolutionRequest
    decision: ContextualResolutionDecision


class ContextualReasoner(Protocol):
    """Define a provider-independent boundary for one contextual decision."""

    def resolve(
        self, request: ContextualResolutionRequest
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return raw decision data and provider measurement metadata for one request."""


_SYSTEM_INSTRUCTIONS = """You decide whether one contextual reference identifies a supplied candidate.

RESOLVED: exactly one supplied candidate is uniquely supported by the reference and context.
AMBIGUOUS: two or more supplied candidates remain genuinely plausible.
UNRESOLVED: no supplied candidate is sufficiently supported.

A false RESOLVED is substantially worse than abstention. Do not invent facts or relationships.
Respect explicit negative evidence. Semantic similarity and rank are not identity proof. Do not force
the closest candidate. If evidence is insufficient, abstain. Return only the requested decision."""


def build_openai_payload(
    request: ContextualResolutionRequest,
    model: str,
    *,
    reasoning_effort: str = "medium",
    examples: tuple[ContextualResolutionExample, ...] = (),
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    """Build one blind Responses API request with strict Structured Outputs.

    Args:
        request: Reference, context, type, and supplied candidate evidence.
        model: Exact OpenAI model identifier to benchmark.
        reasoning_effort: Responses API reasoning effort.
        examples: Pre-existing labelled calibration turns shared by every evaluated model.
        prompt_cache_key: Stable routing key for explicit caching, or ``None`` to disable caching.

    Returns:
        JSON-compatible payload containing no benchmark labels, scoring metadata, or case identity.

    Raises:
        ValueError: If candidate identities are empty or duplicated.
    """
    _validate_request(request)
    input_turns: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM_INSTRUCTIONS}]
    for index, example in enumerate(examples):
        _validate_request(example.request)
        validate_contextual_decision(
            {"outcome": example.decision.outcome, "id": example.decision.id},
            frozenset(candidate.id for candidate in example.request.candidates),
        )
        user_content: str | list[dict[str, Any]] = _render_user_evidence(example.request)
        if index == len(examples) - 1 and prompt_cache_key is not None:
            user_content = [
                {
                    "type": "input_text",
                    "text": user_content,
                    "prompt_cache_breakpoint": {"mode": "explicit"},
                }
            ]
        input_turns.extend(
            (
                {"role": "user", "content": user_content},
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"outcome": example.decision.outcome, "id": example.decision.id},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            )
        )
    input_turns.append({"role": "user", "content": _render_user_evidence(request)})
    payload = {
        "model": model,
        "store": False,
        "reasoning": {"effort": reasoning_effort},
        "input": input_turns,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "contextual_entity_resolution",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "outcome": {"type": "string", "enum": sorted(OUTCOMES)},
                        "id": {"type": ["string", "null"]},
                    },
                    "required": ["outcome", "id"],
                    "additionalProperties": False,
                },
            }
        },
    }
    if examples and prompt_cache_key is not None:
        payload["prompt_cache_key"] = prompt_cache_key
        payload["prompt_cache_options"] = {"mode": "explicit"}
    return payload


def _validate_request(request: ContextualResolutionRequest) -> None:
    """Reject empty or duplicate candidate identities before constructing a provider payload."""
    candidate_ids = [candidate.id for candidate in request.candidates]
    if not candidate_ids or any(not identity for identity in candidate_ids):
        raise ValueError("Contextual resolution requires non-empty candidate identities")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Contextual resolution candidate identities must be unique")


def _render_user_evidence(request: ContextualResolutionRequest) -> str:
    """Render one label-free contextual request identically for calibration and evaluation turns."""
    evidence = {
        "reference": request.reference,
        "context": request.context,
        "entity_type": request.entity_type,
        "candidates": [
            {"id": candidate.id, "evidence": candidate.evidence} for candidate in request.candidates
        ],
    }
    return "Resolve this synthetic entity reference:\n" + json.dumps(
        evidence, ensure_ascii=False, separators=(",", ":")
    )


def validate_contextual_decision(
    output: object, candidate_ids: set[str] | frozenset[str]
) -> ContextualResolutionDecision:
    """Fail closed unless model output satisfies the complete Odyssey decision contract.

    Args:
        output: Parsed model output to validate independently of provider enforcement.
        candidate_ids: Exact identities supplied to the model for this request.

    Returns:
        Validated contextual-resolution decision.

    Raises:
        ContextualResolutionError: If schema, outcome, nullability, or candidate membership is invalid.
    """
    if not isinstance(output, dict) or set(output) != {"outcome", "id"}:
        raise ContextualResolutionError("Contextual decision has an invalid schema")
    outcome = output["outcome"]
    identity = output["id"]
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise ContextualResolutionError("Contextual decision has an invalid outcome")
    if identity is not None and not isinstance(identity, str):
        raise ContextualResolutionError("Contextual decision ID must be a string or null")
    if outcome == "RESOLVED":
        if identity is None:
            raise ContextualResolutionError("RESOLVED requires a non-null candidate ID")
        if identity not in candidate_ids:
            raise ContextualResolutionError("RESOLVED selected an ID outside the candidate set")
    elif identity is not None:
        raise ContextualResolutionError(f"{outcome} requires a null ID")
    return ContextualResolutionDecision(outcome=outcome, id=identity)


class OpenAIContextualReasoner:
    """Request one measured decision from the OpenAI Responses API.

    Args:
        model: Exact model identifier selected by the cost-first benchmark stage.
        reasoning_effort: Responses API reasoning effort.
        timeout_seconds: Per-request network timeout.

    The API key is read only from ``OPENAI_API_KEY`` when a request is made. It is never included in
    returned metadata or persisted benchmark output.
    """

    def __init__(
        self,
        model: str,
        *,
        reasoning_effort: str = "medium",
        timeout_seconds: float = 120.0,
        examples: tuple[ContextualResolutionExample, ...] = (),
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.examples = examples

    def resolve(
        self, request: ContextualResolutionRequest
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Call Responses once and return parsed output plus compact usage metadata.

        Args:
            request: One blind contextual-resolution request.

        Returns:
            Raw parsed decision and token/provider metadata needed by the benchmark.

        Raises:
            ContextualResolutionError: If configuration, transport, response, or JSON is invalid.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ContextualResolutionError("OPENAI_API_KEY is required for the live benchmark")
        payload = build_openai_payload(
            request,
            self.model,
            reasoning_effort=self.reasoning_effort,
            examples=self.examples,
        )
        http_request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ContextualProviderError("OpenAI Responses request failed") from error
        if body.get("status") != "completed":
            raise ContextualResolutionError("OpenAI response did not complete")
        output_text = _response_output_text(body)
        try:
            output = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as error:
            raise ContextualResolutionError("OpenAI response output was not valid JSON") from error
        if not isinstance(output, dict):
            raise ContextualResolutionError("OpenAI response output was not a JSON object")
        return output, _usage_metadata(body)


def _response_output_text(response: dict[str, Any]) -> str:
    """Extract the single output-text item from a completed Responses API document."""
    texts = [
        content.get("text")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    ]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise ContextualResolutionError("OpenAI response lacked one output-text item")
    return texts[0]


def _usage_metadata(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize available Responses API token counters without retaining response content."""
    usage = response.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    return {
        "response_id": response.get("id"),
        "input_tokens": int(usage.get("input_tokens", 0)),
        "cached_input_tokens": int(input_details.get("cached_tokens", 0)),
        "cache_write_tokens": int(input_details.get("cache_write_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_tokens": int(output_details.get("reasoning_tokens", 0)),
    }
