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


def test_repeated_current_receipt_for_one_identity_is_not_ambiguity(tmp_path):
    repo, predecessor = _completed_predecessor(tmp_path)
    action = predecessor.action_results[0]
    receipt = action.canonical_direct_target_evidence[0]
    repeated = replace(
        predecessor,
        action_results=(replace(action, canonical_direct_target_evidence=(receipt, receipt)),),
    )
    source, before, after, mention, _ = _scenario("Nora")
    handoff = prove_source_bound_dependency(
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
    assert handoff.evidence.stable_note_id == receipt.stable_note_id


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


def test_nm_graph_accepts_duplicate_current_receipts_for_one_person(tmp_path):
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
    handoff = prove_canonical_group_handoff(
        graph=graph, consumer_index=1, predecessors={0: repeated}, repository=repo, schema=SCHEMA
    )
    assert handoff.require_all_current(repo, SCHEMA) == (receipt.stable_note_id,)


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
