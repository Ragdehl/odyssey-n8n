"""General hybrid source-note context and exact clock-prefix hygiene."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.canonical_source_context import matching_canonical_source_names
from odyssey_core.hybrid_fact_presentation import normalize_hybrid_day_clock_prefix
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    TemporalReferencePart,
)
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def _scoped_context(case: str):
    source = next(row["source"] for row in CASES if row["id"] == case)
    saved = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_semantic_live_v3/{case}.json").read_text()
    )
    client = FrozenProvider(saved["real_model_outputs"][:1])
    proposal = OpenAIFactCandidateRouter(client, prompt_revision="v4").propose(source)
    return compile_hybrid_candidate_bundle(proposal).units[0].context


def test_named_participants_get_only_existing_exact_vault_names(tmp_path: Path):
    repo, *_ = fresh_corpus_vault(tmp_path)
    hints = matching_canonical_source_names(_scoped_context("F07"), repo, SCHEMA)
    assert {(h.mention, h.name, h.note_type) for h in hints} == {
        ("Bea", "Bea", "person"),
        ("Luis", "Luis", "person"),
    }
    assert not matching_canonical_source_names(_scoped_context("F05"), repo, SCHEMA) == ()


def test_duplicate_canonical_names_do_not_become_unambiguous_identity_hints(tmp_path: Path):
    repo, *_ = fresh_corpus_vault(tmp_path)
    original = repo.read_text("Bea.md")
    assert "fixture-person-bea" in original
    repo.create_text(
        "Duplicate-Bea.md", original.replace("fixture-person-bea", "fixture-person-bea-2")
    )
    hints = matching_canonical_source_names(_scoped_context("F07"), repo, SCHEMA)
    assert {(h.mention, h.name) for h in hints} == {("Luis", "Luis")}


def _intent(clock: str, literal: str, *, day: str = "2026-10-10"):
    return SemanticWriteIntent(
        (
            SemanticWriteOperation(
                target=IdentityIntent(day, IdentityBinding.DESCRIBED, note_type="calendar_day"),
                apply_to=ApplyTo.ONE,
                intent="record",
                facts=(
                    SemanticFact(
                        (
                            LiteralPart(literal),
                            TemporalReferencePart(clock, day + "T10:00:00+02:00"),
                        )
                    ),
                ),
            ),
        )
    )


def test_verified_clock_only_deduplicates_exact_partial_source_prefix():
    intent = _intent("at 10", "We'll have dinner with Leo at ")
    fixed = normalize_hybrid_day_clock_prefix(intent, "Tomorrow we'll have dinner at 10")
    parts = fixed.operations[0].facts[0].parts
    assert parts == (
        LiteralPart("We'll have dinner with Leo."),
        TemporalReferencePart("at 10", "2026-10-10T10:00:00+02:00"),
    )
    assert normalize_hybrid_day_clock_prefix(intent, "Tomorrow at eleven") == intent


def test_nonduplicate_clock_text_and_noncalendar_targets_are_untouched():
    intent = _intent("at 10", "We'll have dinner with Leo ")
    assert normalize_hybrid_day_clock_prefix(intent, "Tomorrow at 10") == intent
    intent2 = _intent("at 10", "We got here at ")
    other_day = replace(
        intent2.operations[0],
        target=IdentityIntent("2026-10-11", IdentityBinding.DESCRIBED, note_type="calendar_day"),
    )
    wrong_target = SemanticWriteIntent((other_day,))
    assert normalize_hybrid_day_clock_prefix(wrong_target, "We got here at 10") == wrong_target


def _compiled_real_planner_fact(case: str, cohort: str, output_index: int):
    """Exercise Core's real semantic compiler with an immutable genuine reply.

    The independent reviewer's old response cannot be reused after changing
    the fact text: a new reviewer must see the newly compiled fact.
    """
    from odyssey_core.semantic_write import compile_semantic_write, decode_semantic_write_action

    receipt = json.loads((ROOT / f"benchmarks/application_router/{cohort}/{case}.json").read_text())
    raw = json.loads(receipt["real_model_outputs"][output_index]["output_text"])["result"]
    assert raw["outcome"] == "PLAN"
    intent = decode_semantic_write_action(raw["actions"][0], allow_temporal_reference=True)
    normalized = normalize_hybrid_day_clock_prefix(
        intent, next(row["source"] for row in CASES if row["id"] == case)
    )
    return compile_semantic_write(
        normalized,
        SCHEMA,
        authorized_calendar_dates=("2026-10-03", "2026-10-04", "2026-10-09", "2026-10-10"),
    )


def test_original_real_partial_clock_literal_is_rendered_once():
    action = _compiled_real_planner_fact("F05", "hybrid_semantic_live_v3", 2)
    assert action.units[1].facts == ("10:00 — Cenaremos con Luis en Albi.",)
    assert action.units[0].facts == ("Cenaremos con Ana en Toulouse.",)


def test_original_real_sibling_linked_event_has_complete_punctuation():
    action = _compiled_real_planner_fact("F05", "hybrid_semantic_live_v7", 2)
    assert action.units[0].facts == ("Cenaremos con {{ref:0}} en Toulouse.",)
    assert action.units[1].facts == ("10:00 — Cenaremos con {{ref:0}} en Albi.",)


def test_original_real_date_link_and_following_fact_keep_separator():
    action = _compiled_real_planner_fact("F15", "hybrid_semantic_live_v4", 4)
    assert action.units[0].facts == ("[[calendar/days/2026-10-03|03-10-2026]] Se quedó en casa.",)


def test_shared_time_reference_is_not_misrouted_as_first_group_person_pronoun():
    context = _scoped_context("F08")
    source = next(row["source"] for row in CASES if row["id"] == "F08")
    saved = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_semantic_live_v4/F08.json").read_text()
    )
    sdk = FrozenProvider(saved["real_model_outputs"][:1])
    bundle = compile_hybrid_candidate_bundle(
        OpenAIFactCandidateRouter(sdk, prompt_revision="v4").propose(source)
    )
    assert len(bundle.units) == 1
    assert bundle.units[0].route.capability_id == "temporal"
    assert bundle.units[0].route.depends_on is None
    assert bundle.units[0].route.dependent_mention is None
    assert len(context.candidates) == 2
