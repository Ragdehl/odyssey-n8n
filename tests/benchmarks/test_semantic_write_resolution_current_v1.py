"""Provider-free sentinels for the current-schema bounded-source successor."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.semantic_write_resolution_current_v1.evaluate import evaluate, load_registry
from odyssey_core.request_planning import RequestPlan
from odyssey_core.semantic_write import (
    ApplyTo,
    CandidateScope,
    CandidateScopeExtent,
    ExistingSource,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
)

ROOT = Path(__file__).resolve().parents[2]


def _schema() -> dict:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def _identity(description: str, scope: CandidateScope) -> IdentityIntent:
    return IdentityIntent(
        description,
        IdentityBinding.DESCRIBED,
        note_type="person",
        candidate_scope=scope,
    )


def _self_member(description: str) -> IdentityIntent:
    return _identity(
        description,
        CandidateScope(IdentityBinding.SELF, "mi hija", CandidateScopeExtent.ONE_MEMBER),
    )


def _directory_member(description: str) -> IdentityIntent:
    return _identity(
        description,
        CandidateScope(
            ExistingSource("Directorio Faro"),
            "las personas del Directorio Faro",
            CandidateScopeExtent.ONE_MEMBER,
        ),
    )


def _compile(target: IdentityIntent, fact: SemanticFact):
    action = compile_semantic_write(
        SemanticWriteIntent(
            (SemanticWriteOperation(target, ApplyTo.ONE, "record", facts=(fact,)),)
        ),
        _schema(),
    )
    return RequestPlan((action,), ())


def test_current_registry_is_separate_from_historical_journal_event_sentinels() -> None:
    registry = load_registry()
    assert registry["version"] == "semantic-write-resolution-current-v1"
    assert registry["schema_contract"] == "current-canonical-document-source"
    assert [case["id"] for case in registry["cases"]] == [
        "CSWR01-qualified-bounded-source-member",
        "CSWR02-relational-target-one-bounded-reference",
        "CSWR03-relational-target-two-bounded-references",
    ]
    assert all("Directorio Faro" in case["request"] for case in registry["cases"])
    assert all("cena relacional" not in case["request"].casefold() for case in registry["cases"])


def test_current_qualified_bounded_source_target_contract() -> None:
    target = _directory_member("la persona del Directorio Faro que trabaja en Airbus Test")
    plan = _compile(target, SemanticFact((LiteralPart("Se ha comprado un paraguas rojo."),)))
    verdict = evaluate(plan, "qualified_bounded_source_target")
    assert verdict.passed, verdict.findings


def test_current_relational_target_with_one_bounded_reference_contract() -> None:
    companion = _directory_member("la persona del Directorio Faro que trabaja en Airbus Test")
    fact = SemanticFact(
        (
            LiteralPart("Va a cenar con "),
            IdentityPart(companion.description, companion),
            LiteralPart("."),
        )
    )
    plan = _compile(_self_member("mi hija mayor"), fact)
    verdict = evaluate(plan, "relational_target_and_one_bounded_reference")
    assert verdict.passed, verdict.findings


def test_current_two_bounded_references_keep_saturday_literal() -> None:
    airbus = _directory_member("la persona del Directorio Faro que trabaja en Airbus Test")
    italian = _directory_member("la persona del Directorio Faro que habla italiano")
    fact = SemanticFact(
        (
            LiteralPart("Va al parque el sábado con "),
            IdentityPart(airbus.description, airbus),
            LiteralPart(" y con "),
            IdentityPart(italian.description, italian),
            LiteralPart("."),
        )
    )
    plan = _compile(_self_member("mi hija mayor"), fact)
    verdict = evaluate(plan, "relational_target_and_two_bounded_references")
    assert verdict.passed, verdict.findings
