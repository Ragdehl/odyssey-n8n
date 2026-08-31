"""Benchmark whole-note, fact-level, and deterministic fused retrieval units."""

from __future__ import annotations

import json
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.atomic_facts import parse_atomic_facts, render_atomic_facts
from odyssey_core.context import build_context_retrieval_text
from odyssey_core.notes import Note, validate_note
from odyssey_core.semantic import FastEmbedTextEmbedder, TextEmbedder, _normalized_vector

TOPS = (5, 20, 50, 100, 200, 300, 500)
RRF_K = 60
FIXTURE_TIMESTAMP = "2026-08-31T00:00:00Z"
TIER_TARGETS = {
    "medium": "The central fact explains a coherent long-form idea about preserving personal knowledge and making careful decisions from context while keeping evidence separate from authority and leaving room for later human review. It also emphasizes that a useful record should preserve chronology, distinguish observation from interpretation, and make uncertainty visible so that future readers can understand both what was known and why a conclusion was reached.",
    "long": "The central fact explains a coherent long-form idea about preserving personal knowledge and making careful decisions from context. It connects capture, interpretation, retrieval, and later review as related parts of one durable practice. The idea is not a list of independent events; it is a single explanation of why trustworthy systems should keep source material authoritative, expose uncertainty, and use derived evidence to support rather than silently replace human judgment. This paragraph remains one meaningful conceptual fact even though it contains several sentences and qualifications.",
    "very-long": "The central fact explains a coherent long-form idea about preserving personal knowledge and making careful decisions from context. It connects capture, interpretation, retrieval, and later review as related parts of one durable practice. The idea is not a list of independent events; it is a single explanation of why trustworthy systems should keep source material authoritative, expose uncertainty, and use derived evidence to support rather than silently replace human judgment. This paragraph remains one meaningful conceptual fact even though it contains several sentences and qualifications. It also describes how people revisit assumptions, compare evidence across languages and situations, retain historical context without confusing it with current truth, and leave ambiguous references unresolved until identity can be established safely. The point is conceptual coherence, not mechanical sentence splitting, and the whole passage should remain attributable to one concept note. It includes practical reflection about patience, revision, evidence, communication, and the responsibility to avoid turning a plausible interpretation into an irreversible claim before the person concerned has had an opportunity to review it.",
}


@dataclass(frozen=True)
class CorpusNote:
    """Represent one canonical benchmark note and its parsed fact units."""

    id: str
    path: str
    note: Note
    whole_text: str
    facts: tuple[str, ...]


@dataclass(frozen=True)
class QueryCase:
    """Define an evaluation query with entity and optional exact-fact oracles."""

    id: str
    query: str
    expected_entities: tuple[str, ...]
    expected_facts: tuple[str, ...]
    category: str
    note_shape: str
    fact_shape: str = "short"


def load_cases(path: Path) -> dict[str, Any]:
    """Load the frozen benchmark corpus and evaluation oracle JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_corpus(
    data: dict[str, Any], schema: dict[str, Any], *, scale_size: int = 0
) -> tuple[CorpusNote, ...]:
    """Build and validate isolated canonical notes from the frozen corpus definition."""
    corpus: list[CorpusNote] = []
    for item in data["notes"]:
        content = render_atomic_facts(
            tuple(item["facts"]),
            f"fixture-{item['id']}",
            tuple(range(len(item["facts"]))),
            "2026-08-31",
        )
        note = Note(
            metadata={
                "id": item["id"],
                "name": item["name"],
                "type": item["type"],
                "created_at": FIXTURE_TIMESTAMP,
                "updated_at": FIXTURE_TIMESTAMP,
                "created_by": {"human": None, "app": "phase17e-benchmark"},
                "updated_by": {"human": None, "app": "phase17e-benchmark"},
                "revision": 1,
                "schema_version": 3,
                **item.get("metadata", {}),
            },
            content=content,
        )
        validate_note(note, schema)
        facts = tuple(fact.text for fact in parse_atomic_facts(content))
        corpus.append(
            CorpusNote(
                item["id"],
                item["path"],
                note,
                build_context_retrieval_text(note, item["path"]),
                facts,
            )
        )
    if scale_size:
        if scale_size < len(corpus):
            raise ValueError("scale_size cannot be smaller than diagnostic corpus")
        tier_specs = (("medium", 20), ("long", 50), ("very-long", 100))
        for tier, count in tier_specs:
            facts = tuple(
                [
                    f"Maintains a meaningful recurring activity {index} related to community life."
                    for index in range(count)
                ]
            )
            target = TIER_TARGETS[tier]
            facts = facts[: count // 2] + (target,) + facts[count // 2 :]
            note_id = f"tier-{tier}"
            path = f"concepts/Tier {tier}.md"
            content = render_atomic_facts(
                facts, f"fixture-{note_id}", tuple(range(len(facts))), "2026-08-31"
            )
            note = Note(
                metadata={
                    "id": note_id,
                    "name": f"Tier {tier}",
                    "type": "concept",
                    "created_at": FIXTURE_TIMESTAMP,
                    "updated_at": FIXTURE_TIMESTAMP,
                    "created_by": {"human": None, "app": "phase17e-benchmark"},
                    "updated_by": {"human": None, "app": "phase17e-benchmark"},
                    "revision": 1,
                    "schema_version": 3,
                },
                content=content,
            )
            validate_note(note, schema)
            corpus.append(
                CorpusNote(note_id, path, note, build_context_retrieval_text(note, path), facts)
            )
        for number in range(len(corpus), scale_size):
            name = f"Scale Person {number:04d}"
            facts = tuple(
                (
                    f"Works at Company {number % 17} in City {number % 23}.",
                    f"Studies subject {number % 11} during the week.",
                    f"Enjoys activity {number % 19} with close friends.",
                    f"Keeps a collection of object {number % 13}.",
                    f"Plans a project about topic {number % 29}.",
                )
            )
            item = {
                "id": f"scale-{number:04d}",
                "path": f"people/Scale Person {number:04d}.md",
                "name": name,
                "type": "person",
                "facts": facts,
            }
            content = render_atomic_facts(
                facts, f"fixture-scale-{number}", tuple(range(5)), "2026-08-31"
            )
            note = Note(
                metadata={
                    "id": item["id"],
                    "name": name,
                    "type": "person",
                    "created_at": FIXTURE_TIMESTAMP,
                    "updated_at": FIXTURE_TIMESTAMP,
                    "created_by": {"human": None, "app": "phase17e-benchmark"},
                    "updated_by": {"human": None, "app": "phase17e-benchmark"},
                    "revision": 1,
                    "schema_version": 3,
                },
                content=content,
            )
            validate_note(note, schema)
            corpus.append(
                CorpusNote(
                    item["id"],
                    item["path"],
                    note,
                    build_context_retrieval_text(note, item["path"]),
                    facts,
                )
            )
    return tuple(corpus)


def query_cases(data: dict[str, Any], *, scale_size: int = 0) -> tuple[QueryCase, ...]:
    """Return immutable query cases with explicit entity and fact oracles."""
    cases = [
        QueryCase(
            item["id"],
            item["query"],
            tuple(item["expected_entities"]),
            tuple(item.get("expected_facts", ())),
            item["category"],
            item["note_shape"],
            item.get("fact_shape", "short"),
        )
        for item in data["queries"]
    ]
    if scale_size:
        for tier in ("medium", "long", "very-long"):
            cases.append(
                QueryCase(
                    f"tier-{tier}",
                    "central coherent idea about careful knowledge decisions",
                    (f"tier-{tier}",),
                    (TIER_TARGETS[tier],),
                    "note-dilution",
                    tier,
                    tier,
                )
            )
    for number in (100, 250, 400, 550, 700, 850, 999):
        if number >= scale_size:
            continue
        cases.append(
            QueryCase(
                f"scale-{number}",
                f"Which person works at Company {number % 17} in City {number % 23}, studies subject {number % 11}, and enjoys activity {number % 19}?",
                (f"scale-{number:04d}",),
                (
                    f"Works at Company {number % 17} in City {number % 23}.",
                    f"Studies subject {number % 11} during the week.",
                    f"Enjoys activity {number % 19} with close friends.",
                ),
                "scale-contextual",
                "scale",
            )
        )
    return tuple(cases)


def validate_scale_oracles(corpus: tuple[CorpusNote, ...], cases: tuple[QueryCase, ...]) -> None:
    """Prove each generated scale query matches exactly one fixture entity by all attributes."""
    scale_cases = [case for case in cases if case.category == "scale-contextual"]
    for case in scale_cases:
        matches = [
            note.id
            for note in corpus
            if all(
                fragment.casefold() in " ".join(note.facts).casefold()
                for fragment in case.expected_facts
            )
        ]
        if matches != list(case.expected_entities):
            raise ValueError(f"Scale oracle {case.id} is not unique: {matches!r}")


def run_note_length_controls(
    corpus: tuple[CorpusNote, ...], embedder: TextEmbedder
) -> dict[str, Any]:
    """Measure the same coherent target across isolated note-length variants and distractors."""
    controls: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ("whole_note", "fact_level", "combined")
    }
    distractors = tuple(note for note in corpus if not note.id.startswith("tier-"))[:50]
    query = QueryCase(
        "control",
        "coherent long-form idea about preserving personal knowledge",
        (),
        (),
        "control",
        "control",
    )
    for tier in ("medium", "long", "very-long"):
        target = next(note for note in corpus if note.id == f"tier-{tier}")
        for strategy in controls:
            result = run_strategy(distractors + (target,), (query,), embedder, strategy)
            rank = next(
                index + 1
                for index, item in enumerate(result["rankings"][0])
                if item["entity"] == target.id
            )
            controls[strategy].append(
                {
                    "tier": tier,
                    "facts": len(target.facts),
                    "target_rank": rank,
                    "recall_at_5": rank <= 5,
                }
            )
    return {"query": query.query, "fixed_distractors": len(distractors), "results": controls}


def run_fact_length_controls(
    corpus: tuple[CorpusNote, ...], embedder: TextEmbedder
) -> dict[str, Any]:
    """Measure target-fact rank while only its coherent prose length changes."""
    controls: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ("whole_note", "fact_level", "combined")
    }
    distractors = tuple(note for note in corpus if not note.id.startswith("tier-"))[:50]
    query = QueryCase(
        "control-fact",
        "coherent long-form idea about preserving personal knowledge",
        (),
        (),
        "control",
        "control",
    )
    for tier in ("medium", "long", "very-long"):
        target = next(note for note in corpus if note.id == f"tier-{tier}")
        for strategy in controls:
            result = run_strategy(distractors + (target,), (query,), embedder, strategy)
            ranking = result["rankings"][0]
            rank = next(
                (
                    index + 1
                    for index, item in enumerate(ranking)
                    if item["fact"] == TIER_TARGETS[tier]
                ),
                None,
            )
            controls[strategy].append(
                {"tier": tier, "words": len(TIER_TARGETS[tier].split()), "target_fact_rank": rank}
            )
    return {"query": query.query, "fixed_distractors": len(distractors), "results": controls}


def _rank(query_vector: Any, vectors: list[tuple[float, ...]]) -> list[int]:
    """Return deterministic descending cosine ranks for normalized vectors."""
    scores = [sum(a * b for a, b in zip(query_vector, vector, strict=True)) for vector in vectors]
    return sorted(range(len(vectors)), key=lambda index: (-scores[index], index))


def _metric_table(
    ranking: list[list[tuple[str, str]]], cases: tuple[QueryCase, ...]
) -> dict[str, Any]:
    """Calculate candidate recall and clearly separated required-fact evidence metrics."""
    output: dict[str, Any] = {
        "unit": {},
        "entity": {},
        "fact_any_required": {},
        "fact_all_required": {},
        "fact_coverage": {},
    }
    for top in TOPS:
        unit_hits = entity_hits = any_fact_hits = all_fact_hits = 0
        coverage: list[float] = []
        for case, ranked in zip(cases, ranking, strict=True):
            units = ranked[:top]
            entities = []
            for entity, _ in ranked:
                if entity not in entities:
                    entities.append(entity)
                if len(entities) == top:
                    break
            facts = {fact for _, fact in units}
            unit_hits += bool(set(case.expected_entities) & set(entity for entity, _ in units))
            entity_hits += set(case.expected_entities).issubset(entities)
            if case.expected_facts:
                matched = len(set(case.expected_facts) & facts)
                any_fact_hits += matched > 0
                all_fact_hits += matched == len(set(case.expected_facts))
                coverage.append(matched / len(set(case.expected_facts)))
        count = len(cases)
        output["unit"][str(top)] = unit_hits / count
        output["entity"][str(top)] = entity_hits / count
        fact_cases = sum(bool(case.expected_facts) for case in cases)
        output["fact_any_required"][str(top)] = any_fact_hits / fact_cases if fact_cases else None
        output["fact_all_required"][str(top)] = all_fact_hits / fact_cases if fact_cases else None
        output["fact_coverage"][str(top)] = {
            "mean": statistics.mean(coverage) if coverage else None,
            "median": statistics.median(coverage) if coverage else None,
        }
    return output


def _evaluate(ranking: list[list[tuple[str, str]]], cases: tuple[QueryCase, ...]) -> dict[str, Any]:
    """Calculate overall and long/short/category recall without changing ranking inputs."""
    metrics = _metric_table(ranking, cases)
    metrics["note_shape"] = {
        shape: _metric_table(
            [rank for rank, case in zip(ranking, cases, strict=True) if case.note_shape == shape],
            tuple(case for case in cases if case.note_shape == shape),
        )
        for shape in sorted({case.note_shape for case in cases})
    }
    metrics["category"] = {
        category: _metric_table(
            [rank for rank, case in zip(ranking, cases, strict=True) if case.category == category],
            tuple(case for case in cases if case.category == category),
        )
        for category in sorted({case.category for case in cases})
    }
    return metrics


def _payload_stats(
    rankings: list[list[tuple[str, str]]], texts: list[tuple[str, str, str]]
) -> dict[str, Any]:
    """Summarize raw-unit and first-seen unique-entity payload at every cutoff."""
    text_by_unit = {(entity, fact): text for entity, fact, text in texts}
    result: dict[str, Any] = {}
    for top in TOPS:
        raw = [sum(len(text_by_unit[unit]) for unit in ranking[:top]) for ranking in rankings]
        unique_values = []
        for ranking in rankings:
            seen: set[str] = set()
            selected = []
            for entity, fact in ranking:
                if entity not in seen:
                    seen.add(entity)
                    selected.append((entity, fact))
                if len(selected) == top:
                    break
            unique_values.append(sum(len(text_by_unit[unit]) for unit in selected))
        result[str(top)] = {
            "raw_units_chars": _summary(raw),
            "raw_units_approx_tokens": _summary([value / 4 for value in raw]),
            "unique_entities_chars": _summary(unique_values),
            "unique_entities_approx_tokens": _summary([value / 4 for value in unique_values]),
        }
    return result


def _fact_width_stats(
    rankings: list[list[tuple[str, str]]],
    cases: tuple[QueryCase, ...],
    texts: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """Report raw-fact width, unique-entity width, ranks, and grouped payload estimates."""
    text_by_unit = {(entity, fact): text for entity, fact, text in texts}
    result: dict[str, Any] = {"widths": {}, "ranks": [], "misses": {}}
    for top in TOPS:
        raw_entity_counts = []
        max_slots = []
        unique_entity_scans = []
        raw_entity_hits = unique_entity_hits = any_fact_hits = exact_fact_hits = 0
        coverage: list[float] = []
        for case, ranking in zip(cases, rankings, strict=True):
            raw = ranking[:top]
            counts: dict[str, int] = {}
            for entity, _ in raw:
                counts[entity] = counts.get(entity, 0) + 1
            raw_entities = set(counts)
            raw_entity_counts.append(len(raw_entities))
            max_slots.append(max(counts.values(), default=0))
            raw_entity_hits += bool(raw_entities & set(case.expected_entities))
            unique = []
            for _scanned, (entity, _) in enumerate(ranking, start=1):
                if entity not in unique:
                    unique.append(entity)
                if len(unique) == top:
                    break
            unique_entity_scans.append(_scanned if unique else 0)
            unique_entity_hits += set(case.expected_entities).issubset(unique)
            if case.expected_facts:
                expected = set(case.expected_facts)
                matched = expected & {fact for _, fact in raw}
                exact_fact_hits += matched == expected
                any_fact_hits += bool(matched)
                coverage.append(len(matched) / len(expected))
        fact_case_count = sum(bool(case.expected_facts) for case in cases)
        result["widths"][str(top)] = {
            "raw_fact_entity_recall": raw_entity_hits / len(cases),
            "raw_fact_any_required_recall": any_fact_hits / fact_case_count
            if fact_case_count
            else None,
            "raw_fact_all_required_recall": exact_fact_hits / fact_case_count
            if fact_case_count
            else None,
            "raw_fact_coverage": {
                "mean": statistics.mean(coverage) if coverage else None,
                "median": statistics.median(coverage) if coverage else None,
            },
            "raw_unique_entity_count": _summary(raw_entity_counts),
            "raw_max_facts_per_entity": _summary(max_slots),
            "unique_entity_recall": unique_entity_hits / len(cases),
            "unique_entity_raw_units_scanned": _summary(unique_entity_scans),
            "grouped_payload": {
                str(limit): {
                    "chars": _summary(
                        [
                            _grouped_payload_summary(ranking, text_by_unit, top, limit)["chars"]
                            for ranking in rankings
                        ]
                    ),
                    "approx_tokens": _summary(
                        [
                            _grouped_payload_summary(ranking, text_by_unit, top, limit)[
                                "approx_tokens"
                            ]
                            for ranking in rankings
                        ]
                    ),
                }
                for limit in (1, 2, 3)
            },
        }
    for case, ranking in zip(cases, rankings, strict=True):
        entity_ranks = [
            index
            for index, (entity, _) in enumerate(ranking, start=1)
            if entity in case.expected_entities
        ]
        required_ranks = {
            fact: next(
                (
                    index
                    for index, (_, ranked_fact) in enumerate(ranking, start=1)
                    if ranked_fact == fact
                ),
                None,
            )
            for fact in case.expected_facts
        }
        present_ranks = [rank for rank in required_ranks.values() if rank is not None]
        result["ranks"].append(
            {
                "id": case.id,
                "first_expected_entity_fact_rank": min(entity_ranks, default=None),
                "required_fact_ranks": required_ranks,
                "first_required_fact_rank": min(present_ranks, default=None),
                "last_required_fact_rank": (
                    max(required_ranks.values())
                    if required_ranks and None not in required_ranks.values()
                    else None
                ),
            }
        )
    for top in (100, 200, 300, 500):
        result["misses"][str(top)] = [
            row["id"]
            for row in result["ranks"]
            if row["first_expected_entity_fact_rank"] is None
            or row["first_expected_entity_fact_rank"] > top
        ]
    return result


def _grouped_payload_summary(
    ranking: list[tuple[str, str]],
    text_by_unit: dict[tuple[str, str], str],
    entity_limit: int,
    facts_per_entity: int,
) -> dict[str, float]:
    """Estimate payload after retaining the first N ranked facts per selected entity."""
    selected: list[tuple[str, str]] = []
    counts: dict[str, int] = {}
    entities: list[str] = []
    for entity, fact in ranking:
        if entity not in counts:
            if len(entities) == entity_limit:
                break
            entities.append(entity)
        if counts.get(entity, 0) < facts_per_entity:
            selected.append((entity, fact))
            counts[entity] = counts.get(entity, 0) + 1
    chars = sum(len(text_by_unit[unit]) for unit in selected)
    return {"chars": round(chars, 2), "approx_tokens": round(chars / 4, 2)}


def _summary(values: list[float]) -> dict[str, float]:
    """Return mean, median, minimum, and maximum for a measured query series."""
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def run_strategy(
    corpus: tuple[CorpusNote, ...],
    cases: tuple[QueryCase, ...],
    embedder: TextEmbedder,
    strategy: str,
) -> dict[str, Any]:
    """Run one retrieval arm and return rankings plus measurable build/query costs."""
    if strategy == "whole_note":
        units = [(note.id, "", note.whole_text) for note in corpus]
    elif strategy == "fact_level":
        units = [
            (
                note.id,
                fact,
                f"Name: {note.note.metadata['name']}\nType: {note.note.metadata['type']}\nFact: {fact}",
            )
            for note in corpus
            for fact in note.facts
        ]
    elif strategy == "combined":
        units = [
            (
                note.id,
                fact,
                f"Name: {note.note.metadata['name']}\nType: {note.note.metadata['type']}\nFact: {fact}",
            )
            for note in corpus
            for fact in note.facts
        ]
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    started = time.perf_counter()
    document_vectors = [
        _normalized_vector(vector)
        for vector in embedder.embed_documents([text for _, _, text in units])
    ]
    entity_vectors = []
    if strategy == "combined":
        entity_vectors = [
            _normalized_vector(vector)
            for vector in embedder.embed_documents([note.whole_text for note in corpus])
        ]
    build_seconds = time.perf_counter() - started
    started = time.perf_counter()
    query_vectors = [
        _normalized_vector(vector)
        for vector in embedder.embed_queries([case.query for case in cases])
    ]
    rankings: list[list[tuple[str, str]]] = []
    for query_vector in query_vectors:
        primary = _rank(query_vector, document_vectors)
        if strategy != "combined":
            rankings.append([(units[index][0], units[index][1]) for index in primary])
            continue
        entity_order = _rank(query_vector, entity_vectors)
        entity_rrf = {
            corpus[index].id: 1 / (RRF_K + rank + 1) for rank, index in enumerate(entity_order)
        }
        fused = sorted(
            primary,
            key=lambda index: (
                -(entity_rrf[units[index][0]] + 1 / (RRF_K + primary.index(index) + 1)),
                index,
            ),
        )
        rankings.append([(units[index][0], units[index][1]) for index in fused])
    query_seconds = time.perf_counter() - started
    metrics = _evaluate(rankings, cases)
    if strategy == "whole_note":
        metrics["fact_any_required"] = {str(top): None for top in TOPS}
        metrics["fact_all_required"] = {str(top): None for top in TOPS}
        metrics["fact_coverage"] = {str(top): {"mean": None, "median": None} for top in TOPS}
    payloads = [text for _, _, text in units]
    result = {
        "strategy": strategy,
        "unit_count": len(units),
        "entity_count": len(corpus),
        "payload_chars": sum(len(text) for text in payloads),
        "approx_tokens": round(sum(len(text) for text in payloads) / 4),
        "vector_count": len(document_vectors) + len(entity_vectors),
        "vector_bytes": 4
        * len(document_vectors[0])
        * (len(document_vectors) + len(entity_vectors)),
        "build_seconds": round(build_seconds, 6),
        "query_seconds": round(query_seconds, 6),
        "metrics": metrics,
        "retrieved_payload": _payload_stats(rankings, units),
        "rankings": [
            [{"entity": entity, "fact": fact} for entity, fact in ranking] for ranking in rankings
        ],
    }
    if strategy in {"fact_level", "combined"}:
        result["fact_width"] = _fact_width_stats(rankings, cases, units)
    return result


def run(
    data: dict[str, Any],
    schema: dict[str, Any],
    embedder: TextEmbedder,
    *,
    scale_size: int = 0,
    skip_controls: bool = False,
) -> dict[str, Any]:
    """Run all three arms with one corpus, query set, model, and runtime."""
    corpus = build_corpus(data, schema, scale_size=scale_size)
    cases = query_cases(data, scale_size=scale_size)
    result = {
        "runtime": {
            "architecture": platform.machine(),
            "model": embedder.model_name,
            "model_version": embedder.model_version,
        },
        "cases": len(cases),
        "notes": len(corpus),
        "strategies": [
            run_strategy(corpus, cases, embedder, name)
            for name in ("whole_note", "fact_level", "combined")
        ],
    }
    if scale_size and not skip_controls:
        result["controlled_note_length"] = run_note_length_controls(corpus, embedder)
        result["controlled_fact_length"] = run_fact_length_controls(corpus, embedder)
    return result


def main() -> None:
    """Run the real local MiniLM benchmark and print machine-readable results."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--scale-size", type=int, default=1000)
    parser.add_argument("--skip-controls", action="store_true")
    args = parser.parse_args()
    data = load_cases(args.cases)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    started = time.perf_counter()
    embedder = FastEmbedTextEmbedder(cache_dir=args.cache_dir, local_files_only=True)
    result = run(
        data, schema, embedder, scale_size=args.scale_size, skip_controls=args.skip_controls
    )
    result["runtime"]["model_load_seconds"] = round(time.perf_counter() - started, 6)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
