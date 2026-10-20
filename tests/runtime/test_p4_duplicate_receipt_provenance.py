"""Adversarial receipt cardinality tests for fresh Person -> Task evidence."""

from dataclasses import replace

import pytest

from odyssey_core.source_bound_dependency import (
    SourceBoundDependencyError,
    prove_source_bound_dependency,
)
from tests.runtime.test_p4_fresh_person_task import _physical, _scenario


def _completed_predecessor(tmp_path, *, others=()):
    repo, actor, executor, runtime, source, _calls = _physical(tmp_path, "Nora", others=others)
    assert (
        runtime.execute_product(source, "receipt-fixture", "main", actor)["status"] == "completed"
    )
    return repo, executor.person_core_results[0]


def test_repeated_identical_receipt_is_not_independent_provenance(tmp_path):
    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    receipt = action.canonical_direct_target_evidence[0]
    repeated = replace(
        predecessor,
        action_results=(replace(action, canonical_direct_target_evidence=(receipt, receipt)),),
    )
    source, before, after, mention, _ = _scenario("Nora")
    with pytest.raises(SourceBoundDependencyError):
        prove_source_bound_dependency(
            complete_original_source=source,
            antecedent_quote=before,
            dependent_quote=after,
            exact_dependent_mention=mention,
            predecessor=repeated,
            repository=repo,
            schema=__import__(
                "tests.runtime.test_whole_source_light_product_p4", fromlist=["SCHEMA"]
            ).SCHEMA,
        )


def test_single_handoff_rejects_current_receipt_from_another_source(tmp_path):
    """A live canonical Note does not authorize a different Core message."""
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, predecessor = _completed_predecessor(tmp_path)
    before = "Ayer saludé a Nora."
    after = " Mañana debo llamar a esa persona."
    with pytest.raises(SourceBoundDependencyError, match="different source span"):
        prove_source_bound_dependency(
            complete_original_source=before + after,
            antecedent_quote=before,
            dependent_quote=after,
            exact_dependent_mention="esa persona",
            predecessor=predecessor,
            repository=repo,
            schema=SCHEMA,
        )


def test_nm_handoff_rejects_current_receipt_from_another_source(tmp_path):
    from odyssey_core.dependent_group_evidence import (
        CanonicalGroupEvidenceError,
        prove_canonical_group_handoff,
    )
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, predecessor = _completed_predecessor(tmp_path)
    before = "Ayer saludé a Nora."
    after = " Mañana debo llamar a Nora."
    graph = ReviewedSourceGraph(
        before + after,
        (
            SourceGroup(0, "core", before, ()),
            SourceGroup(1, "tasks", after, (GroupDependency(0, "Nora", "Nora"),)),
        ),
    )
    with pytest.raises(CanonicalGroupEvidenceError, match="different source group"):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=1,
            predecessors={0: predecessor},
            repository=repo,
            schema=SCHEMA,
        )


def test_stale_duplicate_receipt_fails_closed(tmp_path):
    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    receipt = action.canonical_direct_target_evidence[0]
    stale = replace(receipt, source_content_guard="stale-guard")
    repeated = replace(
        predecessor,
        action_results=(replace(action, canonical_direct_target_evidence=(receipt, stale)),),
    )
    source, before, after, mention, _ = _scenario("Nora")
    with pytest.raises(SourceBoundDependencyError):
        prove_source_bound_dependency(
            complete_original_source=source,
            antecedent_quote=before,
            dependent_quote=after,
            exact_dependent_mention=mention,
            predecessor=repeated,
            repository=repo,
            schema=__import__(
                "tests.runtime.test_whole_source_light_product_p4", fromlist=["SCHEMA"]
            ).SCHEMA,
        )


def test_anaphor_cannot_select_one_of_two_distinct_people(tmp_path):
    repo, predecessor = _completed_predecessor(tmp_path, others=("Eva",))
    _, before, _, _, _ = _scenario("Nora", ("Eva",))
    after = " Mañana debo llamar a esa persona."
    with pytest.raises(SourceBoundDependencyError):
        prove_source_bound_dependency(
            complete_original_source=before + after,
            antecedent_quote=before,
            dependent_quote=after,
            exact_dependent_mention="esa persona",
            predecessor=predecessor,
            repository=repo,
            schema=__import__(
                "tests.runtime.test_whole_source_light_product_p4", fromlist=["SCHEMA"]
            ).SCHEMA,
        )


def test_nm_graph_rejects_cloned_duplicate_receipts(tmp_path):
    from odyssey_core.dependent_group_evidence import prove_canonical_group_handoff
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    receipt = action.canonical_direct_target_evidence[0]
    repeated = replace(
        predecessor,
        action_results=(replace(action, canonical_direct_target_evidence=(receipt, receipt)),),
    )
    graph = ReviewedSourceGraph(
        "Hoy conocí a Nora. Mañana debo llamar a Nora.",
        (
            SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
            SourceGroup(
                1, "tasks", " Mañana debo llamar a Nora.", (GroupDependency(0, "Nora", "Nora"),)
            ),
        ),
    )
    from odyssey_core.dependent_group_evidence import CanonicalGroupEvidenceError

    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=1,
            predecessors={0: repeated},
            repository=repo,
            schema=SCHEMA,
        )


def test_nm_graph_rejects_stale_duplicate_receipt(tmp_path):
    from odyssey_core.dependent_group_evidence import (
        CanonicalGroupEvidenceError,
        prove_canonical_group_handoff,
    )
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    receipt = action.canonical_direct_target_evidence[0]
    stale = replace(receipt, source_content_guard="stale-guard")
    repeated = replace(
        predecessor,
        action_results=(replace(action, canonical_direct_target_evidence=(receipt, stale)),),
    )
    graph = ReviewedSourceGraph(
        "Hoy conocí a Nora. Mañana debo llamar a Nora.",
        (
            SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
            SourceGroup(
                1, "tasks", " Mañana debo llamar a Nora.", (GroupDependency(0, "Nora", "Nora"),)
            ),
        ),
    )
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=1,
            predecessors={0: repeated},
            repository=repo,
            schema=SCHEMA,
        )


@pytest.mark.parametrize(
    "tamper",
    ("action_index", "unit_index", "reference_index", "operation", "materialization"),
)
@pytest.mark.parametrize("graph_mode", (False, True))
def test_forged_duplicate_receipts_never_authorize_a_handoff(tmp_path, tamper, graph_mode):
    """A current matching receipt cannot conceal forged action/unit provenance."""
    from odyssey_core.dependent_group_evidence import (
        CanonicalGroupEvidenceError,
        prove_canonical_group_handoff,
    )
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    good = action.canonical_direct_target_evidence[0]
    bad = good
    units = action.unit_results
    if tamper == "action_index":
        bad = replace(good, action_index=good.action_index + 1)
    elif tamper == "unit_index":
        bad = replace(good, source_unit_index=good.source_unit_index + 4)
    elif tamper == "reference_index":
        bad = replace(good, source_reference_index=87)
    elif tamper == "operation":
        units = tuple(replace(u, operation="UPDATED") for u in units)
    else:
        units = tuple(replace(u, materially_affected=False) for u in units)
    duplicated = replace(
        predecessor,
        action_results=(
            replace(action, unit_results=units, canonical_direct_target_evidence=(good, bad)),
        ),
    )
    if graph_mode:
        graph = ReviewedSourceGraph(
            "Hoy conocí a Nora. Mañana debo llamar a Nora.",
            (
                SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
                SourceGroup(
                    1,
                    "tasks",
                    " Mañana debo llamar a Nora.",
                    (GroupDependency(0, "Nora", "Nora"),),
                ),
            ),
        )
        with pytest.raises(CanonicalGroupEvidenceError):
            prove_canonical_group_handoff(
                graph=graph,
                consumer_index=1,
                predecessors={0: duplicated},
                repository=repo,
                schema=SCHEMA,
            )
    else:
        source, before, after, mention, _ = _scenario("Nora")
        with pytest.raises(SourceBoundDependencyError):
            prove_source_bound_dependency(
                complete_original_source=source,
                antecedent_quote=before,
                dependent_quote=after,
                exact_dependent_mention=mention,
                predecessor=duplicated,
                repository=repo,
                schema=SCHEMA,
            )


def _direct_and_linked_receipts(tmp_path):
    """Write distinct direct and linked proofs for one canonical Person."""
    from types import SimpleNamespace

    from odyssey_core.application import execute_request
    from odyssey_core.request_planning import (
        KnowledgeReference,
        KnowledgeUnit,
        RequestPlan,
        SelectionCriteria,
        WriteAction,
    )
    from tests.runtime.test_p4_fresh_person_task import CLOCK
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, actor, executor, runtime, source, _calls = _physical(tmp_path, "Nora")
    assert runtime.execute_product(source, "e4-two-origins", "main", actor)["status"] == "completed"
    predecessor = executor.person_core_results[0]
    direct = predecessor.action_results[0].canonical_direct_target_evidence[0]
    linked_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Bitácora Atlas", "Bitácora Atlas", "project", (), None),
                        "record",
                        (),
                        (),
                        ("Hoy conocí a {{ref:0}}.",),
                        (KnowledgeReference(1, "person", "Nora"),),
                        force_create=True,
                    ),
                    KnowledgeUnit(
                        SelectionCriteria("Nora", "Nora", "person", (), None),
                        "record",
                        (),
                        (),
                        (),
                        (),
                        reference_lookup_only=True,
                    ),
                )
            ),
        ),
        (),
    )
    backlink_write = execute_request(
        "Hoy conocí a Nora.",
        planner=SimpleNamespace(plan=lambda *_args: linked_plan),
        repository=repo,
        schema=SCHEMA,
        context_index=executor.context_index,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=executor.reasoner,
        authenticated_actor=actor,
        self_binding_repository=executor.bindings,
        actor=actor.stable_user_id,
        now=CLOCK,
        context_limit=10,
        request_id_factory=lambda: "e4-independent-backlink",
    )
    from odyssey_core.application import ApplicationStatus

    assert backlink_write.status is ApplicationStatus.COMPLETED
    second_action = backlink_write.action_results[0]
    assert len(second_action.canonical_reference_evidence) == 1
    linked = second_action.canonical_reference_evidence[0]
    assert linked.stable_note_id == direct.stable_note_id
    assert linked.source_note_id != direct.source_note_id
    second_action = replace(
        second_action,
        action_index=1,
        canonical_reference_evidence=(replace(linked, action_index=1),),
    )
    two_receipts = replace(
        predecessor,
        action_results=(*predecessor.action_results, second_action),
        affected_stable_note_ids=(
            *predecessor.affected_stable_note_ids,
            *backlink_write.affected_stable_note_ids,
        ),
        canonical_reference_evidence=(replace(linked, action_index=1),),
    )
    return repo, direct, two_receipts


def test_real_direct_create_and_independent_backlink_share_one_identity(tmp_path):
    """Two *different* Core writes to the same Person must remain valid handoff proof."""
    from odyssey_core.dependent_group_evidence import prove_canonical_group_handoff
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, direct, two_receipts = _direct_and_linked_receipts(tmp_path)
    whole, before, after, mention, _ = _scenario("Nora")
    handoff = prove_source_bound_dependency(
        complete_original_source=whole,
        antecedent_quote=before,
        dependent_quote=after,
        exact_dependent_mention=mention,
        predecessor=two_receipts,
        repository=repo,
        schema=SCHEMA,
    )
    assert handoff.evidence.stable_note_id == direct.stable_note_id
    graph = ReviewedSourceGraph(
        "Hoy conocí a Nora. Mañana debo llamar a Nora.",
        (
            SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
            SourceGroup(
                1,
                "tasks",
                " Mañana debo llamar a Nora.",
                (GroupDependency(0, "Nora", "Nora"),),
            ),
        ),
    )
    grouped = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=1,
        predecessors={0: two_receipts},
        repository=repo,
        schema=SCHEMA,
    )
    assert grouped.require_all_current(repo, SCHEMA) == (direct.stable_note_id,)


def test_nm_graph_rejects_duplicate_request_level_linked_receipt(tmp_path):
    """A cloned top-level carrier cannot count as another Core write."""
    from odyssey_core.dependent_group_evidence import (
        CanonicalGroupEvidenceError,
        prove_canonical_group_handoff,
    )
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, _direct, predecessor = _direct_and_linked_receipts(tmp_path)
    linked = predecessor.canonical_reference_evidence[0]
    duplicate = replace(predecessor, canonical_reference_evidence=(linked, linked))
    graph = ReviewedSourceGraph(
        "Hoy conocí a Nora. Mañana debo llamar a Nora.",
        (
            SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
            SourceGroup(
                1,
                "tasks",
                " Mañana debo llamar a Nora.",
                (GroupDependency(0, "Nora", "Nora"),),
            ),
        ),
    )
    with pytest.raises(CanonicalGroupEvidenceError):
        prove_canonical_group_handoff(
            graph=graph,
            consumer_index=1,
            predecessors={0: duplicate},
            repository=repo,
            schema=SCHEMA,
        )


@pytest.mark.parametrize(
    "tamper",
    (
        "reference_index",
        "operation",
        "unit_index",
        "action_index",
        "action_reindexed",
        "source_guard",
        "malformed",
    ),
)
@pytest.mark.parametrize("graph_mode", (False, True))
def test_forged_linked_receipt_fails_both_handoffs(tmp_path, tamper, graph_mode):
    """Alter linked provenance in every receipt carrier while Markdown stays current."""
    from odyssey_core.dependent_group_evidence import (
        CanonicalGroupEvidenceError,
        prove_canonical_group_handoff,
    )
    from odyssey_core.dependent_group_graph import GroupDependency, ReviewedSourceGraph, SourceGroup
    from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

    repo, _direct, predecessor = _direct_and_linked_receipts(tmp_path)
    action = predecessor.action_results[1]
    linked = action.canonical_reference_evidence[0]
    units = action.unit_results
    if tamper == "reference_index":
        linked = replace(linked, source_reference_index=87)
    elif tamper == "operation":
        units = tuple(replace(unit, operation="NO_CHANGE") for unit in units)
    elif tamper == "unit_index":
        linked = replace(linked, source_unit_index=1)
    elif tamper == "source_guard":
        linked = replace(linked, source_content_guard="stale-source-guard")
    elif tamper == "malformed":
        linked = None
    else:
        linked = replace(linked, action_index=87)
    action_index = 87 if tamper == "action_reindexed" else action.action_index
    predecessor = replace(
        predecessor,
        action_results=(
            predecessor.action_results[0],
            replace(
                action,
                action_index=action_index,
                unit_results=units,
                canonical_reference_evidence=(linked,),
            ),
        ),
        canonical_reference_evidence=(linked,),
    )
    if graph_mode:
        graph = ReviewedSourceGraph(
            "Hoy conocí a Nora. Mañana debo llamar a Nora.",
            (
                SourceGroup(0, "core", "Hoy conocí a Nora.", ()),
                SourceGroup(
                    1,
                    "tasks",
                    " Mañana debo llamar a Nora.",
                    (GroupDependency(0, "Nora", "Nora"),),
                ),
            ),
        )
        with pytest.raises(CanonicalGroupEvidenceError):
            prove_canonical_group_handoff(
                graph=graph,
                consumer_index=1,
                predecessors={0: predecessor},
                repository=repo,
                schema=SCHEMA,
            )
    else:
        source, before, after, mention, _ = _scenario("Nora")
        with pytest.raises(SourceBoundDependencyError):
            prove_source_bound_dependency(
                complete_original_source=source,
                antecedent_quote=before,
                dependent_quote=after,
                exact_dependent_mention=mention,
                predecessor=predecessor,
                repository=repo,
                schema=SCHEMA,
            )
