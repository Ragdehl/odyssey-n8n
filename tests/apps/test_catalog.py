"""Deterministic coverage for the Slice 1 application catalog boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry, RoutingCapability
from odyssey_apps.calendar import CALENDAR_DESCRIPTOR
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_runtime.composition import RuntimeComposition

ROOT = Path(__file__).resolve().parents[2]


def calendar_descriptor() -> ApplicationDescriptor:
    """Return Calendar's app-owned compact routing descriptor."""
    return CALENDAR_DESCRIPTOR


def core_planner_artifacts() -> tuple[str, str, str, tuple[str, str]]:
    """Fingerprint the accepted Core planner artifacts protected from app enablement drift."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    context = {"date": "2026-10-02", "time": "12:00", "timezone": "Europe/Paris"}
    prompt = render_luna_experimental_prompt(schema, context).encode()
    provider_schema = json.dumps(
        luna_experimental_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode()
    teaching = (ROOT / "benchmarks/luna_first_planner/teaching_examples_v3.json").read_bytes()
    return (
        hashlib.sha256(prompt).hexdigest(),
        hashlib.sha256(provider_schema).hexdigest(),
        hashlib.sha256(teaching).hexdigest(),
        (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT),
    )


def test_core_import_has_no_application_package_dependency() -> None:
    """Prove a fresh Core import does not load the optional application package."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import odyssey_core; assert 'odyssey_apps' not in sys.modules",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_core_sources_never_import_application_packages() -> None:
    """Protect the physical Apps -> Core dependency direction across every Core module."""
    violations: list[str] = []
    for path in sorted((ROOT / "odyssey_core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = (alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names = (node.module or "",)
            else:
                continue
            if any(name == "odyssey_apps" or name.startswith("odyssey_apps.") for name in names):
                violations.append(str(path.relative_to(ROOT)))
                break
    assert violations == []


def test_registry_rejects_malformed_and_duplicate_descriptors() -> None:
    """Fail closed before ambiguous registration can reach runtime composition."""
    with pytest.raises(ValueError, match="routing_description"):
        ApplicationDescriptor(id="calendar", routing_description=" ")
    with pytest.raises(ValueError, match="Duplicate application id"):
        ApplicationRegistry.from_descriptors((calendar_descriptor(), calendar_descriptor()))
    with pytest.raises(ValueError, match="reserved"):
        ApplicationDescriptor(id="core", routing_description="shadow Core")


def test_catalog_keeps_disabled_evidence_but_never_makes_it_executable() -> None:
    """Expose enabled and disabled capability state in deterministic identifier order."""
    tasks = ApplicationDescriptor("tasks", "task lifecycle", ("temporal",))
    catalog = ApplicationRegistry.from_descriptors((tasks, calendar_descriptor())).catalog(
        enabled_ids=("tasks",)
    )

    assert catalog.capabilities() == (
        RoutingCapability(
            "calendar",
            "temporal interpretation of date-qualified statements, day/date-owned occurrences, and Calendar navigation",
            ("temporal",),
            False,
        ),
        RoutingCapability("tasks", "task lifecycle", ("temporal",), True),
    )
    assert catalog.executable("calendar") is None
    assert catalog.executable("tasks") == tasks


def test_enablement_only_changes_catalog_not_core_planner_artifacts() -> None:
    """Keep Core's accepted planner contract independent from application availability."""
    before = core_planner_artifacts()
    registry = ApplicationRegistry.from_descriptors((calendar_descriptor(),))
    disabled = registry.catalog()
    enabled = registry.catalog(enabled_ids=("calendar",))

    assert disabled.capabilities() != enabled.capabilities()
    assert disabled.executable("calendar") is None
    assert enabled.executable("calendar") == calendar_descriptor()
    assert core_planner_artifacts() == before


def test_calendar_opt_in_compiler_does_not_change_accepted_core_planner_artifacts() -> None:
    """Freeze the pre-Slice-5 Core prompt/schema/examples/model contract by content hash."""
    assert core_planner_artifacts() == (
        "717c9fea6a7d278be3284146b829a51fc8c7ed38549fe52ae17df2fd26585df9",
        "65877ae84df406d36648c37a7ad4826033990a1d1b2cc8a1d1a193a5e7ecedce",
        "e3ad1321ab56fb0ce0a3b587a73c07f282c748ec6ae0f203bb50ca13d1d3f5c0",
        ("gpt-5.6-luna", "low"),
    )


def test_core_only_runtime_remains_usable_with_empty_or_disabled_calendar_catalog() -> None:
    """Keep Slice 1 catalog state inert for the established Core request execution seam."""

    def execute(*_args: object, **_kwargs: object) -> None:
        """Represent the unchanged injected Core execution seam."""

    def refresh_indexes() -> None:
        """Represent the unchanged injected derived-index refresh seam."""

    empty = RuntimeComposition(core_execute=execute, refresh_indexes=refresh_indexes)
    disabled = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=refresh_indexes,
        application_catalog=ApplicationRegistry.from_descriptors(
            (calendar_descriptor(),)
        ).catalog(),
    )

    assert empty.application_catalog.capabilities() == ()
    assert disabled.application_catalog.executable("calendar") is None
    with pytest.raises(ValueError, match="Calendar application is unavailable"):
        disabled.calendar("month", {"month": "2026-10"})
    assert empty.core_execute("ordinary Core request") is None
    assert disabled.core_execute("ordinary Core request") is None
