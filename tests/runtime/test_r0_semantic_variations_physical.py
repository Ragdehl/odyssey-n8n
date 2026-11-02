"""Actual E3 physical note readback for varied source order, wording and types.

All model interpretations are synthetic, explicit test oracles. This does not
exercise a fresh provider, product HTTP or authenticated browser.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.notes import parse_note
from odyssey_core.whole_source_compiler import compile_reviewed_operations
from tests.core.test_r0_semantic_variations_matrix import CASES, _pack, _prove
from tests.runtime.test_whole_source_light_product_p4 import _fixture

# The fixed acceptance 32 are not altered. This deliberately crosses all
# affirmative non-App families and includes reversed clauses and FR/EN.
IDS = {
    "V001",
    "V002",
    "V005",
    "V006",
    "V007",
    "V008",
    "V011",
    "V012",
    "V013",
    "V014",
    "V016",
    "V017",
    "V018",
    "V019",
    "V020",
    "V021",
    "V022",
    "V040",
    "V041",
    "V042",
    "V045",
    "V046",
    "V047",
    "V048",
    "V050",
    "V052",
}
SELECTED = [c for c in CASES if c["id"] in IDS]


def _display_without_wikilinks(text: str) -> str:
    return re.sub(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]", lambda found: found.group(1), text)


def _expected_rendered_fact(fact: dict) -> str:
    return re.sub(
        r"\{\{ref:(\d+)\}\}",
        lambda match: fact["reference_names"][int(match.group(1))],
        fact["reviewed_text"],
    )


@pytest.mark.parametrize("case", SELECTED, ids=lambda c: c["id"])
def test_paraphrase_and_order_reach_authorized_e3_markdown_without_lost_facts(tmp_path, case):
    assert len(SELECTED) == len(IDS) == 26
    assert not _prove(case).has_write_authority
    _, review, _, _, _ = _pack(case)
    operations = compile_reviewed_operations(
        review,
        tuple(row["self_participant"] for row in case["facts"]),
        reference_types=case["reference_types"],
        declared_types=frozenset({*case["reference_types"].values(), "person", "calendar_day"}),
    )
    assert len(operations) == 1
    repo, actor, service, _runtime = _fixture(tmp_path)
    referenced = list(
        dict.fromkeys(name for row in case["facts"] for name in row["reference_names"])
    )
    for i, name in enumerate(referenced):
        create_entity(
            repo,
            service.schema,
            path=f"{name}.md",
            entity_id=f"test-identity-{i}",
            metadata={"name": name, "type": case["reference_types"][name]},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    if referenced:
        service.refresh_affected_indexes(
            tuple(f"test-identity-{i}" for i in range(len(referenced)))
        )
    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda *_args: operations[0].plan),
        repository=repo,
        schema=service.schema,
        context_index=service.context_index,
        semantic_index=service.semantic_index,
        embedder=service.embedder,
        contextual_reasoner=service.reasoner,
        actor=actor.stable_user_id,
        now="2026-10-16T15:30:00+02:00",
        context_limit=20,
        authenticated_actor=actor,
        self_binding_repository=service.bindings,
        request_id_factory=lambda: f"variation-{case['id']}",
    )
    assert result.status is ApplicationStatus.COMPLETED, (case["id"], result)
    target = "calendar/days/2026-10-16.md" if case["facts"][0]["date"] is not None else "self.md"
    actual = _display_without_wikilinks(parse_note(repo.read_text(target)).content)
    for fact in case["facts"]:
        expected = _expected_rendered_fact(fact).rstrip(".")
        matching_lines = [line for line in actual.splitlines() if expected in line]
        assert len(matching_lines) == 1, (case["id"], expected, actual)
        # The earlier double-renumbering bug could silently attach an identity
        # from another fact. Each physical line owns exactly its grounded names.
        assert all(
            name not in matching_lines[0]
            for name in referenced
            if name not in fact["reference_names"]
        ), (case["id"], expected, matching_lines[0])
    assert "{{ref:" not in actual
    # A readback must not invent a new identity or duplicate an existing note.
    # E3 also maintains its real audit/capture Day on the trusted NOW even for
    # an undated SELF fact. It is metadata, not a second semantic owner.
    assert set(repo.list_markdown_paths()) == (
        {"self.md", "calendar/days/2026-10-16.md", *[f"{name}.md" for name in referenced]}
    )
