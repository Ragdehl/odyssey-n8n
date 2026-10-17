"""Private-free derived-index telemetry and fallback integration on isolated Markdown."""

from __future__ import annotations

import json
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime import composition
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write
from tests.core.test_reference_preflight import UnresolvedReasoner


def _runtime(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    runtime_root = tmp_path / "runtime"
    for path in (vault, state / "pending", runtime_root):
        path.mkdir(parents=True)
    repo = VaultRepository(vault)
    schema = compose_application_schema(
        json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()),
        (TASK_SCHEMA_EXTENSION,),
    )
    write(repo, "people/Lucía.md", note("lucia", "person", "Original.", name="Lucía"))
    write(repo, "people/ordinary.md", note("ordinary", "person", "Original.", name="Ordinary"))
    embedder = KeywordEmbedder()
    ContextIndex(runtime_root / "context.sqlite3").rebuild(repo, schema, embedder)
    SemanticEntityIndex(runtime_root / "semantic.sqlite3").rebuild(repo, schema, embedder)
    SemanticEntityIndex(runtime_root / "semantic-tasks.sqlite3").rebuild(
        repo, planning_schema_for_capability(schema, "tasks"), embedder
    )
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_ENABLED_APPLICATIONS", "tasks")
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", str(vault))
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(state))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(state / "pending"))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "embedding-cache"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-not-used")
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **_kwargs: embedder)
    monkeypatch.setattr(composition, "_build_contextual_reasoner", UnresolvedReasoner)
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda _root: None)
    return composition.build_runtime_from_environment(), repo


def _only_event(capsys):
    messages = [
        json.loads(line.partition("odyssey_dev_index_refresh ")[2])
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("odyssey_dev_index_refresh ")
    ]
    assert len(messages) == 1
    return messages[0]


def test_refresh_reports_real_incremental_work_and_no_private_paths(tmp_path, monkeypatch, capsys):
    runtime, repo = _runtime(tmp_path, monkeypatch)
    write(repo, "people/ordinary.md", note("ordinary", "person", "Updated.", name="Ordinary"))
    runtime.refresh_affected_indexes(("ordinary",))
    event = _only_event(capsys)
    log = tmp_path / "runtime" / "index-refresh-events.jsonl"
    assert json.loads(log.read_text().splitlines()[-1].split(" ", 1)[1]) == event
    assert log.stat().st_mode & 0o077 == 0
    assert event["outcome"] == "incremental"
    assert event["note_count"] == 1
    assert all(name in event["stages_ms"] for name in ("context", "semantic", "semantic.tasks"))
    assert "full_rebuild" not in event["stages_ms"]
    assert "ordinary" not in json.dumps(event)
    assert "Lucía" not in json.dumps(event)
    assert "people/" not in json.dumps(event)


def test_refresh_reports_full_rebuild_reason_for_unrelated_real_drift(
    tmp_path, monkeypatch, capsys
):
    runtime, repo = _runtime(tmp_path, monkeypatch)
    write(repo, "people/other.md", note("other", "person", "External.", name="Other"))
    runtime.refresh_affected_indexes(("ordinary",))
    event = _only_event(capsys)
    log = tmp_path / "runtime" / "index-refresh-events.jsonl"
    assert json.loads(log.read_text().splitlines()[-1].split(" ", 1)[1]) == event
    assert event["outcome"] == "full_rebuild"
    assert event["failure_class"] == "ContextIndexError"
    assert event["failure_stage"] == "context"
    assert event["note_count"] == 1
    assert "full_rebuild" in event["stages_ms"]
    assert "people/" not in json.dumps(event)
    assert "other" not in json.dumps(event)


def test_telemetry_off_outside_dev(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(tmp_path))
    composition._emit_dev_index_refresh_diagnostic(
        outcome="full_rebuild",
        note_count=1,
        duration_ms=15.0,
        stages_ms={"context": 4.0, "full_rebuild": 11.0},
        failure_class="ContextIndexError",
        failure_stage="context",
    )
    assert capsys.readouterr().err == ""
    assert not (tmp_path / "index-refresh-events.jsonl").exists()


def test_dev_telemetry_is_bounded_and_rotates(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(tmp_path))
    log = tmp_path / "index-refresh-events.jsonl"
    log.write_text("x" * 262_145)
    composition._emit_dev_index_refresh_diagnostic(
        outcome="incremental",
        note_count=1,
        duration_ms=2.0,
        stages_ms={"context": 1.0},
    )
    assert log.stat().st_size < 4096
    assert "incremental" in log.read_text()
    assert "index-refresh-events" not in capsys.readouterr().err
