"""Type-generic, language-agnostic Router relationship and source boundary contract.

These tests create unrelated assertions and misleading source fragments without
provider calls or canonical writes. Router cannot grant mutation authority.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import (
    OpenAIFactCandidateRouter,
    fact_candidate_json_schema,
    semantic_fact_candidate_json_schema,
    validate_semantic_fact_candidate_proposal,
)
from odyssey_apps.router import RouterError
from odyssey_runtime.hybrid_group_compiler import (
    candidate_decision_trace,
    compile_hybrid_candidate_bundle,
)


def quote(text: str, occurrence: int = 0) -> dict[str, object]:
    return {"text": text, "occurrence": occurrence}


def unit(
    source: str,
    anchor: str,
    *,
    kind: str = "occurrence",
    predicate: str | None = None,
    date: str | None = None,
) -> dict[str, object]:
    assert anchor in source
    scopes = []
    if predicate:
        assert predicate in source
        scopes.append({"role": "predicate", "anchor": quote(predicate)})
    if date:
        assert date in source
        scopes.append({"role": "date", "anchor": quote(date)})
    return {
        "kind": kind,
        "anchors": [quote(anchor)],
        "scoped_source": scopes,
        "inheritance": [],
        "state": "candidate",
    }


def proposal(
    source: str,
    units: list[dict[str, object]],
    links: list[tuple[str, int]],
) -> dict[str, object]:
    assert len(units) == len(links)
    return {
        "version": 2,
        "units": units,
        "semantic_relations": [
            {
                "unit": index,
                "kind": kind,
                "parent_unit": parent,
                "evidence": row["anchors"][0],
            }
            for index, (row, (kind, parent)) in enumerate(zip(units, links, strict=True), 1)
        ],
    }


@pytest.mark.parametrize(
    ("source", "parts", "links", "expected_count"),
    [
        (
            "I ate a blue pear to evaluate the sensor.",
            [
                ("I ate a", "ate", None, "occurrence"),
                ("blue pear", None, None, "property"),
                ("to evaluate the sensor", "evaluate", None, "occurrence"),
            ],
            [
                ("independent_assertion", 0),
                ("attribute_of", 1),
                ("purpose_of", 1),
            ],
            1,
        ),
        (
            "Je répare une voiture bleue pour aider Camille.",
            [
                ("Je répare une voiture", "répare", None, "occurrence"),
                ("bleue", None, None, "property"),
                ("pour aider Camille", "aider", None, "occurrence"),
            ],
            [
                ("independent_assertion", 0),
                ("attribute_of", 1),
                ("purpose_of", 1),
            ],
            1,
        ),
        (
            "El técnico vio una tubería oxidada porque había una fuga.",
            [
                ("El técnico vio una tubería", "vio", None, "occurrence"),
                ("oxidada", None, None, "property"),
                ("porque había una fuga", "había", None, "occurrence"),
            ],
            [
                ("independent_assertion", 0),
                ("attribute_of", 1),
                ("condition_of", 1),
            ],
            1,
        ),
        (
            "I bought a notebook and called my friend.",
            [
                ("I bought a notebook", "bought", None, "purchase_item"),
                ("called my friend", "called", None, "occurrence"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            1,  # preserve BOTH candidates for Core, not a single asserted fact
        ),
        (
            "Compré arroz ayer y fui al cine mañana.",
            [
                ("Compré arroz", "Compré", "ayer", "purchase_item"),
                ("fui al cine", "fui", "mañana", "occurrence"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            2,  # two positive date anchors in original source
        ),
        (
            "Rang Marie. Wrote the report.",
            [
                ("Rang Marie", "Rang", None, "occurrence"),
                ("Wrote the report", "Wrote", None, "occurrence"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            2,
        ),
        (
            "I bought a blue bicycle.",
            [
                ("I bought a", "bought", None, "purchase_item"),
                ("blue bicycle", None, None, "property"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            1,  # even an INCORRECT Router independence claim cannot split it
        ),
        (
            "Je vais au marché pour trouver des légumes.",
            [
                ("Je vais au marché", "vais", None, "occurrence"),
                ("pour trouver des légumes", "trouver", None, "occurrence"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            1,  # another incorrect independence claim: same-clause interpreted together
        ),
        (
            "The bike was red. And very old.",
            [
                ("The bike was red", "was", None, "property"),
                ("very old", None, None, "property"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            1,  # sentence punctuation is not proof of an autonomous predicate
        ),
        (
            "Yesterday I prepared lunch for tomorrow's visitors.",
            [
                ("Yesterday I prepared lunch", "prepared", "Yesterday", "occurrence"),
                ("tomorrow's visitors", None, "tomorrow", "property"),
            ],
            [("independent_assertion", 0), ("independent_assertion", 0)],
            1,  # a later date is not itself a new action
        ),
        (
            "The engine rattled while the mechanic was checking the belts.",
            [
                ("The engine rattled", "rattled", None, "occurrence"),
                ("while the mechanic was checking the belts", "checking", None, "occurrence"),
            ],
            [("independent_assertion", 0), ("unresolved", 0)],
            1,
        ),
    ],
)
def test_generic_semantic_scope_is_not_inferred_from_router_citation(
    source, parts, links, expected_count
):
    rows = [
        unit(source, anchor, predicate=predicate, date=date, kind=kind)
        for anchor, predicate, date, kind in parts
    ]
    validated = validate_semantic_fact_candidate_proposal(source, proposal(source, rows, links))
    assert validated.contract_version == 2
    bundle = compile_hybrid_candidate_bundle(validated)
    assert len(bundle.units) == expected_count
    assert sum(len(route.original_candidate_ids) for route in bundle.units) == len(rows)
    assert "".join(route.route.source_text for route in bundle.units) == source

    trace = candidate_decision_trace(validated, bundle)
    assert trace["candidate_count"] == len(rows)
    assert trace["source_sha256"] == hashlib.sha256(source.encode("utf8")).hexdigest()
    assert len(trace["boundaries"]) == len(rows) - 1
    # No source text, internal model reasoning, credentials or rendered Markdown.
    assert source not in json.dumps(trace)
    assert not any(key in trace for key in ("reasoning", "provider_prompt", "write_plan"))


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (lambda x: x["semantic_relations"].pop(), "cover"),
        (lambda x: x["semantic_relations"][1].update({"unit": 1}), "acyclic"),
        (lambda x: x["semantic_relations"][1].update({"parent_unit": 2}), "acyclic"),
        (lambda x: x["semantic_relations"][1].update({"parent_unit": True}), "acyclic"),
        (lambda x: x["semantic_relations"][1].update({"kind": "canonical_write"}), "acyclic"),
        (
            lambda x: x["semantic_relations"][1].update({"kind": "attribute_of", "parent_unit": 0}),
            "acyclic",
        ),
        (lambda x: x["semantic_relations"][1].update({"evidence": quote("remote")}), "occurrence"),
        (
            lambda x: x["semantic_relations"][1].update({"evidence": quote("I ate a")}),
            "own candidate",
        ),
        (lambda x: x["semantic_relations"][1].update({"unknown": "not allowed"}), "fields"),
        (lambda x: x.update({"canonical_id": "person:any"}), "fields"),
    ],
)
def test_untrusted_semantic_relations_fail_closed(edit, reason):
    source = "I ate a blue pear."
    rows = [
        unit(source, "I ate a", predicate="ate"),
        unit(source, "blue pear", kind="property"),
    ]
    data = proposal(source, rows, [("independent_assertion", 0), ("attribute_of", 1)])
    edit(data)
    with pytest.raises(RouterError, match=reason):
        validate_semantic_fact_candidate_proposal(source, data)


def test_v6_schema_is_strict_without_changing_v1():
    old = fact_candidate_json_schema()
    new = semantic_fact_candidate_json_schema()
    assert old["required"] == ["version", "units"]
    assert old["properties"]["version"]["enum"] == [1]
    assert new["required"] == ["version", "units", "semantic_relations"]
    assert new["properties"]["version"]["enum"] == [2]
    assert new["additionalProperties"] is False
    assert new["properties"]["semantic_relations"]["items"]["additionalProperties"] is False
    assert "semantic_relations" not in old["properties"]
    assert "canonical_id" not in json.dumps(new)


def test_v6_router_provider_uses_v2_only_with_explicit_revision():
    source = "The red lamp flickered."
    rows = [unit(source, "The red lamp flickered", predicate="flickered")]
    body = proposal(source, rows, [("independent_assertion", 0)])
    kwargs = []

    class Fake:
        class Responses:
            def create(self, **params):
                kwargs.append(params)
                return SimpleNamespace(status="completed", output_text=json.dumps(body), usage=None)

        responses = Responses()

    result = OpenAIFactCandidateRouter(Fake(), prompt_revision="v6").propose(source)
    assert result.contract_version == 2
    assert len(result.semantic_relations) == 1
    assert kwargs[0]["text"]["format"]["schema"]["properties"]["version"]["enum"] == [2]
    assert kwargs[0]["store"] is False
    assert "do not" in kwargs[0]["input"][0]["content"].lower()


def test_nonadjacent_unsupported_semantic_link_fails_closed():
    source = "Alex played chess. Beth cooked soup. Alex felt tired."
    parts = [
        unit(source, "Alex played chess", predicate="played"),
        unit(source, "Beth cooked soup", predicate="cooked"),
        unit(source, "Alex felt tired", predicate="felt"),
    ]
    data = proposal(
        source,
        parts,
        [
            ("independent_assertion", 0),
            ("independent_assertion", 0),
            ("condition_of", 1),  # crosses an independent middle sentence
        ],
    )
    with pytest.raises(RouterError, match="Nonadjacent semantic dependency"):
        compile_hybrid_candidate_bundle(validate_semantic_fact_candidate_proposal(source, data))


def test_mixed_task_and_core_dependent_source_cannot_be_silently_rewritten():
    source = "The boiler leaks and I need to fix it."
    rows = [
        unit(source, "The boiler leaks", predicate="leaks", kind="property"),
        unit(source, "I need to fix it", predicate="fix", kind="task"),
    ]
    data = proposal(source, rows, [("independent_assertion", 0), ("purpose_of", 1)])
    with pytest.raises(RouterError, match="Mixed Task/Core"):
        compile_hybrid_candidate_bundle(
            validate_semantic_fact_candidate_proposal(source, data), enable_tasks=True
        )


def test_same_clause_independent_tasks_do_not_gain_grouped_mutation_authority():
    source = "Send invoice and book train tickets."
    rows = [
        unit(source, "Send invoice", predicate="Send", kind="task"),
        unit(source, "book train tickets", predicate="book", kind="task"),
    ]
    data = proposal(source, rows, [("independent_assertion", 0), ("independent_assertion", 0)])
    with pytest.raises(RouterError, match="Grouped Task lifecycle"):
        compile_hybrid_candidate_bundle(
            validate_semantic_fact_candidate_proposal(source, data), enable_tasks=True
        )


@pytest.mark.parametrize("count", [1, 3, 5, 8])
def test_v6_scales_across_unseen_independent_sentence_counts(count):
    source = " ".join(f"Action{index} completed successfully." for index in range(count))
    rows = [
        unit(
            source,
            f"Action{index} completed successfully",
            predicate="completed",
        )
        for index in range(count)
    ]
    # Each predicate has the same lexical text but a different source
    # occurrence; all role references must resolve without guessing.
    for index, row in enumerate(rows):
        row["scoped_source"][0]["anchor"]["occurrence"] = index
    data = proposal(source, rows, [("independent_assertion", 0)] * count)
    result = validate_semantic_fact_candidate_proposal(source, data)
    compiled = compile_hybrid_candidate_bundle(result)
    assert len(compiled.units) == count
    assert all(len(unit.original_candidate_ids) == 1 for unit in compiled.units)
    assert "".join(unit.route.source_text for unit in compiled.units) == source


def test_v6_compiler_rejects_forged_local_relation_even_after_validation():
    from dataclasses import replace

    from odyssey_apps.fact_candidates import SourceAnchor

    source = "The lamp is red and the screen is blue."
    rows = [
        unit(source, "The lamp is red", predicate="is"),
        unit(source, "the screen is blue", predicate="is"),
    ]
    # Repeated "is" must be explicitly indexed in the second clause.
    rows[1]["scoped_source"][0]["anchor"]["occurrence"] = 1
    data = proposal(source, rows, [("independent_assertion", 0), ("independent_assertion", 0)])
    validated = validate_semantic_fact_candidate_proposal(source, data)
    second = replace(
        validated.semantic_relations[1],
        evidence=SourceAnchor("The lamp", 0, 0, 8),
    )
    forged = replace(
        validated,
        semantic_relations=(validated.semantic_relations[0], second),
    )
    with pytest.raises(RouterError, match="witness"):
        compile_hybrid_candidate_bundle(forged)
