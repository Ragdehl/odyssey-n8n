"""Safe semantic enrichment for facts whose canonical destination is already trusted."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from odyssey_core.context import ContextRetrievalError, find_filtered_note_ids
from odyssey_core.contextual import ContextualResolutionError
from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.materialization import capture_calendar_day_literal
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
    normalize_provider_usage,
)
from odyssey_core.persistence import ActorInput, EntityPersistenceResult, PersistenceOperation
from odyssey_core.relational_resolution import (
    RelationalResolutionError,
    resolve_relational_reference,
)
from odyssey_core.relationship_evidence import (
    CanonicalIdentity,
    RelationshipEvidenceError,
    RelationshipEvidenceProjector,
)
from odyssey_core.resolution import (
    ExistingEntityOutcome,
    ExistingEntityResolutionError,
    resolve_existing_entity,
)
from odyssey_core.semantic_write import (
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteCompileError,
    compile_semantic_identity_selection,
    decode_semantic_fact,
    semantic_write_schema_definitions,
)
from odyssey_core.storage import VaultRepository

FIXED_FACT_ENRICHMENT_CONTRACT_VERSION = "fixed-fact-semantic-enrichment-v2"
FIXED_FACT_ENRICHMENT_FORMAT_NAME = "odyssey_fixed_fact_semantic_enrichment_v2"
FIXED_FACT_ENRICHMENT_MAX_OUTPUT_TOKENS = 1024
FIXED_FACT_SET_SEPARATOR = " · "

_FIXED_FACT_PROMPT = """You enrich one exact user-authored fact for a destination already fixed by Odyssey Core.

Return only ordered semantic fact parts. The concatenation of every part.text MUST equal the supplied fact byte-for-byte. Never paraphrase, translate, normalize, omit, reorder, or add text.

Use literal parts for ordinary wording. Use an identity part for an exact occurrence that may denote an existing reusable Odyssey identity. The identity object is lookup evidence only: it never selects a destination, authorizes a mutation, or creates a note. Use binding=self only when the occurrence denotes the authenticated human. When the wording itself defines a bounded identity universe through SELF or one bounded source, emit a described identity with candidate_scope; do not leave that occurrence literal merely because the source or members may not exist. Core, not you, decides whether the bounded source and members resolve. Use extent=complete_set only when the wording denotes the entire finite current set, and one_member otherwise. SOURCE_DESCRIPTION describes the user's bounded source wording; it does not assert that the source exists. Literal is safe for unbounded generic wording that does not define such an identity universe. Never supply stable IDs, paths, Markdown, targets, destinations, note creation, mutation intent, or persistence details.

Return only the strict JSON object."""


class FixedFactCaptureError(RuntimeError):
    """Indicate invalid trusted-destination capture inputs or persistence failure."""


class FixedFactEnricher(Protocol):
    """Describe the one-attempt Core semantic enrichment boundary."""

    def enrich_fixed_fact(self, capture_text: str) -> SemanticFact:
        """Return one exact-partition semantic fact or raise without persistence authority."""


class ManagedFactDestination(Protocol):
    """Persist one already rendered fact to a destination selected outside model output."""

    def persist(
        self,
        rendered_fact: str,
        *,
        actor: ActorInput,
        now: str,
        request_id: str,
    ) -> EntityPersistenceResult:
        """Persist one fact through the destination's established Core primitive."""


@dataclass(frozen=True, slots=True)
class CalendarDayFactDestination:
    """Bind one normalized Calendar date to Core's deterministic managed Day identity."""

    repository: VaultRepository
    schema: dict[str, Any]
    date: str

    def persist(
        self,
        rendered_fact: str,
        *,
        actor: ActorInput,
        now: str,
        request_id: str,
    ) -> EntityPersistenceResult:
        """Persist the fact on this trusted Day without reopening destination selection."""
        return capture_calendar_day_literal(
            repository=self.repository,
            schema=self.schema,
            date=self.date,
            literal=rendered_fact,
            actor=actor,
            now=now,
            request_id=request_id,
        )


@dataclass(frozen=True, slots=True)
class FixedFactCaptureResult:
    """Return bounded evidence for one fixed-destination capture."""

    note_id: str
    changed: bool
    history: GitHistoryResult
    rendered_fact: str
    enriched: bool
    operational: OperationalEvidence = OperationalEvidence()


def fixed_fact_enrichment_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return the separate closed provider schema for fact parts and identity occurrences only."""
    shared = semantic_write_schema_definitions(schema)
    definition_names = (
        "filter_array",
        "semantic_candidate_scope",
        "semantic_identity",
        "semantic_literal_part",
        "semantic_identity_part",
    )
    definitions = {name: shared[name] for name in definition_names}
    return {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "anyOf": [
                        {"$ref": "#/$defs/semantic_literal_part"},
                        {"$ref": "#/$defs/semantic_identity_part"},
                    ]
                },
            }
        },
        "required": ["parts"],
        "additionalProperties": False,
        "$defs": definitions,
    }


def render_fixed_fact_enrichment_prompt() -> str:
    """Render the versioned scoped prompt without touching ordinary planner instructions."""
    return _FIXED_FACT_PROMPT


def decode_fixed_fact_enrichment(payload: object, capture_text: str) -> SemanticFact:
    """Decode fact parts and require their ordered source text to equal the capture exactly.

    Args:
        payload: Untrusted JSON object from the scoped enrichment model.
        capture_text: Exact already-authorized capture text.

    Returns:
        One semantic fact whose occurrence text is an exact partition of ``capture_text``.

    Raises:
        FixedFactCaptureError: If the payload is open, malformed, unsafe, or changes source text.
    """
    if not isinstance(capture_text, str) or not capture_text.strip():
        raise FixedFactCaptureError("Fixed fact capture text is invalid")
    if not isinstance(payload, dict) or set(payload) != {"parts"}:
        raise FixedFactCaptureError("Fixed fact enrichment fields are invalid")
    try:
        fact = decode_semantic_fact(payload)
    except SemanticWriteCompileError as error:
        raise FixedFactCaptureError("Fixed fact enrichment is invalid") from error
    if not fact.parts or "".join(part.text for part in fact.parts) != capture_text:
        raise FixedFactCaptureError("Fixed fact enrichment changed capture text")
    return fact


def validate_fixed_fact_partition(fact: object, capture_text: str) -> SemanticFact:
    """Revalidate an injected enrichment result before any identity resolution or mutation."""
    if (
        not isinstance(fact, SemanticFact)
        or not isinstance(fact.parts, tuple)
        or not fact.parts
        or not all(isinstance(part, (LiteralPart, IdentityPart)) for part in fact.parts)
        or "".join(part.text for part in fact.parts) != capture_text
    ):
        raise FixedFactCaptureError("Fixed fact enrichment is not an exact text partition")
    return fact


class FixedFactCaptureService:
    """Enrich optional existing references and persist one fact to a trusted destination.

    Destination selection is supplied by Core-owned code, never by model output. Enrichment and
    resolution are advisory: malformed output or any unresolved optional identity preserves literal
    wording. Persistence remains authoritative and is the only mutation performed by this service.
    """

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
        *,
        enricher: FixedFactEnricher | None = None,
        semantic_index: Any | None = None,
        embedder: Any | None = None,
        contextual_reasoner: Any | None = None,
        semantic_set_selector: Any | None = None,
        semantic_limit: int = 10,
        self_binding_repository: SelfBindingRepository | None = None,
        monotonic: Any = perf_counter,
    ) -> None:
        """Bind existing Core resolution, persistence, and optional model dependencies."""
        if (
            not isinstance(semantic_limit, int)
            or isinstance(semantic_limit, bool)
            or semantic_limit < 1
        ):
            raise ValueError("Fixed fact semantic limit must be positive")
        self.repository = repository
        self.schema = schema
        self.history = history
        self.enricher = enricher
        self.semantic_index = semantic_index
        self.embedder = embedder
        self.contextual_reasoner = contextual_reasoner
        self.semantic_set_selector = semantic_set_selector
        self.semantic_limit = semantic_limit
        self.self_binding_repository = self_binding_repository
        self.monotonic = monotonic

    def capture_calendar_day(
        self,
        *,
        date: str,
        capture_text: str,
        request_id: str,
        actor: ActorInput,
        now: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
    ) -> FixedFactCaptureResult:
        """Capture exact text on the Core-derived Calendar Day for ``date``."""
        destination = CalendarDayFactDestination(self.repository, self.schema, date)
        return self.capture(
            destination=destination,
            capture_text=capture_text,
            request_id=request_id,
            actor=actor,
            now=now,
            authenticated_actor=authenticated_actor,
        )

    def capture(
        self,
        *,
        destination: ManagedFactDestination,
        capture_text: str,
        request_id: str,
        actor: ActorInput,
        now: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
    ) -> FixedFactCaptureResult:
        """Persist one exact fact after best-effort existing-only reference enrichment."""
        if (
            not isinstance(capture_text, str)
            or not capture_text.strip()
            or "\n" in capture_text
            or "\r" in capture_text
            or not isinstance(request_id, str)
            or not request_id.strip()
        ):
            raise FixedFactCaptureError("Fixed fact capture input is invalid")
        fact, operational = self._attempt_enrichment(capture_text)
        rendered, enriched = self._render_existing_references(
            fact, capture_text, authenticated_actor
        )
        snapshot = self._begin_history(request_id)
        try:
            persisted = destination.persist(
                rendered,
                actor=actor,
                now=now,
                request_id=request_id,
            )
        except Exception as error:
            raise FixedFactCaptureError("Fixed fact persistence failed") from error
        history = self._record_history(request_id, snapshot, persisted.id)
        return FixedFactCaptureResult(
            persisted.id,
            persisted.operation is not PersistenceOperation.NO_CHANGE,
            history,
            rendered,
            enriched,
            operational,
        )

    def _attempt_enrichment(self, capture_text: str) -> tuple[SemanticFact, OperationalEvidence]:
        """Make at most one semantic attempt and fall back to the complete literal on any failure."""
        if self.enricher is None:
            return SemanticFact((LiteralPart(capture_text),)), OperationalEvidence()
        started = self.monotonic()
        error: Exception | None = None
        try:
            fact = validate_fixed_fact_partition(
                self.enricher.enrich_fixed_fact(capture_text), capture_text
            )
        except Exception as caught:
            error = caught
            fact = SemanticFact((LiteralPart(capture_text),))
        duration_ms = max(0.0, (self.monotonic() - started) * 1000)
        attempted = bool(getattr(self.enricher, "last_call", True))
        calls: tuple[ProviderCallEvidence, ...] = ()
        if attempted:
            calls = (
                ProviderCallEvidence(
                    name="core.fixed_fact_enrichment",
                    outcome=(
                        OperationalOutcome.FAILED
                        if error is not None
                        else OperationalOutcome.COMPLETED
                    ),
                    duration_ms=duration_ms,
                    model=getattr(self.enricher, "model", None),
                    reasoning_effort=getattr(self.enricher, "reasoning_effort", None),
                    usage=normalize_provider_usage(getattr(self.enricher, "last_usage", None)),
                    error_category=type(error).__name__ if error is not None else None,
                    response_id=getattr(self.enricher, "last_response_id", None),
                    provider_status=getattr(self.enricher, "last_provider_status", None),
                    attempt_count=1,
                    ordinal=1,
                ),
            )
        stage = OperationalStage(
            "core.fixed_fact_enrichment",
            OperationalOutcome.FAILED if error is not None else OperationalOutcome.COMPLETED,
            duration_ms,
            model=getattr(self.enricher, "model", None),
            reasoning_effort=getattr(self.enricher, "reasoning_effort", None),
            usage=normalize_provider_usage(getattr(self.enricher, "last_usage", None)),
            error_category=type(error).__name__ if error is not None else None,
            provider_calls=calls,
            start_offset_ms=0.0,
        )
        return fact, OperationalEvidence(total_duration_ms=duration_ms, stages=(stage,))

    def _render_existing_references(
        self,
        fact: SemanticFact,
        capture_text: str,
        authenticated_actor: AuthenticatedActorContext | None,
    ) -> tuple[str, bool]:
        """Resolve each optional occurrence independently while preserving all literal text."""
        pieces: list[str] = []
        enriched = False
        for part in fact.parts:
            if isinstance(part, LiteralPart):
                pieces.append(part.text)
                continue
            try:
                identities = self._resolve_existing_identity(
                    part, capture_text, authenticated_actor
                )
                rendered = FIXED_FACT_SET_SEPARATOR.join(
                    _canonical_wikilink(identity) for identity in identities
                )
            except (
                FixedFactCaptureError,
                SemanticWriteCompileError,
                ContextRetrievalError,
                ContextualResolutionError,
                RelationalResolutionError,
                RelationshipEvidenceError,
                ExistingEntityResolutionError,
                ValueError,
            ):
                pieces.append(part.text)
                continue
            pieces.append(rendered)
            enriched = True
        return "".join(pieces), enriched

    def _resolve_existing_identity(
        self,
        part: IdentityPart,
        capture_text: str,
        authenticated_actor: AuthenticatedActorContext | None,
    ) -> tuple[CanonicalIdentity, ...]:
        """Resolve one occurrence under EXISTING_ONLY, including all-or-nothing complete sets."""
        selection = compile_semantic_identity_selection(part.identity, self.schema)
        projector = RelationshipEvidenceProjector(self.repository, self.schema)
        if selection.relational_reference is not None:
            resolved = resolve_relational_reference(
                selection,
                repository=self.repository,
                schema=self.schema,
                semantic_index=self._required(self.semantic_index),
                embedder=self._required(self.embedder),
                contextual_reasoner=self._required(self.contextual_reasoner),
                semantic_limit=self.semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self.self_binding_repository,
                semantic_set_selector=self.semantic_set_selector,
                refine_singular_with_query=True,
            )
            if not resolved.targets:
                raise FixedFactCaptureError("Fixed fact relational identity is unavailable")
            return resolved.targets
        if selection.self_target is not None:
            if (
                selection.self_target != "self"
                or authenticated_actor is None
                or self.self_binding_repository is None
            ):
                raise FixedFactCaptureError("Fixed fact self identity is unavailable")
            try:
                identity_id = self.self_binding_repository.resolve(
                    authenticated_actor.stable_user_id
                ).person_note_id
            except SelfBindingError as error:
                raise FixedFactCaptureError("Fixed fact self identity is unavailable") from error
        else:
            allowed_ids = None
            if selection.filters:
                allowed_ids = find_filtered_note_ids(
                    self.repository,
                    self.schema,
                    selection.filters,
                    note_type=selection.type,
                )
            self_note_id = None
            if authenticated_actor is not None and self.self_binding_repository is not None:
                try:
                    self_note_id = self.self_binding_repository.resolve(
                        authenticated_actor.stable_user_id
                    ).person_note_id
                except SelfBindingError:
                    self_note_id = None
            resolution = resolve_existing_entity(
                selection.entity or selection.query,
                capture_text,
                type=selection.type,
                repository=self.repository,
                schema=self.schema,
                semantic_index=self._required(self.semantic_index),
                embedder=self._required(self.embedder),
                contextual_reasoner=self._required(self.contextual_reasoner),
                semantic_limit=self.semantic_limit,
                allowed_candidate_ids=allowed_ids,
                expand_relationship_context=True,
                self_note_id=self_note_id,
            )
            if resolution.outcome is not ExistingEntityOutcome.RESOLVED or resolution.id is None:
                raise FixedFactCaptureError("Fixed fact identity is not uniquely resolved")
            identity_id = resolution.id
        projection = projector.project_entity_evidence_candidates(identity_id)
        if projection is None:
            raise FixedFactCaptureError("Fixed fact identity became stale")
        return (projection.entity,)

    @staticmethod
    def _required(value: Any | None) -> Any:
        """Reject unavailable optional resolution machinery without weakening to creation."""
        if value is None:
            raise FixedFactCaptureError("Fixed fact identity resolution is unavailable")
        return value

    def _begin_history(self, request_id: str) -> object | None:
        """Begin established Core history without making Git a mutation authority."""
        if self.history is None:
            return None
        try:
            return self.history.begin(request_id)
        except Exception:
            return None

    def _record_history(
        self, request_id: str, snapshot: object | None, note_id: str
    ) -> GitHistoryResult:
        """Record the fixed destination through the shared request-level history boundary."""
        if self.history is None:
            return GitHistoryResult.disabled()
        if snapshot is None:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history snapshot failed")
        try:
            return self.history.record(
                request_id=request_id,
                snapshot=snapshot,
                affected_stable_note_ids=(note_id,),
                repository=self.repository,
                schema=self.schema,
            )
        except Exception:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history record failed")


def _canonical_wikilink(identity: CanonicalIdentity) -> str:
    """Render one current canonical identity as a safe path-qualified wikilink."""
    path = identity.path
    name = identity.name
    if (
        not path.endswith(".md")
        or path.startswith(("/", "\\"))
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(character in path for character in "#|^:%[]")
        or not name
        or any(character in name for character in "|[]\r\n")
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise FixedFactCaptureError("Fixed fact canonical identity is unsafe")
    return f"[[{path.removesuffix('.md')}|{name}]]"
