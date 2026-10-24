"""Managed one-time schema restart only after the HTTP response is durable."""

from __future__ import annotations

import pytest

from odyssey_runtime import __main__ as runtime_main
from odyssey_runtime.server import SchemaActivationRestartRequested


def test_managed_restart_uses_existing_systemd_on_failure_policy(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(runtime_main, "build_runtime_from_environment", lambda: "runtime")
    monkeypatch.setattr(
        runtime_main,
        "serve",
        lambda *a, **kw: (
            called.append((a, kw)),
            (_ for _ in ()).throw(SchemaActivationRestartRequested("approved")),
        ),
    )
    with pytest.raises(SystemExit) as error:
        runtime_main.main()
    assert error.value.code == 75
    assert len(called) == 1


def test_normal_server_completion_does_not_trigger_restart(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(runtime_main, "build_runtime_from_environment", lambda: "runtime")
    monkeypatch.setattr(runtime_main, "serve", lambda *a, **kw: called.append((a, kw)))
    assert runtime_main.main() is None
    assert len(called) == 1
