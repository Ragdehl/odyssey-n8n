"""Deterministic tests for the provider-independent authenticated identity boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    ExternalPrincipal,
    IdentityBoundaryError,
    IdentityMappingRepository,
    OdysseyUser,
)


def test_trusted_actor_context_accepts_only_an_odyssey_user_id() -> None:
    """Normalize one trusted actor payload without accepting provider fields."""
    user = OdysseyUser.new()
    context = AuthenticatedActorContext.from_payload({"stable_user_id": user.stable_user_id})

    assert context.stable_user_id == user.stable_user_id


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"stable_user_id": "not-a-uuid"}, {"stable_user_id": "x", "email": "x"}],
)
def test_actor_context_rejects_missing_malformed_and_extra_fields(payload: object) -> None:
    """Reject absent, malformed, or provider-shaped normalized identity input."""
    with pytest.raises(IdentityBoundaryError):
        AuthenticatedActorContext.from_payload(payload)


def test_mapping_is_stable_and_provider_identifiers_are_not_the_user_id(tmp_path: Path) -> None:
    """Map one provider principal once and persist its separate Odyssey-owned UUID."""
    repository = IdentityMappingRepository(tmp_path)
    principal = ExternalPrincipal("https://issuer.example", "provider-subject")

    first = repository.resolve_or_create(principal)
    second = repository.resolve_or_create(principal)
    persisted = json.loads((tmp_path / "identity-mappings.json").read_text(encoding="utf-8"))

    assert first == second
    assert first.stable_user_id != principal.subject
    assert persisted["principals"][0]["odyssey_user_id"] == first.stable_user_id
    assert (tmp_path / "identity-mappings.json").stat().st_mode & 0o077 == 0


def test_provider_principal_does_not_cross_into_normalized_actor_context(tmp_path: Path) -> None:
    """Keep provider identity in mapping state rather than the Core actor context."""
    principal = ExternalPrincipal("https://issuer.example", "provider-subject")
    user = IdentityMappingRepository(tmp_path).resolve_or_create(principal)
    context = AuthenticatedActorContext.from_payload({"stable_user_id": user.stable_user_id})

    assert context.stable_user_id == user.stable_user_id
    assert principal.subject not in json.dumps({"stable_user_id": context.stable_user_id})


def test_two_external_principals_remain_distinct(tmp_path: Path) -> None:
    """Do not collapse different issuer/subject pairs into one Odyssey user."""
    repository = IdentityMappingRepository(tmp_path)

    first = repository.resolve_or_create(ExternalPrincipal("issuer", "subject-a"))
    second = repository.resolve_or_create(ExternalPrincipal("issuer", "subject-b"))

    assert first != second


def test_mapping_state_fails_closed_when_malformed(tmp_path: Path) -> None:
    """Reject malformed durable identity state instead of guessing or repairing it."""
    (tmp_path / "identity-mappings.json").write_text('{"principals": []}\n', encoding="utf-8")

    with pytest.raises(IdentityBoundaryError):
        IdentityMappingRepository(tmp_path).resolve_or_create(
            ExternalPrincipal("issuer", "subject")
        )


def test_browser_controlled_identity_fields_are_not_a_trusted_context() -> None:
    """The normalized context cannot be constructed from an email or external subject field."""
    with pytest.raises(IdentityBoundaryError):
        AuthenticatedActorContext.from_payload({"subject": "provider-subject"})
