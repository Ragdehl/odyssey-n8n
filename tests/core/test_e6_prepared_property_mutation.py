"""E6.2: Events and Tasks share one Core-owned prepared update path."""

from __future__ import annotations

import pytest

from odyssey_core.mutation_gate import (
    CanonicalMutationError,
    MutationCommand,
)
from odyssey_core.prepared_property_mutation import execute_prepared_property_mutation
from odyssey_core.request_planning import PropertyChange
from tests.apps.events.test_event_core_e3_mutations import make_event

NOW = "2026-10-22T19:00:00+02:00"


def _prepared_event(tmp_path):
    schema, repo, service, receipt = make_event(tmp_path)
    command = MutationCommand(
        "event_cancel",
        receipt.target_id,
        1,
        receipt.source_hash,
        "e6-direct-update",
        "fixture",
        NOW,
        "event",
    )
    target = service._gate.prepare(command)
    kwargs = dict(
        gate=service._gate,
        command=command,
        target=target,
        note_type="event",
        changes=(PropertyChange("event_status", "set", "cancelled"),),
        repository=repo,
        schema=schema,
        actor="fixture",
        now=NOW,
        request_id="e6-direct-update",
    )
    return repo, receipt, kwargs


def test_core_prepared_property_use_case_preserves_e3_readback_and_cas(tmp_path):
    repo, created, options = _prepared_event(tmp_path)
    result = execute_prepared_property_mutation(**options)
    assert result.before_revision == 1
    assert result.after_revision == 2
    assert result.readback.metadata["event_status"] == "cancelled"
    assert result.readback.metadata["id"] == created.target_id
    assert result.after_source_hash != created.source_hash
    assert result.history is not None
    with pytest.raises(CanonicalMutationError, match="STALE_TARGET"):
        execute_prepared_property_mutation(**options)


@pytest.mark.parametrize(
    "override",
    (
        {"note_type": "task"},
        {"actor": "forged-actor"},
        {"request_id": "forged-request"},
        {"now": "2026-10-22T20:00:00+02:00"},
        {"changes": ()},
        {"changes": ("not a PropertyChange",)},
    ),
)
def test_core_property_boundary_rejects_mixed_type_tokens_before_write(tmp_path, override):
    repo, created, options = _prepared_event(tmp_path)
    raw_before = repo.read_text(created.target_path)
    options.update(override)
    with pytest.raises(CanonicalMutationError, match="PREPARED_PROPERTY_MUTATION_INVALID"):
        execute_prepared_property_mutation(**options)
    assert repo.read_text(created.target_path) == raw_before


def test_core_property_use_case_never_crosses_another_repository_or_schema(tmp_path):
    repo, created, options = _prepared_event(tmp_path)
    raw_before = repo.read_text(created.target_path)
    other_root = tmp_path / "other-vault"
    other_root.mkdir()
    another_repo = type(repo)(other_root)
    for patch in ({"repository": another_repo}, {"schema": dict(options["schema"])}):
        with pytest.raises(CanonicalMutationError, match="PREPARED_PROPERTY_MUTATION_INVALID"):
            execute_prepared_property_mutation(**(options | patch))
    assert repo.read_text(created.target_path) == raw_before
