"""E2 stable, bounded display hints for observed stages, never synthetic events.

Presentation is derived from observed stage IDs, not from prompt content or a
client-side catalog. Unknown App names receive a safe generic view; no client
release is required to display a newly registered `capability.operation`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_STAGE_NAME = re.compile(r"[a-zA-Z][a-zA-Z0-9_.-]{0,79}\Z")
_ALLOWED_ICONS = frozenset(
    {"router", "temporal", "planner", "tasks", "core", "git", "index", "pending", "result"}
)


@dataclass(frozen=True, slots=True)
class StageView:
    version: int
    label: str
    icon: str

    def __post_init__(self) -> None:
        if (
            self.version != 1
            or not isinstance(self.label, str)
            or not 1 <= len(self.label) <= 80
            or not isinstance(self.icon, str)
            or self.icon not in _ALLOWED_ICONS
        ):
            raise ValueError("Stage view violates the public presentation contract")

    def to_response(self) -> dict[str, str | int]:
        return {"version": self.version, "label": self.label, "icon": self.icon}


_KNOWN = {
    "application.router": ("Router", "router"),
    "candidate.source_proposal": ("Router", "router"),
    "candidate.router_revision": ("Router · corrección", "router"),
    "candidate.source_boundary_review": ("Core · revisión de la división", "core"),
    "candidate.temporal_interpretation": ("Temporal", "temporal"),
    "planner": ("Planner", "planner"),
    "temporal.interpretation": ("Temporal", "temporal"),
    "temporal.coherence": ("Coherencia de fechas", "temporal"),
    "tasks.interpretation": ("Tasks", "tasks"),
    "git": ("Git", "git"),
    "index_barrier": ("Índices", "index"),
    "pending": ("Pendientes", "pending"),
}


def stage_view_for(name: str) -> StageView:
    """Make a safe generic label/icon without changing observed stage identity."""
    if not isinstance(name, str) or _STAGE_NAME.fullmatch(name) is None:
        return StageView(1, "Etapa", "result")
    if name in _KNOWN:
        label, icon = _KNOWN[name]
        return StageView(1, label, icon)
    if name.startswith(("action.write", "write")):
        return StageView(1, "Core · guardar", "core")
    if name.startswith("action."):
        return StageView(1, "Core · " + name[7:].replace(".", " · ")[:65], "core")
    namespace = name.split(".", 1)[0]
    icon = {
        "candidate": "core",
        "core": "core",
        "application": "router",
        "temporal": "temporal",
        "tasks": "tasks",
        "git": "git",
        "index": "index",
        "planner": "planner",
        "pending": "pending",
    }.get(namespace, "result")
    label = name.replace("_", " ").replace(".", " · ")[:80]
    return StageView(1, label, icon)
