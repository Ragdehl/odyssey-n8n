"""Deterministic tests for bounded SonarQube baseline-hardening guards."""

from __future__ import annotations

import pytest

from benchmarks.phase14_retrieval_plan.run_benchmark import validate_run_id
from benchmarks.run_phase11a_contextual_resolution import validate_local_server_url


def test_run_id_is_a_safe_directory_identifier() -> None:
    """Accept ordinary benchmark IDs and reject traversal or absolute paths."""
    assert validate_run_id("20260820T_PHASE14_INITIAL") == "20260820T_PHASE14_INITIAL"
    for value in ("../../foo", "/tmp/foo", "", "../foo", "foo/bar"):
        with pytest.raises(ValueError):
            validate_run_id(value)


def test_local_server_url_accepts_loopback_http() -> None:
    """Keep the benchmark's local HTTP model-server endpoint usable."""
    for value in (
        "http://localhost:8080/v1/chat/completions",
        "http://127.0.0.1:8080/v1/chat/completions",
        "http://[::1]:8080/v1/chat/completions",
    ):
        assert validate_local_server_url(value) == value


def test_local_server_url_rejects_external_or_malformed_destinations() -> None:
    """Prevent credentials, external hosts, and non-HTTP URLs at the CLI boundary."""
    for value in (
        "https://localhost:8080/model",
        "http://example.com/model",
        "http://localhost.evil/model",
        "http://user:password@localhost/model",
        "file:///tmp/model",
        "localhost:8080/model",
        "http://[::1/model",
        "http://localhost:not-a-port/model",
    ):
        with pytest.raises(ValueError):
            validate_local_server_url(value)
