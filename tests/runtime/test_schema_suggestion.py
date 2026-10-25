"""Provider-free semantic boundary and registration gates for schema conversation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_runtime.schema_suggestion import (
    SCHEMA_SUGGESTION_INSTRUCTIONS,
    SUGGESTION_SCHEMA,
    SchemaSuggestionError,
    SchemaSuggestionService,
    catalog_for_model,
    validate_model_suggestion,
)
from odyssey_runtime.user_schema_registry import UserSchemaRegistry

ROOT = Path(__file__).resolve().parents[2]


def registry(tmp_path: Path) -> UserSchemaRegistry:
    return UserSchemaRegistry(
        tmp_path,
        json.loads((ROOT / "config/note-schema.json").read_text()),
        (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION),
    )


def raw(decision: str, quote: str | None, **override) -> dict:
    base = {
        "decision": decision,
        "subject_quote": quote,
        "type_name": None,
        "type_id": None,
        "description": None,
        "properties": [],
        "question": None,
        "explanation": "La propuesta debe revisarse antes de crear un modelo.",
    }
    return {**base, **override}


class FakeGateway:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    def _complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_strict_schema_closed_and_instructions_never_grant_approval() -> None:
    assert SUGGESTION_SCHEMA["additionalProperties"] is False
    assert SUGGESTION_SCHEMA["properties"]["properties"]["items"]["additionalProperties"] is False
    assert "confirmation" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "reclassify" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "exact" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "partial dates" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert set(SUGGESTION_SCHEMA["required"]) == set(SUGGESTION_SCHEMA["properties"])


def test_catalogue_only_exposes_registered_visible_types_and_editability(tmp_path: Path) -> None:
    catalogue = catalog_for_model(registry(tmp_path).snapshot()[1])
    by_id = {item["id"]: item for item in catalogue}
    assert by_id["person"]["editable"] is True
    assert by_id["task"]["editable"] is False
    assert by_id["event"]["editable"] is False
    assert "calendar_day" not in by_id
    assert all(set(x) == {"id", "name", "description", "editable", "properties"} for x in catalogue)


def test_natural_request_new_type_stays_a_proposal_and_registry_previews(tmp_path: Path) -> None:
    source = "Quiero crear un tipo Libro para recordar cada autor y sus páginas"
    model = FakeGateway(
        raw(
            "ADD_TYPE",
            "Libro",
            type_name="Libro",
            description="Obra escrita individual.",
            properties=[
                {
                    "quote": "autor",
                    "name": "autor",
                    "description": "Quién lo escribió",
                    "value_type": "string",
                },
                {
                    "quote": "páginas",
                    "name": "páginas",
                    "description": "Número de páginas",
                    "value_type": "integer",
                },
            ],
        )
    )
    reg = registry(tmp_path)
    result = SchemaSuggestionService(model).suggest(source, reg, expected_revision=0)
    assert result["decision"] == "PROPOSE"
    assert result["change"]["type"]["id"] == "libro"
    assert result["change"]["type"]["properties"][1]["value_type"] == "integer"
    assert result["preview"]["next_revision"] == 1
    assert len(result["preview"]["proposal_hash"]) == 64
    assert reg.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/current.json").exists()
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["name"] == "odyssey_schema_suggestion_v1"
    assert call["max_tokens"] <= 1200
    assert call["data"]["source"] == source
    assert "change" not in call["data"]
    assert "actor_id" not in result
    assert "approved" not in result


def test_add_property_uses_canonical_type_and_queryable_optional_preview(tmp_path: Path) -> None:
    reg = registry(tmp_path)
    source = "Me gustaría guardar la profesión de cada persona"
    model = FakeGateway(
        raw(
            "ADD_PROPERTY",
            "profesión",
            type_id="person",
            description="Profesión conocida.",
            properties=[
                {
                    "quote": "profesión",
                    "name": "profesion",
                    "description": "Profesión conocida",
                    "value_type": "string",
                }
            ],
        )
    )
    result = SchemaSuggestionService(model).suggest(source, reg, expected_revision=0)
    assert result["change"]["type_id"] == "person"
    assert result["preview"]["affected_type_id"] == "person"
    added = next(
        x for x in result["preview"]["type_preview"]["properties"] if x["id"] == "profesion"
    )
    assert added["required"] is False and added["filterable"] is True


def test_reuse_and_clarify_are_read_only_even_with_canonical_type(tmp_path: Path) -> None:
    reg = registry(tmp_path)
    reuse = SchemaSuggestionService(FakeGateway(raw("REUSE", "personas", type_id="person")))
    assert reuse.suggest("Quiero organizar personas", reg, expected_revision=0) == {
        "kind": "schema_suggestion",
        "decision": "REUSE",
        "message": "La propuesta debe revisarse antes de crear un modelo.",
        "reuse_type_id": "person",
    }
    clarify = SchemaSuggestionService(
        FakeGateway(raw("CLARIFY", None, question="¿Qué información quieres conservar?"))
    )
    assert (
        clarify.suggest("Quiero guardar algo más", reg, expected_revision=0)["decision"]
        == "CLARIFY"
    )
    assert reg.snapshot()[0] == 0


def test_rejects_ungrounded_mixed_or_unapproved_semantics(tmp_path: Path) -> None:
    source = "Quiero una nota sobre libros y sus autores"
    catalogue = catalog_for_model(registry(tmp_path).snapshot()[1])
    good = raw("ADD_TYPE", "libros", type_name="Libro", description="Obra escrita")
    invalid = [
        {**good, "actor_id": "attacker"},
        {**good, "approved": True},
        {**good, "subject_quote": "plantas"},
        {**good, "subject_quote": "libro"},  # inside 'libros': not a full word
        {**good, "type_name": "Person"},  # known existing Core type
        {**good, "type_id": "person"},
        {**good, "question": "¿Confirmas?"},
        {
            **good,
            "properties": [
                {
                    "quote": "precio",
                    "name": "precio",
                    "description": "Precio",
                    "value_type": "integer",
                }
            ],
        },
        {
            **good,
            "properties": [
                {"quote": "autores", "name": "autor", "description": "Autor", "value_type": "float"}
            ],
        },
        {
            **good,
            "properties": [
                {
                    "quote": "autores",
                    "name": "autor",
                    "description": "Autor",
                    "value_type": "string",
                    "can_write": True,
                }
            ],
        },
        raw(
            "ADD_PROPERTY",
            "libros",
            type_id="task",
            description="Dato",
            properties=[
                {
                    "quote": "autores",
                    "name": "autor",
                    "description": "Autor",
                    "value_type": "string",
                }
            ],
        ),
        raw("ADD_PROPERTY", "libros", type_id="person", description="Dato", properties=[]),
        raw("REUSE", "libros", type_id="unknown"),
        raw("CLARIFY", None, type_name="Libro", question="¿Cuál?"),
        raw("ABSTAIN", None, question="¿Cuál?"),
    ]
    for case in invalid:
        with pytest.raises(SchemaSuggestionError):
            validate_model_suggestion(source, case, catalogue)


def test_stale_snapshot_and_bad_input_never_call_provider(tmp_path: Path) -> None:
    reg = registry(tmp_path)
    model = FakeGateway(raw("CLARIFY", None, question="¿Cuál?"))
    service = SchemaSuggestionService(model)
    for text, revision in [(("x" * 1300), 0), ("nota", -1), ("nota", True), ("nota", 1)]:
        with pytest.raises(ValueError):
            service.suggest(text, reg, expected_revision=revision)
    assert model.calls == []


def test_registry_rejects_compatible_shape_but_conflicting_proposal(tmp_path: Path) -> None:
    reg = registry(tmp_path)
    model = FakeGateway(raw("ADD_TYPE", "Personas", type_name="person", description="Personas"))
    with pytest.raises(SchemaSuggestionError):
        SchemaSuggestionService(model).suggest(
            "Quiero organizar Personas", reg, expected_revision=0
        )
    assert reg.snapshot()[0] == 0


def test_source_quotes_cannot_be_forged_or_ambiguous(tmp_path: Path) -> None:
    catalogue = catalog_for_model(registry(tmp_path).snapshot()[1])
    base = raw("ADD_TYPE", "libros", type_name="Libro", description="Obra escrita")
    for source, subject in [
        ("libros y libros", "libros"),
        ("Quiero libros", "libro"),
        ("me interesan LIBROS", "libros"),
        ("libros", " libros"),
        ("", "libros"),
    ]:
        with pytest.raises(SchemaSuggestionError):
            validate_model_suggestion(source, {**base, "subject_quote": subject}, catalogue)


def test_model_selection_has_single_no_tools_no_store_provider_contract() -> None:
    from odyssey_runtime.conversation_gateway import OpenAIConversationGateway

    class Client:
        def __init__(self):
            self.calls = []
            self.responses = self

        def create(self, **payload):
            self.calls.append(payload)
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps(raw("CLARIFY", None, question="¿Qué quieres organizar?")),
            )

    client = Client()
    gateway = OpenAIConversationGateway(client)
    # exercise shared Responses invocation in isolation: no original corpus or API key
    result = gateway._complete(
        schema=SUGGESTION_SCHEMA,
        name="odyssey_schema_suggestion_v1",
        system=SCHEMA_SUGGESTION_INSTRUCTIONS,
        data={"source": "Quiero organizar mis notas", "existing_note_types": []},
        max_tokens=1200,
    )
    assert result["decision"] == "CLARIFY"
    payload = client.calls[0]
    assert payload["model"] == gateway.model
    assert payload["reasoning"] == {"effort": gateway.reasoning_effort}
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert len(client.calls) == 1
    assert "tools" not in payload


def test_versioned_multilingual_prompt_evaluation_matrix_is_explicitly_not_live_evidence() -> None:
    import hashlib
    from collections import Counter

    path = ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json"
    matrix = json.loads(path.read_text(encoding="utf-8"))
    assert matrix["suite_version"] == "v1"
    assert matrix["model"] == "gpt-6-luna"
    assert matrix["reasoning_effort"] == "low"
    assert "not observations of a live provider" in matrix["note"]
    cases = matrix["cases"]
    assert len(cases) >= 20
    assert len({x["id"] for x in cases}) == len(cases)
    assert set(x["expected"] for x in cases) == {
        "ADD_TYPE",
        "ADD_PROPERTY",
        "REUSE",
        "CLARIFY",
        "ABSTAIN",
    }
    assert all(5 < len(case["source"]) <= 1200 and case["reason"] for case in cases)
    assert Counter(x["id"].split("_", 1)[0] for x in cases) >= Counter({"es": 1, "fr": 1, "en": 1})
    assert len(hashlib.sha256(SCHEMA_SUGGESTION_INSTRUCTIONS.encode("utf-8")).hexdigest()) == 64


def test_schema_model_cannot_take_a_hidden_nonstring_type_id_from_provider(tmp_path: Path) -> None:
    source = "Quiero conservar el autor de cada libro"
    catalogue = catalog_for_model(registry(tmp_path).snapshot()[1])
    invalid = raw("REUSE", "libro", type_id={"forged": "person"})
    with pytest.raises(SchemaSuggestionError):
        validate_model_suggestion(source, invalid, catalogue)
    invalid_property = raw(
        "ADD_TYPE",
        "libro",
        type_name="Libro",
        description="Libro",
        properties=[
            {
                "quote": "autor",
                "name": "autor",
                "description": "Autor",
                "value_type": {"fake": "string"},
            }
        ],
    )
    with pytest.raises(SchemaSuggestionError):
        validate_model_suggestion(source, invalid_property, catalogue)
