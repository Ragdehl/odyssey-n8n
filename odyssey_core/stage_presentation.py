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
    "application.source_processing": ("Interpretación del mensaje", "router"),
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
    if name.startswith("provider."):
        # Keep model/provider identifiers out of user-facing diagnostic prose;
        # every provider substep reuses one stable E2 presentation.
        return StageView(1, "Consulta al servicio de IA", "planner")
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


# The existing product milestones use *real* dispatcher callbacks. This
# presentation contract is shared by the progress store and all consumers;
# it does not infer that an unobserved step has happened.
_PROGRESS_COPY = {
    "starting": "Preparando tu solicitud…",
    "routing.started": "Entendiendo tu mensaje…",
    "routing.boundary_review_started": "Comprobando que las partes conservan su significado…",
    "routing.boundary_review_ready": "He verificado la división del mensaje.",
    "routing.boundary_review_required": "Necesito revisar cómo se relacionan las partes.",
    "routing.ready": "He entendido cómo dividir tu mensaje.",
    "temporal.started": "Interpretando fechas y horas…",
    "temporal.ready": "He interpretado la fecha y la hora.",
    "planner.started": "Organizando la información…",
    "planner.ready": "He identificado las referencias importantes.",
    "action.retrieve.started": "Buscando la información relacionada…",
    "action.delegate.started": "Preparando la siguiente acción…",
    "action.write.started": "Guardando la información…",
    "finalizing": "Terminando…",
}
_PROGRESS_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")
_PROGRESS_SUFFIXES = (".started", ".ready", ".failed", ".required")


def progress_stage_view(stage: str) -> StageView | None:
    """Describe an *observed* milestone with no arbitrary source-derived text.

    Unknown future Apps get their own readable label, but not a fabricated
    progress percentage. Unbounded/untrusted strings never enter the UI.
    """
    if not isinstance(stage, str) or _PROGRESS_NAME.fullmatch(stage) is None:
        return None
    if stage in _PROGRESS_COPY:
        base = stage.rsplit(".", 1)[0]
        if base == "routing" or base.startswith("routing."):
            icon = "router"
        elif base.startswith("action"):
            icon = "core"
        elif base in {"starting", "finalizing"}:
            icon = "result"
        else:
            icon = stage_view_for(base).icon
        return StageView(1, _PROGRESS_COPY[stage], icon)
    if not stage.endswith(_PROGRESS_SUFFIXES):
        return None
    base, state = stage.rsplit(".", 1)
    if not base or base in {"starting", "finalizing"}:
        return None
    view = stage_view_for(base)
    suffix = {
        "started": " · en curso",
        "ready": " · preparado",
        "failed": " · error",
        "required": " · revisión necesaria",
    }[state]
    return StageView(1, (view.label[: 80 - len(suffix)] + suffix), view.icon)
