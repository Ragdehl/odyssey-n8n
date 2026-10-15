"""Operational stages provide versioned UI metadata without exposing source data."""

from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_core.stage_presentation import StageView, stage_view_for
from odyssey_runtime.serialization import operational_to_response


def test_known_stage_name_preserves_legacy_title_and_category():
    view = stage_view_for("candidate.temporal_interpretation")
    assert view == StageView(1, "Temporal", "temporal")
    assert stage_view_for("planner").label == "Planner"
    assert stage_view_for("action.write").icon == "core"


def test_future_app_without_any_ui_registry_change_is_safe_and_readable():
    view = stage_view_for("events.classify_occurrence")
    assert view.version == 1
    assert view.label == "events · classify occurrence"
    assert view.icon == "result"
    assert stage_view_for("unsafe user text: private info").label == "Etapa"
    assert stage_view_for("x" * 120).label == "Etapa"


def test_operational_serializer_preserves_observed_stage_count_order_and_receipts():
    source = OperationalEvidence(
        total_duration_ms=50,
        stages=(
            OperationalStage("candidate.temporal_interpretation", OperationalOutcome.COMPLETED, 15),
            OperationalStage(
                "events.classify_occurrence",
                OperationalOutcome.FAILED,
                35,
                error_category="ProviderError",
            ),
        ),
    )
    payload = operational_to_response(source)
    assert payload["total_duration_ms"] == 50
    assert [item["name"] for item in payload["stages"]] == [
        "candidate.temporal_interpretation",
        "events.classify_occurrence",
    ]
    assert payload["stages"][0]["stage_view"] == {
        "version": 1,
        "label": "Temporal",
        "icon": "temporal",
    }
    assert payload["stages"][1]["stage_view"] == {
        "version": 1,
        "label": "events · classify occurrence",
        "icon": "result",
    }
    assert payload["stages"][1]["error_category"] == "ProviderError"
    assert payload["stages"][1]["provider_calls"] == []
