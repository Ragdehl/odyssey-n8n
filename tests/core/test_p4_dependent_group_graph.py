"""N:M edges remain lexical source evidence, never canonical identity authority."""

from copy import deepcopy

import pytest

from odyssey_core.dependent_group_graph import (
    DependentGroupGraphError,
    verify_dependent_group_graph,
)


def _proof():
    parts = [
        {"capability": "core", "source_quote": "Conocí a Ana. ", "dependencies": []},
        {"capability": "core", "source_quote": "Presenté Luis a Ana. ", "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": "Prepara un resumen para ella. ",
            "dependencies": [
                {"predecessor_index": 0, "mention": "ella", "antecedent_mention": "Ana"}
            ],
        },
        {
            "capability": "tasks",
            "source_quote": "Y manda el documento a ambos.",
            "dependencies": [
                {"predecessor_index": 0, "mention": "ambos", "antecedent_mention": "Ana"},
                {"predecessor_index": 1, "mention": "ambos", "antecedent_mention": "Luis"},
            ],
        },
    ]
    original = "".join(part["source_quote"] for part in parts)
    proposal = {"full_source_quote": original, "groups": parts}
    review = {
        "full_source_quote": original,
        "complete": True,
        "dependency_edges_verified": True,
        "review_reason": "APPROVED",
        "failing_group_index": None,
        "groups": deepcopy(parts),
    }
    return original, proposal, review


def test_nm_reviewed_source_graph_preserves_all_spans_and_parent_edges():
    source, proposal, review = _proof()
    graph = verify_dependent_group_graph(source, proposal, review)
    assert "".join(group.source for group in graph.groups) == source
    assert [group.ordinal for group in graph.groups] == [0, 1, 2, 3]
    assert graph.edges == ((0, 2, "Ana", "ella"), (0, 3, "Ana", "ambos"), (1, 3, "Luis", "ambos"))
    assert all(not group.dependencies for group in graph.groups[:2])


@pytest.mark.parametrize(
    "mutation",
    [
        "review_missing",
        "review_mismatched",
        "missing_quote",
        "duplicate_quote",
        "forward_edge",
        "self_edge",
        "wrong_parent",
        "missing_mention",
        "duplicate_mention",
        "duplicate_parent",
        "unknown_field",
        "bool_parent",
        "no_edge",
        "unsupported_cap",
    ],
)
def test_nm_group_graph_fails_closed_on_unverified_edge_or_source(mutation):
    source, proposal, review = _proof()
    if mutation == "review_missing":
        review["dependency_edges_verified"] = False
    elif mutation == "review_mismatched":
        review["groups"][3]["dependencies"][1]["mention"] = "documento"
    elif mutation == "missing_quote":
        proposal["groups"][2]["source_quote"] = "Prepara un resumen para ella."
    elif mutation == "duplicate_quote":
        proposal["groups"][2]["source_quote"] += " "
    elif mutation == "forward_edge":
        proposal["groups"][2]["dependencies"][0]["predecessor_index"] = 3
    elif mutation == "self_edge":
        proposal["groups"][2]["dependencies"][0]["predecessor_index"] = 2
    elif mutation == "wrong_parent":
        proposal["groups"][2]["dependencies"][0]["predecessor_index"] = -1
    elif mutation == "missing_mention":
        proposal["groups"][2]["dependencies"][0]["mention"] = "desconocido"
    elif mutation == "duplicate_mention":
        proposal["groups"][2]["source_quote"] = "Prepara ella un resumen para ella. "
    elif mutation == "duplicate_parent":
        proposal["groups"][3]["dependencies"][1]["predecessor_index"] = 0
    elif mutation == "unknown_field":
        proposal["groups"][1]["id"] = "fabricated-id"
    elif mutation == "bool_parent":
        proposal["groups"][3]["dependencies"][1]["predecessor_index"] = True
    elif mutation == "no_edge":
        for part in proposal["groups"]:
            part["dependencies"] = []
    elif mutation == "unsupported_cap":
        proposal["groups"][2]["capability"] = "unregistered_app"
    if mutation not in {"review_missing", "review_mismatched"}:
        review["groups"] = deepcopy(proposal["groups"])
    with pytest.raises(DependentGroupGraphError):
        verify_dependent_group_graph(source, proposal, review)


def test_nm_two_distinct_reference_occurrences_may_share_one_predecessor():
    groups = [
        {"capability": "core", "source_quote": "Revisé Alfa y Beta. ", "dependencies": []},
        {
            "capability": "tasks",
            "source_quote": "Organiza ambas tareas.",
            "dependencies": [
                {"predecessor_index": 0, "mention": "ambas tareas", "antecedent_mention": "Alfa"},
                {"predecessor_index": 0, "mention": "ambas tareas", "antecedent_mention": "Beta"},
            ],
        },
    ]
    full = "".join(group["source_quote"] for group in groups)
    graph = verify_dependent_group_graph(
        full,
        {"full_source_quote": full, "groups": groups},
        {
            "full_source_quote": full,
            "complete": True,
            "dependency_edges_verified": True,
            "review_reason": "APPROVED",
            "failing_group_index": None,
            "groups": deepcopy(groups),
        },
    )
    assert graph.edges == ((0, 1, "Alfa", "ambas tareas"), (0, 1, "Beta", "ambas tareas"))
    groups[1]["dependencies"].append(deepcopy(groups[1]["dependencies"][0]))
    with pytest.raises(DependentGroupGraphError):
        verify_dependent_group_graph(
            full,
            {"full_source_quote": full, "groups": groups},
            {
                "full_source_quote": full,
                "complete": True,
                "dependency_edges_verified": True,
                "review_reason": "APPROVED",
                "failing_group_index": None,
                "groups": deepcopy(groups),
            },
        )


def test_nm_reviewed_graph_never_exposes_or_guesses_a_canonical_id():
    source, proposal, review = _proof()
    graph = verify_dependent_group_graph(source, proposal, review)
    assert not hasattr(graph, "stable_note_ids")
    assert not hasattr(graph.groups[2].dependencies[0], "target_id")


@pytest.mark.parametrize(
    "reason,index",
    [
        ("SOURCE_COVERAGE", None),
        ("GROUP_CLASSIFICATION", 1),
        ("GROUP_ATOMICITY", 3),
        ("DEPENDENCY_AMBIGUOUS", 2),
        ("DEPENDENCY_UNGROUNDED", 3),
        ("DEPENDENCY_MISSING", 3),
        ("OTHER", None),
    ],
)
def test_rejection_reason_is_bounded_diagnostic_and_never_graph_approval(reason, index):
    from odyssey_core.dependent_group_graph import classify_dependent_group_review_rejection

    source, proposal, _ = _proof()
    review = {
        "full_source_quote": source,
        "complete": False,
        "dependency_edges_verified": False,
        "review_reason": reason,
        "failing_group_index": index,
        "groups": [],
    }
    assert classify_dependent_group_review_rejection(source, proposal, review) == (reason, index)
    with pytest.raises(DependentGroupGraphError):
        verify_dependent_group_graph(source, proposal, review)


@pytest.mark.parametrize(
    "change",
    [
        "false_approved",
        "invalid_reason",
        "group_index_outside",
        "bool_index",
        "rejected_with_groups",
        "source_changed",
        "no_veto",
        "extra_identity",
    ],
)
def test_rejection_cannot_upgrade_a_result_or_smuggle_identity(change):
    from odyssey_core.dependent_group_graph import classify_dependent_group_review_rejection

    source, proposal, _ = _proof()
    review = {
        "full_source_quote": source,
        "complete": False,
        "dependency_edges_verified": False,
        "review_reason": "DEPENDENCY_AMBIGUOUS",
        "failing_group_index": 2,
        "groups": [],
    }
    if change == "false_approved":
        review["review_reason"] = "APPROVED"
    elif change == "invalid_reason":
        review["review_reason"] = "ACCEPT_AND_WRITE"
    elif change == "group_index_outside":
        review["failing_group_index"] = 100
    elif change == "bool_index":
        review["failing_group_index"] = True
    elif change == "rejected_with_groups":
        review["groups"] = proposal["groups"]
    elif change == "source_changed":
        review["full_source_quote"] = "other"
    elif change == "no_veto":
        review["complete"] = True
        review["dependency_edges_verified"] = True
    elif change == "extra_identity":
        review["note_id"] = "untrusted"
    with pytest.raises(DependentGroupGraphError):
        classify_dependent_group_review_rejection(source, proposal, review)
