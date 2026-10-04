"""Provider-free freeze for the current Router -> Temporal -> Core boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry, Route, RouteOutcome, RoutePlan
from odyssey_apps.router import render_router_prompt, route_plan_json_schema, validate_route_plan
from odyssey_core.temporal_interpretation import (
    TemporalInterpreterError,
    parse_temporal_interpretation,
    render_temporal_prompt,
    temporal_interpretation_json_schema,
)
from odyssey_core.temporal_resolution import TemporalResolutionKind

ROOT = Path(__file__).resolve().parents[2]
ROUTER_MATRIX = ROOT / "benchmarks/application_router/regression_v6.json"
TEMPORAL_MATRIX = ROOT / "benchmarks/temporal_interpreter/regression_v1.json"
ROUTER_MATRIX_SHA256 = "cdc2b55c54f5e690c82e33bf526ed7191fe5aa866ad86a1b7ee501fdd319ff8f"
TEMPORAL_MATRIX_SHA256 = "245960c46257e348f25e99c38166b93c06d5ee82512567e84ab44338c728b027"
ROUTER_PROMPT_SHA256 = "b14b1fd61c09f6fb27ab07d53640491a17eca9863443b5958ff5769c4e3069e0"
ROUTER_SCHEMA_SHA256 = "8a8b61ede7cecdc1a5b278385fcaa74e7a82b0c3f7f42192ae0c042e60845700"
TEMPORAL_PROMPT_SHA256 = "f8dba1dfecc6c3001b7de75c08770babbaec8d2c8f5bbf9fc2bf00320c02b406"
TEMPORAL_SCHEMA_SHA256 = "f436355ed01111629c8fd47695384c2c4ec6f2004a5660c2d2b813d933fd72a0"


def _catalog():  # type: ignore[no-untyped-def]
    return ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor(
                "tasks",
                "task lifecycle, due dates, completion and obligations",
                ("temporal",),
            ),
        )
    ).catalog()


def _sha_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_current_router_v6_supersedes_only_the_old_multi_intent_oracle_and_adds_split_sentinels() -> (
    None
):
    v5 = json.loads((ROOT / "benchmarks/application_router/regression_v5.json").read_text())
    v6 = json.loads(ROUTER_MATRIX.read_text())

    assert hashlib.sha256(ROUTER_MATRIX.read_bytes()).hexdigest() == ROUTER_MATRIX_SHA256
    assert v6["version"] == 6
    assert v6["catalog"] == v5["catalog"]
    assert v6["route_source_comparison"] == v5["route_source_comparison"]

    old_by_id = {case["id"]: case for case in v5["cases"]}
    new_by_id = {case["id"]: case for case in v6["cases"]}
    unchanged_ids = set(old_by_id) - {"multiple-exact-dates-one-core-source"}
    for case_id in unchanged_ids:
        assert new_by_id[case_id] == old_by_id[case_id]

    assert new_by_id["independent-temporal-temporal-split"]["expect"]["routes"] == [
        ["temporal", "Ayer vi a Ana"],
        ["temporal", "y hoy vi a Luis."],
    ]
    assert new_by_id["independent-core-core-split"]["expect"]["routes"] == [
        ["core", "Marta vive en Lyon."],
        ["core", "Luis vive en París."],
    ]
    for case_id in (
        "shared-temporal-scope-no-split",
        "shared-predicate-no-split",
        "elliptical-predicate-no-split",
        "shared-event-participants-no-split",
    ):
        assert len(new_by_id[case_id]["expect"]["routes"]) == 1

    catalog = _catalog()
    for case in v6["cases"]:
        expected = case["expect"]
        routes = tuple(Route(capability_id, text) for capability_id, text in expected["routes"])
        validate_route_plan(
            RoutePlan(RouteOutcome(expected["outcome"]), routes), case["source"], catalog
        )


def test_temporal_v1_matrix_is_closed_and_locally_valid() -> None:
    matrix = json.loads(TEMPORAL_MATRIX.read_text())
    assert hashlib.sha256(TEMPORAL_MATRIX.read_bytes()).hexdigest() == TEMPORAL_MATRIX_SHA256
    assert matrix["version"] == 1
    assert [case["id"] for case in matrix["cases"]] == [
        "today-day-owned",
        "tomorrow-entity-owned",
        "multiple-exact-dates",
        "exact-datetime",
        "date-range",
        "unresolved",
    ]

    context = matrix["current_context"]
    for case in matrix["cases"]:
        parsed = parse_temporal_interpretation(
            case["expect"], case["source"], timezone=context["timezone"]
        )
        outcome = case["core_outcome"]
        if outcome == "SUPPORTED":
            evidence = parsed.core_domain_interpretation()
            assert evidence.source_text == case["source"]
            assert len(evidence.evidence) == len(parsed.mentions)
        elif outcome == "TEMPORAL_VALUE_REQUIRES_DOMAIN_OWNER":
            assert TemporalResolutionKind.DATE_RANGE in parsed.kinds()
            try:
                parsed.core_domain_interpretation()
            except TemporalInterpreterError:
                pass
            else:  # pragma: no cover - explicit safety sentinel
                raise AssertionError("unsupported Temporal shape reached Core")
        elif outcome == "TEMPORAL_UNRESOLVED":
            assert TemporalResolutionKind.UNSPECIFIED in parsed.kinds()
        else:  # pragma: no cover - closed frozen oracle
            raise AssertionError(f"unknown frozen outcome: {outcome}")


def test_current_router_and_temporal_model_contracts_are_hash_pinned() -> None:
    catalog = _catalog()
    temporal_matrix = json.loads(TEMPORAL_MATRIX.read_text())
    context = temporal_matrix["current_context"]

    assert (
        hashlib.sha256(render_router_prompt(catalog, ()).encode()).hexdigest()
        == ROUTER_PROMPT_SHA256
    )
    assert _sha_json(route_plan_json_schema(catalog)) == ROUTER_SCHEMA_SHA256
    assert (
        hashlib.sha256(render_temporal_prompt(context).encode()).hexdigest()
        == TEMPORAL_PROMPT_SHA256
    )
    assert _sha_json(temporal_interpretation_json_schema()) == TEMPORAL_SCHEMA_SHA256


def test_current_contract_keeps_calendar_out_and_temporal_bounded() -> None:
    prompt = render_router_prompt(_catalog(), ())
    temporal_prompt = render_temporal_prompt(
        {"date": "2026-10-04", "time": "10:00:00", "timezone": "Europe/Paris"}
    )

    assert '"id":"calendar"' not in prompt
    assert '"id":"temporal"' in prompt
    assert "its exact text standing alone preserves the same user meaning" in prompt
    assert "check dependencies in both directions" in prompt
    assert "surface resemblance" in prompt
    assert "exact clock time" in prompt
    assert "Never normalize or resolve dates or times yourself" in prompt
    assert "Never classify the user's domain" in temporal_prompt
    assert "every material temporal mention" in temporal_prompt
    assert "choose a target" in temporal_prompt
    assert "emit a mutation" in temporal_prompt
