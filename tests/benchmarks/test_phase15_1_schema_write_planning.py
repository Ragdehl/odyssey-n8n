"""Offline contract tests for the frozen Phase 15.1 benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.phase15_1_schema_write_planning import benchmark as benchmark_module
from benchmarks.phase15_1_schema_write_planning import run_benchmark
from benchmarks.phase15_1_schema_write_planning.benchmark import (
    BenchmarkContractError,
    load_cases,
    production_request,
    schema_for,
)
from benchmarks.phase15_1_schema_write_planning.evaluate import evaluate


def _unit(
    query: str,
    *,
    note_type: str | None,
    intent: str,
    properties: list[dict],
    facts: list[str],
    filters: list[dict] | None = None,
) -> dict:
    """Build one valid raw Phase 15.1 write unit for deterministic oracle tests."""
    return {
        "target": {"query": query, "type": note_type, "filters": filters or []},
        "intent": intent,
        "properties": properties,
        "facts": facts,
        "references": [],
    }


def _output(*actions: dict) -> dict:
    """Build one complete locally valid RequestPlan fixture."""
    return {"actions": list(actions), "limitations": []}


def _write(unit: dict) -> dict:
    """Wrap one unit in the non-executing write action shape."""
    return {"kind": "write", "units": [unit]}


def test_frozen_cases_cover_required_semantics_once_and_fix_context() -> None:
    """Keep the compact benchmark at its approved fifteen independent Sol calls."""
    cases = load_cases()
    assert [case["id"] for case in cases] == [
        "P01",
        "P02",
        "P03",
        "P04",
        "P05",
        "P06",
        "P07",
        "P08",
        "P09",
        "P10",
        "P11",
        "P12",
        "R01",
        "R02",
        "R03",
    ]
    assert cases[4]["request"].endswith("ahora vive en Lyon")
    assert cases[6]["current_context"] == {
        "date": "2026-08-22",
        "time": "09:30",
        "timezone": "Europe/Paris",
    }


def test_production_request_uses_exact_production_prompt_and_structured_output() -> None:
    """Prevent the benchmark from silently testing a different provider contract."""
    canonical = next(case for case in load_cases() if case["id"] == "P01")
    request, _schema = production_request(canonical)
    assert request["model"] == "gpt-5.6-sol"
    assert request["reasoning"] == {"effort": "low"} and request["store"] is False
    assert request["text"]["format"]["name"] == "odyssey_request_plan"
    assert request["text"]["format"]["strict"] is True
    assert "Planner writable type/property capabilities" in request["input"][0]["content"]


def test_schema_guard_rejects_unapproved_future_v2_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep the frozen harness fail-closed after the one explicitly approved v2 schema evolution."""
    original_root = benchmark_module.ROOT
    canonical_path = original_root / "config/note-schema.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["metadata_fields"][0]["description"] += " Future drift sentinel."
    copied_path = tmp_path / "config/note-schema.json"
    copied_path.parent.mkdir(parents=True)
    copied_path.write_text(json.dumps(canonical, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    monkeypatch.setattr(benchmark_module, "ROOT", tmp_path)
    case = next(case for case in load_cases() if case["id"] == "P01")
    with pytest.raises(BenchmarkContractError, match="drifted"):
        benchmark_module.schema_for(case)


def test_synthetic_snapshot_supports_dynamic_car_filter_and_mutation() -> None:
    """Use the frozen car schema extension without production knowledge of its names."""
    case = next(case for case in load_cases() if case["id"] == "P12")
    schema = schema_for(case)
    payload = _output(
        _write(
            _unit(
                "coche con matrícula 1234 ABC",
                note_type="car",
                intent="amend",
                filters=[{"field": "registration_number", "op": "eq", "value": "1234 ABC"}],
                properties=[{"field": "registration_number", "op": "set", "value": "5678 DEF"}],
                facts=[],
            )
        )
    )
    assert evaluate("P12", payload, schema) == ("PASS", [])


def test_oracle_rejects_duplicate_structured_date_and_extra_write_lookup() -> None:
    """Preserve the high-risk target/mutation and no-extra-retrieval boundaries."""
    schema = schema_for(next(case for case in load_cases() if case["id"] == "P01"))
    duplicate = _output(
        _write(
            _unit(
                "Marta",
                note_type="person",
                intent="record",
                properties=[{"field": "birth_date", "op": "set", "value": "1990-05-03"}],
                facts=["Marta nació en mayo de 1990."],
            )
        )
    )
    assert evaluate("P01", duplicate, schema)[0] == "FAIL"
    extra_retrieval = _output(
        {
            "kind": "retrieve",
            "plan": {"query": "tienda de la esquina", "type": None, "filters": []},
        },
        _write(
            _unit(
                "tienda de la esquina",
                note_type=None,
                intent="amend",
                properties=[],
                facts=["Cierra a las 20:30."],
            )
        ),
    )
    assert evaluate("R01", extra_retrieval, schema)[0] == "FAIL"


def test_oracle_requires_semantic_content_for_reviewed_cases() -> None:
    """Ensure reviewed benchmark sentinels preserve the user's requested knowledge."""
    schema = schema_for(next(case for case in load_cases() if case["id"] == "P05"))
    p05 = _output(
        _write(
            _unit(
                "amiga de Marta nacida en 1990",
                note_type="person",
                intent="amend",
                properties=[],
                facts=["Ahora vive en Lyon."],
                filters=[
                    {"field": "birth_date", "op": "gte", "value": "1990-01-01"},
                    {"field": "birth_date", "op": "lt", "value": "1991-01-01"},
                ],
            )
        )
    )
    assert evaluate("P05", p05, schema) == ("PASS", [])
    missing_filter = _output(
        _write(
            _unit(
                "amiga de Marta nacida en 1990",
                note_type="person",
                intent="amend",
                properties=[],
                facts=["Ahora vive en Lyon."],
            )
        )
    )
    assert evaluate("P05", missing_filter, schema) == ("FAIL", ["incorrect_target_filters"])
    missing_mutation = _output(
        _write(_unit("amiga de Marta", note_type="person", intent="amend", properties=[], facts=[]))
    )
    assert evaluate("P05", missing_mutation, schema)[0] == "INVALID"


def test_oracle_accepts_current_reflection_as_journal_entry() -> None:
    """Treat a current personal reflection as a dated journal entry when represented fully."""
    schema = schema_for(next(case for case in load_cases() if case["id"] == "P09"))
    payload = _output(
        _write(
            _unit(
                "entrada de diario de hoy",
                note_type="journal_entry",
                intent="record",
                properties=[{"field": "entry_date", "op": "set", "value": "2026-08-22"}],
                facts=["Estoy pensando si cambiar el sofá."],
            )
        )
    )
    assert evaluate("P09", payload, schema) == ("PASS", [])


def test_regression_sentinels_require_user_content() -> None:
    """Reject shape-only regressions that discard the request's essential content."""
    schema = schema_for(next(case for case in load_cases() if case["id"] == "R02"))
    r02 = _output(
        _write(
            _unit(
                "Odyssey",
                note_type=None,
                intent="record",
                properties=[],
                facts=["Antes pensaba usar LangGraph para Odyssey."],
            )
        )
    )
    assert evaluate("R02", r02, schema) == ("PASS", [])
    assert (
        evaluate(
            "R02",
            _output(
                _write(
                    _unit(
                        "Odyssey",
                        note_type=None,
                        intent="record",
                        properties=[],
                        facts=["Antes pensaba usar una herramienta."],
                    )
                )
            ),
            schema,
        )[0]
        == "FAIL"
    )

    r03 = _output(
        {
            "kind": "retrieve",
            "plan": {"query": "n8n", "type": None, "filters": []},
        },
        _write(
            _unit(
                "n8n",
                note_type=None,
                intent="record",
                properties=[],
                facts=["Debemos revisar los tickets."],
            )
        ),
    )
    assert evaluate("R03", r03, schema) == ("PASS", [])
    missing_content = _output(
        {
            "kind": "retrieve",
            "plan": {"query": "tema", "type": None, "filters": []},
        },
        _write(_unit("tema", note_type=None, intent="record", properties=[], facts=["Anotado."])),
    )
    assert evaluate("R03", missing_content, schema)[0] == "FAIL"


def test_runner_persists_each_complete_input_and_stops_without_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Persist a result after every call, including a provider error, with no retry path."""
    monkeypatch.setattr(run_benchmark, "RESULTS_DIR", tmp_path)
    calls = 0

    def create(**_kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("transient provider failure")
        usage = SimpleNamespace(
            model_dump=lambda mode: {
                "input_tokens": 10,
                "input_tokens_details": {},
                "output_tokens": 5,
                "output_tokens_details": {},
            }
        )
        return SimpleNamespace(
            output_text=json.dumps(
                _output(
                    _write(_unit("x", note_type=None, intent="record", properties=[], facts=["x"]))
                )
            ),
            usage=usage,
        )

    directory = run_benchmark.run(
        "offline", SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    rows = [json.loads(line) for line in (directory / "raw_results.jsonl").read_text().splitlines()]
    assert len(rows) == len(load_cases()) == calls
    assert rows[0]["api_request"]["store"] is False and "schema" in rows[0]
    assert rows[1]["classification"] == "INVALID" and rows[1]["failure_kind"] == "provider"
    with pytest.raises(BenchmarkContractError, match="already complete"):
        run_benchmark.run("offline", SimpleNamespace(responses=SimpleNamespace(create=create)))
