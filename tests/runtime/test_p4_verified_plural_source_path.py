"""Independent plural reviewers must agree on all exact source Persons before any write."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_runtime.whole_source_light import WholeSourceLightExecutor

BEFORE = "Hoy he conocido a Ana Prototipo y a Luis Prototipo."
AFTER = " Mañana tengo que llamar a los dos."
SOURCE = BEFORE + AFTER
SCOPE = SimpleNamespace(antecedent=BEFORE, dependent=AFTER, mention="los dos")
SCOPES = [
    {"capability": "core", "depends_on_another_scope": False},
    {"capability": "tasks", "depends_on_another_scope": True},
]
REVIEW = {
    "full_source_quote": SOURCE,
    "antecedent_quote": BEFORE,
    "dependent_quote": AFTER,
    "dependent_mention": "los dos",
    "antecedent_mentions": ["Ana Prototipo", "Luis Prototipo"],
    "all_referents": True,
    "single_personal_task": True,
    "operation_supported": True,
}


def run(monkeypatch, first=None, second=None, *, scoped=SCOPE, routes=SCOPES):
    from odyssey_core.dependent_group_graph import ReviewedSourceGraph

    answers = [
        deepcopy(REVIEW) if first is None else first,
        deepcopy(REVIEW) if second is None else second,
    ]
    calls = []

    def ask(_self, _model, _instructions, payload, _schema, name):
        calls.append(("review", name, payload))
        return answers.pop(0)

    def execute(
        _self,
        source,
        delivery,
        actor,
        *,
        route_scopes,
        preverified_graph,
        preapproved_person_reviews,
        **_,
    ):
        assert (source, delivery, actor) == (SOURCE, "delivery", None)
        assert route_scopes == routes
        assert isinstance(preverified_graph, ReviewedSourceGraph)
        assert preverified_graph.original == SOURCE
        assert preverified_graph.edges == (
            (0, 1, "Ana Prototipo", "los dos"),
            (0, 1, "Luis Prototipo", "los dos"),
        )
        assert preapproved_person_reviews[0] == preapproved_person_reviews[1] == REVIEW
        calls.append(("would_execute",))
        return "SAFE_HANDOFF"

    monkeypatch.setattr(WholeSourceLightExecutor, "_ask", ask)
    monkeypatch.setattr(WholeSourceLightExecutor, "_execute_dependent_graph", execute)
    executor = object.__new__(WholeSourceLightExecutor)
    result = executor._execute_verified_plural_person_scope(
        SOURCE,
        "delivery",
        None,
        scoped,
        delivery_instant=None,
        router_started=0.0,
        route_scopes=routes,
    )
    return result, calls


def test_complete_two_reviewer_source_set_yields_reviewed_not_authorized_graph(monkeypatch):
    result, calls = run(monkeypatch)
    assert result == "SAFE_HANDOFF"
    assert len(calls) == 3
    assert calls[0][1].endswith("review_a_v1")
    assert calls[1][1].endswith("review_b_v1")
    assert "antecedent_mentions" not in calls[0][2]


@pytest.mark.parametrize(
    "mutation",
    [
        {"antecedent_mentions": ["Ana Prototipo"]},
        {"antecedent_mentions": ["Luis Prototipo", "Ana Prototipo"]},
        {"antecedent_mentions": ["Ana Prototipo", "Ana Prototipo"]},
        {"antecedent_mentions": ["Ana Prototipo", "Marta Prototipo"]},
        {"antecedent_mentions": ["Ana Prototipo", "Luis Prototipo", "Marta Prototipo"]},
        {"all_referents": False},
        {"single_personal_task": False},
        {"operation_supported": False},
        {"dependent_quote": " otra consulta."},
    ],
)
def test_one_review_cannot_drop_or_invent_person_to_enable_a_task(monkeypatch, mutation):
    second = {**deepcopy(REVIEW), **mutation}
    result, calls = run(monkeypatch, second=second)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not any(row[0] == "would_execute" for row in calls)


def test_cardinal_requires_complete_number_of_people(monkeypatch):
    both = {**REVIEW, "antecedent_mentions": ["Ana Prototipo"]}
    result, calls = run(monkeypatch, first=both, second=both)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not any(row[0] == "would_execute" for row in calls)


def test_open_nonfinite_reference_does_not_invite_models(monkeypatch):
    scoped = SimpleNamespace(antecedent=BEFORE, dependent=AFTER, mention="algunos")
    result, calls = run(monkeypatch, scoped=scoped)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert calls == []


def test_both_models_omit_third_explicit_person_before_any_core_write(monkeypatch):
    """Even two agreeing models cannot promote an arbitrary two-of-three subset."""
    expanded_before = "Hoy he conocido a Ana Prototipo, a Luis Prototipo y a Marta Prototipo."
    expanded_source = expanded_before + AFTER
    untrusted = {
        **REVIEW,
        "full_source_quote": expanded_source,
        "antecedent_quote": expanded_before,
    }
    calls = []

    def ask(_self, *_args):
        calls.append("review")
        return deepcopy(untrusted)

    def must_not_write(*_args, **_kwargs):
        raise AssertionError("An incomplete cohort reached the Core writer")

    monkeypatch.setattr(WholeSourceLightExecutor, "_ask", ask)
    monkeypatch.setattr(WholeSourceLightExecutor, "_execute_dependent_graph", must_not_write)
    executor = object.__new__(WholeSourceLightExecutor)
    result = executor._execute_verified_plural_person_scope(
        expanded_source,
        "delivery",
        None,
        SimpleNamespace(antecedent=expanded_before, dependent=AFTER, mention="los dos"),
        delivery_instant=None,
        router_started=0.0,
        route_scopes=SCOPES,
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert calls == ["review", "review"]
