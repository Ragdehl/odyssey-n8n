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

    repository = IdentityMappingRepository(tmp_path)
    principal = ExternalPrincipal("issuer", "subject")
    with pytest.raises(IdentityBoundaryError):
        repository.resolve_or_create(principal)


def test_known_principal_resolves_existing_user_without_provisioning(tmp_path: Path) -> None:
    """Resolve one provisioned principal without changing its durable mapping."""
    repository = IdentityMappingRepository(tmp_path)
    principal = ExternalPrincipal("issuer", "subject")
    user = repository.resolve_or_create(principal)
    before = (tmp_path / "identity-mappings.json").read_bytes()

    assert repository.resolve_existing(principal) == user
    assert (tmp_path / "identity-mappings.json").read_bytes() == before


def test_unknown_principal_does_not_create_mapping_or_allocate_user(tmp_path: Path) -> None:
    """Fail closed for an unknown principal while leaving absent state absent."""
    repository = IdentityMappingRepository(tmp_path)

    with pytest.raises(IdentityBoundaryError):
        repository.resolve_existing(ExternalPrincipal("issuer", "unknown"))

    assert not (tmp_path / "identity-mappings.json").exists()


def test_duplicate_principal_fails_closed_for_existing_lookup(tmp_path: Path) -> None:
    """Reject duplicate durable principal state instead of selecting one mapping."""
    path = tmp_path / "identity-mappings.json"
    path.write_text(
        json.dumps(
            {
                "format": "odyssey_identity_mapping",
                "format_version": 1,
                "principals": [
                    {
                        "issuer": "issuer",
                        "subject": "subject",
                        "odyssey_user_id": str(OdysseyUser.new().stable_user_id),
                    },
                    {
                        "issuer": "issuer",
                        "subject": "subject",
                        "odyssey_user_id": str(OdysseyUser.new().stable_user_id),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(IdentityBoundaryError):
        IdentityMappingRepository(tmp_path).resolve_existing(ExternalPrincipal("issuer", "subject"))

    assert path.read_bytes() == before


def test_external_principal_payload_is_exact_and_rejects_provider_fields() -> None:
    """Accept only issuer/subject and reject email, audience, token, or actor fields."""
    principal = ExternalPrincipal.from_payload({"issuer": "issuer", "subject": "subject"})

    assert principal == ExternalPrincipal("issuer", "subject")
    for payload in (
        {"issuer": "issuer"},
        {"subject": "subject"},
        {"issuer": "issuer", "subject": "subject", "email": "ignored"},
        {"issuer": "issuer", "subject": "subject", "aud": "ignored"},
    ):
        with pytest.raises(IdentityBoundaryError):
            ExternalPrincipal.from_payload(payload)


def test_browser_controlled_identity_fields_are_not_a_trusted_context() -> None:
    """The normalized context cannot be constructed from an email or external subject field."""
    with pytest.raises(IdentityBoundaryError):
        AuthenticatedActorContext.from_payload({"subject": "provider-subject"})
