"""Optional prewrite Core review of Router source segmentation (never mutation authority).

One whole-message semantic check ONLY when the opt-in Router contract v2
proposes multiple executable routes. Unlike per-route candidate attribution,
this check sees all proposed boundaries before ANY route can write.

Reviewer feedback is a bounded correction request, not model reasoning, a
replacement Router plan, or approval to write. Canonical Core planning and
the independent candidate/fact coverage gate are always still required.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .experimental_luna_planning import LUNA_EXPERIMENT_MODEL

MAX_BOUNDARY_SOURCE_CHARS = 4096
MAX_BOUNDARY_UNITS = 26
MAX_BOUNDARY_CONTEXT_BYTES = 20_480
MAX_BOUNDARY_OUTPUT_TOKENS = 400

BOUNDARY_REVIEW_REASONS = frozenset(
    {
        "DEPENDENT_SOURCE_FRAGMENT",
        "SPLIT_LOSES_CONTEXT",
        "UNSUPPORTED_REFERENCE",
        "INDEPENDENCE_NOT_PROVEN",
    }
)
BOUNDARY_REVIEW_DECISIONS = frozenset({"accept", "revise", "needs_attention"})


class SourceBoundaryReviewError(ValueError):
    """A semantic review or its provenance is invalid; no work may start."""


@dataclass(frozen=True, slots=True)
class CoreSourceBoundaryUnit:
    """Immutable ORIGINAL-source route with bounded, untrusted source hints."""

    start: int
    end: int
    capability: str
    candidate_kinds: tuple[str, ...]
    candidate_relations: tuple[str, ...]

    def validate(self, source: str) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= len(source)
            or self.end - self.start > MAX_BOUNDARY_SOURCE_CHARS
            or not isinstance(self.capability, str)
            or re.fullmatch(r"[a-z][a-z0-9_.-]{0,47}", self.capability) is None
            or not isinstance(self.candidate_kinds, tuple)
            or not isinstance(self.candidate_relations, tuple)
            or not 1 <= len(self.candidate_kinds) <= MAX_BOUNDARY_UNITS
            or len(self.candidate_kinds) != len(self.candidate_relations)
            or any(
                not isinstance(label, str) or not 1 <= len(label) <= 50
                for label in (*self.candidate_kinds, *self.candidate_relations)
            )
        ):
            raise SourceBoundaryReviewError("Invalid source-boundary route evidence")


@dataclass(frozen=True, slots=True)
class CoreSourceBoundaryInput:
    """Provenance and route partition presented to one independent Core review."""

    source: str
    routes: tuple[CoreSourceBoundaryUnit, ...]

    def validate(self) -> None:
        if (
            not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > MAX_BOUNDARY_SOURCE_CHARS
            or not isinstance(self.routes, tuple)
            or not 1 <= len(self.routes) <= MAX_BOUNDARY_UNITS
        ):
            raise SourceBoundaryReviewError("Invalid bounded source-boundary input")
        boundary = 0
        for route in self.routes:
            if not isinstance(route, CoreSourceBoundaryUnit):
                raise SourceBoundaryReviewError("Source boundary unit type is invalid")
            route.validate(self.source)
            if route.start != boundary:
                raise SourceBoundaryReviewError("Source boundary partition is not contiguous")
            boundary = route.end
        if boundary != len(self.source):
            raise SourceBoundaryReviewError("Source boundary partition omitted original text")

    @property
    def source_digest(self) -> str:
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()

    @property
    def partition_digest(self) -> str:
        payload = [
            [
                route.start,
                route.end,
                route.capability,
                route.candidate_kinds,
                route.candidate_relations,
            ]
            for route in self.routes
        ]
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def model_payload(self) -> str:
        self.validate()
        payload = {
            "original_source": self.source,
            "routes": [
                {
                    "index": index + 1,
                    "text": self.source[route.start : route.end],
                    "capability": route.capability,
                    "candidate_kinds": list(route.candidate_kinds),
                    "claimed_relations": list(route.candidate_relations),
                }
                for index, route in enumerate(self.routes)
            ],
        }
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(rendered.encode("utf-8")) > MAX_BOUNDARY_CONTEXT_BYTES:
            raise SourceBoundaryReviewError("Source boundary review exceeds context budget")
        return rendered


@dataclass(frozen=True, slots=True)
class CoreSourceBoundaryReview:
    """Source-fingerprint-bound evidence, not an assertion that facts are true."""

    source_digest: str
    partition_digest: str
    decision: Literal["accept", "revise", "needs_attention"]
    boundary_index: int  # One-based boundary between adjacent routes; zero on accept
    reason: str | None

    def validate(self, context: CoreSourceBoundaryInput) -> None:
        context.validate()
        if (
            self.source_digest != context.source_digest
            or self.partition_digest != context.partition_digest
            or self.decision not in BOUNDARY_REVIEW_DECISIONS
            or type(self.boundary_index) is not int
            or (self.decision == "accept" and (self.boundary_index != 0 or self.reason is not None))
            or (
                self.decision != "accept"
                and (
                    self.reason not in BOUNDARY_REVIEW_REASONS
                    or not 1 <= self.boundary_index < len(context.routes)
                )
            )
        ):
            raise SourceBoundaryReviewError("Core source-boundary decision is invalid or stale")


def parse_core_source_boundary_review(
    context: CoreSourceBoundaryInput, raw: Mapping[str, Any]
) -> CoreSourceBoundaryReview:
    """Validate a closed provider reply; never accept free text or extra authority."""
    if not isinstance(raw, Mapping) or set(raw) != {"decision", "boundary_index", "reason"}:
        raise SourceBoundaryReviewError("Core boundary reviewer emitted invalid fields")
    review = CoreSourceBoundaryReview(
        context.source_digest,
        context.partition_digest,
        raw["decision"],
        raw["boundary_index"],
        raw["reason"],
    )
    review.validate(context)
    return review


def source_boundary_review_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": sorted(BOUNDARY_REVIEW_DECISIONS),
            },
            "boundary_index": {"type": "integer", "minimum": 0, "maximum": MAX_BOUNDARY_UNITS},
            "reason": {
                "type": ["string", "null"],
                "enum": [*sorted(BOUNDARY_REVIEW_REASONS), None],
            },
        },
        "required": ["decision", "boundary_index", "reason"],
        "additionalProperties": False,
    }


class OpenAICoreSourceBoundaryReviewer:
    """ONE optional independent low-effort GPT-5.6 call per multi-route proposal."""

    def __init__(self, client: object, *, model: str = LUNA_EXPERIMENT_MODEL):
        self.client = client
        self.model = model
        self.reasoning_effort = "low"
        self.last_usage: object | None = None
        self.last_error_category: str | None = None

    def review(self, context: CoreSourceBoundaryInput) -> CoreSourceBoundaryReview:
        context.validate()
        if len(context.routes) < 2:
            raise SourceBoundaryReviewError("Semantic split review requires at least two routes")
        self.last_usage = None
        self.last_error_category = None
        try:
            response = self.client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                store=False,
                max_output_tokens=MAX_BOUNDARY_OUTPUT_TOKENS,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You independently review whether proposed source route BOUNDARIES "
                            "preserve the complete meaning of the original user utterance. "
                            "Do not assume the Router labels or cited predicates are correct. "
                            "A subordinate purpose, attribute, circumstance, negation, correction, "
                            "shared subject or omitted context cannot be executed as an "
                            "independent fact simply because it contains a verb or a date. "
                            "Check all adjacent boundaries. If the decision is accept, "
                            "boundary_index MUST be the INTEGER 0 and reason MUST be null, "
                            "even when there are multiple correctly separated routes. "
                            "Return accept ONLY when the routes "
                            "can be interpreted separately without losing or inventing scope, "
                            "participants, modality, causality, dates or dependencies. "
                            "For an unsafe split return revise, select the FIRST unsafe "
                            "ONE-BASED boundary index (1 means between routes 1 and 2), "
                            "and supply exactly one enum reason. Return needs_attention "
                            "if there is no safe explanation of the boundary. Do not generate "
                            "facts, notes, writes, names, candidate edits or free-text analysis. "
                            "Your output is advisory: deterministic Core gates still apply."
                        ),
                    },
                    {"role": "user", "content": context.model_payload()},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_core_source_boundary_review_v1",
                        "strict": True,
                        "schema": source_boundary_review_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:100]
            raise SourceBoundaryReviewError("Core boundary review provider failed") from error
        self.last_usage = getattr(response, "usage", None)
        if getattr(response, "status", None) != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise SourceBoundaryReviewError("Core boundary review incomplete")
        try:
            raw = json.loads(response.output_text)
            return parse_core_source_boundary_review(context, raw)
        except (TypeError, ValueError, AttributeError) as error:
            self.last_error_category = type(error).__name__[:100]
            raise SourceBoundaryReviewError(
                "Core boundary reviewer returned invalid evidence"
            ) from error
