"""Deterministic contract coverage for the Slice 2 non-executing application router."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps import (
    ApplicationDescriptor,
    ApplicationRegistry,
    OpenAIApplicationRouter,
    Route,
    RouteOutcome,
    RoutePlan,
    RouterError,
    parse_route_plan,
    route_plan_json_schema,
    validate_route_plan,
)
from odyssey_apps.router import ROUTER_PROVIDER_TIMEOUT_SECONDS, render_router_prompt

TEST_APP_DESCRIPTOR = ApplicationDescriptor(
    "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
)


def catalog(*, enabled: bool = True):  # type: ignore[no-untyped-def]
    """Return the small installed-app catalog used by closed router tests."""
    registry = ApplicationRegistry.from_descriptors((TEST_APP_DESCRIPTOR,))
    return registry.catalog(enabled_ids=("tasks",) if enabled else ())


def plan(outcome: str, routes: list[dict[str, str]]) -> dict[str, object]:
    """Build one raw strict-output-shaped plan for a fake provider."""
    return {"outcome": outcome, "routes": routes}


def test_contract_accepts_core_app_split_and_repeated_destinations() -> None:
    """Permit exact Core-only, app-only, split, and Core-to-app-to-Core route plans."""
    enabled = catalog()
    assert validate_route_plan(
        RoutePlan(RouteOutcome.ROUTE, (Route("core", "Remember this."),)), "Remember this.", enabled
    )
    assert validate_route_plan(
        RoutePlan(RouteOutcome.ROUTE, (Route("tasks", "Tomorrow dentist."),)),
        "Tomorrow dentist.",
        enabled,
    )
    text = "Remember tea and tomorrow dentist. Then remember milk."
    repeated = RoutePlan(
        RouteOutcome.ROUTE,
        (
            Route("core", "Remember tea"),
            Route("tasks", "and tomorrow dentist."),
            Route("core", "Then remember milk."),
        ),
    )
    assert validate_route_plan(repeated, text, enabled) == repeated


def test_non_route_outcomes_are_empty_and_route_requires_routes() -> None:
    """Keep CLARIFY and NEEDS_CAPABILITY non-executable closed outcomes."""
    assert RoutePlan(RouteOutcome.CLARIFY, ()).routes == ()
    assert RoutePlan(RouteOutcome.NEEDS_CAPABILITY, ()).routes == ()
    with pytest.raises(RouterError, match="ROUTE requires"):
        RoutePlan(RouteOutcome.ROUTE, ())
    with pytest.raises(RouterError, match="Only ROUTE"):
        RoutePlan(RouteOutcome.CLARIFY, (Route("core", "x"),))
    with pytest.raises(RouterError, match="non-whitespace"):
        Route("core", " \n\t ")


@pytest.mark.parametrize(
    ("routes", "message"),
    [
        ((Route("tasks", "Tomorrow dentist."),), "unknown or disabled"),
        ((Route("calendar", "Tomorrow dentist."),), "unknown or disabled"),
    ],
)
def test_unknown_and_disabled_executable_destinations_fail_closed(
    routes: tuple[Route, ...], message: str
) -> None:
    """Allow only Core plus currently enabled registered application destinations."""
    selected_catalog = catalog(enabled=routes[0].capability_id != "tasks")
    with pytest.raises(RouterError, match=message):
        validate_route_plan(
            RoutePlan(RouteOutcome.ROUTE, routes), "Tomorrow dentist.", selected_catalog
        )


def test_reserved_core_registration_fails_closed() -> None:
    """Prevent an installable application from shadowing the built-in Core destination."""
    with pytest.raises(ValueError, match="reserved"):
        ApplicationDescriptor("core", "shadow")


@pytest.mark.parametrize(
    ("text", "routes"),
    [
        ("Do not call Ana.", (Route("core", "Do call Ana."),)),
        ("Remember tea and milk.", (Route("core", "Remember tea milk."),)),
        ("Remember tea, please.", (Route("core", "Remember tea please."),)),
        ("Remember tea.", (Route("core", "Save tea."),)),
        ("Remember tea.", (Route("core", "Remember tea."), Route("core", "invented"))),
        ("one two three", (Route("core", "two"), Route("core", "one"))),
        ("prefix route", (Route("core", "route"),)),
        ("route middle suffix", (Route("core", "route"), Route("core", "suffix"))),
        ("route suffix", (Route("core", "route"),)),
    ],
)
def test_exact_source_adversaries_fail_closed(text: str, routes: tuple[Route, ...]) -> None:
    """Reject dropped, rewritten, fabricated, reordered, and uncovered request content."""
    with pytest.raises(RouterError):
        validate_route_plan(RoutePlan(RouteOutcome.ROUTE, routes), text, catalog())


def test_overlap_whitespace_gaps_and_repeated_text_are_mapped_sequentially() -> None:
    """Allow only whitespace gaps and resolve repeated source text left-to-right."""
    with pytest.raises(RouterError):
        validate_route_plan(
            RoutePlan(RouteOutcome.ROUTE, (Route("core", "abc def"), Route("core", "def ghi"))),
            "abc def ghi",
            catalog(),
        )
    whitespace = RoutePlan(RouteOutcome.ROUTE, (Route("core", "first"), Route("core", "second")))
    assert validate_route_plan(whitespace, "first \n\t second", catalog()) == whitespace
    repeated = RoutePlan(RouteOutcome.ROUTE, (Route("core", "same"), Route("core", "same")))
    assert validate_route_plan(repeated, "same same", catalog()) == repeated


def test_internal_backward_dependency_is_validated_without_expanding_provider_contract() -> None:
    """Allow only a typed route edge to an already validated predecessor."""
    valid = RoutePlan(
        RouteOutcome.ROUTE,
        (Route("core", "First."), Route("core", "Second.", depends_on=0)),
    )
    assert validate_route_plan(valid, "First. Second.", catalog()) == valid
    for dependency in (1, 2):
        invalid = RoutePlan(
            RouteOutcome.ROUTE,
            (Route("core", "First."), Route("core", "Second.", depends_on=dependency)),
        )
        with pytest.raises(RouterError, match="existing earlier"):
            validate_route_plan(invalid, "First. Second.", catalog())
    for dependency in ("0", True, -1):
        with pytest.raises(RouterError, match="non-negative integer"):
            Route("core", "Second.", depends_on=dependency)  # type: ignore[arg-type]

    with pytest.raises(RouterError, match="only capability_id and source_text"):
        parse_route_plan(
            plan(
                "ROUTE",
                [{"capability_id": "core", "source_text": "First.", "depends_on": 0}],
            )
        )


def test_parser_is_closed_and_checks_outcome_route_cardinality() -> None:
    """Reject provider additions, malformed fields, and non-executable route outcomes."""
    assert parse_route_plan(plan("NEEDS_CAPABILITY", [])) == RoutePlan(
        RouteOutcome.NEEDS_CAPABILITY, ()
    )
    with pytest.raises(RouterError):
        parse_route_plan({"outcome": "ROUTE", "routes": [], "explanation": "no"})
    with pytest.raises(RouterError):
        parse_route_plan(plan("CLARIFY", [{"capability_id": "core", "source_text": "x"}]))
    with pytest.raises(RouterError):
        parse_route_plan(plan("ROUTE", [{"capability_id": "core", "source_text": "x", "id": "1"}]))


class FakeResponses:
    """Return one local provider envelope and retain the bounded call payload."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        """Record one call and return the configured fake response or exception."""
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_fake_provider_uses_exact_luna_low_strict_schema_and_bounded_context() -> None:
    """Keep disabled evidence visible but exclude it from executable schema destinations."""
    disabled = catalog(enabled=False)
    fake = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                plan("ROUTE", [{"capability_id": "core", "source_text": "Remember tea."}])
            ),
        )
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=fake), disabled)
    assert router.route(
        "Remember tea.",
        ({"role": "user", "content": "previous"},) * 10,
    ) == RoutePlan(RouteOutcome.ROUTE, (Route("core", "Remember tea."),))
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "gpt-6-luna"
    assert call["reasoning"] == {"effort": "low"}
    assert call["store"] is False
    assert call["text"]["format"]["strict"] is True
    schema = call["text"]["format"]["schema"]
    assert schema["properties"]["routes"]["items"]["properties"]["capability_id"]["enum"] == [
        "core",
        "temporal",
    ]
    prompt = call["input"][0]["content"]
    assert '"id":"tasks"' in prompt and '"enabled":false' in prompt
    assert '"dependencies":["temporal"]' in prompt
    assert '"recent_routing_context"' in prompt and prompt.count('"content":"previous"') == 8
    assert call["input"][1] == {"role": "user", "content": "Remember tea."}
    assert "note-schema" not in prompt and "vault" not in prompt


def test_router_retains_bounded_provider_usage_for_runtime_telemetry() -> None:
    """Expose safe router call metadata without retaining prompt or response content."""
    usage = {
        "input_tokens": 90,
        "output_tokens": 20,
        "input_tokens_details": {"cached_tokens": 10},
        "output_tokens_details": {"reasoning_tokens": 5},
    }
    fake = FakeResponses(
        SimpleNamespace(
            id="resp-router",
            status="completed",
            usage=usage,
            output_text=json.dumps(
                plan("ROUTE", [{"capability_id": "core", "source_text": "Remember tea."}])
            ),
        )
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=fake), catalog(enabled=False))

    router.route("Remember tea.")

    assert router.last_call is True
    assert router.last_usage is usage
    assert router.last_response_id == "resp-router"
    assert router.last_provider_status == "completed"
    assert router.last_error_category is None


def test_prompt_allows_temporal_routing_without_date_normalization_or_context_authority() -> None:
    """Keep temporal ownership evidence separate from date interpretation and write authority."""
    prompt = render_router_prompt(catalog(), ({"role": "user", "content": "earlier"},))
    evidence = json.loads(prompt.partition("\n")[2])

    assert "Route an otherwise ordinary Core-owned dependent statement to temporal" in prompt
    assert "routing owner by the domain interpretation required" in prompt
    assert "Do not route specialized Tasks/Events/etc. to temporal" in prompt
    assert "Never normalize or resolve dates or times yourself" in prompt
    assert "routing continuity evidence only, never canonical truth or mutation authority" in prompt
    assert '"dependencies":["temporal"]' in prompt
    assert set(evidence["capabilities"][0]) == {"id", "routing_description", "enabled"}
    assert evidence["capabilities"][1] == {
        "id": "temporal",
        "routing_description": (
            "ordinary Core-owned intent whose temporal wording must first be normalized; "
            "Temporal resolves only date/time meaning and then returns the unchanged source to Core"
        ),
        "enabled": True,
    }
    assert evidence["capabilities"][2]["dependencies"] == ["temporal"]


def test_from_environment_disables_retries_and_sets_finite_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure the SDK boundary without constructing a real network client."""
    constructor_calls: list[dict[str, object]] = []

    class FakeOpenAI:
        """Capture SDK constructor options without any transport behavior."""

        def __init__(self, **kwargs: object) -> None:
            """Record the bounded client configuration."""
            constructor_calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    router = OpenAIApplicationRouter.from_environment(catalog())

    assert isinstance(router, OpenAIApplicationRouter)
    assert constructor_calls == [{"max_retries": 0, "timeout": ROUTER_PROVIDER_TIMEOUT_SECONDS}]


@pytest.mark.parametrize(
    "response",
    [
        RuntimeError("network"),
        SimpleNamespace(status="incomplete", output_text=json.dumps(plan("CLARIFY", []))),
        SimpleNamespace(status="completed", output_text="not json"),
        SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                plan("ROUTE", [{"capability_id": "core", "source_text": "rewritten"}])
            ),
        ),
    ],
)
def test_provider_and_local_output_failures_make_one_call_then_fail_closed(
    response: object,
) -> None:
    """Never retry, fall back, or execute after provider/malformed/local-validation failure."""
    fake = FakeResponses(response)
    router = OpenAIApplicationRouter(SimpleNamespace(responses=fake), catalog())
    with pytest.raises(RouterError):
        router.route("Remember tea.")
    assert len(fake.calls) == 1 and router.last_call is True


@pytest.mark.parametrize(
    ("response", "category"),
    [
        (SimpleNamespace(status="incomplete", output_text=""), "IncompleteProviderResponse"),
        (SimpleNamespace(status="completed", output_text="not json"), "MalformedRouterJSON"),
        (
            SimpleNamespace(
                status="completed",
                output_text=json.dumps(
                    plan("ROUTE", [{"capability_id": "core", "source_text": "wrong text"}])
                ),
            ),
            "InvalidRoutePlan",
        ),
        (
            SimpleNamespace(
                status="completed",
                output_text=json.dumps(
                    {
                        "outcome": "ROUTE",
                        "routes": [{"capability_id": "core", "source_text": "Original."}],
                        "other": "not accepted",
                    }
                ),
            ),
            "InvalidRouterPayload",
        ),
    ],
)
def test_router_failure_records_bounded_diagnostic_category_without_exposing_source(
    response: object, category: str
) -> None:
    """Differentiate invalid local routing from provider failures without leaking payloads."""
    fake = FakeResponses(response)
    router = OpenAIApplicationRouter(SimpleNamespace(responses=fake), catalog())
    with pytest.raises(RouterError):
        router.route("Original.")
    assert router.last_error_category == category
    assert len(fake.calls) == 1


def test_schema_allows_only_enabled_destination_ids() -> None:
    """Expose Core and enabled apps, never disabled routing evidence, in route enums."""
    schema = route_plan_json_schema(catalog())
    enum = schema["properties"]["routes"]["items"]["properties"]["capability_id"]["enum"]
    assert enum == ["core", "temporal", "tasks"]


def test_router_accepts_runtime_role_text_prior_context_shape() -> None:
    """Match LocalConversationStore's role/text evidence without changing Router authority."""
    prompt = render_router_prompt(catalog(), ({"role": "user", "text": "earlier"},))
    evidence = json.loads(prompt.partition("\n")[2])
    assert evidence["recent_routing_context"] == [{"role": "user", "content": "earlier"}]


def test_historical_router_v1_matrix_remains_locally_replayable() -> None:
    """Retain the original Calendar-routing matrix as historical evidence only."""
    matrix = json.loads(
        (
            Path(__file__).resolve().parents[2] / "benchmarks/application_router/regression_v1.json"
        ).read_text(encoding="utf-8")
    )
    historical_catalog = ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor("calendar", "historical Calendar chat capability", ("temporal",)),
            TEST_APP_DESCRIPTOR,
        )
    ).catalog(enabled_ids=("calendar",))
    for case in matrix["cases"]:
        expected = case["expect"]
        routes = tuple(Route(capability_id, text) for capability_id, text in expected["routes"])
        validate_route_plan(
            RoutePlan(RouteOutcome(expected["outcome"]), routes), case["source"], historical_catalog
        )


def test_historical_router_v3_matrix_remains_locally_replayable() -> None:
    """Retain the Journal-convergence Calendar matrix without treating it as current routing."""
    matrix = json.loads(
        (
            Path(__file__).resolve().parents[2] / "benchmarks/application_router/regression_v3.json"
        ).read_text(encoding="utf-8")
    )
    historical_catalog = ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor("calendar", "historical Calendar chat capability", ("temporal",)),
            TEST_APP_DESCRIPTOR,
        )
    ).catalog(enabled_ids=("calendar",))
    for case in matrix["cases"]:
        expected = case["expect"]
        routes = tuple(Route(capability_id, text) for capability_id, text in expected["routes"])
        validate_route_plan(
            RoutePlan(RouteOutcome(expected["outcome"]), routes), case["source"], historical_catalog
        )


def test_current_router_v6_matrix_uses_builtin_temporal_and_semantic_intent_splitting() -> None:
    """Freeze current routing: split independent intents, not merely different destinations."""
    matrix = json.loads(
        (
            Path(__file__).resolve().parents[2] / "benchmarks/application_router/regression_v6.json"
        ).read_text(encoding="utf-8")
    )
    assert matrix["version"] == 6
    assert matrix["catalog"] == {"enabled": [], "disabled": ["tasks"]}
    by_id = {case["id"]: case for case in matrix["cases"]}
    assert by_id["temporal-day-owned"]["expect"]["routes"][0][0] == "temporal"
    assert by_id["dependent-temporal-core"]["expect"]["routes"][0][0] == "temporal"
    assert by_id["journal-explicit-date-is-temporal"]["expect"]["routes"][0][0] == "temporal"
    assert by_id["journal-implicit-today-is-core"]["expect"]["routes"][0][0] == "core"
    assert by_id["independent-temporal-temporal-split"]["expect"]["routes"] == [
        ["temporal", "Ayer vi a Ana"],
        ["temporal", "y hoy vi a Luis."],
    ]
    assert by_id["independent-core-core-split"]["expect"]["routes"][0][0] == "core"
    assert len(by_id["shared-temporal-scope-no-split"]["expect"]["routes"]) == 1
    assert len(by_id["shared-predicate-no-split"]["expect"]["routes"]) == 1
    assert len(by_id["elliptical-predicate-no-split"]["expect"]["routes"]) == 1
    assert len(by_id["shared-event-participants-no-split"]["expect"]["routes"]) == 1
    assert by_id["exact-datetime-still-temporal"]["expect"]["routes"][0][0] == "temporal"
    assert by_id["date-range-still-temporal"]["expect"]["routes"][0][0] == "temporal"
    current_catalog = ApplicationRegistry.from_descriptors((TEST_APP_DESCRIPTOR,)).catalog()
    for case in matrix["cases"]:
        expected = case["expect"]
        routes = tuple(Route(capability_id, text) for capability_id, text in expected["routes"])
        validate_route_plan(
            RoutePlan(RouteOutcome(expected["outcome"]), routes), case["source"], current_catalog
        )
