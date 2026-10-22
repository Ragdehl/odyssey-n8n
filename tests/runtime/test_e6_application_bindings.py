"""E6.1: one closed executor-binding contract for real and future applications."""

from __future__ import annotations

import pytest

from odyssey_apps import (
    ApplicationDescriptor,
    ApplicationRegistry,
    Route,
    RouteOutcome,
    RoutePlan,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_runtime.application_bindings import bind_registered_executors
from odyssey_runtime.routing import execute_routed_request


def catalog(*enabled: str):
    registry = ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor("tasks", "task lifecycle", ("core",)),
            ApplicationDescriptor("events", "event lifecycle", ("temporal",)),
            ApplicationDescriptor("projects", "future fixture lifecycle", ("core",)),
        )
    )
    return registry.catalog(enabled_ids=enabled)


def test_tasks_events_and_future_app_bind_from_one_closed_catalog():
    calls = []

    def handler(name):
        def execute(source, locator, _actor=None, _prior=()):
            calls.append((name, source, locator))
            return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), ())

        return execute

    tasks, events, projects = handler("tasks"), handler("events"), handler("projects")
    bound = bind_registered_executors(
        catalog("tasks", "events", "projects"),
        {"tasks": tasks, "events": events, "projects": projects},
        require_enabled=True,
    )
    assert set(bound) == {"tasks", "events", "projects"}

    source = "Project audit."
    result = execute_routed_request(
        user_request=source,
        outer_request_id="e6-future-app",
        router=type(
            "Router",
            (),
            {
                "route": lambda self, _source, _prior=(): RoutePlan(
                    RouteOutcome.ROUTE, (Route("projects", source),)
                )
            },
        )(),
        catalog=catalog("tasks", "events", "projects"),
        core_execute=lambda *_args, **_kwargs: pytest.fail("Not Core"),
        application_executors=bound,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(calls) == 1
    assert calls[0][:2] == ("projects", source)
    assert calls[0][2].startswith("route-")


def test_disabled_capability_never_becomes_executable_despite_trusted_callable():
    called = []
    bound = bind_registered_executors(
        catalog("tasks"),
        {
            "tasks": lambda *_: None,
            "events": lambda *_: called.append("events"),
            "projects": lambda *_: called.append("projects"),
        },
        require_enabled=True,
    )
    assert set(bound) == {"tasks"}
    assert called == []


@pytest.mark.parametrize("bad_id", ("unknown", "core", "temporal", ""))
def test_unknown_or_reserved_executors_fail_before_dispatch(bad_id):
    with pytest.raises(ValueError, match="unregistered"):
        bind_registered_executors(catalog("tasks"), {bad_id: lambda *_: None})


def test_invalid_callable_and_invalid_catalog_are_rejected():
    with pytest.raises(ValueError, match="not callable"):
        bind_registered_executors(catalog("tasks"), {"tasks": "untrusted"})
    with pytest.raises(ValueError, match="catalog"):
        bind_registered_executors(object(), {"tasks": lambda *_: None})


def test_missing_enabled_executor_is_a_closed_preflight_error_when_required():
    with pytest.raises(ValueError, match="unavailable"):
        bind_registered_executors(
            catalog("tasks", "events"), {"tasks": lambda *_: None}, require_enabled=True
        )


def test_optional_missing_app_preserves_existing_runtime_safe_failure():
    """The scoped dispatcher may omit a handler; the router returns a failed route."""
    bound = bind_registered_executors(catalog("events"), {"events": None})
    assert bound == {}
    source = "Cancel event."
    result = execute_routed_request(
        user_request=source,
        outer_request_id="e6-missing-app",
        router=type(
            "Router",
            (),
            {
                "route": lambda self, _source, _prior=(): RoutePlan(
                    RouteOutcome.ROUTE, (Route("events", source),)
                )
            },
        )(),
        catalog=catalog("events"),
        core_execute=lambda *_args, **_kwargs: pytest.fail("Not Core"),
        application_executors=bound,
    )
    assert result.status is ApplicationStatus.FAILED
    assert result.execution_flow["routes"][0]["status"] == "failed"


def test_empty_registration_keeps_core_only_routes_unmodified():
    empty = ApplicationRegistry().catalog()
    assert bind_registered_executors(empty, {}) == {}
    # Explicitly refuse phantom optional app keys; the dispatcher is
    # responsible for offering only the entries in its validated catalog.
    with pytest.raises(ValueError, match="unregistered"):
        bind_registered_executors(empty, {"events": None})
