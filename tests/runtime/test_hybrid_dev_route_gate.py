"""Provider-free E1 gates for the disabled-by-default DEV hybrid seam."""

from __future__ import annotations

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import (
    RuntimeComposition,
    _hybrid_dev_enabled,
    _hybrid_source_review_enabled,
)

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
    reads: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        hybrid_candidate_execute=lambda *args: calls.append(args) or _completed(args[1]),
        hybrid_read_execute=lambda *args: reads.append(args) or _completed(args[1]),
    )

    result = runtime.execute("Mañana iré al cine.", "hybrid-unbound")

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "HYBRID_AUTHENTICATED_CONVERSATION_REQUIRED"
    assert calls == []
    assert reads == []


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


def test_hybrid_proven_read_preserves_the_exact_source_and_bypasses_candidates(tmp_path) -> None:
    """A Core-proven retrieval keeps ordinary reading available in hybrid DEV."""
    reads: list[tuple[object, ...]] = []
    candidates: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        hybrid_read_execute=lambda *args: reads.append(args) or _completed(args[1]),
        hybrid_candidate_execute=lambda *args: candidates.append(args) or _completed(args[1]),
    )

    result = runtime.execute("¿Dónde trabajo?", "read-request", "main", ACTOR)

    assert result.status is ApplicationStatus.COMPLETED
    assert reads == [("¿Dónde trabajo?", "read-request", ACTOR, "main")]
    assert candidates == []


def test_hybrid_possible_write_stays_on_the_candidate_guard(tmp_path) -> None:
    """An unproven read disposition cannot bypass hybrid write validation."""
    candidates: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        hybrid_read_execute=lambda *args: None,
        hybrid_candidate_execute=lambda *args: candidates.append(args) or _completed(args[1]),
    )

    result = runtime.execute(
        "Guardar que trabajo en Synthetic Systems.", "write-request", "main", ACTOR
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert candidates == [
        ("Guardar que trabajo en Synthetic Systems.", "write-request", ACTOR, "main")
    ]


def test_hybrid_mixed_result_does_not_silently_drop_the_read_or_write(tmp_path) -> None:
    """A proven mixed plan returns its clarification without candidate fallback."""
    candidates: list[tuple[object, ...]] = []
    mixed = ApplicationResult(
        "mixed-request",
        ApplicationStatus.NEEDS_ATTENTION,
        (),
        (),
        clarification_code="HYBRID_MIXED_REQUEST_REQUIRES_SEPARATE_REQUESTS",
    )
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        hybrid_read_execute=lambda *args: mixed,
        hybrid_candidate_execute=lambda *args: candidates.append(args) or _completed(args[1]),
    )

    result = runtime.execute(
        "¿Dónde trabajo? Guarda que hoy teletrabajo.", "mixed-request", "main", ACTOR
    )

    assert result.clarification_code == "HYBRID_MIXED_REQUEST_REQUIRES_SEPARATE_REQUESTS"
    assert candidates == []


def test_hybrid_ambiguous_disposition_remains_on_candidate_guard(tmp_path) -> None:
    """No read execution follows an unresolved semantic disposition."""
    candidates: list[tuple[object, ...]] = []
    runtime = RuntimeComposition(
        core_execute=lambda source, request_id, *args: _completed(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        hybrid_read_execute=lambda *args: None,
        hybrid_candidate_execute=lambda *args: candidates.append(args) or _completed(args[1]),
    )

    runtime.execute("Haz lo necesario con mi trabajo.", "ambiguous-request", "main", ACTOR)

    assert candidates == [("Haz lo necesario con mi trabajo.", "ambiguous-request", ACTOR, "main")]


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


def test_source_review_remains_disabled_without_its_own_opt_in(monkeypatch) -> None:
    """DEV hybrid alone retains Router v5 until source review is explicitly selected."""
    monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.delenv("ODYSSEY_HYBRID_SOURCE_REVIEW_ENABLED", raising=False)

    assert not _hybrid_source_review_enabled(_hybrid_dev_enabled())


def test_source_review_rejects_prod_or_missing_hybrid_gate(monkeypatch) -> None:
    """The v6 boundary cannot be accidentally activated independently of DEV hybrid."""
    monkeypatch.setenv("ODYSSEY_HYBRID_SOURCE_REVIEW_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")

    with pytest.raises(ValueError, match="HYBRID_DEV_ENABLED"):
        _hybrid_source_review_enabled(False)
