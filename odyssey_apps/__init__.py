"""Closed application descriptors used by runtime composition.

Applications may depend on Odyssey Core.  Core deliberately does not import this package.
"""

from .catalog import (
    CORE_CAPABILITY_ID,
    TEMPORAL_CAPABILITY_ID,
    ApplicationCatalog,
    ApplicationDescriptor,
    ApplicationRegistry,
    RoutingCapability,
)
from .router import (
    OpenAIApplicationRouter,
    Route,
    RouteOutcome,
    RoutePlan,
    RouterError,
    parse_route_plan,
    route_plan_json_schema,
    validate_route_plan,
)

__all__ = [
    "ApplicationCatalog",
    "ApplicationDescriptor",
    "ApplicationRegistry",
    "CORE_CAPABILITY_ID",
    "TEMPORAL_CAPABILITY_ID",
    "OpenAIApplicationRouter",
    "Route",
    "RouteOutcome",
    "RoutePlan",
    "RouterError",
    "RoutingCapability",
    "parse_route_plan",
    "route_plan_json_schema",
    "validate_route_plan",
]
