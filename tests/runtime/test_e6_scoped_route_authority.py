"""E6.1: scoped app and Core routes share exact source/actor/history checks."""

from types import SimpleNamespace

import pytest

from odyssey_apps.router import Route
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.scoped_route_authority import (
    ScopedRouteAuthority,
    missing_inherited_temporal_spans,
)

ACTOR = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
OTHER = AuthenticatedActorContext("22222222-2222-4222-8222-222222222222")


def _scope(capability="tasks"):
    original = "Today: Call Ana. Tomorrow: Book a room."
    source = "Call Ana."
    start = original.index(source)
    scoped = SimpleNamespace(
        route=Route(capability, source),
        context=SimpleNamespace(source=source),
        original_start=start,
        original_end=start + len(source),
    )
    prior = ({"role": "user", "content": "Remember Ana"},)
    return ScopedRouteAuthority(original, {"route-1": (0, scoped)}, ACTOR, prior), prior


@pytest.mark.parametrize("capability", ["tasks", "events", "core", "temporal", "projects"])
def test_same_scope_contract_for_existing_and_future_apps(capability):
    authority, prior = _scope(capability)
    ordinal, scoped = authority.verify(
        source="Call Ana.",
        locator="route-1",
        capability=capability,
        actor=ACTOR,
        conversation=list(prior),
    )
    assert (ordinal, scoped.route.capability_id) == (0, capability)


@pytest.mark.parametrize(
    "change,bad",
    [
        ("source", "Call Ana"),
        ("source", "Book a room."),
        ("locator", "route-unknown"),
        ("capability", "events"),
        ("actor", OTHER),
        ("actor", None),
        ("conversation", ()),
        ("conversation", ({"role": "user", "content": "Different"},)),
        ("conversation", "Not a sequence of turns"),
    ],
)
def test_source_actor_and_conversation_substitution_is_rejected(change, bad):
    authority, prior = _scope()
    kwargs = dict(
        source="Call Ana.", locator="route-1", capability="tasks", actor=ACTOR, conversation=prior
    )
    kwargs[change] = bad
    with pytest.raises(ValueError):
        authority.verify(**kwargs)


@pytest.mark.parametrize("changed", ["original_start", "original_end", "context", "route"])
def test_compiler_scopes_are_source_checked_again(changed):
    authority, prior = _scope()
    original = authority.scopes["route-1"][1]
    updates = dict(
        route=original.route,
        context=original.context,
        original_start=original.original_start,
        original_end=original.original_end,
    )
    updates[changed] = {
        "original_start": 0,
        "original_end": 11,
        "context": SimpleNamespace(source="Call Eli."),
        "route": Route("tasks", "Call Eli."),
    }[changed]
    altered = ScopedRouteAuthority(
        authority.original_source,
        {"route-1": (0, SimpleNamespace(**updates))},
        ACTOR,
        prior,
    )
    with pytest.raises(ValueError):
        altered.verify(
            source="Call Ana.",
            locator="route-1",
            capability="tasks",
            actor=ACTOR,
            conversation=prior,
        )


def test_temporal_proof_coverage_is_shared_not_app_specific():
    def role(kind, start, end):
        return SimpleNamespace(role=kind, original_start=start, original_end=end)

    context = SimpleNamespace(
        source_provenance=(
            role("date", 0, 8),
            role("time", 9, 14),
            role("subject", 0, 8),
            role("date", 0, 8),
        )
    )
    assert missing_inherited_temporal_spans(context, ()) == {(0, 8), (9, 14)}
    known = [SimpleNamespace(original_start=0, original_end=8)]
    assert missing_inherited_temporal_spans(context, known) == {(9, 14)}
    known.append(SimpleNamespace(original_start=9, original_end=14))
    assert not missing_inherited_temporal_spans(context, known)
