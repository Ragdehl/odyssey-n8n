"""Closed application descriptors used by runtime composition.

Applications may depend on Odyssey Core.  Core deliberately does not import this package.
"""

from .catalog import (
    ApplicationCatalog,
    ApplicationDescriptor,
    ApplicationRegistry,
    RoutingCapability,
)

__all__ = [
    "ApplicationCatalog",
    "ApplicationDescriptor",
    "ApplicationRegistry",
    "RoutingCapability",
]
