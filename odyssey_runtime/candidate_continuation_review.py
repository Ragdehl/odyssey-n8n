"""Inactive independent semantic-review input for selected candidate continuation.

Inherits Odyssey's existing full-source anchored review prompt and strict JSON
schema. This module prepares bounded input only: no provider call, no route,
no reviewer self-approval and no writes. The existing full-source validator
cannot be applied unchanged because earlier E3 facts are already committed.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from odyssey_core.candidate_continuation_context import CoreCandidateContinuationContext
from odyssey_core.candidate_continuation_plan import (
    CoreContinuationPlanInspection,
)
from odyssey_core.candidate_continuation_semantic import (
    CoreContinuationSemanticVerdict,
    validate_independent_continuation_verdict,
)

from .whole_source_model_contract import (
    PROMPT_SOURCE_REVIEW_CORE_ANCHORED,
    REVIEW_CORE_ANCHORED_SCHEMA,
)

# Inherit all accepted safety guidance for exact source, dates, references,
# condition, polarity and source-spanning semantics. The new scope instruction
# has no production model acceptance until the separately authorized live gate.
CONTINUATION_SEMANTIC_REVIEW_PROMPT = PROMPT_SOURCE_REVIEW_CORE_ANCHORED + (
    " SELECTED CANDIDATE CONTINUATION (read-only): The original user message "
    "has already been partially written by Core. The input contains verified "
    "ordinals of already-written atomic facts; do not ask the Planner to write "
    "them again, and do not reject *solely* because they are absent from the "
    "new proposal. Judge whether EVERY independent meaning remaining in the "
    "exact pending source is faithfully represented by the proposed NEW facts, "
    "using the complete original message for shared actors, antecedents, "
    "negation, corrections, conditions and dates. The selected identity name "
    "comes from a separately verified user clarification; it binds ONLY the "
    "exact pending reference occurrence, not other mentions or people. "
    "Use the original captured_at as the trusted clock, never the time of the "
    "later clarification. Check that all proposed dates follow the source, "
    "that intended future plans are not reported as completed events, and "
    "that no fact duplicates already-written source meaning, including "
    "paraphrases. Do NOT fabricate canonical note IDs, names, dates or facts, "
    "and do NOT treat this independent review as Core write authorization. "
    "If ANY meaning, reference, ownership, source-span partition, cardinality, "
    "polarity or time is unresolved, approved=false or complete=false. "
    "Return the same existing strict output schema, with one verdict for "
    "each proposed new atomic fact; do NOT output source_quote. "
    "IMPORTANT STRUCTURED FIELD RULE: reviewed_text is an exact ECHO of "
    "the corresponding proposed_facts[i].text, byte for byte, including "
    "capitalization, punctuation, tense and every {{ref:N}} marker. NEVER "
    "rewrite, paraphrase, translate, add a relative date such as mañana, "
    "or expand the proposed text in reviewed_text; the meaning check "
    "belongs in approved, complete, supported, date and reason instead. "
    "The proposed_facts[i].kind field is explicitly provided as record, "
    "matching the only admissible Core continuation action. Do not reject "
    "a proposal for an absent kind field when it is present. "
    "Copy ordinal, kind, reference_names, and date faithfully from the "
    "reviewed proposal when supported; report approved=false / "
    "complete=false whenever the proposal is semantically wrong. "
    "DO NOT manufacture a more accurate reviewed_text to repair a bad proposal."
)


def prepare_continuation_semantic_review_call(
    context: CoreCandidateContinuationContext,
    inspection: CoreContinuationPlanInspection,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Project trusted original source and untrusted proposed plan for review.

    No LLM invoked here. The caller will need a separately model-validated
    provider adapter and explicit budget to use it in an Odyssey deployment.
    """
    payload = inspection.review_payload(context)
    return (
        CONTINUATION_SEMANTIC_REVIEW_PROMPT,
        {"source": context.original_source, "clock": context.captured_at, **payload},
        copy.deepcopy(REVIEW_CORE_ANCHORED_SCHEMA),
    )


def review_selected_candidate_with_provider(
    context: CoreCandidateContinuationContext,
    inspection: CoreContinuationPlanInspection,
    *,
    ask: Callable[[str, str, dict[str, Any], dict[str, Any], str], dict[str, Any]],
    model: str,
) -> tuple[dict[str, Any], CoreContinuationSemanticVerdict]:
    """Run one independent review via the existing strict provider adapter.

    The caller supplies WholeSourceLightExecutor._ask (or a compatible fake).
    This creates no new OpenAI client, bypasses no delivery guard and never
    invokes the Core writer. Model selection/spend must be authorized by the
    caller; this helper is NOT wired into the live runtime or E3.
    """
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise ValueError("Explicit bounded continuation reviewer model required")
    instructions, payload, schema = prepare_continuation_semantic_review_call(context, inspection)
    review = ask(
        model,
        instructions,
        payload,
        schema,
        "odyssey_e5_candidate_continuation_v1",
    )
    verdict = validate_independent_continuation_verdict(context, inspection, review)
    # The post-review checkpoint requires the exact reviewed dict. Return an
    # independent copy rather than the provider's mutable response object.
    return copy.deepcopy(review), verdict
