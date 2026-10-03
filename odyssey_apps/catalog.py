"""Small immutable application registration and availability primitives.

This module deliberately contains routing evidence only.  It neither imports Core nor exposes
application execution, persistence, or dynamic discovery behavior.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CORE_CAPABILITY_ID = "core"


def _validate_identifier(value: str, *, field: str) -> str:
    """Return one compact stable identifier or reject malformed routing metadata."""
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"Application {field} must be a non-empty trimmed string")
    if not value.replace("-", "").replace("_", "").isalnum():
        raise ValueError(
            f"Application {field} must use only letters, digits, hyphens, or underscores"
        )
    return value


@dataclass(frozen=True, slots=True)
class ApplicationDescriptor:
    """Describe one registered application's compact router-facing capabilities.

    Args:
        id: Stable application capability identifier.
        routing_description: Compact plain-language routing evidence.
        dependencies: Stable lower-level capability identifiers.

    Raises:
        ValueError: If any descriptor field is malformed or dependencies repeat.
    """

    id: str
    routing_description: str
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate descriptor metadata before it enters the closed registry."""
        _validate_identifier(self.id, field="id")
        if self.id == CORE_CAPABILITY_ID:
            raise ValueError("Application id 'core' is reserved for the built-in destination")
        if (
            not isinstance(self.routing_description, str)
            or not self.routing_description.strip()
            or self.routing_description.strip() != self.routing_description
        ):
            raise ValueError("Application routing_description must be a non-empty trimmed string")
        if not isinstance(self.dependencies, tuple):
            raise ValueError("Application dependencies must be a tuple")
        dependencies = tuple(
            _validate_identifier(dependency, field="dependency") for dependency in self.dependencies
        )
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("Application dependencies must be unique")
        if self.id in dependencies:
            raise ValueError("Application cannot depend on itself")


@dataclass(frozen=True, slots=True)
class RoutingCapability:
    """Represent the complete immutable router-facing state of one registered application."""

    id: str
    routing_description: str
    dependencies: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True, slots=True)
class ApplicationCatalog:
    """Expose registered capabilities and deterministic runtime availability.

    Catalog entries are compact router evidence, not executors.  In particular, a disabled
    descriptor remains visible with ``enabled=False`` but cannot be selected for execution.
    """

    _entries: tuple[tuple[ApplicationDescriptor, bool], ...] = ()

    def __post_init__(self) -> None:
        """Reject non-canonical entries so runtime availability cannot be ambiguous."""
        ids: set[str] = set()
        for descriptor, enabled in self._entries:
            if not isinstance(descriptor, ApplicationDescriptor) or not isinstance(enabled, bool):
                raise ValueError(
                    "Application catalog entries must contain a descriptor and bool state"
                )
            if descriptor.id in ids:
                raise ValueError(f"Duplicate application id: {descriptor.id}")
            ids.add(descriptor.id)

    @classmethod
    def empty(cls) -> ApplicationCatalog:
        """Return the no-application catalog used by ordinary Core-only composition."""
        return cls()

    def capabilities(self) -> tuple[RoutingCapability, ...]:
        """Return compact registered routing evidence in stable identifier order."""
        return tuple(
            RoutingCapability(
                id=descriptor.id,
                routing_description=descriptor.routing_description,
                dependencies=descriptor.dependencies,
                enabled=enabled,
            )
            for descriptor, enabled in self._entries
        )

    def executable(self, capability_id: str) -> ApplicationDescriptor | None:
        """Return an enabled descriptor only; disabled entries are never executable."""
        for descriptor, enabled in self._entries:
            if descriptor.id == capability_id:
                return descriptor if enabled else None
        return None


@dataclass(frozen=True, slots=True)
class ApplicationRegistry:
    """Hold a closed immutable set of application descriptors for one composition root."""

    descriptors: tuple[ApplicationDescriptor, ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed or duplicate registrations before runtime composition."""
        ids: set[str] = set()
        for descriptor in self.descriptors:
            if not isinstance(descriptor, ApplicationDescriptor):
                raise ValueError("Application registry entries must be descriptors")
            if descriptor.id in ids:
                raise ValueError(f"Duplicate application id: {descriptor.id}")
            ids.add(descriptor.id)

    @classmethod
    def from_descriptors(cls, descriptors: Iterable[ApplicationDescriptor]) -> ApplicationRegistry:
        """Build one closed registry from an explicit deterministic descriptor sequence."""
        return cls(tuple(descriptors))

    def catalog(self, *, enabled_ids: Iterable[str] = ()) -> ApplicationCatalog:
        """Project explicit enabled IDs into compact registered availability evidence.

        Raises:
            ValueError: If enablement refers to an unknown or repeated application ID.
        """
        enabled = tuple(enabled_ids)
        if len(set(enabled)) != len(enabled):
            raise ValueError("Enabled application ids must be unique")
        registered_ids = {descriptor.id for descriptor in self.descriptors}
        unknown = set(enabled) - registered_ids
        if unknown:
            raise ValueError(
                f"Enabled application ids are not registered: {', '.join(sorted(unknown))}"
            )
        return ApplicationCatalog(
            tuple(
                (descriptor, descriptor.id in enabled)
                for descriptor in sorted(self.descriptors, key=lambda item: item.id)
            )
        )
