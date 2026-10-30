"""Independent reviewer verdict contract, all on disposable Core evidence.

Frozen proposed review dictionaries deliberately do not prove model behavior.
No actual model, note mutation, or production write gate is exercised here.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
from odyssey_core.candidate_continuation_semantic import (
    CandidateContinuationSemanticError,
    validate_independent_continuation_verdict,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_runtime.candidate_continuation_review import (
    prepare_continuation_semantic_review_call,
    review_selected_candidate_with_provider,
)
from odyssey_runtime.whole_source_light import WholeSourceLightError, WholeSourceLightExecutor
from odyssey_runtime.whole_source_model_contract import (
    PROMPT_SOURCE_REVIEW_CORE_ANCHORED,
    REVIEW_CORE_ANCHORED_SCHEMA,
)
from tests.runtime.test_candidate_continuation_plan import _ready_inspector


def _case(tmp_path: Path):
    context, plan, vault = _ready_inspector(tmp_path)
    inspection = inspect_selected_candidate_plan(context, plan)
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "kind": "record",
                "reviewed_text": inspection.proposed_facts[0].text,
                "date": "2026-10-05",
                "reference_names": [context.selected_name],
                "supported": True,
            }
        ],
    }
    return context, inspection, review, vault


def test_reuses_existing_strict_review_schema_and_full_source_safety_prompt(tmp_path: Path):
    context, inspection, review, vault = _case(tmp_path)
    initial = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    instructions, model_data, schema = prepare_continuation_semantic_review_call(
        context, inspection
    )
    assert instructions.startswith(PROMPT_SOURCE_REVIEW_CORE_ANCHORED)
    assert "already-written atomic facts" in instructions
    assert "paraphrases" in instructions
    assert schema == REVIEW_CORE_ANCHORED_SCHEMA
    assert schema["additionalProperties"] is False
    assert "source_quote" not in schema["properties"]["facts"]["items"]["properties"]
    assert model_data["source"] == context.original_source
    assert model_data["clock"] == context.captured_at
    assert model_data["pending_source"] == context.pending_source
    assert model_data["selected_identity_name"] == context.selected_name
    assert model_data["already_written_fact_ordinals"] == [0, 1]
    assert not any("selected_note_id" in key for key in model_data)
    assert "pending_record_digest" not in model_data
    verdict = validate_independent_continuation_verdict(context, inspection, review)
    assert not verdict.may_execute
    assert verdict.reviewed_ordinals == (0,)
    assert verdict.source_digest == context.source_digest
    assert verdict.plan_digest == inspection.plan_digest
    assert len(verdict.reviewer_digest) == 64
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == initial


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("approved",), False),
        (("complete",), False),
        (("facts", 0, "supported"), False),
        (("facts", 0, "ordinal"), 1),
        (("facts", 0, "ordinal"), True),
        (("facts", 0, "kind"), "task"),
        (("facts", 0, "reviewed_text"), "Un hecho inventado."),
        (("facts", 0, "date"), "2026-10-06"),
        (("facts", 0, "date"), None),
        (("facts", 0, "reference_names"), []),
        (("facts", 0, "reference_names"), ["Eric"]),
        (("facts", 0, "reference_names"), ["Luis", "Una persona inventada"]),
        (("facts", 0, "reference_names"), ["Luis", "Luis"]),
        (("facts", 0, "source_quote"), "Mañana iré al cine con él"),
        (("reason",), 101),
        (("complete",), 1),
    ],
)
def test_rejects_unsupported_or_inconsistent_independent_reviews(
    tmp_path: Path, path: tuple[str | int, ...], value: object
):
    context, inspection, review, _vault = _case(tmp_path)
    item = review
    for key in path[:-1]:
        item = item[key]
    item[path[-1]] = value
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, inspection, review)


def test_incomplete_review_cannot_drop_any_proposed_fact(tmp_path: Path):
    context, inspection, review, _vault = _case(tmp_path)
    more = replace(
        inspection.proposed_facts[0],
        ordinal=1,
        text="Visitaremos el museo con {{ref:0}}.",
    )
    many = replace(
        inspection,
        proposed_facts=inspection.proposed_facts + (more,),
        selected_identity_reference_ordinals=(0, 1),
    )
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, many, review)
    review["facts"].append(
        {
            **review["facts"][0],
            "ordinal": 1,
            "reviewed_text": more.text,
        }
    )
    verdict = validate_independent_continuation_verdict(context, many, review)
    assert verdict.reviewed_ordinals == (0, 1)
    assert not verdict.may_execute
    review["facts"][1]["ordinal"] = 0
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, many, review)


def test_selected_source_state_and_plan_hash_cannot_be_swapped(tmp_path: Path):
    context, inspection, review, _vault = _case(tmp_path)
    for changed in (
        replace(context, original_source="Mañana iré a otro lugar con él"),
        replace(context, pending_record_digest="f" * 64),
        replace(inspection, plan_digest="0" * 64),
    ):
        changed_context = changed if type(changed) is type(context) else context
        changed_inspection = changed if type(changed) is type(inspection) else inspection
        if changed_context is context and changed_inspection is not inspection:
            # There is no supplied plan in this function: the verdict binds
            # to the altered inspection; the later prewrite revalidates plan.
            verdict = validate_independent_continuation_verdict(context, changed_inspection, review)
            assert not verdict.may_execute
        else:
            with pytest.raises(CandidateContinuationSemanticError):
                validate_independent_continuation_verdict(
                    changed_context, changed_inspection, review
                )


def test_prompt_review_is_not_preapproved_semantic_truth(tmp_path: Path):
    context, plan, _vault = _ready_inspector(tmp_path)
    action = plan.actions[0]
    wrong_date = replace(
        action.units[0],
        target=replace(action.units[0].target, query="2026-10-09"),
        fact_temporal_anchors=action.units[0].fact_temporal_anchors,
    )
    altered = RequestPlan((WriteAction((wrong_date, action.units[1])),), ())
    inspection = inspect_selected_candidate_plan(context, altered)
    assert not inspection.may_execute
    # A flattering model verdict copying the planned date would NOT
    # independently prove "mañana" means the planned date. The provider
    # must pass the separate frozen semantic evaluation before integration.
    review = {
        "approved": False,
        "complete": False,
        "reason": "wrong destination",
        "facts": [
            {
                "ordinal": 0,
                "kind": "record",
                "reviewed_text": inspection.proposed_facts[0].text,
                "date": "2026-10-09",
                "reference_names": ["Luis"],
                "supported": False,
            }
        ],
    }
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, inspection, review)


def test_review_rejects_unproven_nonselected_participant(tmp_path: Path):
    context, inspection, review, _vault = _case(tmp_path)
    review["facts"][0]["reference_names"].append("Alguien inexistente")
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, inspection, review)


def test_review_input_is_not_mutated_by_validator(tmp_path: Path):
    context, inspection, review, _vault = _case(tmp_path)
    before = deepcopy(review)
    validate_independent_continuation_verdict(context, inspection, review)
    assert review == before


def test_reviewer_can_not_claim_extra_real_source_person(tmp_path: Path):
    context, inspection, review, _vault = _case(tmp_path)
    review["facts"][0]["reference_names"] = ["Luis", "Eric"]
    # Eric occurs in the previous clause, but is not part of the new plan.
    assert "Eric" in context.original_source
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict(context, inspection, review)


def test_reviewed_source_final_guard_against_replay_and_tamper(tmp_path: Path):
    from odyssey_core.candidate_continuation_context import (
        prepare_selected_candidate_continuation,
    )
    from odyssey_core.candidate_continuation_semantic import (
        validate_independent_continuation_verdict_current,
    )
    from tests.runtime.test_candidate_pending_state import _ready, _reply
    from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _linked_day_plan

    preview, repo, vault, state = _ready(tmp_path)
    _reply(repo, vault, "Luis")
    ctx = prepare_selected_candidate_continuation(
        repo,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    plan = _linked_day_plan(
        "2026-10-05",
        "Iré al cine con {{ref:0}}.",
        "él",
        "2026-10-05",
        target_name="Luis",
    )
    inspection = inspect_selected_candidate_plan(ctx, plan)
    independent = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "kind": "record",
                "reviewed_text": inspection.proposed_facts[0].text,
                "date": "2026-10-05",
                "reference_names": ["Luis"],
                "supported": True,
            }
        ],
    }
    verdict = validate_independent_continuation_verdict(ctx, inspection, independent)
    validate_independent_continuation_verdict_current(
        verdict, ctx, inspection, independent, plan, repo, vault=vault, schema=SCHEMA
    )
    changed_review = deepcopy(independent)
    changed_review["reason"] = "untrusted alternate review"
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict_current(
            verdict, ctx, inspection, changed_review, plan, repo, vault=vault, schema=SCHEMA
        )
    altered = RequestPlan(
        (
            WriteAction(
                (
                    replace(plan.actions[0].units[0], facts=("Cambio con {{ref:0}}.",)),
                    plan.actions[0].units[1],
                )
            ),
        ),
        (),
    )
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict_current(
            verdict,
            ctx,
            inspection,
            independent,
            altered,
            repo,
            vault=vault,
            schema=SCHEMA,
        )
    (vault.root / "Luis.md").write_text(
        (vault.root / "Luis.md").read_text(encoding="utf-8") + chr(10),
        encoding="utf-8",
    )
    with pytest.raises(CandidateContinuationSemanticError):
        validate_independent_continuation_verdict_current(
            verdict, ctx, inspection, independent, plan, repo, vault=vault, schema=SCHEMA
        )
    assert repo.read(preview.request_id)["status"] == "selected"


@pytest.mark.parametrize(
    "proposed_text",
    [
        "Iré al cine con {{ref:9}}.",
        "Iré al cine con {{ref:0}} y {{ref:0}}.",
        "Iré al cine con {{ref:x}}.",
        "Iré al cine con Luis.",
    ],
)
def test_symbolic_references_must_match_core_typed_bindings(tmp_path: Path, proposed_text: str):
    context, plan, _vault = _ready_inspector(tmp_path)
    writer, helper = plan.actions[0].units
    modified = RequestPlan((WriteAction((replace(writer, facts=(proposed_text,)), helper)),), ())
    from odyssey_core.candidate_continuation_plan import CandidateContinuationPlanError

    with pytest.raises(CandidateContinuationPlanError):
        inspect_selected_candidate_plan(context, modified)


def test_provider_adapter_reuses_strict_existing_ask_and_never_writes(tmp_path: Path):
    context, inspection, expected, vault = _case(tmp_path)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    calls = []

    def fake_ask(model, instructions, payload, schema, name):
        calls.append((model, instructions, payload, schema, name))
        return expected

    result, verdict = review_selected_candidate_with_provider(
        context, inspection, ask=fake_ask, model="synthetic-model"
    )
    assert len(calls) == 1
    model, instructions, payload, schema, name = calls[0]
    assert model == "synthetic-model"
    assert instructions.startswith(PROMPT_SOURCE_REVIEW_CORE_ANCHORED)
    assert schema == REVIEW_CORE_ANCHORED_SCHEMA
    assert name == "odyssey_e5_candidate_continuation_v1"
    assert payload["source"] == context.original_source
    assert payload["clock"] == context.captured_at
    assert payload["already_written_fact_ordinals"] == [0, 1]
    assert not any("guard" in key or "note_id" in key for key in payload)
    assert result == expected
    assert result is not expected
    assert not verdict.may_execute
    result["facts"][0]["reviewed_text"] = "Altered by caller"
    assert expected["facts"][0]["reviewed_text"] != "Altered by caller"
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == before


@pytest.mark.parametrize("failure", ["denied", "missing", "invented", "malformed"])
def test_provider_adapter_rejects_unsafe_review_without_any_write(tmp_path: Path, failure: str):
    context, inspection, baseline, vault = _case(tmp_path)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    answer = deepcopy(baseline)
    if failure == "denied":
        answer["approved"] = False
    elif failure == "missing":
        answer["facts"].clear()
    elif failure == "invented":
        answer["facts"][0]["reference_names"].append("Someone else")
    else:
        answer = {"approved": "true"}
    with pytest.raises(CandidateContinuationSemanticError):
        review_selected_candidate_with_provider(
            context, inspection, ask=lambda *_: answer, model="synthetic-model"
        )
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == before


def test_provider_adapter_does_not_call_provider_without_explicit_model(tmp_path: Path):
    context, inspection, _, _vault = _case(tmp_path)
    called = []
    with pytest.raises(ValueError):
        review_selected_candidate_with_provider(
            context, inspection, ask=lambda *_: called.append(True), model=""
        )
    assert not called


def test_adapter_with_existing_responses_client_strict_envelope(tmp_path: Path):
    context, inspection, expected, vault = _case(tmp_path)
    calls = []

    def create(**arguments):
        calls.append(arguments)
        return SimpleNamespace(
            status="completed", output_text=json.dumps(expected, ensure_ascii=False)
        )

    executor = object.__new__(WholeSourceLightExecutor)
    executor.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    actual, verdict = review_selected_candidate_with_provider(
        context, inspection, ask=executor._ask, model="synthetic-model"
    )
    assert actual == expected
    assert verdict.reviewed_ordinals == (0,)
    assert not verdict.may_execute
    assert len(calls) == 1
    args = calls[0]
    assert args["model"] == "synthetic-model"
    assert args["store"] is False
    assert args["reasoning"] == {"effort": "low"}
    assert args["text"]["format"]["strict"] is True
    assert args["text"]["format"]["schema"] == REVIEW_CORE_ANCHORED_SCHEMA
    assert args["text"]["format"]["name"] == "odyssey_e5_candidate_continuation_v1"
    assert json.loads(args["input"][1]["content"])["source"] == context.original_source
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == before


def test_existing_provider_incomplete_response_cannot_pass_adapter(tmp_path: Path):
    context, inspection, _expected, _vault = _case(tmp_path)
    executor = object.__new__(WholeSourceLightExecutor)
    executor.client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_kwargs: SimpleNamespace(status="incomplete", output_text="{}")
        )
    )
    with pytest.raises(WholeSourceLightError, match="not complete"):
        review_selected_candidate_with_provider(
            context, inspection, ask=executor._ask, model="synthetic-model"
        )
