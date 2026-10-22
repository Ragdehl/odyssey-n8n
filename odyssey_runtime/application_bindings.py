"""Closed, trusted composition of application executors.

Router candidates and descriptors are never executable authority. Only the
composition root can supply a callable, and only an explicitly enabled
registered capability may be dispatched. No Core, provider or persistence
implementation is imported by this adapter.
"""

from __future__ import annotations

from collections.abc import Mapping

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_runtime.routing import ApplicationExecutor


def bind_registered_executors(
    catalog: ApplicationCatalog,
    trusted: Mapping[str, ApplicationExecutor | None],
    *,
    require_enabled: bool = False,
) -> dict[str, ApplicationExecutor]:
    """Bind trusted executors through the existing immutable capability catalog.

    Disabled capabilities never gain execution authority, even if the
    composition root supplies a callable. Unknown, reserved or malformed
    registrations fail before routing. require_enabled is used by the
    composition root; the candidate dispatcher retains its historical
    per-route safe failure for unavailable optional executors.
    """
    if not isinstance(catalog, ApplicationCatalog) or not isinstance(trusted, Mapping):
        raise ValueError("A trusted application catalog and executor mapping are required")
    registered = {capability.id for capability in catalog.capabilities()}
    if any(
        not isinstance(capability_id, str)
        or capability_id not in registered
        or (executor is not None and not callable(executor))
        for capability_id, executor in trusted.items()
    ):
        raise ValueError("Application executor is unregistered or not callable")

    bound: dict[str, ApplicationExecutor] = {}
    for capability in catalog.capabilities():
        if not capability.enabled:
            continue
        executor = trusted.get(capability.id)
        if executor is None:
            if require_enabled:
                raise ValueError("Enabled application executor is unavailable")
            continue
        bound[capability.id] = executor
    return bound
