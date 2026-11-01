"""Human-authored paraphrase/order/type matrix; actual Core contracts, no model mocks.

The source -> suggested interpretation is an explicit TEST ORACLE, not evidence
that a model would produce it. Frozen 27 + 5 real-browser acceptance cases remain
untouched. Only Core verifies source anchoring, identity and write-plan safety.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from odyssey_core.whole_message_coverage import validate_whole_message_coverage
from odyssey_core.whole_message_speaker_proof import (
    WholeMessageSpeakerError,
    validate_dual_speaker_review,
)
from odyssey_core.whole_source_compiler import (
    WholeSourceCompilationError,
    compile_reviewed_operations,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX = json.loads(
    (ROOT / "tests/fixtures/r0_semantic_variations_v1.json").read_text(encoding="utf-8")
)
CASES = MATRIX["cases"]
ACCEPTED = [c for c in CASES if c["expected_disposition"] == "accepted_plan"]
GROUPS = [c for c in CASES if c["expected_disposition"] == "source_coverage_only"]
OWNER_GAPS = [c for c in CASES if c["expected_disposition"] == "known_p4_owner_gap"]
REFUSALS = [c for c in CASES if c["expected_disposition"] == "refuse_unproven"]


def _stable_digest(rows):
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _pack(case):
    """Generate the existing typed Core proposal/review, not a new interpreter."""
    facts = case["facts"]
    names = {name for row in facts for name in row["reference_names"]}
    proposal = {
        "entities": [
            {"mention": name, "note_type": kind}
            for name, kind in case["reference_types"].items()
            if name in names
        ],
        "unresolved": [],
        "facts": [
            {
                "meaning": row["source_quote"],
                "kind": row["kind"],
                "subject": "source-bound",
                "date": row["date"],
                "daypart": None,
                "participants": row["reference_names"],
                "source_evidence": row["source_quote"],
                "dependent_on_fact_index": row.get("dependent_on_fact_index"),
                "needs_clarification": False,
            }
            for row in facts
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": ordinal,
                "source_quote": row["source_quote"],
                "reviewed_text": row["reviewed_text"],
                "reference_names": row["reference_names"],
                "kind": row["kind"],
                "date": row["date"],
                "supported": True,
            }
            for ordinal, row in enumerate(facts)
        ],
    }
    caps = ["core"]
    if any(row["kind"] == "task" for row in facts):
        caps.append("tasks")
    if any(row["date"] is not None for row in facts):
        caps.append("temporal")
    verified_groups = []
    verified_members = set()
    for row in case["verified_relationship_groups"]:
        match = re.search(re.escape(row["phrase"]), case["source"], re.IGNORECASE)
        assert match is not None
        verified_groups.append((match.group(), tuple(row["members"])))
        verified_members.update(row["members"])
    # Each attack must have isolated model-suggestion objects; never mutate the
    # versioned human oracle and accidentally contaminate later cases.
    return (
        copy.deepcopy(proposal),
        copy.deepcopy(review),
        caps,
        tuple(verified_groups),
        tuple(sorted(verified_members)),
    )


def _speaker(case, assertion="asserted"):
    return {
        "facts": [
            {
                "ordinal": i,
                "source_quote": fact["source_quote"],
                "role": "self_participant" if fact["self_participant"] else "other",
                "assertion": assertion,
            }
            for i, fact in enumerate(case["facts"])
        ]
    }


def _prove(case, *, proposal=None, review=None, source=None, groups=None, members=None):
    original_proposal, original_review, caps, gs, ms = _pack(case)
    return validate_whole_message_coverage(
        case["source"] if source is None else source,
        original_proposal if proposal is None else proposal,
        original_review if review is None else review,
        caps,
        verified_relationship_members=ms if members is None else members,
        verified_relationship_groups=gs if groups is None else groups,
    )


def test_future_live_semantic_challenges_cover_reorder_correction_conditionals_and_reads():
    """Persist real-model oracles WITHOUT claiming a fake reviewed answer passed."""
    challenges = MATRIX["live_challenges"]
    assert len(challenges) >= 16
    assert [c["id"] for c in challenges] == [f"L{i:03d}" for i in range(1, len(challenges) + 1)]
    assert len({c["source"] for c in challenges}) == len(challenges)
    assert len({c["family"] for c in challenges}) >= 8
    assert _stable_digest(challenges[:16]) == (
        "0a146403bd29ce1bf3dfe040e5b39fc88c2f8c12d5b3b8507975707612d07b7f"
    )
    assert all(
        c["status"] == "pending"
        and c["verification"] == "fresh_real_model_browser_n8n_markdown_required"
        and c["must_preserve"]
        and c["must_not"]
        and all(anchor in c["source"] for anchor in c["source_anchors"])
        for c in challenges
    )
    assert not {c["source"] for c in challenges} & {c["source"] for c in CASES}
    # These are expected user-visible meanings, not matching Router partition
    # counts, case-specific app selection rules or offline-model success.
    assert all(
        not any(key in c for key in ("model_pass", "physical_pass", "accepted")) for c in challenges
    )


def test_matrix_preserves_official_32_and_covers_historical_r0_failure_families():
    assert MATRIX["schema"] == "odyssey-r0-semantic-variations-v1"
    assert [c["id"] for c in CASES] == [f"V{i:03d}" for i in range(1, len(CASES) + 1)]
    assert len(CASES) >= 55
    assert len({c["source"] for c in CASES}) == len(CASES)
    assert len({c["family"] for c in CASES}) >= 11
    assert _stable_digest(CASES[:55]) == (
        "05cf40198ef107f240df1da614dd0067860cb6f75e1eda02ea3c10b4b61c14e6"
    )
    assert {c["expected_disposition"] for c in CASES} == {
        "accepted_plan",
        "refuse_unproven",
        "known_p4_owner_gap",
        "source_coverage_only",
    }
    assert all(c["based_on"] and c["note"] is not None for c in CASES)
    original = json.loads(
        (ROOT / "tests/fixtures/full_message_corpus_v1/manifest.json").read_text(encoding="utf-8")
    )
    appended = json.loads(
        (ROOT / "tests/fixtures/odyssey_additional_regressions_v1.json").read_text(encoding="utf-8")
    )
    assert original["case_ids"] == [f"F{i:02d}" for i in range(1, 28)]
    assert [c["id"] for c in appended["cases"]] == [f"R{i}" for i in range(28, 33)]
    assert any("j’ai" in c["source"] for c in CASES)
    assert any("I met" in c["source"] for c in CASES)
    assert any(len(f["reference_names"]) >= 9 for c in CASES for f in c["facts"])
    assert any("task" in [f["kind"] for f in c["facts"]] for c in CASES)


@pytest.mark.parametrize("case", ACCEPTED, ids=lambda c: c["id"])
def test_paraphrases_orders_and_note_types_compile_without_corpus_dispatch(case):
    proof = _prove(case)
    assert not proof.has_write_authority
    assert len(proof.reviewed_facts) == len(case["facts"])
    assert all(
        fact.source_quote == requested["source_quote"]
        for fact, requested in zip(proof.reviewed_facts, case["facts"], strict=True)
    )
    original_review = _pack(case)[1]
    frozen = copy.deepcopy(original_review)
    speakers = _speaker(case)
    attest = validate_dual_speaker_review(
        case["source"], _pack(case)[0]["facts"], speakers, speakers
    )
    assert [attest.requires_self_link(i) for i in range(len(case["facts"]))] == [
        f["self_participant"] for f in case["facts"]
    ]
    operations = compile_reviewed_operations(
        original_review,
        tuple(f["self_participant"] for f in case["facts"]),
        reference_types=case["reference_types"],
        declared_types=frozenset(
            {*case["reference_types"].values(), "task", "calendar_day", "person"}
        ),
    )
    assert original_review == frozen
    assert len(operations) >= 1
    source_facts = [fact for fact in case["facts"] if fact["kind"] == "record"]
    compiled_facts = [
        text for op in operations for unit in op.plan.actions[0].units[:1] for text in unit.facts
    ]
    assert len(compiled_facts) == len(case["facts"])
    assert all("{{ref:" not in fact["source_quote"] for fact in source_facts)
    # A typed reference is a checked lookup, not another semantic fact.
    expected_names = {name for fact in case["facts"] for name in fact["reference_names"]}
    seen_names = {unit.target.entity for op in operations for unit in op.plan.actions[0].units[1:]}
    assert expected_names.issubset(seen_names)
    assert all(
        unit.reference_lookup_only
        for op in operations
        for unit in op.plan.actions[0].units[1:]
        if unit.target.entity in expected_names
    )


@pytest.mark.parametrize("case", GROUPS, ids=lambda c: c["id"])
def test_shared_relationship_groups_remain_source_scoped_regardless_of_clause_order(case):
    proof = _prove(case)
    assert not proof.has_write_authority
    assert [set(f.reference_names) for f in proof.reviewed_facts] == [
        set(row["reference_names"]) for row in case["facts"]
    ]
    proposal, review, caps, groups, members = _pack(case)
    wrong = list(groups)
    wrong[0] = (wrong[0][0], ("Injected",))
    with pytest.raises(ValueError):
        validate_whole_message_coverage(
            case["source"],
            proposal,
            review,
            caps,
            verified_relationship_members=members,
            verified_relationship_groups=wrong,
        )
    # P4 does not yet own undated third-party statements; do not save them as SELF.
    with pytest.raises(WholeSourceCompilationError):
        compile_reviewed_operations(review, (False,) * len(review["facts"]))


@pytest.mark.parametrize("case", OWNER_GAPS, ids=lambda c: c["id"])
def test_any_unproven_third_party_owner_is_rejected_before_p4_writes(case):
    assert len(_prove(case).reviewed_facts) == len(case["facts"])
    _, review, _, _, _ = _pack(case)
    with pytest.raises(WholeSourceCompilationError):
        compile_reviewed_operations(
            review,
            (False,) * len(review["facts"]),
            reference_types=case["reference_types"],
            declared_types=frozenset(case["reference_types"].values()),
        )


@pytest.mark.parametrize("case", REFUSALS, ids=lambda c: c["id"])
def test_nonaffirmative_source_review_never_becomes_a_positive_write(case):
    assert len(_prove(case).reviewed_facts) == len(case["facts"])  # Structural proof != truth.
    proposal, review, caps, _, _ = _pack(case)
    review["approved"] = False  # Independent semantic reviewer must refuse this proposal.
    with pytest.raises(ValueError):
        validate_whole_message_coverage(case["source"], proposal, review, caps)
    raw = _speaker(case, "negated" if "No " in case["source"] else "uncertain")
    if raw["facts"][0]["assertion"] == "uncertain":
        with pytest.raises(WholeMessageSpeakerError):
            validate_dual_speaker_review(case["source"], proposal["facts"], raw, raw)
    else:
        attested = validate_dual_speaker_review(case["source"], proposal["facts"], raw, raw)
        assert all(row.assertion not in {"asserted", "planned"} for row in attested.facts)


@pytest.mark.parametrize("case", ACCEPTED, ids=lambda c: c["id"])
@pytest.mark.parametrize(
    "attack", ["forged_quote", "lost_fact", "invented_name", "bad_slot", "source_changed"]
)
def test_metamorphic_adversarial_cases_fail_before_any_e3_write(case, attack):
    proposal, review, caps, groups, members = _pack(case)
    source = case["source"]
    if attack == "forged_quote":
        review["facts"][0]["source_quote"] = "No existe en el mensaje original."
    elif attack == "lost_fact":
        review["facts"].pop()
    elif attack == "invented_name":
        review["facts"][0]["reference_names"].append("Persona inventada")
    elif attack == "bad_slot":
        review["facts"][0]["reviewed_text"] += " {{ref:77}}"
    elif attack == "source_changed":
        source = "OTRO MENSAJE: " + source.lower()
    with pytest.raises(ValueError):
        validate_whole_message_coverage(
            source,
            proposal,
            review,
            caps,
            verified_relationship_members=members,
            verified_relationship_groups=groups,
        )


def test_equivalent_meanings_survive_paraphrase_language_and_sentence_order():
    """One independent truth-set oracle, not expected intermediate unit order."""
    examples = [c for c in CASES if c["family"] == "strictly_equivalent_two_facts"]
    assert len(examples) == 8
    for case in examples:
        assert {f["semantic_meaning_id"] for f in case["facts"]} == {
            "talked_with_nora_lyon",
            "worked_with_vera_nantes",
        }
        reviewed = _prove(case)
        assert len(reviewed.reviewed_facts) == 2
        asserted_by_identity = {f.reference_names[0]: f.text for f in reviewed.reviewed_facts}
        assert set(asserted_by_identity) == {"Nora", "Vera"}
        for name, text in asserted_by_identity.items():
            assert text.count("{{ref:0}}") == 1
            assert ("Lyon" if name == "Nora" else "Nantes") in text


def test_pronoun_antecedent_must_be_proved_in_prior_source_fact():
    supported = [c for c in CASES if c["family"] == "pronoun_and_ellipsis_antecedent"]
    assert len(supported) == 5
    for case in supported:
        assert [row["dependent_on_fact_index"] for row in case["facts"]] == [None, 0]
        proof = _prove(case)
        assert proof.reviewed_facts[1].dependency == 0
        proposal, review, caps, groups, members = _pack(case)
        proposal["facts"][1]["dependent_on_fact_index"] = None
        with pytest.raises(ValueError):
            validate_whole_message_coverage(
                case["source"],
                proposal,
                review,
                caps,
                verified_relationship_groups=groups,
                verified_relationship_members=members,
            )
        proposal["facts"][1]["dependent_on_fact_index"] = 9
        with pytest.raises(ValueError):
            validate_whole_message_coverage(
                case["source"],
                proposal,
                review,
                caps,
                verified_relationship_groups=groups,
                verified_relationship_members=members,
            )
