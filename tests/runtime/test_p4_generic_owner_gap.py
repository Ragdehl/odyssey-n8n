"""R0: show the existing generic Core owner vs the P4 owner-loss boundary.

Synthetic vault and recorded model outputs ONLY. This is a diagnosis of an
unresolved product gap, not a declaration that P4 can write arbitrary owners.
"""

from __future__ import annotations

import pytest

from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
)
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture, _speaker


@pytest.mark.parametrize(
    ("note_type", "source", "fact_text"),
    [
        ("project", "El proyecto Atlas tiene prioridad alta.", "Tiene prioridad alta."),
        ("document", "Atlas requiere una revisión.", "Requiere una revisión."),
        ("concept", "Atlas requiere una revisión.", "Requiere una revisión."),
    ],
)
def test_existing_core_can_target_a_note_but_p4_must_not_claim_unowned_fact_saved(
    tmp_path, note_type, source, fact_text
):
    repo, actor, service, runtime = _fixture(tmp_path)
    create_entity(
        repo,
        service.schema,
        path="Atlas.md",
        entity_id="atlas-id",
        metadata={"name": "Atlas", "type": note_type},
        content="",
        actor="fixture",
        now="2026-10-16T11:00:00+02:00",
    )
    # Existing Core semantic writer correctly represents the owner without
    # creating an identity, app-specific note handler or second writer.
    semantic = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                IdentityIntent("Atlas", IdentityBinding.DESCRIBED, "Atlas", note_type),
                ApplyTo.ONE,
                "record",
                (SemanticFact((LiteralPart(fact_text),)),),
                (),
                (),
                None,
            ),
        )
    )
    compiled = compile_semantic_write(semantic, service.schema)
    assert len(compiled.units) == 1
    assert compiled.units[0].target.type == note_type
    assert compiled.units[0].target.entity == "Atlas"
    assert compiled.units[0].facts == (fact_text,)

    # In the P4 whole-source path, the current reviewer *does* preserve the
    # source and identity proposal, but the old compiler has only Day/SELF
    # owners. It must not silently rewrite a third-party fact into SELF.
    route = {
        "capabilities": ["core"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": "Atlas",
                "canonical_name": None,
                "note_type": note_type,
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": source,
                "kind": "record",
                "subject": "Atlas",
                "date": None,
                "daypart": None,
                "participants": [],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    reviewed = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": fact_text,
                "date": None,
                "reference_names": [],
                "supported": True,
            }
        ],
    }
    service.client = RecordedClient(
        [
            route,
            proposal,
            reviewed,
            _speaker(source, proposal, role="other", base=1),
            _speaker(source, proposal, role="other"),
        ]
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    outcome = runtime.execute_product(source, f"owner-gap-{note_type}", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert not parse_note(repo.read_text("Atlas.md")).content
    replay = runtime.execute_product(source, f"owner-gap-{note_type}", "main", actor)
    assert replay["delivery_replayed"] is True
