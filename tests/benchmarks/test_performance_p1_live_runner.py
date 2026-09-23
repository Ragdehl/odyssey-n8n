"""Provider-free behavior tests for P1's dedicated-fixture baseline executor."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchmarks.performance_p1 import dev_fixture, run_live
from benchmarks.performance_p1.dev_fixture import FixtureError, fixture_notes
from odyssey_core.notes import validate_note


def _cases() -> list[dict[str, Any]]:
    """Load the frozen registry used by the real executor."""
    path = Path(__file__).parents[2] / "benchmarks/performance_p1/cases.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _operational() -> dict[str, Any]:
    """Return one compact, fully supplied fake provider observation."""
    return {
        "total_duration_ms": 20.0,
        "product_execution_duration_ms": 22.0,
        "coverage": {
            "attributed_ms": 20.0,
            "unattributed_ms": 0.0,
            "coverage_pct": 100.0,
            "overlapping_ms": 0.0,
        },
        "stages": [
            {
                "name": "planner",
                "outcome": "completed",
                "duration_ms": 20.0,
                "start_offset_ms": 0.0,
                "provider_calls": [
                    {
                        "name": "planner.luna",
                        "ordinal": 1,
                        "model": "gpt-5.6-luna",
                        "outcome": "completed",
                        "duration_ms": 18.0,
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 0,
                            "output_tokens": 10,
                        },
                    }
                ],
            }
        ],
    }


def _configure_p1_fixture_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Configure a real temporary dedicated fixture identity without host DEV paths."""
    root = tmp_path / "odyssey-p1-fixture"
    vault = root / "vault"
    state = root / "state"
    vault.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(vault),
            "-c",
            "user.name=Odyssey test",
            "-c",
            "user.email=odyssey-test@localhost",
            "commit",
            "--allow-empty",
            "-m",
            "baseline",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    state.mkdir()
    marker = root / ".p1-disposable-fixture"
    marker.write_text(dev_fixture.FIXTURE_IDENTITY, encoding="utf-8")
    monkeypatch.setattr(dev_fixture, "P1_ROOT", root)
    monkeypatch.setattr(dev_fixture, "P1_VAULT", vault)
    monkeypatch.setattr(dev_fixture, "P1_STATE", state)
    monkeypatch.setattr(dev_fixture, "DISPOSABLE_MARKER", marker)
    monkeypatch.setattr(dev_fixture, "MANUAL_DEV_ROOT", tmp_path / "odyssey-dev")
    monkeypatch.setattr(dev_fixture, "PRODUCTION_ROOT", tmp_path / "odyssey")
    return vault, state


def test_disposable_fixture_is_schema_valid_and_requires_dedicated_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen fixture is schema-valid and accepts only its exact marked P1 root."""
    schema = json.loads((Path(__file__).parents[2] / "config/note-schema.json").read_text())
    notes = fixture_notes({"Marta": ["Marta prefiere el té."]})
    assert set(notes) == {"Marta", "Elena", "Pablo", "self"}
    for note in notes.values():
        validate_note(note, schema)

    vault, state = _configure_p1_fixture_root(tmp_path, monkeypatch)
    dev_fixture._require_exact_p1_roots(vault, state)
    result = dev_fixture.reset_fixture(schema, vault_root=vault, state_root=state)
    assert result["note_ids"] == ["p1-marta", "p1-elena", "p1-pablo"]
    with pytest.raises(FixtureError):
        dev_fixture._require_exact_p1_roots(tmp_path / "other" / "vault", state)


@pytest.mark.parametrize("protected_name", ["MANUAL_DEV_ROOT", "PRODUCTION_ROOT"])
def test_fixture_reset_rejects_manual_or_production_roots_before_any_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, protected_name: str
) -> None:
    """A protected root retains its sentinel when the reset guard rejects it."""
    vault, state = _configure_p1_fixture_root(tmp_path, monkeypatch)
    protected_root = getattr(dev_fixture, protected_name)
    protected_vault = protected_root / "vault"
    protected_state = protected_root / "state"
    protected_vault.mkdir(parents=True)
    protected_state.mkdir()
    sentinel = protected_vault / "must-not-delete.md"
    sentinel.write_text("protected", encoding="utf-8")

    with pytest.raises(FixtureError, match="must not overlap"):
        dev_fixture.reset_fixture({}, vault_root=protected_vault, state_root=protected_state)

    assert sentinel.read_text(encoding="utf-8") == "protected"
    dev_fixture._require_exact_p1_roots(vault, state)


def test_fixture_reset_rejects_missing_or_invalid_identity_before_any_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad marker leaves dedicated-fixture content untouched before destructive work."""
    vault, state = _configure_p1_fixture_root(tmp_path, monkeypatch)
    sentinel = vault / "must-not-delete.md"
    sentinel.write_text("fixture", encoding="utf-8")

    dev_fixture.DISPOSABLE_MARKER.unlink()
    with pytest.raises(FixtureError, match="not explicitly initialized"):
        dev_fixture.reset_fixture({}, vault_root=vault, state_root=state)
    assert sentinel.read_text(encoding="utf-8") == "fixture"

    dev_fixture.DISPOSABLE_MARKER.write_text("wrong identity\n", encoding="utf-8")
    with pytest.raises(FixtureError, match="identity is invalid"):
        dev_fixture.reset_fixture({}, vault_root=vault, state_root=state)
    assert sentinel.read_text(encoding="utf-8") == "fixture"


def test_fixture_reset_rejects_missing_git_baseline_before_any_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker alone cannot authorize deletion without a committed P1 Git baseline."""
    vault, state = _configure_p1_fixture_root(tmp_path, monkeypatch)
    sentinel = vault / "must-not-delete.md"
    sentinel.write_text("fixture", encoding="utf-8")
    shutil.rmtree(vault / ".git")
    (vault / ".git").mkdir()

    with pytest.raises(FixtureError, match="Git baseline is unavailable"):
        dev_fixture.reset_fixture({}, vault_root=vault, state_root=state)

    assert sentinel.read_text(encoding="utf-8") == "fixture"


def test_live_request_payloads_use_the_explicit_p1_webhook_prefix() -> None:
    """The runner uses its supplied dedicated P1 n8n URL, never the manual DEV default."""
    p1_url = "https://p1-fixture.test:28781"
    chat_url, _ = run_live._request_payload(_cases()[0], "p1-test", p1_url)
    notes_url, _ = run_live._request_payload(_cases()[-1], "p1-test", p1_url)
    assert chat_url.startswith(p1_url)
    assert notes_url.startswith(p1_url)
    assert chat_url.endswith("/api/request")
    assert notes_url.endswith("/api/notes")


def test_live_entry_refuses_to_select_an_implicit_manual_dev_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live command stops before fixture work unless the P1 endpoint is explicit."""
    monkeypatch.delenv(run_live.P1_N8N_URL_ENV, raising=False)
    evidence = tmp_path / "must-not-exist.jsonl"

    with pytest.raises(SystemExit, match="dedicated P1 n8n HTTPS URL"):
        run_live.main(
            [
                "--confirm-live-provider-calls",
                "--evidence-path",
                str(evidence),
            ]
        )

    assert not evidence.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://p1-fixture.test",
        "https://odyssey-dev.ragdehl.com",
        "https://odyssey.ragdehl.com",
        "https://n8n.ragdehl.com",
        "https://user:password@p1-fixture.test",
        "https://p1-fixture.test/api",
        "https://p1-fixture.test/?target=other",
        "https://p1-fixture.test:99999",
    ],
)
def test_p1_url_rejects_insecure_or_nonisolated_targets(url: str) -> None:
    """Reject insecure transport and known non-P1 destinations before requests can run."""
    with pytest.raises(run_live.LiveRunError):
        run_live._validated_p1_n8n_url(url)


def test_p1_url_normalizes_only_an_isolated_https_origin() -> None:
    """An isolated HTTPS origin is normalized before fixed webhook paths are appended."""
    assert (
        run_live._validated_p1_n8n_url("HTTPS://P1-Fixture.Test:28781/")
        == "https://p1-fixture.test:28781"
    )


def test_live_http_client_rejects_redirects_to_unvalidated_origins() -> None:
    """A validated P1 origin cannot redirect provider-bearing requests elsewhere."""
    handler = run_live._NoRedirectHandler()
    request = run_live.urllib.request.Request("https://p1-fixture.test/api/request")
    assert (
        handler.redirect_request(request, None, 307, "Temporary Redirect", {}, "http://target")
        is None
    )


def test_live_runner_rejects_unsafe_url_before_creating_evidence_or_requesting(
    tmp_path: Path,
) -> None:
    """An unsafe configured target is rejected before any runner side effect."""
    evidence = tmp_path / "must-not-exist.jsonl"
    with pytest.raises(run_live.LiveRunError, match="isolated HTTPS origin"):
        run_live.run_live_cases(
            _cases(),
            evidence_path=evidence,
            pricing={},
            provenance={},
            confirmed=True,
            n8n_url="http://odyssey-dev.ragdehl.com",
            post=lambda *_args: pytest.fail("unsafe target must not receive a request"),
            reset=lambda _case: pytest.fail("unsafe target must be rejected before fixture work"),
            restart=lambda: pytest.fail("unsafe target must be rejected before runtime restart"),
        )
    assert not evidence.exists()


def test_live_runner_flushes_every_case_and_keeps_semantic_failures_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A safe oracle failure is recorded once and does not cause a retry or lost later evidence."""
    state = {
        "Marta": "marta trabaja en thales. marta vive en lyon.",
        "Elena": "elena vive en girona.",
        "Pablo": "pablo vive en barcelona.",
    }
    requests: list[dict[str, object]] = []
    restarts: list[None] = []

    def reset(case: dict[str, Any]) -> dict[str, object]:
        state.update(
            {
                "Marta": "marta trabaja en thales. marta vive en lyon.",
                "Elena": "elena vive en girona.",
                "Pablo": "pablo vive en barcelona.",
            }
        )
        for person, facts in case.get("extra_fixture_facts", {}).items():
            state[person] += " " + " ".join(facts).casefold()
        return {"fixture_version": 1, "fixture_git_commit": f"fixture-{case['id']}"}

    def post(_url: str, payload: dict[str, object], _timeout: float) -> dict[str, Any]:
        requests.append(payload)
        if payload.get("operation") == "turn":
            return {"conversation_id": "main"}
        if payload.get("operation") == "intelligent":
            return {
                "kind": "page",
                "mode": "intelligent",
                "items": [{"id": "p1-marta"}],
                "operational": _operational(),
            }
        request = payload["request"]
        assert isinstance(request, str)
        if request == "???":
            return {
                "request_id": payload["request_id"],
                "status": "needs_attention",
                "kind": "clarification",
                "request_detail": {"operational": _operational(), "changes": {"units": []}},
            }
        if request.startswith("¿"):
            fact = "Marta trabaja en Thales." if "trabaja" in request else "Marta vive en Lyon."
            return {
                "request_id": payload["request_id"],
                "status": "completed",
                "kind": "answer",
                "message": fact,
                "request_detail": {"operational": _operational(), "changes": {"units": []}},
            }
        if request.startswith("Guarda"):
            state["Marta"] += " prefiere el té"
        elif request.startswith("Marta prefiere"):
            state["Marta"] += " prefiere el té"
            state["Elena"] += " prefiere el café"
        else:
            state["Marta"] += " prefiere el té"
            state["Elena"] += " le gusta el café"
            state["Pablo"] += " trabaja en thales"
        kind = "empty" if request.startswith("Guarda") else "acknowledgement"
        return {
            "request_id": payload["request_id"],
            "status": "completed",
            "kind": kind,
            "request_detail": {
                "operational": _operational(),
                "changes": {"units": [{"status": "completed"}]},
            },
        }

    monkeypatch.setattr(run_live, "_fixture_note_text", lambda person: state[person])
    rows = run_live.run_live_cases(
        _cases(),
        evidence_path=tmp_path / "baseline.jsonl",
        pricing=json.loads(
            (
                Path(__file__).parents[2] / "benchmarks/performance_p1/pricing_snapshot.json"
            ).read_text()
        ),
        provenance={"source_commit": "test", "deployed_commit": "test"},
        confirmed=True,
        post=post,
        reset=reset,
        restart=lambda: restarts.append(None),
        n8n_url="https://p1-fixture.test:28781",
        run_id="deterministic",
    )
    assert len(rows) == 7 and len(restarts) == 7
    assert [row["case_id"] for row in rows] == ["R1", "R2", "W1", "W2", "W3", "C1", "N1"]
    assert rows[2]["semantic_passed"] is False and rows[2]["semantic_oracle"] == "write_shape"
    assert rows[3]["semantic_passed"] is True and rows[4]["semantic_passed"] is True
    assert len([request for request in requests if "request" in request]) == 6
    assert len([request for request in requests if request.get("operation") == "turn"]) == 2
    persisted = [
        json.loads(line) for line in (tmp_path / "baseline.jsonl").read_text().splitlines()
    ]
    assert len(persisted) == 8 and persisted[0]["record_type"] == "run"
    assert all(row["record_type"] == "case" for row in persisted[1:])


def test_live_runner_stops_after_persisting_an_unsafe_transport_failure(tmp_path: Path) -> None:
    """A malformed product reply writes its stop record and performs no later request or retry."""
    calls = 0

    def post(_url: str, _payload: dict[str, object], _timeout: float) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"request_id": "wrong"}

    with pytest.raises(run_live.LiveRunError, match="fresh execution"):
        run_live.run_live_cases(
            _cases(),
            evidence_path=tmp_path / "stopped.jsonl",
            pricing={"as_of": "test", "models": {}},
            provenance={"source_commit": "test", "deployed_commit": "test"},
            confirmed=True,
            post=post,
            reset=lambda _case: {},
            restart=lambda: None,
            n8n_url="https://p1-fixture.test:28781",
            run_id="unsafe",
        )
    rows = [json.loads(line) for line in (tmp_path / "stopped.jsonl").read_text().splitlines()]
    assert calls == 1 and rows[-1]["record_type"] == "unsafe_stop" and len(rows) == 2


def test_live_runner_refuses_existing_evidence_without_reset_or_request(tmp_path: Path) -> None:
    """An immutable evidence name is checked before fixture mutation or provider-boundary work."""
    evidence = tmp_path / "existing.jsonl"
    evidence.write_text("existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_live.run_live_cases(
            _cases(),
            evidence_path=evidence,
            pricing={},
            provenance={},
            confirmed=True,
            post=lambda *_args: pytest.fail("request must not run"),
            reset=lambda _case: pytest.fail("reset must not run"),
            restart=lambda: pytest.fail("restart must not run"),
            n8n_url="https://p1-fixture.test:28781",
        )
