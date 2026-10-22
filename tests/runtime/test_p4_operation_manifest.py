"""Actor-local, immutable E3 operation traces do not permit crash recovery."""

import json

import pytest

from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore

SOURCE = "Escribí una nota. Haz una tarea. Otra nota."
GROUPS = (
    ("core", "Escribí una nota. ", ()),
    ("tasks", "Haz una tarea. ", ()),
    ("core", "Otra nota.", ()),
)


def _case(tmp_path):
    store = LocalDeliveryResultStore(tmp_path / "actor-a" / "delivery-results")
    request_id = "p4-group-three"
    fingerprint = store.fingerprint(SOURCE, "main")
    return store, request_id, fingerprint


def test_three_operations_have_immutable_source_bound_prewrite_plan_and_outcomes(tmp_path):
    store, delivery, fingerprint = _case(tmp_path)
    store.claim_mutation(delivery, fingerprint)
    store.begin_operation_manifest(delivery, fingerprint, SOURCE, GROUPS)
    plan = next(tmp_path.rglob("*.operation-plan.json"))
    content = json.loads(plan.read_text())
    assert SOURCE not in plan.read_text()
    assert len(content["groups"]) == 3
    assert [row["capability"] for row in content["groups"]] == ["core", "tasks", "core"]
    assert content["groups"][1]["predecessors"] == []
    store.observe_operation_manifest(delivery, fingerprint, 0, "core", "completed", ("note-a",))
    store.observe_operation_manifest(delivery, fingerprint, 1, "tasks", "completed", ("session-1",))
    assert store.inspect_operation_manifest(delivery, fingerprint) == {
        "manifest_present": True,
        "planned_operations": 3,
        "observed_operations": 2,
        "claim_state": "unresolved_attempt",
        "recovery_authorized": False,
    }
    snapshot = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert store.inspect_operation_manifest(delivery, fingerprint)["observed_operations"] == 2
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == snapshot
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        store.claim_mutation(delivery, fingerprint)
    store.observe_operation_manifest(delivery, fingerprint, 2, "core", "partial", ())
    store.save(
        delivery,
        fingerprint,
        {"request_id": delivery, "status": "partial"},
        "2026-10-17T15:00:00+02:00",
    )
    store.finish_mutation_claim(delivery)
    assert store.load(delivery, fingerprint)["status"] == "partial"
    assert store.inspect_operation_manifest(delivery, fingerprint)["recovery_authorized"] is False


@pytest.mark.parametrize(
    "invalid", ["no_claim", "bad_source", "bad_order", "bad_cap", "forward_edge", "oversized"]
)
def test_manifest_prewrite_cannot_publish_unbound_plan(tmp_path, invalid):
    store, delivery, fingerprint = _case(tmp_path)
    if invalid != "no_claim":
        store.claim_mutation(delivery, fingerprint)
    groups = GROUPS
    source = SOURCE
    if invalid == "bad_source":
        source = SOURCE + " extra"
    elif invalid == "bad_order":
        groups = (GROUPS[1], GROUPS[0], GROUPS[2])
    elif invalid == "bad_cap":
        groups = (GROUPS[0], ("calendar", *GROUPS[1][1:]), GROUPS[2])
    elif invalid == "forward_edge":
        groups = (GROUPS[0], ("tasks", GROUPS[1][1], (2,)), GROUPS[2])
    elif invalid == "oversized":
        source = SOURCE * 200
    with pytest.raises(DeliveryResultError):
        store.begin_operation_manifest(delivery, fingerprint, source, groups)
    assert not list(tmp_path.rglob("*.operation-plan.json"))


def test_manifest_observations_reject_skip_conflict_and_different_actor(tmp_path):
    store, delivery, fingerprint = _case(tmp_path)
    store.claim_mutation(delivery, fingerprint)
    store.begin_operation_manifest(delivery, fingerprint, SOURCE, GROUPS)
    other = LocalDeliveryResultStore(tmp_path / "actor-b" / "delivery-results")
    assert other.inspect_operation_manifest(delivery, fingerprint)["manifest_present"] is False
    with pytest.raises(DeliveryResultError):
        store.observe_operation_manifest(delivery, fingerprint, 1, "tasks", "completed", ())
    store.observe_operation_manifest(delivery, fingerprint, 0, "core", "completed", ("id-a",))
    store.observe_operation_manifest(delivery, fingerprint, 0, "core", "completed", ("id-a",))
    with pytest.raises(DeliveryResultError, match="immutable"):
        store.observe_operation_manifest(delivery, fingerprint, 0, "core", "completed", ("id-b",))
    with pytest.raises(DeliveryResultError):
        store.observe_operation_manifest(delivery, fingerprint, 1, "core", "completed", ())


def test_tampered_or_symlink_manifest_is_not_trusted(tmp_path):
    store, delivery, fingerprint = _case(tmp_path)
    store.claim_mutation(delivery, fingerprint)
    store.begin_operation_manifest(delivery, fingerprint, SOURCE, GROUPS)
    plan = next(tmp_path.rglob("*.operation-plan.json"))
    content = json.loads(plan.read_text())
    content["fingerprint"] = "different"
    plan.write_text(json.dumps(content))
    with pytest.raises(DeliveryResultError):
        store.inspect_operation_manifest(delivery, fingerprint)
    plan.unlink()
    target = tmp_path / "other-manifest.txt"
    target.write_text(json.dumps(content))
    plan.symlink_to(target)
    with pytest.raises(DeliveryResultError):
        store.inspect_operation_manifest(delivery, fingerprint)


def test_dependent_core_write_then_task_crash_is_forensic_not_recoverable(tmp_path):
    """Actual Core Writer persists its fact, but an uncertain Task leaves E3 locked."""
    from tests.runtime.test_p4_dependent_router_integrated import SOURCE, _setup

    repo, actor, executor, runtime, calls, sessions = _setup(tmp_path)
    state_store = LocalDeliveryResultStore(
        runtime.conversation_root_resolver.resolve(actor.stable_user_id) / "delivery-results"
    )

    def begin(request, source, _actor, groups):
        state_store.begin_operation_manifest(
            request, state_store.fingerprint(source, "main"), source, groups
        )

    def observe(request, source, _actor, index, cap, result):
        state_store.observe_operation_manifest(
            request,
            state_store.fingerprint(source, "main"),
            index,
            cap,
            result.status.value,
            result.affected_stable_note_ids,
        )

    executor.operation_manifest_begin = begin
    executor.operation_manifest_observe = observe
    task = executor.dependent_task_delegate
    assert task is not None

    def crash_after_task_write(*args):
        task(*args)
        raise RuntimeError("simulated service crash before operation journal write")

    executor.dependent_task_delegate = crash_after_task_write
    req = "p4-manifest-core-then-task-crash"
    with pytest.raises(RuntimeError, match="simulated service crash"):
        runtime.execute_product(SOURCE, req, "main", actor)
    report = state_store.inspect_operation_manifest(req, state_store.fingerprint(SOURCE, "main"))
    assert report == {
        "manifest_present": True,
        "planned_operations": 2,
        "observed_operations": 1,
        "claim_state": "unresolved_attempt",
        "recovery_authorized": False,
    }
    assert len(sessions.list_for_task("atlas-p4-dependent-task")) == 1
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        runtime.execute_product(SOURCE, req, "main", actor)
    assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert calls == ["prepare", "core", "task"]


def test_manifest_storage_failure_before_core_write_blocks_all_mutations(tmp_path):
    from tests.runtime.test_p4_dependent_router_integrated import SOURCE, _setup

    repo, actor, executor, runtime, calls, sessions = _setup(tmp_path)
    executor.operation_manifest_begin = lambda *_: (_ for _ in ()).throw(
        DeliveryResultError("manifest unavailable before first mutation")
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(DeliveryResultError, match="manifest unavailable"):
        runtime.execute_product(SOURCE, "p4-manifest-unavailable", "main", actor)
    assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert calls == ["prepare"]
    assert sessions.list_for_task("atlas-p4-dependent-task") == ()


def test_registering_events_extends_only_the_forensic_capability_vocabulary(tmp_path):
    source = "Concierto con horario. Tengo que preparar informe."
    groups = (
        ("events", "Concierto con horario. ", ()),
        ("tasks", "Tengo que preparar informe.", ()),
    )
    root = tmp_path / "actor-events" / "delivery-results"
    legacy = LocalDeliveryResultStore(root)
    delivery = "e5-registered-capability"
    fingerprint = legacy.fingerprint(source, "main")
    legacy.claim_mutation(delivery, fingerprint)
    with pytest.raises(DeliveryResultError, match="operation group or dependency"):
        legacy.begin_operation_manifest(delivery, fingerprint, source, groups)
    registered = LocalDeliveryResultStore(
        root, manifest_capabilities=frozenset({"core", "tasks", "events"})
    )
    registered.begin_operation_manifest(delivery, fingerprint, source, groups)
    registered.observe_operation_manifest(delivery, fingerprint, 0, "events", "completed", ("e-1",))
    registered.observe_operation_manifest(delivery, fingerprint, 1, "tasks", "completed", ("t-1",))
    evidence = registered.inspect_operation_manifest(delivery, fingerprint)
    assert evidence["manifest_present"] is True
    assert evidence["planned_operations"] == 2
    assert evidence["observed_operations"] == 2
    assert evidence["recovery_authorized"] is False
    with pytest.raises(DeliveryResultError):
        LocalDeliveryResultStore(root, manifest_capabilities=frozenset({"events/../unsafe"}))
