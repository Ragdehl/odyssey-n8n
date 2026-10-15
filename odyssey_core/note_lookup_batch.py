"""E2 bounded parallel preparation of *independent* canonical Note mention candidates.

Reuses the existing Core exact resolver; it does not mint trusted identities or
bypass canonical NoteSchema identity rules. Contextual/anaphoric decisions and
write-time freshness checks still belong to Core. Reads must be from a stable
local vault snapshot or treated as speculative until Core rechecks freshness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .execution_context import (
    ContextContractError,
    ContextPort,
    NoteMention,
    NoteReferenceCandidate,
    PendingContext,
    StageInput,
    StageOutput,
    StageSpec,
)
from .identity import ExactEntityResolution, resolve_exact_entity
from .schema_types import referenceable_type_ids
from .storage import VaultRepository

MAX_MENTION_LOOKUPS = 12
MAX_LOOKUP_WORKERS = 3


@dataclass(frozen=True, slots=True)
class NoteLookupRequest:
    """A previously extracted, exact character-offset source mention.

    Proposing mentions is a source interpretation, not the job of the Note
    lookup stage; no substring scanning or invented lexical identities here.
    """

    text: str
    start: int
    end: int
    note_type: str | None = None

    def validate(self, source: str) -> None:
        if (
            not isinstance(self.text, str)
            or not self.text.strip()
            or len(self.text) > 240
            or type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= len(source)
            or source[self.start : self.end] != self.text
            or self.note_type is not None
            and (not isinstance(self.note_type, str) or not self.note_type.strip())
        ):
            raise ContextContractError("Note lookup must retain exact original source offsets")


class ParallelExactNoteLookup:
    """Core-compatible local exact-name lookup stage, never an authorization.

    For referenceable types, every occurrence is evaluated independently with
    the already-tested exact canonical resolver. Multi-matches remain ambiguous;
    no match is merely missing *exact* evidence, not proof the Note is absent.
    Managed app types are left pending, not silently reclassified as person.
    No provider/LLM calls or writes run in these workers.
    """

    spec = StageSpec(
        "core.note_lookup_exact",
        frozenset({ContextPort.SOURCE}),
        frozenset({ContextPort.NOTE_MENTIONS, ContextPort.PENDING}),
    )

    def __init__(
        self,
        *,
        requests: tuple[NoteLookupRequest, ...],
        repository: VaultRepository,
        schema: Mapping[str, Any],
        max_workers: int = MAX_LOOKUP_WORKERS,
        lookup: Callable[..., ExactEntityResolution] = resolve_exact_entity,
    ) -> None:
        if (
            not isinstance(requests, tuple)
            or not 1 <= len(requests) <= MAX_MENTION_LOOKUPS
            or any(not isinstance(item, NoteLookupRequest) for item in requests)
            or type(max_workers) is not int
            or not 1 <= max_workers <= MAX_LOOKUP_WORKERS
        ):
            raise ContextContractError("Parallel Note lookup batch is unbounded or malformed")
        self._requests = requests
        self._repository = repository
        self._schema = schema
        self._max_workers = max_workers
        self._lookup = lookup

    def execute(self, data: StageInput) -> StageOutput:
        if not isinstance(data.source, str):
            raise ContextContractError("Note lookup requires an unmodified source")
        source = data.source
        for request in self._requests:
            request.validate(source)
        ranges = [(request.start, request.end) for request in self._requests]
        if len(set(ranges)) != len(ranges):
            raise ContextContractError("Duplicate source occurrences must not be resolved twice")
        # A type can be known by schema but managed by an app. It is NOT
        # eligible for ordinary Core exact identity discovery.
        referenceable = referenceable_type_ids(self._schema)
        all_types = {item["id"] for item in self._schema.get("types", ())}
        for request in self._requests:
            if request.note_type is not None and request.note_type not in all_types:
                raise ContextContractError("Note lookup type is not in canonical NoteSchema")

        def find(request: NoteLookupRequest) -> tuple[NoteMention, PendingContext | None]:
            if request.note_type is not None and request.note_type not in referenceable:
                return NoteMention(request.text, (), request.start, request.end), PendingContext(
                    "core.note_lookup_exact",
                    "APP_MANAGED_NOTE_IDENTITY",
                    request.text,
                    request.start,
                    request.end,
                )
            outcome = self._lookup(
                self._repository, self._schema, request.text, type=request.note_type
            )
            if not isinstance(outcome, ExactEntityResolution):
                raise ContextContractError("Core exact lookup returned an invalid result")
            if any(
                candidate.type not in referenceable
                or request.note_type is not None
                and candidate.type != request.note_type
                for candidate in outcome.candidates
            ):
                raise ContextContractError("Core lookup returned an unauthorized Note type")
            # Never silently truncate a large ambiguity: either keep the full
            # bounded candidate set or require independent clarification.
            overflow = len(outcome.candidates) > 8
            mention = NoteMention(
                request.text,
                ()
                if overflow
                else tuple(
                    NoteReferenceCandidate(candidate.id, candidate.type, candidate.primary_name)
                    for candidate in outcome.candidates
                ),
                request.start,
                request.end,
            )
            if not outcome.candidates or overflow or len(outcome.candidates) > 1:
                code = (
                    "NO_EXACT_MATCH"
                    if not outcome.candidates
                    else "EXACT_MATCH_SET_TOO_LARGE"
                    if overflow
                    else "AMBIGUOUS_EXACT_MATCH"
                )
                return mention, PendingContext(
                    "core.note_lookup_exact", code, request.text, request.start, request.end
                )
            return mention, None

        # map returns results in source request order even when workers finish
        # out of order. An exception aborts the whole stage; no partial merge.
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(self._requests))) as pool:
            results = tuple(pool.map(find, self._requests))
        return StageOutput(
            note_mentions=tuple(item for item, _ in results),
            pending=tuple(reason for _, reason in results if reason is not None),
        )
