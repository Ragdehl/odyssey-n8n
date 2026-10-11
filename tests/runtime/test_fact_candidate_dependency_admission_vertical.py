"""Cross-request-ID and concurrent execution safety for real Core plans.

The operation journal is non-knowledge state; actual write tests only touch
disposable Markdown. A stable client key, never source-text deduplication,
survives retries with a new Core per-attempt request identifier.
"""

from __future__ import annotations

import multiprocessing
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_dependency_admission import (
    DependentOperationAdmissionError,
    DependentOperationJournal,
    execute_dependent_core_once,
)
from odyssey_core.storage import VaultRepository
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_dependency_global_coverage_vertical import _setup
from tests.runtime.test_fact_candidate_dependent_actual_core_vertical import _vault
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _execute(case, key, repo, index, state, request_id):
    source, context, plans, *_ = _setup(case)
    return execute_dependent_core_once(
        logical_operation_key=key,
        state_root=state,
        source=source,
        context=context,
        independent_plans=plans,
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=EmptyIndex(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner(),
        actor="dependent-admission-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: request_id,
    )


@pytest.mark.parametrize("case,existing", [("F23", False), ("F26", True), ("F26", False)])
def test_stable_logical_operation_key_survives_new_core_request_id(tmp_path: Path, case, existing):
    repo, index = _vault(tmp_path, existing_report=existing)
    state = tmp_path / "state"
    state.mkdir()
    first = _execute(case, "conversation42-message103", repo, index, state, "attempt-one")
    assert first.status is ApplicationStatus.COMPLETED
    journal = DependentOperationJournal(state, repo)
    record = journal.inspect("conversation42-message103")
    assert record is not None
    assert record.state == "completed"
    assert record.request_id == "attempt-one"
    assert record.source_digest and record.plan_digest and record.vault_digest
    files = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    with pytest.raises(DependentOperationAdmissionError, match="already admitted"):
        _execute(case, "conversation42-message103", repo, index, state, "attempt-two")
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == files
    assert len(list((state / "dependent-operations").glob("*.json"))) == 1


def test_journal_serializes_two_real_concurrent_requests_for_same_key(tmp_path):
    repo, index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    gate = threading.Barrier(2)

    def attempt(i):
        gate.wait(timeout=10)
        try:
            result = _execute("F23", "shared-logical-message", repo, index, state, f"try-{i}")
            return "ok", result.request_id
        except DependentOperationAdmissionError as error:
            return "blocked", str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(attempt, 1)
        second = pool.submit(attempt, 2)
        results = [first.result(timeout=20), second.result(timeout=20)]
    assert sorted(row[0] for row in results) == ["blocked", "ok"]
    assert repo.read_text("Odyssey.md").count("<!-- odyssey:fact request=try-") == 2


def test_crash_after_reservation_before_any_fact_stays_unknown_and_never_retries(tmp_path):
    repo, _index = _vault(tmp_path, existing_report=True)
    root = tmp_path / "state"
    root.mkdir()
    journal = DependentOperationJournal(root, repo)
    calls = []

    def raises():
        calls.append("start")
        raise RuntimeError("simulated process failure before writing any fact")

    with pytest.raises(RuntimeError, match="simulated"):
        journal.execute_once(
            logical_operation_key="crash-before-fact",
            request_id="attempt-one",
            source="Sample original",
            plan_repr="one real validated Core plan",
            operation=raises,
            classify=lambda _: "completed",
        )
    assert journal.inspect("crash-before-fact").state == "unknown"
    with pytest.raises(DependentOperationAdmissionError, match="already admitted"):
        journal.execute_once(
            logical_operation_key="crash-before-fact",
            request_id="attempt-two",
            source="Sample original",
            plan_repr="one real validated Core plan",
            operation=lambda: calls.append("unsafe_second_execution"),
            classify=lambda _: "completed",
        )
    assert calls == ["start"]


def test_malformed_or_symlink_state_never_runs_core(tmp_path):
    repo, _index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    journal = DependentOperationJournal(state, repo)
    with pytest.raises(DependentOperationAdmissionError, match="key"):
        journal.inspect("../../outside")
    with pytest.raises(DependentOperationAdmissionError, match="vault"):
        DependentOperationJournal(repo.root, repo)
    lock = state / "dependent-operations" / ".admission.lock"
    lock.symlink_to(state / "outside")
    with pytest.raises(DependentOperationAdmissionError, match="symlink"):
        journal.execute_once(
            logical_operation_key="unsafe",
            request_id="one",
            source="original",
            plan_repr="plan",
            operation=lambda: "not-called",
            classify=lambda _: "completed",
        )


def _separate_process_worker(vault: str, state: str, key: str, out):
    repo = VaultRepository(vault)
    journal = DependentOperationJournal(Path(state), repo)
    try:
        journal.execute_once(
            logical_operation_key=key,
            request_id="isolated-process",
            source="nonpersonal",
            plan_repr="already-reviewed-immutable",
            operation=lambda: (time.sleep(0.15), "ok")[1],
            classify=lambda _: "completed",
        )
        out.put("executed")
    except DependentOperationAdmissionError:
        out.put("blocked")


def test_two_separate_processes_cannot_admit_same_logical_operation(tmp_path):
    repo, _index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    ctx = multiprocessing.get_context("fork")
    output = ctx.Queue()
    workers = [
        ctx.Process(
            target=_separate_process_worker,
            args=(str(repo.root), str(state), "same-message-cross-process", output),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=12)
        if worker.is_alive():
            worker.terminate()
            worker.join()
            pytest.fail("Concurrent admission deadlocked")
        assert worker.exitcode == 0
    assert sorted([output.get(timeout=2), output.get(timeout=2)]) == ["blocked", "executed"]
    record = DependentOperationJournal(state, repo).inspect("same-message-cross-process")
    assert record is not None and record.state == "completed"


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_real_core_second_write_failure_is_durable_across_new_request_ids(
    case, tmp_path, monkeypatch
):
    """One source fact persists, and a different technical attempt stays blocked."""
    import odyssey_core.application as core_application
    from odyssey_core.application import ActionResult, ActionStatus

    repo, index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    original = core_application._execute_write

    def failed_second(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(
                action_index,
                "write",
                ActionStatus.FAILED,
                reason="injected second write failure",
            )
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(core_application, "_execute_write", failed_second)
    first = _execute(case, "stable-retry-key", repo, index, state, "attempt-before-crash")
    assert first.status is ApplicationStatus.PARTIAL
    journal = DependentOperationJournal(state, repo)
    assert journal.inspect("stable-retry-key").state == "partial"
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}

    monkeypatch.setattr(core_application, "_execute_write", original)
    with pytest.raises(DependentOperationAdmissionError, match="already admitted"):
        _execute(case, "stable-retry-key", repo, index, state, "another-tech-request")
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before


def test_content_alone_does_not_accidentally_identify_distinct_messages(tmp_path):
    """Different stable client IDs remain distinct regardless of source text."""
    repo, _index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    journal = DependentOperationJournal(state, repo)
    for identifier in ("first-distinct-message", "second-distinct-message"):
        journal.execute_once(
            logical_operation_key=identifier,
            request_id=identifier,
            source="La misma frase deliberadamente otra vez.",
            plan_repr="same already validated plan",
            operation=lambda: "executed",
            classify=lambda _: "completed",
        )
    records = list((state / "dependent-operations").glob("*.json"))
    assert len(records) == 2
    assert journal.inspect("first-distinct-message").source_digest == (
        journal.inspect("second-distinct-message").source_digest
    )


def test_recovery_requires_trusted_external_root_and_never_uses_vault_for_journal(tmp_path):
    repo, _index = _vault(tmp_path, existing_report=True)
    nonexistent = tmp_path / "unconfigured-state"
    with pytest.raises(DependentOperationAdmissionError, match="root"):
        DependentOperationJournal(nonexistent, repo)
    root = tmp_path / "state"
    root.mkdir()
    nested = root / "dependent-operations"
    nested.symlink_to(repo.root)
    with pytest.raises(DependentOperationAdmissionError, match="trusted"):
        DependentOperationJournal(root, repo)


def _abrupt_crash_process(vault: str, state: str) -> None:
    import os

    repo = VaultRepository(vault)
    journal = DependentOperationJournal(Path(state), repo)
    journal.execute_once(
        logical_operation_key="crash-restart-stable-message",
        request_id="aborted-execution",
        source="One original dependent message",
        plan_repr="original validated plan",
        operation=lambda: os._exit(9),
        classify=lambda _: "completed",
    )


def test_abrupt_process_death_leaves_reservation_and_blocks_restart(tmp_path):
    """No stale process lock is used as false proof a dead write was safe."""
    repo, _index = _vault(tmp_path, existing_report=True)
    state = tmp_path / "state"
    state.mkdir()
    child = multiprocessing.get_context("fork").Process(
        target=_abrupt_crash_process, args=(str(repo.root), str(state))
    )
    child.start()
    child.join(timeout=12)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail("Crash simulation did not exit")
    assert child.exitcode == 9
    ledger = DependentOperationJournal(state, repo)
    assert ledger.inspect("crash-restart-stable-message").state == "reserved"
    with pytest.raises(DependentOperationAdmissionError, match="already admitted"):
        ledger.execute_once(
            logical_operation_key="crash-restart-stable-message",
            request_id="fresh-id-after-crash",
            source="One original dependent message",
            plan_repr="original validated plan",
            operation=lambda: pytest.fail("Unsafe duplicate work"),
            classify=lambda _: "completed",
        )
