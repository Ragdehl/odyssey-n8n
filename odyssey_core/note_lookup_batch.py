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

from .candidate_context import CoreCandidateContext
from .canonical_source_context import CanonicalSourceNameHint, source_note_role_spans
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
from .identity import ExactEntityResolution, resolve_exact_entities_batch, resolve_exact_entity
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


def note_lookup_requests_from_source_roles(
    context: CoreCandidateContext,
) -> tuple[NoteLookupRequest, ...]:
    """Convert existing Core-validated Router role spans to read-only queries.

    Every mention carries its own exact occurrence. An oversized candidate
    set fails CLOSED for this optional enrichment; no first-N truncation and
    no cross-route/cross-source shortcut. A missing role means no lookup.
    """
    spans = source_note_role_spans(context)
    if len(spans) > MAX_MENTION_LOOKUPS:
        raise ContextContractError("Source-role Note lookup exceeds bounded mention budget")
    return tuple(NoteLookupRequest(span.text, span.start, span.end) for span in spans)


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
        frozenset({ContextPort.NOTE_MENTIONS, ContextPort.SOURCE_NOTE_HINTS, ContextPort.PENDING}),
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

        def find(
            request: NoteLookupRequest,
            outcome: ExactEntityResolution | None = None,
        ) -> tuple[NoteMention, PendingContext | None]:
            if request.note_type is not None and request.note_type not in referenceable:
                return NoteMention(request.text, (), request.start, request.end), PendingContext(
                    "core.note_lookup_exact",
                    "APP_MANAGED_NOTE_IDENTITY",
                    request.text,
                    request.start,
                    request.end,
                )
            if outcome is None:
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

        # Reuse Core canonical evidence to prepare the SAME exact-name prompt
        # hints that Luna previously assembled in a SECOND full-vault scan.
        # Aliases and ambiguous matches never become unique source-name hints.
        hints_by_name: dict[str, CanonicalSourceNameHint] = {}

        # Ordinary Core lookup needs only ONE vault scan, not one scan per
        # mention. The real batch has the same canonical exact/alias rules.
        # Optional custom lookups retain a concurrent test/adaptor port; the
        # outer context can execute this whole stage in parallel with Temporal.
        if self._lookup is resolve_exact_entity:
            scanned = (
                resolve_exact_entities_batch(
                    self._repository,
                    self._schema,
                    tuple(
                        (request.text, request.note_type)
                        for request in self._requests
                        if request.note_type is None or request.note_type in referenceable
                    ),
                )
                if any(
                    request.note_type is None or request.note_type in referenceable
                    for request in self._requests
                )
                else ()
            )
            iterator = iter(scanned)

            def from_scan(request: NoteLookupRequest):
                if request.note_type is not None and request.note_type not in referenceable:
                    return find(request)  # returns pending with no vault read
                outcome = next(iterator)
                if (
                    len(outcome.candidates) == 1
                    and outcome.candidates[0].primary_name.casefold() == request.text.casefold()
                ):
                    candidate = outcome.candidates[0]
                    hints_by_name.setdefault(
                        request.text.casefold(),
                        CanonicalSourceNameHint(
                            request.text,
                            candidate.primary_name,
                            candidate.type,
                            candidate.content_excerpt,
                        ),
                    )
                return find(request, outcome)

            results = tuple(from_scan(request) for request in self._requests)
        else:
            # Injected resolver implementations may perform genuinely
            # independent work; retain bounded parallel execution for those.
            with ThreadPoolExecutor(
                max_workers=min(self._max_workers, len(self._requests))
            ) as pool:
                results = tuple(pool.map(find, self._requests))
        return StageOutput(
            note_mentions=tuple(item for item, _ in results),
            source_note_hints=tuple(hints_by_name.values())[:16],
            pending=tuple(reason for _, reason in results if reason is not None),
        )
