"""Real generic Core exact lookup fan-out without creating or authorizing Notes."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Barrier

import pytest

from odyssey_core.execution_context import (
    ContextContractError,
    ExecutionContext,
    NoteMention,
    NoteReferenceCandidate,
    QualitativeTime,
    run_context_stage,
    run_independent_stages,
)
from odyssey_core.identity import resolve_exact_entity
from odyssey_core.note_lookup_batch import NoteLookupRequest, ParallelExactNoteLookup
from odyssey_core.storage import VaultRepository
from tests.core.test_execution_context import TemporalStage
from tests.core.test_identity import _write_note

SOURCE = "Marta vio a María y Marta habló de Proyecto Atlas mañana por la tarde."


def fixtures(tmp_path):
    root = tmp_path / "vault"
    for dirname in ("people/one", "people/two", "projects", "calendar/days"):
        (root / dirname).mkdir(parents=True, exist_ok=True)
    repo = VaultRepository(root)
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
    )
    _write_note(repo, "people/one/Marta.md", note_id="marta-1", note_type="person")
    _write_note(repo, "people/two/Marta.md", note_id="marta-2", note_type="person")
    _write_note(repo, "people/one/María.md", note_id="maria-1", note_type="person")
    _write_note(repo, "projects/Proyecto Atlas.md", note_id="atlas-1", note_type="project")
    _write_note(
        repo,
        "calendar/days/2026-10-15.md",
        note_id="day-1",
        note_type="calendar_day",
        extra_metadata={"date": "2026-10-15"},
    )
    return repo, schema


def request(token, *, ordinal=0, type=None):
    start = -1
    for _ in range(ordinal + 1):
        start = SOURCE.index(token, start + 1)
    return NoteLookupRequest(token, start, start + len(token), type)


def context():
    return ExecutionContext("req-batch", SOURCE, "2026-10-14T08:00:00+02:00", "Europe/Paris")


def test_multiple_real_note_lookups_preserve_ambiguity_source_order_and_types(tmp_path):
    repo, schema = fixtures(tmp_path)
    stage = ParallelExactNoteLookup(
        requests=(
            request("Marta"),
            request("María"),
            request("Marta", ordinal=1),
            request("Proyecto Atlas", type="project"),
        ),
        repository=repo,
        schema=schema,
    )
    result = run_context_stage(context(), stage)
    assert len(result.note_mentions) == 4
    assert [m.source_text for m in result.note_mentions] == [
        "Marta",
        "María",
        "Marta",
        "Proyecto Atlas",
    ]
    assert [m.start for m in result.note_mentions] == sorted(m.start for m in result.note_mentions)
    assert [len(m.candidates) for m in result.note_mentions] == [2, 1, 2, 1]
    assert {candidate.stable_note_id for candidate in result.note_mentions[0].candidates} == {
        "marta-1",
        "marta-2",
    }
    assert result.note_mentions[1].candidates == (
        NoteReferenceCandidate("maria-1", "person", "María"),
    )
    assert result.note_mentions[3].candidates == (
        NoteReferenceCandidate("atlas-1", "project", "Proyecto Atlas"),
    )
    assert [x.reason for x in result.pending] == ["AMBIGUOUS_EXACT_MATCH", "AMBIGUOUS_EXACT_MATCH"]
    # The exact candidates do NOT mint a canonical identity or mutate Markdown.
    assert all(
        "Marta" in repo.read_text(path) for path in ("people/one/Marta.md", "people/two/Marta.md")
    )


def test_no_exact_match_and_app_managed_type_are_not_made_into_generic_write_targets(tmp_path):
    repo, schema = fixtures(tmp_path)
    source = "No encontré a Luis pero sí el día 2026-10-15."
    start = source.index("Luis")
    day_start = source.index("2026-10-15")
    stage = ParallelExactNoteLookup(
        requests=(
            NoteLookupRequest("Luis", start, start + 4, "person"),
            NoteLookupRequest("2026-10-15", day_start, day_start + 10, "calendar_day"),
        ),
        repository=repo,
        schema=schema,
    )
    ctx = ExecutionContext("req-managed", source, "2026-10-14T08:00:00+02:00", "Europe/Paris")
    result = run_context_stage(ctx, stage)
    assert result.note_mentions == (
        NoteMention("Luis", (), start, start + 4),
        NoteMention("2026-10-15", (), day_start, day_start + 10),
    )
    assert tuple(x.reason for x in result.pending) == (
        "NO_EXACT_MATCH",
        "APP_MANAGED_NOTE_IDENTITY",
    )
    assert not hasattr(stage, "create_note")


def test_multiple_searches_run_concurrently_with_bounded_worker_count(tmp_path):
    repo, schema = fixtures(tmp_path)
    gate = Barrier(3)
    import threading

    active = set()
    observed_threads = set()

    def exact(repository, schema, word, *, type=None):
        with threading.Lock():
            observed_threads.add(threading.get_ident())
        gate.wait(timeout=5)
        return resolve_exact_entity(repository, schema, word, type=type)

    batch = ParallelExactNoteLookup(
        requests=(request("Marta"), request("María"), request("Proyecto Atlas")),
        repository=repo,
        schema=schema,
        max_workers=3,
        lookup=exact,
    )
    result = run_context_stage(context(), batch)
    assert len(result.note_mentions) == 3
    assert len(observed_threads) == 3
    assert not active


def test_inner_batch_parallelism_can_overlap_independent_temporal_stage(tmp_path):
    repo, schema = fixtures(tmp_path)
    ctx = context()
    batch = ParallelExactNoteLookup(
        requests=(request("Marta"), request("María")),
        repository=repo,
        schema=schema,
    )

    class RealTemporalFixture(TemporalStage):
        def execute(self, data):
            # This test's source has a distinct time phrase but shares the same
            # immutable context. A deterministic fake supplies a typed date.
            from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
            from odyssey_core.execution_context import StageOutput

            assert data.source == SOURCE and data.actor is None
            phrase = "mañana por la tarde"
            return StageOutput(
                domains=(
                    DomainInterpretation(
                        "temporal",
                        SOURCE,
                        "TEMPORAL_RESOLUTION",
                        (DomainEvidence("temporal_reference", phrase, "2026-10-15"),),
                    ),
                ),
                qualitative_times=(
                    QualitativeTime(phrase, "2026-10-15", "por la tarde", "Europe/Paris"),
                ),
            )

    enriched = run_independent_stages(ctx, (RealTemporalFixture(), batch))
    assert enriched.qualitative_times[0].qualifier == "por la tarde"
    assert len(enriched.note_mentions) == 2
    assert enriched.source == SOURCE and enriched.authenticated_actor is None


@pytest.mark.parametrize(
    "bad",
    [
        NoteLookupRequest("Marta", 0, 5, "invalid-type"),
        NoteLookupRequest("María", 0, 5),
        NoteLookupRequest("Marta", 0, 6),
    ],
)
def test_lookup_rejects_bad_span_or_unknown_type_before_read(tmp_path, bad):
    repo, schema = fixtures(tmp_path)
    invoked = []

    def forbidden(*_args, **_kwargs):
        invoked.append(True)
        raise AssertionError("must fail before worker")

    stage = ParallelExactNoteLookup(
        requests=(bad,), repository=repo, schema=schema, lookup=forbidden
    )
    with pytest.raises(ContextContractError):
        run_context_stage(context(), stage)
    assert invoked == []


def test_lookup_rejects_unbounded_fanout_and_source_replay(tmp_path):
    repo, schema = fixtures(tmp_path)
    with pytest.raises(ContextContractError):
        ParallelExactNoteLookup(requests=(request("Marta"),) * 13, repository=repo, schema=schema)
    with pytest.raises(ContextContractError):
        ParallelExactNoteLookup(
            requests=(request("Marta"),), repository=repo, schema=schema, max_workers=5
        )
    with pytest.raises(ContextContractError):
        run_context_stage(
            context(),
            ParallelExactNoteLookup(
                requests=(request("Marta"), request("Marta")),
                repository=repo,
                schema=schema,
            ),
        )


def test_exact_candidate_overflow_is_pending_not_arbitrarily_truncated(tmp_path):
    repo, schema = fixtures(tmp_path)
    for ordinal in range(3, 11):
        folder = repo.root / "people" / f"additional-{ordinal}"
        folder.mkdir(parents=True)
        _write_note(
            repo,
            f"people/additional-{ordinal}/Marta.md",
            note_id=f"marta-{ordinal}",
            note_type="person",
        )
    stage = ParallelExactNoteLookup(
        requests=(request("Marta"),),
        repository=repo,
        schema=schema,
    )
    result = run_context_stage(context(), stage)
    assert result.note_mentions[0].candidates == ()
    assert result.pending[0].reason == "EXACT_MATCH_SET_TOO_LARGE"
    assert result.pending[0].source_text == "Marta"
    assert result.pending[0].start == 0


def test_worker_failure_does_not_merge_partial_candidates(tmp_path):
    repo, schema = fixtures(tmp_path)
    original = context()

    def failed_lookup(repository, schema, query, *, type=None):
        if query == "María":
            raise RuntimeError("read failure")
        return resolve_exact_entity(repository, schema, query, type=type)

    stage = ParallelExactNoteLookup(
        requests=(request("Marta"), request("María")),
        repository=repo,
        schema=schema,
        lookup=failed_lookup,
    )
    with pytest.raises(RuntimeError, match="read failure"):
        run_context_stage(original, stage)
    assert original.note_mentions == () and original.pending == ()
