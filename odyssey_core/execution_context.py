"""E2: minimal, immutable source/authority envelope for composable Odyssey stages.

This is an assembly contract over *existing* Core domain evidence, not another
source of truth for identity or writing. Router and Apps supply proposals; Core
alone can resolve canonical targets and authorize persistence. The stage input
view intentionally exposes only declared read dependencies.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .candidate_context import CoreCandidateContext
from .canonical_source_context import CanonicalSourceNameHint
from .domain_interpretation import DomainEvidence, DomainInterpretation
from .identity_boundary import AuthenticatedActorContext
from .temporal_resolution import TemporalResolution, TemporalResolutionKind

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_CAPABILITY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


class ContextContractError(ValueError):
    """An incompatible, altered or unauthorized context handoff was rejected."""


class ContextPort(StrEnum):
    """Closed stage ports; adding a capability must not expose mutation authority."""

    SOURCE = "source"
    CLOCK = "clock"
    ACTOR = "actor"
    CANDIDATES = "candidates"
    DOMAIN = "domain"
    TEMPORAL = "temporal"
    PENDING = "pending"
    NOTE_MENTIONS = "note_mentions"
    MANAGED_NOTES = "managed_notes"
    SOURCE_NOTE_HINTS = "source_note_hints"


@dataclass(frozen=True, slots=True)
class NoteReferenceCandidate:
    """Generic Note identity, including person, Task, Work Session or future types.

    This is an immutable value. Possessing it conveys no write permission and
    does not prove a mention matches it; only canonical Core lookup may do so.
    """

    stable_note_id: str
    note_type: str
    canonical_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.stable_note_id, str)
            or _ID.fullmatch(self.stable_note_id) is None
            or not isinstance(self.note_type, str)
            or _CAPABILITY.fullmatch(self.note_type) is None
            or not isinstance(self.canonical_name, str)
            or not self.canonical_name.strip()
            or len(self.canonical_name) > 240
        ):
            raise ContextContractError("Canonical Note reference is invalid")


@dataclass(frozen=True, slots=True)
class NoteMention:
    """Untrusted, source-anchored possible Note references of ANY NoteSchema type.

    Candidate note IDs are read-only hints for Core. The current repository,
    ownership and ambiguity must be validated again before creating a wikilink.
    """

    source_text: str
    candidates: tuple[NoteReferenceCandidate, ...]
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_text, str)
            or not self.source_text.strip()
            or len(self.source_text) > 240
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > 8
            or any(not isinstance(item, NoteReferenceCandidate) for item in self.candidates)
            or len({item.stable_note_id for item in self.candidates}) != len(self.candidates)
            or (self.start is None) != (self.end is None)
            or self.start is not None
            and (
                type(self.start) is not int
                or type(self.end) is not int
                or self.start < 0
                or self.end - self.start != len(self.source_text)
            )
        ):
            raise ContextContractError("Note mentions must be bounded source proposals")


@dataclass(frozen=True, slots=True)
class ManagedNoteHandle:
    """Read-only identity of an app-owned/virtual Note; no right to link or write."""

    stable_note_id: str
    note_type: str
    owner: str
    materialized: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.stable_note_id, str)
            or not self.stable_note_id.strip()
            or not isinstance(self.note_type, str)
            or not self.note_type.strip()
            or not isinstance(self.owner, str)
            or not self.owner.strip()
            or type(self.materialized) is not bool
        ):
            raise ContextContractError("Managed identity evidence is invalid")


@dataclass(frozen=True, slots=True)
class QualitativeTime:
    """Preserve an exact non-clock precision qualifier alongside a verified date.

    A Temporal adapter supplies this value after interpreting the original
    source. No static dictionary decides that 'tarde' starts at 15:00.
    """

    source_text: str
    date: str
    qualifier: str
    timezone: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_text, str)
            or not self.source_text.strip()
            or not isinstance(self.qualifier, str)
            or not self.qualifier.strip()
            or self.source_text.count(self.qualifier) != 1
            or not isinstance(self.timezone, str)
            or len(self.source_text) > 240
            or len(self.qualifier) > 80
        ):
            raise ContextContractError("Qualitative time qualifier is not source-grounded")
        try:
            ZoneInfo(self.timezone)
            TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=self.date)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ContextContractError("Qualitative time date or zone is invalid") from error


@dataclass(frozen=True, slots=True)
class PendingContext:
    """A bounded unresolved observation, optionally tied to one exact source span."""

    capability: str
    reason: str
    source_text: str | None = None
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability, str)
            or _CAPABILITY.fullmatch(self.capability) is None
            or not isinstance(self.reason, str)
            or not self.reason
            or len(self.reason) > 120
            or (self.source_text is None) != (self.start is None)
            or (self.start is None) != (self.end is None)
            or self.source_text is not None
            and (
                not isinstance(self.source_text, str)
                or not self.source_text.strip()
                or len(self.source_text) > 240
                or type(self.start) is not int
                or type(self.end) is not int
                or self.start < 0
                or self.end - self.start != len(self.source_text)
            )
        ):
            raise ContextContractError("Pending context is invalid")


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Immutable, source-bound envelope reusing existing Core contracts.

    Trusted actor and source come exclusively from the runtime/ingress. No
    StageOutput field can replace them, assert Note identity, or mint a write.
    """

    request_id: str
    source: str
    captured_at: str
    timezone: str
    authenticated_actor: AuthenticatedActorContext | None = None
    conversation_id: str | None = None
    candidates: CoreCandidateContext | None = None
    domains: tuple[DomainInterpretation, ...] = ()
    note_mentions: tuple[NoteMention, ...] = ()
    source_note_hints: tuple[CanonicalSourceNameHint, ...] = ()
    managed_notes: tuple[ManagedNoteHandle, ...] = ()
    qualitative_times: tuple[QualitativeTime, ...] = ()
    pending: tuple[PendingContext, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if (
            type(self.version) is not int
            or self.version != 1
            or not isinstance(self.request_id, str)
            or _ID.fullmatch(self.request_id) is None
            or not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > 4096
            or self.conversation_id is not None
            and (
                not isinstance(self.conversation_id, str)
                or _ID.fullmatch(self.conversation_id) is None
            )
            or self.authenticated_actor is not None
            and not isinstance(self.authenticated_actor, AuthenticatedActorContext)
        ):
            raise ContextContractError("Execution source or authenticated boundary is invalid")
        try:
            instant = datetime.fromisoformat(self.captured_at)
            if instant.utcoffset() is None:
                raise ValueError("timestamp is not timezone-aware")
            ZoneInfo(self.timezone)
        except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
            raise ContextContractError("Execution clock is invalid") from error
        if self.candidates is not None:
            if not isinstance(self.candidates, CoreCandidateContext):
                raise ContextContractError("Candidate context is not typed")
            self.candidates.validate(self.source)
        if (
            not isinstance(self.domains, tuple)
            or len(self.domains) > 16
            or any(
                not isinstance(domain, DomainInterpretation) or domain.source_text != self.source
                for domain in self.domains
            )
            or len({domain.capability_id for domain in self.domains}) != len(self.domains)
        ):
            raise ContextContractError("Domain evidence source/owner is inconsistent")
        if (
            not isinstance(self.note_mentions, tuple)
            or len(self.note_mentions) > 24
            or any(
                not isinstance(item, NoteMention)
                or item.source_text not in self.source
                or item.start is not None
                and self.source[item.start : item.end] != item.source_text
                for item in self.note_mentions
            )
        ):
            raise ContextContractError("Note reference proposal is not source-grounded")
        if (
            not isinstance(self.source_note_hints, tuple)
            or len(self.source_note_hints) > 16
            or any(
                not isinstance(hint, CanonicalSourceNameHint)
                or not hint.mention
                or hint.mention not in self.source
                or not hint.name
                or not hint.note_type
                or len(hint.content_excerpt) > 320
                for hint in self.source_note_hints
            )
        ):
            raise ContextContractError("Canonical name hints are not source-grounded")
        if (
            not isinstance(self.managed_notes, tuple)
            or len(self.managed_notes) > 16
            or any(not isinstance(item, ManagedNoteHandle) for item in self.managed_notes)
            or len({(item.note_type, item.stable_note_id) for item in self.managed_notes})
            != len(self.managed_notes)
        ):
            raise ContextContractError("Managed Note identities cannot be duplicated or forged")
        if (
            not isinstance(self.qualitative_times, tuple)
            or len(self.qualitative_times) > 8
            or any(
                not isinstance(item, QualitativeTime)
                or item.source_text not in self.source
                or item.timezone != self.timezone
                for item in self.qualitative_times
            )
            or not isinstance(self.pending, tuple)
            or len(self.pending) > 16
            or any(
                not isinstance(item, PendingContext)
                or item.start is not None
                and self.source[item.start : item.end] != item.source_text
                for item in self.pending
            )
        ):
            raise ContextContractError("Execution temporal or pending evidence is inconsistent")
        date_sources = {
            (evidence.source_text, evidence.value[:10])
            for domain in self.domains
            for evidence in domain.temporal_references()
        }
        if any(
            (item.source_text, item.date) not in date_sources for item in self.qualitative_times
        ):
            raise ContextContractError("Qualitative time needs a verified temporal date anchor")


@dataclass(frozen=True, slots=True)
class StageSpec:
    """Declarative read/write ports for a capability; never an authorization list."""

    capability: str
    requires: frozenset[ContextPort]
    provides: frozenset[ContextPort]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability, str)
            or _CAPABILITY.fullmatch(self.capability) is None
            or not isinstance(self.requires, frozenset)
            or not all(isinstance(port, ContextPort) for port in self.requires)
            or not isinstance(self.provides, frozenset)
            or not self.provides
            <= {
                ContextPort.CANDIDATES,
                ContextPort.DOMAIN,
                ContextPort.TEMPORAL,
                ContextPort.PENDING,
                ContextPort.NOTE_MENTIONS,
                ContextPort.MANAGED_NOTES,
                ContextPort.SOURCE_NOTE_HINTS,
            }
        ):
            raise ContextContractError("Stage port declaration is invalid")


@dataclass(frozen=True, slots=True)
class StageInput:
    """Least-privilege projection: absent ports are *not* accessible to a stage."""

    source: str | None = None
    captured_at: str | None = None
    timezone: str | None = None
    actor: AuthenticatedActorContext | None = None
    candidates: CoreCandidateContext | None = None
    domains: tuple[DomainInterpretation, ...] = ()
    note_mentions: tuple[NoteMention, ...] = ()
    source_note_hints: tuple[CanonicalSourceNameHint, ...] = ()
    managed_notes: tuple[ManagedNoteHandle, ...] = ()
    temporal_references: tuple[DomainEvidence, ...] = ()
    qualitative_times: tuple[QualitativeTime, ...] = ()


@dataclass(frozen=True, slots=True)
class StageOutput:
    """Stage proposals only; independent Core authorization is still required."""

    candidates: CoreCandidateContext | None = None
    domains: tuple[DomainInterpretation, ...] = ()
    note_mentions: tuple[NoteMention, ...] = ()
    source_note_hints: tuple[CanonicalSourceNameHint, ...] = ()
    managed_notes: tuple[ManagedNoteHandle, ...] = ()
    qualitative_times: tuple[QualitativeTime, ...] = ()
    pending: tuple[PendingContext, ...] = ()


@runtime_checkable
class ContextStage(Protocol):
    """Structural protocol: plug capabilities into the same checked seam."""

    spec: StageSpec

    def execute(self, data: StageInput) -> StageOutput:
        """Run without mutating canonical storage or trusted ingress facts."""
        ...


def stage_input(context: ExecutionContext, spec: StageSpec) -> StageInput:
    """Validate dependencies before invocation and expose only requested ports."""
    if not isinstance(context, ExecutionContext) or not isinstance(spec, StageSpec):
        raise ContextContractError("Stage boundary requires typed context and port specification")
    missing = (
        {ContextPort.CANDIDATES}
        if ContextPort.CANDIDATES in spec.requires and context.candidates is None
        else set()
    )
    if ContextPort.ACTOR in spec.requires and context.authenticated_actor is None:
        missing.add(ContextPort.ACTOR)
    if ContextPort.DOMAIN in spec.requires and not context.domains:
        missing.add(ContextPort.DOMAIN)
    verified_temporal = tuple(
        evidence for domain in context.domains for evidence in domain.temporal_references()
    )
    if ContextPort.TEMPORAL in spec.requires and not verified_temporal:
        missing.add(ContextPort.TEMPORAL)
    if ContextPort.NOTE_MENTIONS in spec.requires and not context.note_mentions:
        missing.add(ContextPort.NOTE_MENTIONS)
    if ContextPort.MANAGED_NOTES in spec.requires and not context.managed_notes:
        missing.add(ContextPort.MANAGED_NOTES)
    if ContextPort.SOURCE_NOTE_HINTS in spec.requires and not context.source_note_hints:
        missing.add(ContextPort.SOURCE_NOTE_HINTS)
    if missing:
        raise ContextContractError(f"Missing required context ports: {sorted(missing)}")
    return StageInput(
        source=context.source if ContextPort.SOURCE in spec.requires else None,
        captured_at=context.captured_at if ContextPort.CLOCK in spec.requires else None,
        timezone=context.timezone if ContextPort.CLOCK in spec.requires else None,
        actor=context.authenticated_actor if ContextPort.ACTOR in spec.requires else None,
        candidates=context.candidates if ContextPort.CANDIDATES in spec.requires else None,
        domains=context.domains if ContextPort.DOMAIN in spec.requires else (),
        note_mentions=(context.note_mentions if ContextPort.NOTE_MENTIONS in spec.requires else ()),
        source_note_hints=(
            context.source_note_hints if ContextPort.SOURCE_NOTE_HINTS in spec.requires else ()
        ),
        managed_notes=(context.managed_notes if ContextPort.MANAGED_NOTES in spec.requires else ()),
        temporal_references=(verified_temporal if ContextPort.TEMPORAL in spec.requires else ()),
        qualitative_times=(
            context.qualitative_times if ContextPort.TEMPORAL in spec.requires else ()
        ),
    )


def apply_stage_output(
    context: ExecutionContext, spec: StageSpec, output: StageOutput
) -> ExecutionContext:
    """Join independent proposals without overwriting source, actor or prior facts."""
    if not isinstance(output, StageOutput):
        raise ContextContractError("Stage must return a typed StageOutput")
    claimed = set()
    if output.candidates is not None:
        claimed.add(ContextPort.CANDIDATES)
    if output.domains:
        claimed.add(ContextPort.DOMAIN)
    if output.qualitative_times:
        claimed.add(ContextPort.TEMPORAL)
    if output.note_mentions:
        claimed.add(ContextPort.NOTE_MENTIONS)
    if output.source_note_hints:
        claimed.add(ContextPort.SOURCE_NOTE_HINTS)
    if output.managed_notes:
        claimed.add(ContextPort.MANAGED_NOTES)
    if output.pending:
        claimed.add(ContextPort.PENDING)
    if not claimed <= spec.provides:
        raise ContextContractError("Stage produced an undeclared context port")
    if output.candidates is not None and context.candidates is not None:
        raise ContextContractError("Stage cannot replace established source candidates")
    return replace(
        context,
        candidates=output.candidates or context.candidates,
        domains=context.domains + output.domains,
        note_mentions=context.note_mentions + output.note_mentions,
        source_note_hints=context.source_note_hints + output.source_note_hints,
        managed_notes=context.managed_notes + output.managed_notes,
        qualitative_times=context.qualitative_times + output.qualitative_times,
        pending=context.pending + output.pending,
    )


def run_context_stage(context: ExecutionContext, stage: ContextStage) -> ExecutionContext:
    """Compose one stage via a checked port; no mutation grants or implied retries."""
    if not isinstance(stage, ContextStage) or not isinstance(stage.spec, StageSpec):
        raise ContextContractError("Stage does not implement the runtime port Protocol")
    return apply_stage_output(context, stage.spec, stage.execute(stage_input(context, stage.spec)))


def run_independent_stages(
    context: ExecutionContext, stages: tuple[ContextStage, ...]
) -> ExecutionContext:
    """Prepare independent source-only capabilities in parallel, then merge atomically.

    Reject data dependencies or missing inputs before scheduling any worker.
    This is only for effect-free proposal providers; the canonical Writer and
    operations whose evidence depends on another result remain sequential.
    Exceptions do not produce a partially enriched context.
    """
    if (
        not isinstance(stages, tuple)
        or not 1 <= len(stages) <= 4
        or any(
            not isinstance(stage, ContextStage) or not isinstance(stage.spec, StageSpec)
            for stage in stages
        )
        or len({stage.spec.capability for stage in stages}) != len(stages)
    ):
        raise ContextContractError("Concurrent stage specification is invalid")
    provided = tuple(stage.spec.provides for stage in stages)
    for index, stage in enumerate(stages):
        sibling_ports = frozenset().union(
            *(ports for i, ports in enumerate(provided) if i != index)
        )
        if stage.spec.requires & sibling_ports:
            raise ContextContractError("Dependent stages cannot execute in parallel")
    inputs = tuple(stage_input(context, stage.spec) for stage in stages)
    with ThreadPoolExecutor(max_workers=len(stages)) as executor:
        results = tuple(
            executor.map(lambda pair: pair[0].execute(pair[1]), zip(stages, inputs, strict=True))
        )
    updated = context
    for stage, output in zip(stages, results, strict=True):
        updated = apply_stage_output(updated, stage.spec, output)
    return updated
