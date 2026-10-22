"""Trusted, non-discoverable binding for one scoped source-candidate application.

A model never supplies this registration. Its kind is Router source evidence,
not a Note type or permission to write. The application remains responsible
for its own meaning, source interpretation and E3 mutations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from odyssey_apps.catalog import ApplicationDescriptor
from odyssey_apps.fact_candidates import CANDIDATE_KINDS

_RESERVED = frozenset({"tasks", "events", "core", "temporal"})


@dataclass(frozen=True, slots=True)
class RegisteredScopedApp:
    descriptor: ApplicationDescriptor
    candidate_kind: str
    execute: Callable[..., object]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.descriptor, ApplicationDescriptor)
            or self.descriptor.id in _RESERVED
            or not isinstance(self.candidate_kind, str)
            or self.candidate_kind not in CANDIDATE_KINDS
            or self.candidate_kind in {"task", "event"}
            or not callable(self.execute)
        ):
            raise ValueError("Untrusted or conflicting scoped app registration")


def registered_app_index(
    apps: tuple[RegisteredScopedApp, ...],
) -> dict[str, RegisteredScopedApp]:
    """Reject duplicate capabilities and ambiguous source-kind ownership."""
    if not isinstance(apps, tuple) or any(not isinstance(app, RegisteredScopedApp) for app in apps):
        raise ValueError("Scoped applications must be trusted registrations")
    if (
        len(apps) > 16
        or len({app.descriptor.id for app in apps}) != len(apps)
        or len({app.candidate_kind for app in apps}) != len(apps)
    ):
        raise ValueError("Scoped app registrations collide or exceed bounds")
    return {app.descriptor.id: app for app in apps}
