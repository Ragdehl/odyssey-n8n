"""Real E2 concurrent Temporal+Core read seam and unchanged Luna evidence.

All files are in a disposable fixture vault. No provider requests or PROD.
"""

from __future__ import annotations

from threading import Barrier, Lock, current_thread

from odyssey_core.canonical_source_context import matching_canonical_source_names
from odyssey_core.execution_context import ExecutionContext, run_context_stage
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.note_lookup_batch import (
    ParallelExactNoteLookup,
    note_lookup_requests_from_source_roles,
)
from odyssey_runtime.context_planner_ports import (
    ContextAwareCorePlannerFactory,
    OpenAILunaContextPlannerFactory,
)
from tests.runtime.test_e2_context_planner_integration import ContextFactory, Temporal, _execute
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_hybrid_canonical_context_and_clock_rendering import _scoped_context


def test_existing_luna_hints_match_e2_one_pass_canonical_hints(tmp_path):
    repo, *_ = fresh_corpus_vault(tmp_path)
    context = _scoped_context("F07")
    requests = note_lookup_requests_from_source_roles(context)
    enriched = run_context_stage(
        ExecutionContext(
            "e2-same-hints", context.source, "2026-10-15T11:00:00+02:00", "Europe/Paris"
        ),
        ParallelExactNoteLookup(requests=requests, repository=repo, schema=SCHEMA),
    )
    old = matching_canonical_source_names(context, repo, SCHEMA)
    assert old
    assert enriched.source_note_hints == old

    # Repeated canonical names must remain ambiguous in both paths.
    original = repo.read_text("Bea.md")
    repo.create_text(
        "Different-Bea.md", original.replace("fixture-person-bea", "fixture-person-bea-2")
    )
    after = run_context_stage(
        ExecutionContext(
            "e2-duplicated", context.source, "2026-10-15T11:00:00+02:00", "Europe/Paris"
        ),
        ParallelExactNoteLookup(requests=requests, repository=repo, schema=SCHEMA),
    )
    assert after.source_note_hints == matching_canonical_source_names(context, repo, SCHEMA)
    assert all(hint.name != "Bea" for hint in after.source_note_hints)
    assert any(
        mention.source_text == "Bea" and len(mention.candidates) == 2
        for mention in after.note_mentions
    )


def test_real_luna_factory_is_structural_and_uses_unchanged_model_prompt_contract():
    from odyssey_core.experimental_luna_planning import (
        LUNA_EXPERIMENT_MODEL,
        LUNA_EXPERIMENT_REASONING_EFFORT,
    )

    factory = OpenAILunaContextPlannerFactory(
        client=object(),
        schema=SCHEMA,
        clock={"date": "2026-10-15", "time": "11:00", "timezone": "Europe/Paris"},
    )
    assert isinstance(factory, ContextAwareCorePlannerFactory)
    assert ContextAwareCorePlannerFactory not in type(factory).__bases__
    scope = _scoped_context("F07")
    context = ExecutionContext(
        "e2-luna-production",
        scope.source,
        "2026-10-15T11:00:00+02:00",
        "Europe/Paris",
        candidates=scope,
    )
    planner = factory.create_for_context(context)
    legacy = OpenAILunaExperimentalPlanner(
        factory._client,
        SCHEMA,
        factory._clock,
        candidate_context=scope,
        domain_interpretation=None,
    )
    assert type(planner) is OpenAILunaExperimentalPlanner
    assert (planner.model, planner.reasoning_effort, planner.max_output_tokens) == (
        legacy.model,
        legacy.reasoning_effort,
        legacy.max_output_tokens,
    )
    assert planner.model == LUNA_EXPERIMENT_MODEL
    assert planner.reasoning_effort == LUNA_EXPERIMENT_REASONING_EFFORT
    assert planner._candidate_context is scope
    assert planner._domain_interpretation is None


def test_temporal_model_call_overlaps_exactly_one_vault_scan_on_real_core_route(tmp_path):
    barrier = Barrier(2)
    seen: list[str] = []
    sync = Lock()
    participants = set()

    class OverlappingTemporal(Temporal):
        def interpret(self, source):
            with sync:
                participants.add(current_thread().name)
                seen.append("temporal")
            barrier.wait(timeout=5)
            return super().interpret(source)

    def before_execute(repo):
        prior = repo.list_markdown_paths
        was_called = False

        def observed_scan():
            nonlocal was_called
            with sync:
                first = not was_called
                was_called = True
                if first:
                    seen.append("notes")
                    participants.add(current_thread().name)
            if first:
                barrier.wait(timeout=5)
            return prior()

        repo.list_markdown_paths = observed_scan

    factory = ContextFactory()
    _execute(
        tmp_path, factory, temporal_override=OverlappingTemporal(), repository_hook=before_execute
    )
    assert set(seen) == {"temporal", "notes"}
    assert len(participants) == 2
    assert len(factory.seen) == 1
    assert factory.seen[0].note_mentions[0].source_text == "Bea"


def test_large_source_role_budget_does_not_truncate_or_claim_validated_identity():
    from odyssey_core.execution_context import PendingContext

    assert PendingContext("core.note_lookup_exact", "LOOKUP_BUDGET_EXCEEDED").reason == (
        "LOOKUP_BUDGET_EXCEEDED"
    )


def test_optional_lookup_budget_overflow_keeps_ordinary_core_writer_functional(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from odyssey_core import canonical_source_context
    from odyssey_core.candidate_context import CoreSourceSpan
    from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

    # Force just the overflow boundary; a normal CoreCandidateContext accepts
    # at most 16 distinct scoped roles but cannot claim an invented identity.
    def too_many(context):
        at = context.source.index("Bea")
        return (CoreSourceSpan("Bea", at, at + 3),) * 13

    monkeypatch.setattr(canonical_source_context, "source_note_role_spans", too_many)

    class BudgetFactory:
        def create_for_context(self, context):
            assert context.note_mentions == ()
            assert context.source_note_hints == ()
            assert context.pending[0].reason == "LOOKUP_BUDGET_EXCEEDED"
            return SimpleNamespace(
                plan=lambda _: _linked_day_plan(
                    "2026-10-04", "Hablé con {{ref:0}}.", "Bea", "2026-10-04"
                )
            )

    _execute(tmp_path, BudgetFactory())


def test_real_composed_luna_factory_receives_same_prompt_hints_and_keeps_real_writer(
    tmp_path,
    monkeypatch,
):
    """No provider calls: actual composition adapter + Luna class + canonical Writer."""

    from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
    from odyssey_runtime.context_planner_ports import OpenAILunaContextPlannerFactory
    from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

    planned = []

    def recorded_plan(self, source, conversation_context=()):
        assert source == "Hoy hablé con Bea."
        assert self._candidate_context is not None
        assert self._domain_interpretation.capability_id == "temporal"
        assert [hint.name for hint in self._known_source_notes] == ["Bea"]
        assert self._known_source_notes[0].mention == "Bea"
        planned.append(self._known_source_notes)
        return _linked_day_plan("2026-10-04", "Hablé con {{ref:0}}.", "Bea", "2026-10-04")

    monkeypatch.setattr(OpenAILunaExperimentalPlanner, "plan", recorded_plan)
    factory = OpenAILunaContextPlannerFactory(
        client=object(),
        schema=SCHEMA,
        clock={"date": "2026-10-04", "time": "12:00", "timezone": "Europe/Paris"},
    )
    _execute(tmp_path, factory)
    assert len(planned) == 1
    assert planned[0][0].name == "Bea"


def test_real_parallel_core_note_scan_reports_observed_progress_without_fake_percentage(tmp_path):
    """Dispatcher reports start/join of ONE real Core batch in its normal route."""
    from odyssey_runtime.composition import RuntimeComposition
    from odyssey_runtime.progress import ProductProgressStore

    store = ProductProgressStore()
    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: None,
        refresh_indexes=lambda: None,
        product_progress_store=store,
    )
    actor = "odyssey-runtime"
    request_id = "e2-observed-scan"
    store.begin(actor, request_id)
    observed = []

    def report(stage, payload):
        runtime._record_progress_event(actor, request_id, stage, payload)
        observed.append((stage, store.read(actor, request_id)))

    factory = ContextFactory()
    _execute(tmp_path, factory, progress_callback=report)
    names = [name for name, _ in observed]
    assert names.index("core.notes.started") < names.index("core.notes.ready")
    assert names.index("core.notes.started") < names.index("temporal.ready")
    assert names.index("temporal.ready") < names.index("core.notes.ready")
    assert len(factory.seen) == 1
    assert [item.stage for _, item in observed if item.stage.startswith("core.notes")] == [
        "core.notes.started",
        "core.notes.ready",
    ]
    stages = [item for _, item in observed]
    assert all(
        after.sequence > before.sequence for before, after in zip(stages, stages[1:], strict=False)
    )
    assert all(
        after.progress >= before.progress for before, after in zip(stages, stages[1:], strict=False)
    )
    assert all(item.stage_view is not None for item in stages)
    assert all(item.progress < 100 for item in stages)
