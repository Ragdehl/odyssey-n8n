"""Frozen within-note MiniLM retrieval evidence for the Phase 16.3 Luna writer benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from odyssey_core.semantic import TextEmbedder, _normalized_vector


@dataclass(frozen=True)
class RetrievedFragment:
    """Keep an exact authoritative unit and separate ranking-only projection."""

    ordinal: int
    exact_text: str
    projection: str
    similarity: float


def retrieve(case: dict[str, Any], embedder: TextEmbedder, *, limit: int) -> dict[str, Any]:
    """Rank exact note-body units for independently embedded planned facts.

    Only runtime fields (`current_body`, `facts`, identity, and note type) are read. Evaluation
    labels such as expected spans or outcomes are deliberately not consulted.
    """
    if limit not in {3, 5}:
        raise ValueError("retrieval limit must be TOP_3 or TOP_5")
    exact_units = exact_body_units(case["current_body"])
    identity = case["identity"]
    projections = [
        f"Entity: {identity}\nType: {case['note_type']}\nFragment: {unit}" for unit in exact_units
    ]
    started = perf_counter()
    unit_vectors = list(embedder.embed_documents(projections))
    fact_vectors = list(embedder.embed_queries(case["facts"]))
    elapsed_ms = (perf_counter() - started) * 1000
    selected: dict[int, float] = {}
    ranks_by_fact: list[list[dict[str, float | int]]] = []
    for vector in fact_vectors:
        query = _normalized_vector(vector)
        scored = sorted(
            (
                (index, sum(a * b for a, b in zip(query, _normalized_vector(unit), strict=True)))
                for index, unit in enumerate(unit_vectors)
            ),
            key=lambda pair: (-pair[1], pair[0]),
        )
        ranks_by_fact.append([{"ordinal": index, "similarity": score} for index, score in scored])
        for index, score in scored[:limit]:
            selected[index] = max(selected.get(index, float("-inf")), score)
    fragments = [
        RetrievedFragment(index, exact_units[index], projections[index], selected[index])
        for index in sorted(selected)
    ]
    return {
        "fragment_count": len(exact_units),
        "retrieval_latency_ms": round(elapsed_ms, 3),
        "fact_rankings": ranks_by_fact,
        "fragments": [fragment.__dict__ for fragment in fragments],
    }


def render_retrieved_context(case: dict[str, Any], retrieval: dict[str, Any]) -> str:
    """Render source-ordered exact fragments for Luna without ranking projections or scores."""
    return "\n\n".join(fragment["exact_text"] for fragment in retrieval["fragments"])


def target_rank(case: dict[str, Any], retrieval: dict[str, Any]) -> int | None:
    """Return evaluation-only rank of an expected exact fragment, or None for independent facts."""
    target = case.get("target_fragment")
    if target is None:
        return None
    ranking = retrieval["fact_rankings"][0]
    exact_units = exact_body_units(case["current_body"])
    index = exact_units.index(target)
    return next(position + 1 for position, item in enumerate(ranking) if item["ordinal"] == index)


def exact_body_units(markdown: str) -> list[str]:
    """Split simple Markdown into source-order units while retaining exact anchor substrings."""
    if not isinstance(markdown, str):
        raise TypeError("Markdown body must be text")
    units: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        """Store one prose block exactly as it occurs between blank lines or headings."""
        if paragraph:
            units.append("\n".join(paragraph))
            paragraph.clear()

    for raw in markdown.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
        elif stripped.startswith("#") and stripped.lstrip("#").startswith(" "):
            flush()
        elif len(stripped) >= 2 and stripped[0] in "-*+" and stripped[1].isspace():
            flush()
            units.append(raw)
        else:
            paragraph.append(raw)
    flush()
    return units


def classify_pipeline(
    case: dict[str, Any], *, rank: int | None, semantic_status: str, taxonomy: str
) -> str:
    """Classify a reviewed result as retrieval, writer, contract, or passing pipeline evidence."""
    if case.get("target_fragment") is not None and rank is not None and rank > 5:
        return "RETRIEVAL_FAIL"
    if semantic_status != "MATERIAL_FAIL":
        return "PASS"
    if taxonomy.startswith("A."):
        return "CONTRACT_FAIL"
    return "WRITER_FAIL"
