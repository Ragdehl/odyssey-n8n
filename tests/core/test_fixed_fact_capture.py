"""Provider-free coverage for Core-owned fixed-destination semantic fact capture."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_core.atomic_facts import parse_atomic_facts, render_atomic_facts
from odyssey_core.fixed_fact_capture import (
    FixedFactCaptureError,
    FixedFactCaptureService,
    decode_fixed_fact_enrichment,
    fixed_fact_enrichment_json_schema,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.semantic import SemanticEntityCandidate
from odyssey_core.semantic_write import (
    CandidateScope,
    CandidateScopeExtent,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
ACTOR = AuthenticatedActorContext("8c1a06bc-17cc-4f81-a026-e3ba04c971e5")


class EmptyIndex:
    """Return no semantic candidates beyond exact canonical identity matches."""

    def find_candidates(self, *args: Any, **kwargs: Any) -> tuple[()]:
        return ()


class MappedIndex:
    """Return deterministic candidates for semantic identity tests."""

    def __init__(self, mapping: dict[str, tuple[SemanticEntityCandidate, ...]]) -> None:
        self.mapping = mapping

    def find_candidates(
        self, _embedder: object, reference: str, **kwargs: Any
    ) -> tuple[SemanticEntityCandidate, ...]:
        return self.mapping.get(reference, ())[: int(kwargs["limit"])]


class Embedder:
    """Satisfy the local semantic lookup protocol without external work."""

    model_name = "tests"
    model_version = "1"


class ResolvingReasoner:
    """Resolve supplied Beatriz candidates and SELF relationship facts deterministically."""

    def __init__(self, *, ambiguous: bool = False) -> None:
        self.ambiguous = ambiguous
        self.requests: list[Any] = []

    def resolve(self, request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        self.requests.append(request)
        if self.ambiguous:
            return (
                {
                    "outcome": "AMBIGUOUS",
                    "id": None,
                    "ambiguous_ids": [item.id for item in request.candidates[:2]],
                },
                {},
            )
        selected = next(
            (
                item
                for item in request.candidates
                if "beatriz" in item.evidence.casefold() or "mis hijos" in item.evidence.casefold()
            ),
            request.candidates[0],
        )
        return ({"outcome": "RESOLVED", "id": selected.id, "ambiguous_ids": []}, {})


class SelfBinding:
    """Bind the synthetic actor to its canonical person note."""

    def resolve(self, stable_user_id: str) -> Any:
        assert stable_user_id == ACTOR.stable_user_id
        return SimpleNamespace(person_note_id="self")


class Enricher:
    """Return one controlled semantic fact and expose bounded call evidence."""

    model = "fake-luna"
    reasoning_effort = "low"
    last_call = True
    last_usage = None
    last_response_id = "fake-response"
    last_provider_status = "completed"

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def enrich_fixed_fact(self, capture_text: str) -> Any:
        del capture_text
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def schema() -> dict[str, Any]:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write_note(
    vault: Path,
    path: str,
    note_id: str,
    name: str,
    body: str = "",
    *,
    aliases: list[str] | None = None,
) -> None:
    """Create one disposable schema-valid person fixture."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": note_id,
        "name": name,
        "type": "person",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
        "aliases": aliases or [],
        "tags": [],
    }
    target.write_text(serialize_note(Note(metadata, body)), encoding="utf-8")


def described(
    text: str,
    *,
    direct_name: str | None = None,
    scope: CandidateScope | None = None,
) -> IdentityPart:
    """Build one described person occurrence for capture fixtures."""
    return IdentityPart(
        text,
        IdentityIntent(
            text,
            IdentityBinding.DESCRIBED,
            direct_name=direct_name,
            note_type="person",
            candidate_scope=scope,
        ),
    )


def service(
    vault: Path,
    schema: dict[str, Any],
    fact: object,
    *,
    index: Any | None = None,
    reasoner: Any | None = None,
) -> tuple[FixedFactCaptureService, Enricher]:
    """Build the isolated Core service with deterministic resolution boundaries."""
    enricher = Enricher(fact)
    return (
        FixedFactCaptureService(
            VaultRepository(vault),
            schema,
            None,
            enricher=enricher,
            semantic_index=index or EmptyIndex(),
            embedder=Embedder(),
            contextual_reasoner=reasoner or ResolvingReasoner(),
            self_binding_repository=SelfBinding(),
        ),
        enricher,
    )


def capture(
    captures: FixedFactCaptureService,
    text: str,
    *,
    request_id: str = "fixed-fact-request",
) -> Any:
    return captures.capture_calendar_day(
        date="2026-10-03",
        capture_text=text,
        request_id=request_id,
        actor={"human": ACTOR.stable_user_id, "app": "calendar"},
        now="2026-10-03T18:00:00+02:00",
        authenticated_actor=ACTOR,
    )


def test_parts_only_schema_contains_no_destination_or_mutation_authority(schema: dict) -> None:
    contract = fixed_fact_enrichment_json_schema(schema)
    serialized = json.dumps(contract, sort_keys=True)

    assert set(contract["properties"]) == {"parts"}
    for forbidden in (
        '"target"',
        '"destination"',
        '"destination_type"',
        '"mutation"',
        '"intent"',
        '"stable_id"',
        '"path"',
        '"markdown"',
    ):
        assert forbidden not in serialized.casefold()


@pytest.mark.parametrize(
    "parts",
    [
        [{"kind": "literal", "text": "Hola Beatriz"}],
        [
            {"kind": "literal", "text": "Hola "},
            {
                "kind": "identity",
                "text": "Beatriz",
                "identity": {
                    "description": "Beatriz",
                    "binding": "described",
                    "direct_name": "Beatriz",
                    "note_type": "person",
                    "filters": [],
                    "candidate_scope": None,
                },
            },
        ],
        [
            {
                "kind": "identity",
                "text": "Bea",
                "identity": {
                    "description": "Bea",
                    "binding": "described",
                    "direct_name": "Bea",
                    "note_type": "person",
                    "filters": [],
                    "candidate_scope": None,
                },
            },
            {"kind": "literal", "text": " Hola"},
        ],
    ],
)
def test_exact_partition_rejects_omission_paraphrase_and_reordering(parts: list[dict]) -> None:
    with pytest.raises(FixedFactCaptureError, match="changed capture text"):
        decode_fixed_fact_enrichment({"parts": parts}, "Hola Bea")


def test_existing_singular_identity_renders_one_canonical_wikilink(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/cloe.md", "cloe", "Cloe")
    text = "He merendado con Cloe."
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact(
            (
                LiteralPart("He merendado con "),
                described("Cloe", direct_name="Cloe"),
                LiteralPart("."),
            )
        ),
    )

    result = capture(captures, text)

    assert result.rendered_fact == "He merendado con [[people/cloe|Cloe]]."
    day = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))
    assert [item.text for item in parse_atomic_facts(day.content)] == [result.rendered_fact]


def test_contextual_resolution_maps_bea_without_calendar_alias_logic(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/beatriz.md", "beatriz", "Beatriz Carrero")
    text = "He vaciado el garaje con bea."
    index = MappedIndex(
        {
            "bea": (
                SemanticEntityCandidate(
                    "beatriz", "people/beatriz.md", "person", "Beatriz Carrero", 0.9
                ),
            )
        }
    )
    reasoner = ResolvingReasoner()
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact(
            (LiteralPart("He vaciado el garaje con "), described("bea"), LiteralPart("."))
        ),
        index=index,
        reasoner=reasoner,
    )

    result = capture(captures, text)

    assert result.rendered_fact == "He vaciado el garaje con [[people/beatriz|Beatriz Carrero]]."
    assert reasoner.requests[0].reference == "bea"


def test_complete_self_set_is_all_or_nothing_and_renders_every_grounded_member(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    self_fact = render_atomic_facts(
        ("Mis hijos son [[Clara]] y [[Marta]].",), "fixture", (0,), "2026-10-03"
    )
    write_note(vault, "people/self.md", "self", "Edgar", self_fact)
    write_note(vault, "people/clara.md", "clara", "Clara")
    write_note(vault, "people/marta.md", "marta", "Marta")
    text = "He ordenado el garaje con mis hijos."
    scope = CandidateScope(IdentityBinding.SELF, "mis hijos", CandidateScopeExtent.COMPLETE_SET)
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact(
            (
                LiteralPart("He ordenado el garaje con "),
                described("mis hijos", scope=scope),
                LiteralPart("."),
            )
        ),
    )

    result = capture(captures, text)

    assert result.rendered_fact == (
        "He ordenado el garaje con [[people/clara|Clara]] · [[people/marta|Marta]]."
    )


def test_complete_self_set_never_renders_a_partial_member_list(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    self_fact = render_atomic_facts(
        ("Mis hijos son [[Clara]] y [[Marta]].",), "fixture", (0,), "2026-10-03"
    )
    write_note(vault, "people/self.md", "self", "Edgar", self_fact)
    write_note(vault, "people/clara.md", "clara", "Clara")
    text = "He ordenado el garaje con mis hijos."
    scope = CandidateScope(IdentityBinding.SELF, "mis hijos", CandidateScopeExtent.COMPLETE_SET)
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact(
            (
                LiteralPart("He ordenado el garaje con "),
                described("mis hijos", scope=scope),
                LiteralPart("."),
            )
        ),
    )

    result = capture(captures, text)

    assert result.rendered_fact == text


def test_missing_identity_remains_literal_and_never_creates_a_person(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    text = "Hoy ha venido el fontanero."
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact((LiteralPart("Hoy ha venido "), described("el fontanero"), LiteralPart("."))),
    )

    result = capture(captures, text)

    assert result.rendered_fact == text
    assert all(
        "fontanero" not in path.casefold() for path in VaultRepository(vault).list_markdown_paths()
    )


@pytest.mark.parametrize("mode", ["ambiguous", "stale"])
def test_ambiguous_or_stale_identity_preserves_the_whole_occurrence(
    tmp_path: Path, schema: dict, mode: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/beatriz.md", "beatriz", "Beatriz Carrero")
    write_note(vault, "people/bea-otra.md", "bea-otra", "Bea Otra")
    candidates = (
        SemanticEntityCandidate("beatriz", "people/beatriz.md", "person", "Beatriz Carrero", 0.9),
        SemanticEntityCandidate("bea-otra", "people/bea-otra.md", "person", "Bea Otra", 0.8),
    )
    if mode == "stale":
        candidates = (
            SemanticEntityCandidate("missing", "people/missing.md", "person", "Beatriz", 0.9),
        )
    text = "He trabajado con bea esta tarde."
    captures, _enricher = service(
        vault,
        schema,
        SemanticFact(
            (LiteralPart("He trabajado con "), described("bea"), LiteralPart(" esta tarde."))
        ),
        index=MappedIndex({"bea": candidates}),
        reasoner=ResolvingReasoner(ambiguous=mode == "ambiguous"),
    )

    result = capture(captures, text)

    assert result.rendered_fact == text


@pytest.mark.parametrize(
    "bad_result",
    [RuntimeError("provider failed"), object(), SemanticFact((LiteralPart("paraphrased"),))],
)
def test_provider_or_validation_failure_falls_back_to_the_complete_literal(
    tmp_path: Path, schema: dict, bad_result: object
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    text = "Hoy hemos vaciado el garaje con bea."
    captures, enricher = service(vault, schema, bad_result)

    result = capture(captures, text)

    assert enricher.calls == 1
    assert result.rendered_fact == text
    assert result.enriched is False
    assert result.operational.stages[0].outcome.value == "failed"


def test_same_request_replay_is_idempotent_despite_enrichment_variation(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/cloe.md", "cloe", "Cloe")
    text = "He merendado con Cloe."
    captures, enricher = service(
        vault,
        schema,
        SemanticFact(
            (
                LiteralPart("He merendado con "),
                described("Cloe", direct_name="Cloe"),
                LiteralPart("."),
            )
        ),
    )
    first = capture(captures, text, request_id="same-request")
    enricher.result = SemanticFact((LiteralPart(text),))
    replay = capture(captures, text, request_id="same-request")

    day = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))
    assert first.changed is True and replay.changed is False
    assert len(parse_atomic_facts(day.content)) == 1


def test_real_luna_adapter_uses_one_parts_only_call(schema: dict) -> None:
    """Keep the fixed-fact contract separate from ordinary planning and free of fallback calls."""
    from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

    class Responses:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return SimpleNamespace(
                id="fixed-fact-response",
                status="completed",
                usage=None,
                output_text=json.dumps(
                    {"parts": [{"kind": "literal", "text": "Hoy vino el fontanero."}]}
                ),
            )

    responses = Responses()
    planner = OpenAILunaExperimentalPlanner(
        SimpleNamespace(responses=responses),
        schema,
        {"date": "2026-10-03", "time": "18:00", "timezone": "Europe/Paris"},
    )

    fact = planner.enrich_fixed_fact("Hoy vino el fontanero.")

    assert fact == SemanticFact((LiteralPart("Hoy vino el fontanero."),))
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call["model"] == "gpt-5.6-luna"
    assert call["reasoning"] == {"effort": "low"}
    assert call["text"]["format"]["name"] == "odyssey_fixed_fact_semantic_enrichment_v1"
    assert set(call["text"]["format"]["schema"]["properties"]) == {"parts"}
