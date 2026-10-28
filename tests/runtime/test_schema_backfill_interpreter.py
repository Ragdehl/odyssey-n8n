"""Source-bounded semantic model proposals; fake provider, real local Core writes.

Not a fresh-model prompt evaluation. End-to-end provider validation remains an
adoption gate before enabling the feature for a real user's local vault.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.schema_auto_backfill import (
    AutoBackfillError,
    AutomaticPropertyBackfill,
)
from odyssey_core.schema_retrospection import SourceFact, SourceNote
from odyssey_runtime.schema_backfill_interpreter import (
    DECISION_SCHEMA,
    EXTRACT_INSTRUCTIONS,
    REVIEW_INSTRUCTIONS,
    REVIEW_SCHEMA,
    BackfillInterpretationError,
    SemanticBatchEnricher,
    SemanticPropertyInterpreter,
    prompt_hashes,
    validate_decision,
    validate_independent_review,
)

ROOT = Path(__file__).resolve().parents[2]
TEXT = "Antes ejercía de médica, pero ahora trabaja como profesora de primaria."
ID = "note-persona-a"
FACT = SourceFact("src-1:0", TEXT)
DEF = {
    "id": "profesion",
    "value_type": "string",
    "description": "Profesión actual",
    "required": False,
}


def source(*, body=TEXT, legacy="", note_id=ID):
    return SourceNote(
        note_id=note_id,
        note_name="Ana",
        note_type="person",
        path="ana.md",
        source_hash="a" * 64,
        revision=1,
        facts=(SourceFact("src-1:0", body),),
        legacy_coverage_unverified=bool(legacy),
        legacy_text=legacy,
    )


def proposal(
    *, locator="src-1:0", quote="ahora trabaja como profesora de primaria", value="profesora"
):
    return {"decision": "SET", "locator": locator, "quote": quote, "value": value}


def approval(
    *,
    locator="src-1:0",
    quote="ahora trabaja como profesora de primaria",
    value="profesora",
    reason="ENTAILED_CURRENT",
):
    return {
        "verdict": "APPROVE",
        "reason": reason,
        "locator": locator,
        "quote": quote,
        "value": value,
    }


class FakeGateway:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def _complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


def test_staged_two_model_calls_preserve_whole_source_and_emits_internal_review():
    gateway = FakeGateway(proposal(), approval())
    reviewed = SemanticPropertyInterpreter(gateway).propose_and_review(
        source=source(), type_id="person", property_definition=DEF
    )
    assert reviewed is not None and reviewed.value == "profesora"
    assert reviewed.source_hash == "a" * 64
    assert reviewed.source_locator == "src-1:0"
    assert len(gateway.calls) == 2
    assert gateway.calls[0]["name"] == "odyssey_schema_backfill_interpret_v1"
    assert gateway.calls[1]["name"] == "odyssey_schema_backfill_review_v1"
    assert gateway.calls[0]["data"]["marked_atomic_facts"][0]["text"] == TEXT
    assert gateway.calls[1]["data"]["untrusted_interpreter_proposal"]["value"] == "profesora"
    assert "conditional" in EXTRACT_INSTRUCTIONS and "past" in REVIEW_INSTRUCTIONS
    assert DECISION_SCHEMA["additionalProperties"] is False
    assert REVIEW_SCHEMA["additionalProperties"] is False
    assert all(len(x) == 64 for x in prompt_hashes().values())


def test_independent_reviewer_rejection_and_mismatched_attestation_fail_closed():
    gateway = FakeGateway(
        proposal(), {**approval(), "verdict": "REJECT", "reason": "TEMPORAL_AMBIGUITY"}
    )
    assert (
        SemanticPropertyInterpreter(gateway).propose_and_review(
            source=source(), type_id="person", property_definition=DEF
        )
        is None
    )
    mismatch = FakeGateway(proposal(), {**approval(), "value": "médica"})
    with pytest.raises(BackfillInterpretationError, match="same evidence"):
        SemanticPropertyInterpreter(mismatch).propose_and_review(
            source=source(), type_id="person", property_definition=DEF
        )


@pytest.mark.parametrize(
    "candidate",
    [
        {**proposal(), "source_id": "forged"},
        {**proposal(), "locator": "wrong:0"},
        {**proposal(), "quote": "profesora de universidad"},
        {**proposal(), "quote": "a"},
        {**proposal(), "value": 3},
        {**proposal(), "value": True},
        {"decision": "NO_EVIDENCE", "locator": "src-1:0", "quote": None, "value": None},
        {**proposal(), "decision": "AUTO_WRITE"},
    ],
)
def test_invalid_or_ungrounded_model_output_is_rejected(candidate):
    with pytest.raises(BackfillInterpretationError):
        validate_decision(candidate, source(), DEF)


def test_non_set_decisions_abstain_without_second_paid_call():
    for decision in ("CONFLICT", "NO_EVIDENCE"):
        gateway = FakeGateway({"decision": decision, "locator": None, "quote": None, "value": None})
        assert (
            SemanticPropertyInterpreter(gateway).propose_and_review(
                source=source(), type_id="person", property_definition=DEF
            )
            is None
        )
        assert len(gateway.calls) == 1


def test_legacy_missing_atomic_source_large_corpus_and_explicit_data_skip_models():
    for input_source in (
        replace(source(), legacy_text="La profesión era médica", legacy_coverage_unverified=True),
        replace(source(), facts=()),
        replace(source(), facts=(FACT,) * 17),
        source(body="Profesion: Profesora"),
        replace(source(), note_name="x" * 241),
    ):
        gateway = FakeGateway()
        assert (
            SemanticPropertyInterpreter(gateway).propose_and_review(
                source=input_source, type_id="person", property_definition=DEF
            )
            is None
        )
        assert not gateway.calls


def test_false_current_semantic_value_is_not_deterministically_guaranteed():
    # Provider-free validation checks locators, quotes, types, and an independent
    # attestation; it deliberately CANNOT prove semantic truth. Live provider
    # evaluation is a separate MUST before accepting source auto-write.
    with pytest.raises(BackfillInterpretationError):
        validate_independent_review(
            {
                "verdict": "APPROVE",
                "reason": "ENTAILED_CURRENT",
                "locator": "src-1:0",
                "quote": "ahora trabaja como profesora de primaria",
                "value": True,
            },
            validate_decision(proposal(), source(), DEF),
        )


def test_provider_nonuse_on_partial_dates_and_unsupported_types():
    full_date = {"id": "nacimiento", "value_type": "date", "description": "Fecha completa"}
    gateway = FakeGateway(proposal(value="2026"))
    with pytest.raises(BackfillInterpretationError, match="field type"):
        SemanticPropertyInterpreter(gateway).propose_and_review(
            source=source(), type_id="person", property_definition=full_date
        )
    empty = FakeGateway()
    assert (
        SemanticPropertyInterpreter(empty).propose_and_review(
            source=source(),
            type_id="person",
            property_definition={"id": "etiquetas", "value_type": "array[string]"},
        )
        is None
    )
    assert not empty.calls


@pytest.mark.parametrize("reviewed_value", ["profesora", "profesora de primaria"])
def test_semantic_approval_binds_review_to_source_and_cannot_overwrite_user_metadata(
    tmp_path: Path,
    reviewed_value: str,
):
    import subprocess

    from odyssey_core.notes import Note, parse_note, serialize_note
    from odyssey_core.schema_retrospection import scan_schema_sources
    from odyssey_core.storage import VaultRepository

    vault = tmp_path / "vault"
    vault.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    person = next(item for item in schema["types"] if item["id"] == "person")
    person["properties"].append({**DEF, "filterable": True})
    note = Note(
        {
            "id": ID,
            "name": "Ana",
            "type": "person",
            "schema_version": 3,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "created_by": {"human": None, "app": "tests"},
            "updated_by": {"human": None, "app": "tests"},
            "revision": 1,
            "aliases": [],
            "tags": [],
        },
        "# Added 01-01-2026\n- " + TEXT + "\n<!-- odyssey:fact request=src-1 ordinal=0 -->\n",
    )
    (vault / "ana.md").write_text(serialize_note(note))
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
    ):
        subprocess.run(["git", *args], cwd=vault, check=True, capture_output=True, timeout=10)
    repo = VaultRepository(vault)
    scanned = scan_schema_sources(
        repository=repo,
        schema=schema,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
    ).eligible_notes[0]
    g = FakeGateway(proposal(value=reviewed_value), approval(value=reviewed_value))
    reviewed = SemanticPropertyInterpreter(g).propose_and_review(
        source=scanned, type_id="person", property_definition=DEF
    )
    assert reviewed is not None
    writer = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(vault)
    )
    receipt = writer.apply(
        source=scanned,
        type_id="person",
        property_id="profesion",
        actor={"human": None, "app": "odyssey-backfill"},
        now="2026-10-26T12:00:00+00:00",
        request_id="semantic-1",
        reviewed_semantic=reviewed,
    )
    assert receipt.status == "updated" and receipt.undo_commit
    updated = parse_note(repo.read_text("ana.md"))
    assert updated.metadata["profesion"] == reviewed_value
    assert updated.metadata["revision"] == 2
    assert updated.content == note.content
    assert (
        writer.apply(
            source=scanned,
            type_id="person",
            property_id="profesion",
            actor={"human": None, "app": "odyssey-backfill"},
            now="2026-10-26T12:00:00+00:00",
            request_id="semantic-replay",
            reviewed_semantic=reviewed,
        ).status
        == "stale"
    )
    # Same reviewer output cannot be replayed against a different physical note.
    with pytest.raises(AutoBackfillError, match="not bound"):
        writer.apply(
            source=replace(scanned, note_id="fake-owner"),
            type_id="person",
            property_id="profesion",
            actor={"human": None, "app": "odyssey-backfill"},
            now="2026-10-26T12:00:00+00:00",
            request_id="semantic-forgery",
            reviewed_semantic=reviewed,
        )


def test_batch_enriches_without_per_note_approval_and_skips_ambiguous_notes(tmp_path: Path):
    import subprocess

    from odyssey_core.notes import Note, parse_note, serialize_note
    from odyssey_core.schema_retrospection import scan_schema_sources
    from odyssey_core.storage import VaultRepository

    vault = tmp_path / "vault"
    vault.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    next(item for item in schema["types"] if item["id"] == "person")["properties"].append(
        {**DEF, "filterable": True}
    )
    examples = [
        "Profesión: farmacéutica",
        "Antes era médica, pero ahora trabaja como profesora de primaria.",
        "Profesión: médico\n- profesión: ingeniero",  # conflicting legacy field
    ]
    for i, content in enumerate(examples):
        # Last extra line deliberately has no fact locator and must not be
        # silently ignored just because the first line is well formed.
        note = Note(
            {
                "id": f"persona-{i}",
                "name": f"Persona {i}",
                "type": "person",
                "schema_version": 3,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "created_by": {"human": None, "app": "tests"},
                "updated_by": {"human": None, "app": "tests"},
                "revision": 1,
                "aliases": [],
                "tags": [],
            },
            "# Added 01-01-2026\n- "
            + content
            + f"\n<!-- odyssey:fact request=src{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(note))
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-q",
            "-m",
            "baseline",
        ),
    ):
        subprocess.run(["git", *args], cwd=vault, check=True, capture_output=True, timeout=10)
    repo = VaultRepository(vault)
    sources = scan_schema_sources(
        repository=repo,
        schema=schema,
        kind="backfill_property",
        target_type_id="person",
        property_id="profesion",
        limit=20,
    ).eligible_notes
    gateway = FakeGateway(
        proposal(locator="src1:0", quote="ahora trabaja como profesora de primaria"),
        approval(locator="src1:0", quote="ahora trabaja como profesora de primaria"),
    )
    stage = SemanticBatchEnricher(
        AutomaticPropertyBackfill(
            repository=repo, schema=schema, history=GitHistoryRecorder(vault)
        ),
        SemanticPropertyInterpreter(gateway),
    )
    receipts, summary = stage.run_batch(
        sources=sources,
        type_id="person",
        property_id="profesion",
        actor={"human": None, "app": "odyssey-autofill"},
        now="2026-10-26T12:00:00+00:00",
        request_prefix="semantic-batch",
    )
    assert [x.status for x in receipts] == ["updated", "updated", "ambiguous"]
    assert summary.updated == 2 and summary.ambiguous == 1 and summary.undo_commits == 2
    assert len(gateway.calls) == 2  # interpret/review only prose source
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "farmacéutica"
    assert parse_note(repo.read_text("1.md")).metadata["profesion"] == "profesora"
    assert "profesion" not in parse_note(repo.read_text("2.md")).metadata
    assert not any(x.get("confirm") for x in gateway.calls)


def test_frozen_semantic_matrix_has_all_risk_categories_and_original_locators():
    fixture = json.loads((ROOT / "tests/fixtures/schema_backfill/evaluation_v1.json").read_text())
    cases = fixture["cases"]
    assert len(cases) >= 18
    assert {item["language"] for item in cases} == {"es", "fr", "en"}
    assert {item["expected_decision"] for item in cases} == {"SET", "NO_EVIDENCE", "CONFLICT"}
    assert len({item["case"] for item in cases}) == len(cases)
    for item in cases:
        assert item["expected_value"] is not None or item["expected_decision"] != "SET"
        assert item["facts"]
        assert all(f["locator"].startswith("src-") and f["text"] for f in item["facts"])
    assert all("evaluat" not in x.get("status", "") for x in cases)


def test_independent_semantic_pass_can_resolve_later_correction_with_two_marked_facts():
    from odyssey_core.schema_auto_backfill import choose_explicit_backfill

    two_facts = replace(
        source(),
        facts=(
            SourceFact("old:0", "Profesión: médica"),
            SourceFact(
                "now:0",
                "Antes era médica, pero ahora trabaja como profesora de primaria.",
            ),
        ),
    )
    assert (
        choose_explicit_backfill(two_facts, type_id="person", definition=DEF).status == "ambiguous"
    )
    gateway = FakeGateway(
        proposal(locator="now:0"),
        approval(locator="now:0"),
    )
    reviewed = SemanticPropertyInterpreter(gateway).propose_and_review(
        source=two_facts, type_id="person", property_definition=DEF
    )
    assert reviewed is not None and reviewed.value == "profesora"
    assert len(gateway.calls) == 2
    assert len(gateway.calls[1]["data"]["marked_atomic_facts"]) == 2
