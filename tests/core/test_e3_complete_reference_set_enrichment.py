"""Core plan enrichment is reusable beyond Tasks; no app may select Note IDs."""

import pytest

from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.write_plan_enrichment import (
    CoreLinkFactSpec,
    ensure_complete_core_reference_set,
)


def _plan(refs=(), helpers=()):
    primary = KnowledgeUnit(
        SelectionCriteria("Reunión", "Reunión", "event", (), None),
        "record",
        (),
        (),
        ("Reunión de proyecto.",),
        refs,
    )
    return RequestPlan((WriteAction((primary, *helpers)),), ())


def _lookup(name, note_type):
    return KnowledgeUnit(
        SelectionCriteria(name, name, note_type, (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )


def _links():
    return (
        CoreLinkFactSpec("Participante", "ellos", "person", "person", "Amalia Ruiz"),
        CoreLinkFactSpec("Proyecto", "proyecto citado", "project", "project", "Odyssey"),
    )


def test_core_enrichment_handles_unrelated_types_and_mentions():
    result = ensure_complete_core_reference_set(_plan(), _links())
    action = result.actions[0]
    assert len(action.units) == 3
    assert [(r.role, r.mention) for r in action.units[0].references] == [
        ("person", "ellos"),
        ("project", "proyecto citado"),
    ]
    assert [(action.units[r.target_index].target.entity) for r in action.units[0].references] == [
        "Amalia Ruiz",
        "Odyssey",
    ]


def test_existing_canonical_is_preserved_and_only_missing_is_added():
    existing = KnowledgeReference(1, "identity", "ellos")
    result = ensure_complete_core_reference_set(
        _plan((existing,), (_lookup("Amalia Ruiz", "person"),)),
        _links(),
        compatible_roles=("identity",),
    )
    assert len(result.actions[0].units) == 3
    assert len(result.actions[0].units[0].references) == 2


@pytest.mark.parametrize("existing", ["wrong-name", "wrong-type", "duplicate"])
def test_core_refuses_unsafe_planner_refs(existing):
    helpers = (_lookup("Marta Ruiz", "person"),)
    refs = (KnowledgeReference(1, "person", "ellos"),)
    if existing == "wrong-type":
        helpers = (_lookup("Amalia Ruiz", "project"),)
    if existing == "duplicate":
        helpers = (_lookup("Amalia Ruiz", "person"),)
        refs = (KnowledgeReference(1, "person", "ellos"),) * 2
    with pytest.raises(RequestPlanningError):
        ensure_complete_core_reference_set(
            _plan(refs, helpers),
            _links(),
            compatible_roles=("identity",),
        )


def test_core_rejects_duplicate_requested_members_and_missing_receipts():
    with pytest.raises(RequestPlanningError, match="Duplicate"):
        ensure_complete_core_reference_set(_plan(), (_links()[0], _links()[0]))
    with pytest.raises(RequestPlanningError, match="require Core receipts"):
        ensure_complete_core_reference_set(
            _plan(),
            (CoreLinkFactSpec("Actor", "ambos", "person", "person"),),
        )
