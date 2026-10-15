"""E2 optional context-aware Core Planner port, preserving legacy factory ABI.

This is a *read-only preparation* boundary. NoteMentions are untrusted
candidate hints; the current Core planner/Writer still owns all write choices.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from odyssey_core.execution_context import ExecutionContext


@runtime_checkable
class ContextAwareCorePlannerFactory(Protocol):
    """A new planner adapter may consume the whole validated E2 envelope."""

    def create_for_context(self, context: ExecutionContext) -> object:
        """Construct the ordinary Core planner, not an alternate Writer."""
        ...
