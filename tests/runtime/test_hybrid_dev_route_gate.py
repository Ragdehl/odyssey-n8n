"""Provider-free E1 gates for the disabled-by-default DEV hybrid seam."""

from __future__ import annotations

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition, _hybrid_dev_enabled

ACTOR = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")


def _completed(request_id: str) -> ApplicationResult:
    """Return a minimal completed result without simulating a Core mutation."""
    return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ())


def test_hybrid_is_disabled_by_default_and_v0_core_remains_authoritative(monkeypatch) -> None:
    """An unset DEV flag must not replace the established core execution path."""
    monkeypatch.delenv("ODYSSEY_HYBRID_DEV_ENABLED", raising=False)
    calls: list[str] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: (
            calls.append(source) or _completed(request_id)
        ),
        refresh_indexes=lambda: None,
    )

    assert not _hybrid_dev_enabled()
    assert runtime.execute("Guardar una nota.", "v0-request").status is ApplicationStatus.COMPLETED
    assert calls == ["Guardar una nota."]


def test_hybrid_refuses_missing_authenticated_conversation_without_v0_fallback() -> None:
    """An enabled hybrid seam never runs for an unbound delivery."""
    calls: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        hybrid_candidate_execute=lambda *args: calls.append(args) or _completed(args[1]),
    )

    result = runtime.execute("Mañana iré al cine.", "hybrid-unbound")

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "HYBRID_AUTHENTICATED_CONVERSATION_REQUIRED"
    assert calls == []


def test_hybrid_receives_only_the_authenticated_conversation_context(tmp_path) -> None:
    """The E1 seam receives a stable actor and main conversation before dispatch."""
    calls: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        hybrid_candidate_execute=lambda *args: calls.append(args) or _completed(args[1]),
    )

    result = runtime.execute(
        "Mañana iré al cine.",
        "hybrid-bound",
        "main",
        authenticated_actor=ACTOR,
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert calls == [("Mañana iré al cine.", "hybrid-bound", ACTOR, "main")]


@pytest.mark.parametrize("value", ("1", "true", "True"))
def test_hybrid_flag_requires_explicit_dev_environment(monkeypatch, value: str) -> None:
    """A truthy hybrid flag is rejected outside an explicitly declared DEV process."""
    monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", value)
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")

    with pytest.raises(ValueError, match="requires ODYSSEY_DEPLOYMENT_ENV=DEV"):
        _hybrid_dev_enabled()


def test_hybrid_flag_accepts_only_explicit_dev_opt_in(monkeypatch) -> None:
    """The deployment builder may opt in only with the exact reviewed DEV pairing."""
    monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")

    assert _hybrid_dev_enabled()
