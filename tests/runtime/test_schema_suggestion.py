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
from odyssey_runtime.user_schema_registry import UserSchemaError, UserSchemaRegistry

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
            description=None,
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


def test_add_property_no_type_description_frozen_real_model_response_is_valid_shape_but_not_semantic_proof(
    tmp_path: Path,
) -> None:
    """Real v1 model produced null type description. Reject semantic inference separately."""
    source = "Quiero apuntar el ISBN de mis libros ya existentes."
    raw_v1 = {
        "decision": "ADD_PROPERTY",
        "subject_quote": "ISBN",
        "type_name": None,
        "type_id": "document",
        "description": None,
        "properties": [
            {
                "quote": "ISBN",
                "name": "ISBN",
                "description": "ISBN de un libro.",
                "value_type": "string",
            }
        ],
        "explanation": "El ISBN es un dato para tus libros existentes.",
        "question": None,
    }
    proposed = validate_model_suggestion(
        source, raw_v1, catalog_for_model(registry(tmp_path).snapshot()[1])
    )
    assert proposed.change is not None
    assert proposed.change["type_id"] == "document"
    # Critically: syntactically well-formed is NOT semantically safe. The
    # user asked about books, not the broader document class. The evaluation
    # matrix keeps this case a failed semantic decision, not a false PASS.
    matrix = json.loads((ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json").read_text())
    case = next(item for item in matrix["cases"] if item["id"] == "es_unique_attribute")
    assert case["expected"] == "CLARIFY"


def test_property_proposals_cannot_mutate_type_description(tmp_path: Path) -> None:
    user = registry(tmp_path)
    source = "Añade profesión a las personas"
    base = raw(
        "ADD_PROPERTY",
        "profesión",
        type_id="person",
        properties=[
            {
                "quote": "profesión",
                "name": "profesion",
                "description": "Profesión cuando se conozca",
                "value_type": "string",
            }
        ],
    )
    assert validate_model_suggestion(source, base, catalog_for_model(user.snapshot()[1])).change
    with pytest.raises(SchemaSuggestionError, match="cannot edit type description"):
        validate_model_suggestion(
            source,
            {**base, "description": "Mutar tipo Persona"},
            catalog_for_model(user.snapshot()[1]),
        )


def test_real_provider_evaluator_requires_separate_dev_only_bounded_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither running tests nor an accidental CLI launch can consume tokens."""
    from scripts.evaluate_schema_suggestion_live import run

    output = tmp_path / "results.json"
    monkeypatch.delenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", raising=False)
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV_EVAL")
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=output)
    monkeypatch.setenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    with pytest.raises(ValueError, match="DEV_EVAL"):
        run(max_cases=1, first_index=0, output=output)
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV_EVAL")
    for count, index in ((25, 0), (1, 24), (6, 19), (0, 0)):
        with pytest.raises(ValueError, match="bound|budget"):
            run(max_cases=count, first_index=index, output=output)
    assert not output.exists()


def test_v2_holdout_is_a_distinct_frozen_semantic_matrix_not_synthetic_pass_evidence() -> None:
    matrix = json.loads(
        (ROOT / "tests/fixtures/schema_suggestion/evaluation_v2_holdout.json").read_text()
    )
    original = json.loads(
        (ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json").read_text()
    )
    assert matrix["suite_version"] == "v2_holdout"
    assert "not yet evaluated with a real model" in matrix["note"]
    assert len(matrix["cases"]) >= 12
    assert {x["id"] for x in matrix["cases"]}.isdisjoint({x["id"] for x in original["cases"]})
    assert {x["source"] for x in matrix["cases"]}.isdisjoint(
        {x["source"] for x in original["cases"]}
    )
    assert {x["expected"] for x in matrix["cases"]} == {
        "ADD_TYPE",
        "ADD_PROPERTY",
        "CLARIFY",
        "ABSTAIN",
    }


def test_live_evaluator_counts_matching_operation_only_not_semantic_correctness() -> None:
    from scripts.evaluate_schema_suggestion_live import decision_score_only

    for expected, actual, agreement in [
        ("ADD_PROPERTY", "ADD_PROPERTY", True),  # Could have WRONG target or attribute!
        ("ADD_TYPE", "ADD_TYPE", True),  # Could propose entirely wrong type!
        ("REUSE", "REUSE", True),  # Could reuse a generic unrelated type!
        ("CLARIFY", "CLARIFY", True),
        ("ADD_TYPE", "REUSE", False),
    ]:
        same, review = decision_score_only(expected, actual)
        assert same is agreement
        assert review == "awaiting_independent_review"
    assert decision_score_only("ADD_TYPE", "INVALID") == (False, "rejected_before_semantic_review")


def test_live_evaluator_will_not_overwrite_any_existing_file_before_provider_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.evaluate_schema_suggestion_live import run

    monkeypatch.setenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV_EVAL")
    # Existing path is rejected before the model client can be constructed.
    existing = tmp_path / "existing.json"
    existing.write_text("original evidence")
    with pytest.raises(ValueError, match="overwrite existing"):
        run(max_cases=1, first_index=0, output=existing)
    assert existing.read_text() == "original evidence"


def test_live_evaluator_can_select_only_known_frozen_holdout_and_checks_budget_without_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.evaluate_schema_suggestion_live import run

    monkeypatch.setenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV_EVAL")
    dest = tmp_path / "holdout.json"
    for matrix, count, index in [
        ("untrusted_file", 1, 0),
        ("v2_holdout", 13, 0),
        ("v2_holdout", 1, 12),
        ("v2_holdout", 4, 10),
    ]:
        with pytest.raises(ValueError, match="Unknown frozen|bound|budget"):
            run(max_cases=count, first_index=index, output=dest, matrix_name=matrix)
    assert not dest.exists()


def test_readonly_clarification_can_use_ambiguous_quote_without_claiming_evidence(
    tmp_path: Path,
) -> None:
    """A repeated phrase must not suppress a clarification; it cannot authorize a change."""
    reg = registry(tmp_path)
    source = "Quiero notas de libros, y no de libros prestados."
    result = SchemaSuggestionService(
        FakeGateway(raw("CLARIFY", "libros", question="¿Qué libros quieres excluir?"))
    ).suggest(source, reg, expected_revision=0)
    assert result == {
        "kind": "schema_suggestion",
        "decision": "CLARIFY",
        "message": "¿Qué libros quieres excluir?",
        "reuse_type_id": None,
    }
    assert reg.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/current.json").exists()
    # The same nonunique source quote is still forbidden for ADD_TYPE.
    with pytest.raises(SchemaSuggestionError):
        validate_model_suggestion(
            source,
            raw("ADD_TYPE", "libros", type_name="Libro", description="Obra escrita"),
            catalog_for_model(reg.snapshot()[1]),
        )


def test_v3_prompt_declares_generic_nonduplication_partial_date_and_broad_clarification() -> None:
    assert "'separate' or 'another'" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "PARTIAL DATE" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "not silently encode it as integer or string" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "underspecified request to organize notes is CLARIFY" in SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "subject_quote null" in SCHEMA_SUGGESTION_INSTRUCTIONS


def test_v4_unseen_matrix_is_authorization_gated_before_any_provider_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.evaluate_schema_suggestion_live import MATRICES, run

    assert MATRICES["v4_holdout"][1] == 16
    monkeypatch.delenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", raising=False)
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=tmp_path / "never.json", matrix_name="v4_holdout")


def test_live_evaluator_does_not_access_provider_without_explicit_isolated_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.evaluate_schema_suggestion_live import run

    monkeypatch.delenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", raising=False)
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=tmp_path / "never.json", matrix_name="v1")
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=tmp_path / "never.json", matrix_name="v2_holdout")


def test_v4_prompt_guards_identity_scope_and_granularity_without_granting_authority() -> None:
    """Prompt is only a risk reducer. These assertions do not prove model behaviour."""
    instructions = SCHEMA_SUGGESTION_INSTRUCTIONS
    for requirement in (
        "WHOLE registered type",
        "already saved does NOT establish their actual registered note type",
        "CLARIFY which registered note type",
        "not a transient lifecycle state",
        "not an executable inclusion/exclusion",
        "A description is NOT an executable inclusion/exclusion policy",
        "manual selection",
        "constraint cannot be supported",
        "do not invent a unit",
    ):
        assert requirement.lower() in instructions.lower()
    assert "Never drop explicit exclusions" not in instructions  # replaced with stronger scope rule
    assert "confirmation" in instructions
    assert "schema fields" in instructions.lower()


def test_v4_holdout_is_unseen_and_contains_semantic_targets_beyond_decision_labels() -> None:
    path = ROOT / "tests/fixtures/schema_suggestion/evaluation_v4_holdout.json"
    matrix = json.loads(path.read_text(encoding="utf-8"))
    original = json.loads(
        (ROOT / "tests/fixtures/schema_suggestion/evaluation_v1.json").read_text()
    )
    prior = json.loads(
        (ROOT / "tests/fixtures/schema_suggestion/evaluation_v2_holdout.json").read_text()
    )
    cases = matrix["cases"]
    assert matrix["suite_version"] == "v4_holdout"
    assert matrix["model"] == "gpt-6-luna" and matrix["reasoning_effort"] == "low"
    assert len(cases) == 16
    assert len({case["id"] for case in cases}) == len(cases)
    frozen_sources = {case["source"] for data in (original, prior) for case in data["cases"]}
    assert all(case["source"] not in frozen_sources for case in cases)
    assert set(case["expected"] for case in cases) == {
        "ADD_TYPE",
        "ADD_PROPERTY",
        "REUSE",
        "CLARIFY",
        "ABSTAIN",
    }
    assert all(case["semantic_checks"] and case["reason"] for case in cases)
    assert all(len(case["source"]) <= 1200 for case in cases)


def test_v5_prompt_multilingual_response_scope_and_temporal_intent_are_explicit() -> None:
    prompt = SCHEMA_SUGGESTION_INSTRUCTIONS
    assert "dominant language of the user's LATEST message" in prompt
    for part in (
        "explanation",
        "question",
        "new type_name",
        "new type description",
        "new property name",
        "property description",
    ):
        assert part in prompt
    assert "Preserve canonical registered type_id" in prompt
    assert "REUSE that type without demanding" in prompt
    assert "explicitly ask to add a NEW schema" in prompt
    assert "FIRST question must ask whether" in prompt
    assert "only considering doing so later" in prompt
    assert "ABSTAIN is also safe" in prompt


def test_v5_holdout_is_frozen_new_synthetic_data_and_has_language_checks() -> None:
    source = ROOT / "tests/fixtures/schema_suggestion/evaluation_v5_holdout.json"
    matrix = json.loads(source.read_text(encoding="utf-8"))
    old_sources = set()
    for old_name in (
        "evaluation_v1.json",
        "evaluation_v2_holdout.json",
        "evaluation_v4_holdout.json",
    ):
        old = json.loads((source.parent / old_name).read_text(encoding="utf-8"))
        old_sources.update(item["source"] for item in old["cases"])
    assert matrix["suite_version"] == "v5_holdout"
    assert (matrix["model"], matrix["reasoning_effort"]) == ("gpt-6-luna", "low")
    cases = matrix["cases"]
    assert len(cases) == 12
    assert len({c["id"] for c in cases}) == len(cases)
    assert not ({c["source"] for c in cases} & old_sources)
    assert all(
        c["semantic_checks"] and c["reason"] and 1 <= len(c["source"]) <= 1200 for c in cases
    )
    assert set(c["expected"] for c in cases) == {"ADD_TYPE", "REUSE", "CLARIFY", "ABSTAIN"}
    assert any("French" in repr(c["semantic_checks"]) for c in cases)
    assert any("Spanish" in repr(c["semantic_checks"]) for c in cases)
    assert any("English" in repr(c["semantic_checks"]) for c in cases)


def test_v5_holdout_cannot_call_paid_provider_without_new_authorization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.evaluate_schema_suggestion_live import MATRICES, run

    assert MATRICES["v5_holdout"][1] == 12
    monkeypatch.delenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", raising=False)
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=tmp_path / "none.json", matrix_name="v5_holdout")


def test_v5_evaluator_alternative_scoring_only_accepts_safe_readonly_choices() -> None:
    from scripts.evaluate_schema_suggestion_live import accepted_case_decisions, decision_score_only

    cases = json.loads(
        (ROOT / "tests/fixtures/schema_suggestion/evaluation_v5_holdout.json").read_text()
    )["cases"]
    alternatives = [c for c in cases if "also_safe_decision" in c]
    assert {c["id"] for c in alternatives} == {"en_hypothetical_future", "es_hypothetical_future"}
    for c in cases:
        choices = accepted_case_decisions(c)
        assert c["expected"] in choices
        if c in alternatives:
            checks = c["semantic_checks_by_decision"]
            assert set(checks) == {"CLARIFY", "ABSTAIN"}
            assert "Question" in " ".join(checks["CLARIFY"])
            assert "no question" in " ".join(checks["ABSTAIN"])
            assert all("Question" not in item for item in c["semantic_checks"])
            assert choices == ("CLARIFY", "ABSTAIN")
            assert decision_score_only(c["expected"], "CLARIFY", accepted=choices)[0]
            assert decision_score_only(c["expected"], "ABSTAIN", accepted=choices)[0]
            assert not decision_score_only(c["expected"], "ADD_TYPE", accepted=choices)[0]
            assert not decision_score_only(c["expected"], "ADD_PROPERTY", accepted=choices)[0]
            assert not decision_score_only(c["expected"], "REUSE", accepted=choices)[0]
        else:
            assert choices == (c["expected"],)
    for invalid in (
        {"expected": "ADD_TYPE", "also_safe_decision": "ABSTAIN"},
        {"expected": "CLARIFY", "also_safe_decision": "ADD_TYPE"},
        {"expected": "REUSE", "also_safe_decision": "CLARIFY"},
    ):
        with pytest.raises(ValueError, match="Unsupported alternative"):
            accepted_case_decisions(invalid)
    assert not decision_score_only("CLARIFY", "ABSTAIN")[0]  # legacy strict cases unchanged


def test_v6_instructions_cover_possessive_fields_integer_counts_temporal_precision_and_locale() -> (
    None
):
    prompt = SCHEMA_SUGGESTION_INSTRUCTIONS
    for part in (
        "Before returning the JSON",
        "review every USER-FACING string",
        "as ONE note type and Y as a property of X",
        "Only propose a separate type for Y when they explicitly",
        "COUNT/CARDINALITY properties",
        "not string merely because",
        "Never offer a whole-number or text workaround for a PARTIAL DATE",
    ):
        assert part in prompt
    assert "guitar" not in prompt.lower()
    assert "board game" not in prompt.lower()
    assert "Unknown" not in prompt


def test_v6_new_holdout_freezes_semantics_and_alternative_safety() -> None:
    from scripts.evaluate_schema_suggestion_live import MATRICES, accepted_case_decisions

    base = ROOT / "tests/fixtures/schema_suggestion"
    cases = json.loads((base / "evaluation_v6_holdout.json").read_text(encoding="utf8"))["cases"]
    prior = set()
    for matrix in (
        "evaluation_v1.json",
        "evaluation_v2_holdout.json",
        "evaluation_v4_holdout.json",
        "evaluation_v5_holdout.json",
    ):
        prior.update(x["source"] for x in json.loads((base / matrix).read_text())["cases"])
    assert MATRICES["v6_holdout"][1] == 12
    assert len(cases) == 12 and len({c["id"] for c in cases}) == 12
    assert all(c["source"] not in prior and c["semantic_checks"] for c in cases)
    assert {c["expected"] for c in cases} == {"ADD_TYPE", "CLARIFY", "REUSE"}
    for case in cases:
        opts = accepted_case_decisions(case)
        if case["id"] == "es_future_later":
            assert opts == ("CLARIFY", "ABSTAIN")
            assert set(case["semantic_checks_by_decision"]) == set(opts)
        else:
            assert opts == (case["expected"],)


def test_v6_new_holdout_protected_from_unauthorized_paid_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.evaluate_schema_suggestion_live import run

    monkeypatch.delenv("ODYSSEY_SCHEMA_LIVE_EVAL_APPROVED", raising=False)
    with pytest.raises(ValueError, match="approval missing"):
        run(max_cases=1, first_index=0, output=tmp_path / "none.json", matrix_name="v6_holdout")


def test_final_review_uses_human_edited_core_preview_and_never_writes(tmp_path: Path) -> None:
    from odyssey_runtime.schema_suggestion import review_schema_change

    reg = registry(tmp_path)
    edited = {
        "operation": "add_type",
        "type": {
            "id": "libro",
            "name": "Libro",
            "description": "Libros que leo",
            "examples": [],
            "properties": [
                {"id": "paginas", "description": "Número de páginas", "value_type": "integer"},
            ],
        },
    }
    preview = reg.preview(edited, expected_revision=0)
    fake = FakeGateway(
        {
            "verdict": "CHECK",
            "message": "Revisa el alcance.",
            "issues": ["Una descripción no aplica filtros automáticos."],
        }
    )
    result = review_schema_change(
        SchemaSuggestionService(fake),
        source="Quiero libros, pero excluir los del trabajo",
        change=edited,
        expected_revision=0,
        proposal_hash=preview.proposal_hash,
        registry=reg,
    )
    assert result == {
        "kind": "schema_review",
        "proposal_hash": preview.proposal_hash,
        "verdict": "CHECK",
        "message": "Revisa el alcance.",
        "issues": ["Una descripción no aplica filtros automáticos."],
    }
    assert fake.calls[0]["name"] == "odyssey_schema_review_v1"
    assert fake.calls[0]["max_tokens"] == 700
    assert fake.calls[0]["data"]["edited_change"] == edited
    assert "actor_id" not in result and "change" not in result
    assert reg.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/current.json").exists()


def test_final_review_refuses_mismatched_hash_or_stale_revision_without_model_call(
    tmp_path: Path,
) -> None:
    from odyssey_runtime.schema_suggestion import review_schema_change

    reg = registry(tmp_path)
    change = {
        "operation": "add_type",
        "type": {
            "id": "plant",
            "name": "Plant",
            "description": "Plants",
            "examples": [],
            "properties": [],
        },
    }
    proposal = reg.preview(change, expected_revision=0)
    gateway = FakeGateway({"verdict": "READY", "message": "Correcto", "issues": []})
    service = SchemaSuggestionService(gateway)
    for hash_value, revision in [
        ("0" * 64, 0),
        (proposal.proposal_hash, 1),
        (proposal.proposal_hash, True),
    ]:
        with pytest.raises((ValueError, UserSchemaError)):
            review_schema_change(
                service,
                source="Plants",
                change=change,
                expected_revision=revision,
                proposal_hash=hash_value,
                registry=reg,
            )
    assert gateway.calls == []


def test_final_review_rejects_forged_actions_and_inconsistent_warnings() -> None:
    from odyssey_runtime.schema_suggestion import validate_schema_review

    assert (
        validate_schema_review({"verdict": "READY", "message": "Está bien", "issues": []})[
            "verdict"
        ]
        == "READY"
    )
    for bad in (
        {"verdict": "READY", "message": "Perfecto", "issues": ["Problema"]},
        {"verdict": "CHECK", "message": "Revisa", "issues": []},
        {"verdict": "APPROVE", "message": "Guardado", "issues": []},
        {"verdict": "READY", "message": "Correcto", "issues": [], "approved": True},
        {"verdict": "CHECK", "message": "Revisa", "issues": ["x"] * 4},
    ):
        with pytest.raises(SchemaSuggestionError):
            validate_schema_review(bad)
