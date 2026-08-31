"""Benchmark whole-note, fact-level, and deterministic fused retrieval units."""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.atomic_facts import parse_atomic_facts, render_atomic_facts
from odyssey_core.context import build_context_retrieval_text
from odyssey_core.notes import Note, validate_note
from odyssey_core.semantic import FastEmbedTextEmbedder, TextEmbedder, _normalized_vector

TOPS = (5, 20, 50, 100)
RRF_K = 60


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


def load_cases(path: Path) -> dict[str, Any]:
    """Load the frozen benchmark corpus and evaluation oracle JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_corpus(data: dict[str, Any], schema: dict[str, Any]) -> tuple[CorpusNote, ...]:
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
                "created_at": "2026-08-31T00:00:00Z",
                "updated_at": "2026-08-31T00:00:00Z",
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
    return tuple(corpus)


def query_cases(data: dict[str, Any]) -> tuple[QueryCase, ...]:
    """Return immutable query cases with explicit entity and fact oracles."""
    return tuple(
        QueryCase(
            item["id"],
            item["query"],
            tuple(item["expected_entities"]),
            tuple(item.get("expected_facts", ())),
            item["category"],
            item["note_shape"],
        )
        for item in data["queries"]
    )


def _rank(query_vector: Any, vectors: list[tuple[float, ...]]) -> list[int]:
    """Return deterministic descending cosine ranks for normalized vectors."""
    scores = [sum(a * b for a, b in zip(query_vector, vector, strict=True)) for vector in vectors]
    return sorted(range(len(vectors)), key=lambda index: (-scores[index], index))


def _metric_table(
    ranking: list[list[tuple[str, str]]], cases: tuple[QueryCase, ...]
) -> dict[str, Any]:
    """Calculate unit, unique-entity, and exact-fact recall for one case slice."""
    output: dict[str, Any] = {"unit": {}, "entity": {}, "fact": {}}
    for top in TOPS:
        unit_hits = entity_hits = fact_hits = 0
        for case, ranked in zip(cases, ranking, strict=True):
            units = ranked[:top]
            entities = {entity for entity, _ in units}
            facts = {fact for _, fact in units}
            unit_hits += bool(
                set(case.expected_entities) & entities
            )  # one unit per entity is enough
            entity_hits += set(case.expected_entities).issubset(entities)
            fact_hits += not case.expected_facts or set(case.expected_facts).issubset(facts)
        count = len(cases)
        output["unit"][str(top)] = unit_hits / count
        output["entity"][str(top)] = entity_hits / count
        fact_cases = sum(bool(case.expected_facts) for case in cases)
        output["fact"][str(top)] = fact_hits / fact_cases if fact_cases else None
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
    payloads = [text for _, _, text in units]
    return {
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
        "rankings": [
            [{"entity": entity, "fact": fact} for entity, fact in ranking] for ranking in rankings
        ],
    }


def run(data: dict[str, Any], schema: dict[str, Any], embedder: TextEmbedder) -> dict[str, Any]:
    """Run all three arms with one corpus, query set, model, and runtime."""
    corpus = build_corpus(data, schema)
    cases = query_cases(data)
    return {
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


def main() -> None:
    """Run the real local MiniLM benchmark and print machine-readable results."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    args = parser.parse_args()
    data = load_cases(args.cases)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    started = time.perf_counter()
    embedder = FastEmbedTextEmbedder()
    result = run(data, schema, embedder)
    result["runtime"]["model_load_seconds"] = round(time.perf_counter() - started, 6)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
