"""Core-owned physical readback for one Task referring to a finite Person set.

All identities are E2/Core-materialized, never proposed by the model or app.
This check is an additional POSTWRITE status guard; it cannot authorize writes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .application import ApplicationResult, ApplicationStatus
from .notes import parse_note
from .reference_preflight import _find_existing_identity
from .source_bound_dependency import SourceBoundDependency
from .storage import VaultRepository


def verify_plural_task_markdown(
    repository: VaultRepository,
    schema: dict[str, Any],
    result: ApplicationResult,
    dependencies: tuple[SourceBoundDependency, ...],
) -> bool:
    """Require exactly one persisted, newly affected Task with ALL canonical links."""
    if (
        result.status is not ApplicationStatus.COMPLETED
        or not 2 <= len(dependencies) <= 8
        or len({d.evidence.stable_note_id for d in dependencies}) != len(dependencies)
    ):
        return False
    try:
        expected_links = set()
        for dependency in dependencies:
            proof = dependency.evidence
            if proof.note_type != "person":
                return False
            path, name = _find_existing_identity(repository, schema, proof.stable_note_id)
            note = parse_note(repository.read_text(path))
            if (
                note.metadata.get("type") != "person"
                or note.metadata.get("id") != proof.stable_note_id
                or note.metadata.get("name") != name
                or name != proof.canonical_name
            ):
                return False
            expected_links.add(f"[[{path.removesuffix('.md')}|{name}]]")
        tasks = []
        for note_id in dict.fromkeys(result.affected_stable_note_ids):
            path, _ = _find_existing_identity(repository, schema, note_id)
            note = parse_note(repository.read_text(path))
            if note.metadata.get("id") == note_id and note.metadata.get("type") == "task":
                tasks.append(note)
        return len(tasks) == 1 and all(
            task.content.count(link) >= 1 for task in tasks for link in expected_links
        )
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
        return False


def guard_plural_task_readback(
    repository: VaultRepository,
    schema: dict[str, Any],
    result: ApplicationResult,
    dependencies: tuple[SourceBoundDependency, ...],
) -> ApplicationResult:
    """Return PARTIAL, never COMPLETED, when persisted links are missing."""
    if result.status is ApplicationStatus.COMPLETED and not verify_plural_task_markdown(
        repository, schema, result, dependencies
    ):
        return replace(
            result,
            status=ApplicationStatus.PARTIAL,
            clarification_code="DEPENDENT_PERSON_SET_PHYSICAL_READBACK_UNVERIFIED",
        )
    return result
