"""Run the bounded Phase 11B.1c large-vault candidate-recall experiment."""

from __future__ import annotations

import argparse
import json
import platform
import re
import resource
import statistics
import sys
import tempfile
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odyssey_core.notes import (  # noqa: E402
    Note,
    parse_note,  # noqa: E402
    serialize_note,
)
from odyssey_core.semantic import (  # noqa: E402
    FastEmbedTextEmbedder,
    SemanticEntityIndex,
    build_semantic_retrieval_text,
)
from odyssey_core.storage import VaultRepository  # noqa: E402

NOTE_COUNT = 1000
RRF_K = 60
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
TIMESTAMP = "2026-08-18T00:00:00Z"


@dataclass(frozen=True, slots=True)
class NoteSpec:
    """Describe one deterministic synthetic note before Markdown serialization."""

    id: str
    type: str
    name: str
    body: str
    aliases: tuple[str, ...] = ()
    relationship: str | None = None


TARGETS = (
    NoteSpec(
        "person-es-esposa",
        "person",
        "Beatriz Alonso",
        "Comparte hogar con el usuario y organiza los cumpleaños familiares.",
        ("Beti Alonso",),
        "esposa",
    ),
    NoteSpec(
        "person-es-mujer",
        "person",
        "Elena Ruiz",
        "Mujer casada con el usuario; trabaja en restauración de libros.",
        (),
        "mujer",
    ),
    NoteSpec(
        "person-fr-epouse",
        "person",
        "Chloé Martin",
        "Épouse de l'utilisateur; prépare les voyages en train.",
        ("Clo Martin",),
        "épouse",
    ),
    NoteSpec(
        "person-fr-femme",
        "person",
        "Nadia Bernard",
        "Femme mariée à l'utilisateur; aime le thé vert.",
        (),
        "femme",
    ),
    NoteSpec(
        "person-en-spouse",
        "person",
        "Alice Morgan",
        "Spouse of the user; keeps the family travel calendar.",
        (),
        "spouse",
    ),
    NoteSpec(
        "person-en-wife",
        "person",
        "Rachel Stone",
        "Wife of the user; restores old photographs.",
        (),
        "wife",
    ),
    NoteSpec(
        "person-atlas-colleague",
        "person",
        "Lucía Vidal",
        "Cartógrafa que colabora en el equipo Atlas y revisa mapas.",
        (),
        "colleague",
    ),
    NoteSpec(
        "person-luc-mother",
        "person",
        "Marie Dubois",
        "Parent de Luc; elle organise les réunions familiales.",
        (),
        "mère",
    ),
    NoteSpec(
        "person-sam-friend",
        "person",
        "Jordan Lee",
        "Climbs every Saturday with Sam and shares route notes.",
        (),
        "friend",
    ),
    NoteSpec(
        "store-carrefour-balma",
        "store",
        "Carrefour Balma",
        "Supermarché près de la mairie de Balma, à l'est de Toulouse.",
        ("Carrefour de Balma",),
    ),
    NoteSpec(
        "store-carrefour-capitole",
        "store",
        "Carrefour Market Capitole",
        "Petit supermarché près de la place du Capitole à Toulouse.",
    ),
    NoteSpec(
        "store-carrefour-labege",
        "store",
        "Carrefour Labège",
        "Hypermarché situé près du cinéma de Labège.",
    ),
    NoteSpec(
        "store-lidl-balma",
        "store",
        "Lidl Balma",
        "Discount supermarket on route de Castres in Balma.",
    ),
    NoteSpec(
        "store-bio-balma",
        "store",
        "Marché Vert Balma",
        "Tienda ecológica y comercio de productos locales en Balma.",
    ),
    NoteSpec(
        "store-hardware-toulouse",
        "store",
        "Quincaillerie Garonne",
        "Hardware shop in Toulouse selling screws, tools, and timber.",
    ),
    NoteSpec(
        "project-odyssey",
        "project",
        "Odyssey",
        "Personal knowledge system producing atomic Markdown notes.",
        ("Proyecto Odisea",),
    ),
    NoteSpec(
        "project-atlas",
        "project",
        "Atlas",
        "Mapping project for bicycle routes and geographic map layers.",
    ),
    NoteSpec(
        "project-lumen",
        "project",
        "Lumen",
        "Projet local de classement par intelligence artificielle, sans service distant.",
    ),
    NoteSpec(
        "project-kitchen",
        "project",
        "Kitchen renovation",
        "Plan and coordinate the kitchen renovation project.",
    ),
    NoteSpec(
        "project-solar-garden",
        "project",
        "Huerto Solar",
        "Proyecto de huerto energético realizado con un socio profesional.",
    ),
    NoteSpec(
        "concept-atomic-notes",
        "concept",
        "Atomic notes",
        "One idea or independently identifiable entity per note.",
        ("Notas atómicas",),
    ),
    NoteSpec(
        "concept-entity-resolution",
        "concept",
        "Entity resolution",
        "Match a reference or mention to the correct existing entity while preserving uncertainty.",
        ("résolution d'identité",),
    ),
    NoteSpec(
        "concept-memory-bank",
        "concept",
        "Memory bank",
        "Banco de memoria informática; no es un banco financiero.",
    ),
    NoteSpec(
        "concept-pair-programming",
        "concept",
        "Pair programming",
        "Programmation en binôme avec un partenaire de code, pas un conjoint.",
    ),
    NoteSpec(
        "product-arduino-uno",
        "product",
        "Arduino Uno",
        "Microcontroller development board used for electronics prototypes.",
    ),
    NoteSpec(
        "product-lactel-milk",
        "product",
        "Lactel semi-skimmed milk",
        "Leche Lactel semidesnatada de un litro.",
        ("Leche Lactel",),
    ),
    NoteSpec(
        "task-renew-passport",
        "task",
        "Renew passport",
        "Renouveler le passeport avant sa date d'expiration.",
    ),
    NoteSpec(
        "document-apartment-lease",
        "document",
        "Apartment lease",
        "Signed rental agreement for the apartment.",
    ),
    NoteSpec(
        "concept-place-capitole",
        "concept",
        "Place du Capitole",
        "Lugar: plaza central de Toulouse donde está el ayuntamiento.",
    ),
    NoteSpec(
        "recipe-tomato-soup",
        "recipe",
        "Roasted tomato soup",
        "Soupe aux tomates rôties, ail et basilic.",
    ),
)

FAMILIES = {
    "person": (
        "Alex Martin",
        "Camille Ruiz",
        "Jordan García",
        "Marie Stone",
        "Sam Bernard",
        "Luc Morgan",
        "Beatriz Vidal",
        "Alice Dubois",
    ),
    "store": (
        "Carrefour Toulouse",
        "Carrefour Market",
        "Lidl Toulouse",
        "Marché Balma",
        "Boutique Atlas",
        "Bank Street Store",
        "Computer Store",
        "Supermarché Central",
    ),
    "project": (
        "Atlas Notes",
        "Odyssey Map",
        "Lumen AI",
        "Project Bank",
        "Toulouse Mapping",
        "Atomic Notebook",
        "Partner Portal",
        "Kitchen Atlas",
    ),
    "concept": (
        "Knowledge graph",
        "Semantic search",
        "Project planning",
        "River bank",
        "Woman and society",
        "Retail store",
        "Partner network",
        "Map projection",
    ),
    "task": (
        "Review map",
        "Call partner",
        "Visit store",
        "Update Odyssey",
        "Plan project",
        "Check bank",
        "Buy milk",
        "Write note",
    ),
    "document": (
        "Atlas brief",
        "Store receipt",
        "Project plan",
        "Marriage certificate",
        "Bank statement",
        "Odyssey guide",
        "Map legend",
        "Family record",
    ),
    "product": (
        "Atlas tablet",
        "Odyssey notebook",
        "Lactel bottle",
        "Carrefour bag",
        "Partner cable",
        "Bank charger",
        "Map case",
        "Tomato tin",
    ),
    "purchase": (
        "Carrefour purchase",
        "Lidl purchase",
        "Hardware order",
        "Market receipt",
        "Online store order",
        "Milk purchase",
        "Project supplies",
        "Family groceries",
    ),
    "recipe": (
        "Tomato salad",
        "Family soup",
        "Partner pasta",
        "Market stew",
        "Green soup",
        "Milk bread",
        "Atlas cake",
        "Balma tart",
    ),
    "journal_entry": (
        "Family day",
        "Atlas meeting",
        "Store visit",
        "Project reflection",
        "Balma walk",
        "Partner discussion",
        "Bank errand",
        "Odyssey session",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON benchmark fixture from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


def generated_specs() -> tuple[NoteSpec, ...]:
    """Return exactly 1,000 deterministic target and adversarial distractor specifications."""
    specs = list(TARGETS)
    counters: defaultdict[str, int] = defaultdict(int)
    types = tuple(FAMILIES)
    while len(specs) < NOTE_COUNT:
        note_type = types[(len(specs) - len(TARGETS)) % len(types)]
        index = counters[note_type]
        counters[note_type] += 1
        base = FAMILIES[note_type][index % len(FAMILIES[note_type])]
        name = f"{base} {index + 1:03d}"
        body = (
            f"Synthetic {note_type} record {index + 1}. Mentions Odyssey, Atlas, Carrefour, "
            "Balma, Toulouse, family, marriage, partner, project, store, bank, maps, and notes "
            "as contextual distractors without representing the benchmark target."
        )
        relationship = None
        if note_type == "person":
            roles = (
                "spouse of another synthetic user",
                "mother of Alex",
                "sister of Sam",
                "colleague on Atlas",
                "friend from Balma",
            )
            relationship = roles[index % len(roles)]
            body += f" Relationship context: {relationship}; family and children are mentioned."
        specs.append(
            NoteSpec(
                f"stress-{note_type}-{index:04d}", note_type, name, body, relationship=relationship
            )
        )
    return tuple(specs)


def metadata(spec: NoteSpec, ordinal: int) -> dict[str, Any]:
    """Build schema-valid metadata for one synthetic specification."""
    values: dict[str, Any] = {
        "id": spec.id,
        "name": spec.name,
        "type": spec.type,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        # Phase 17E compatibility: preserve the frozen body/query/oracle fixture while adapting
        # only the provenance shape required by the current schema-v3 validator.
        "created_by": {"human": None, "app": "phase11b1c-stress-generator"},
        "updated_by": {"human": None, "app": "phase11b1c-stress-generator"},
        "revision": 1,
        "schema_version": 3,
    }
    if spec.aliases:
        values["aliases"] = list(spec.aliases)
    # Phase 11B.1c predated schema-v3's typed metadata allow-list.  Keep the
    # relationship wording in the frozen note body, but omit the retired
    # metadata field so the historical fixture can pass the current validator.
    if spec.type == "journal_entry":
        values["entry_date"] = f"2026-07-{ordinal % 28 + 1:02d}"
    return values


def create_vault(root: Path) -> tuple[NoteSpec, ...]:
    """Materialize the deterministic corpus under a disposable vault root."""
    specs = generated_specs()
    for ordinal, spec in enumerate(specs):
        directory = root / f"{spec.type}s"
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{ordinal:04d}-{spec.name.replace('/', '-')}.md"
        (directory / filename).write_text(
            serialize_note(Note(metadata(spec, ordinal), spec.body)), encoding="utf-8"
        )
    return specs


def tokens(text: str) -> tuple[str, ...]:
    """Tokenize text deterministically using Unicode letters/digits and case folding."""
    return tuple(TOKEN_PATTERN.findall(unicodedata.normalize("NFC", text).casefold()))


def wordnet_expansion(text: str, language: str) -> frozenset[str]:
    """Expand tokens with same-language WordNet/OMW lemmas across all available senses."""
    from nltk.corpus import wordnet as wn

    language_code = {"en": "eng", "es": "spa", "fr": "fra"}[language]
    expanded = set(tokens(text))
    for token in tuple(expanded):
        for synset in wn.synsets(token, lang=language_code):
            for lemma in synset.lemma_names(language_code):
                expanded.update(tokens(lemma.replace("_", " ")))
    return frozenset(expanded)


def lexical_rank(
    specs: tuple[NoteSpec, ...],
    query: dict[str, Any],
    *,
    synonyms: bool,
) -> list[str]:
    """Rank identity text or full projections using literal or synonym-expanded overlap."""
    query_tokens = (
        wordnet_expansion(query["reference"], query["language"])
        if synonyms
        else frozenset(tokens(query["reference"]))
    )
    ranked = []
    for spec in specs:
        if spec.type != query["type"]:
            continue
        identity_text = " ".join((spec.name, *spec.aliases))
        evidence_tokens = frozenset(
            tokens(f"{identity_text} {spec.body} {spec.relationship or ''}")
            if synonyms
            else tokens(identity_text)
        )
        overlap = len(query_tokens & evidence_tokens)
        if overlap:
            ranked.append((overlap / len(evidence_tokens), overlap, spec.name.casefold(), spec.id))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
    return [row[3] for row in ranked]


def rrf(*rankings: list[str]) -> list[str]:
    """Fuse candidate rankings with deterministic reciprocal-rank fusion using ``k=60``."""
    scores: defaultdict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, note_id in enumerate(ranking, start=1):
            scores[note_id] += 1 / (RRF_K + rank)
            best_rank[note_id] = min(rank, best_rank.get(note_id, rank))
    return sorted(scores, key=lambda note_id: (-scores[note_id], best_rank[note_id], note_id))


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate recall at the requested cutoffs across frozen benchmark dimensions."""

    def summarize(items: list[dict[str, Any]]) -> dict[str, float]:
        return {
            f"recall_at_{limit}": sum(row["expected_id"] in row["ranking"][:limit] for row in items)
            / len(items)
            for limit in (1, 3, 5, 10, 20, 50, 100)
        }

    groups: dict[str, Any] = {"overall": summarize(rows)}
    for dimension in ("language", "category", "mismatch"):
        values = sorted({str(row[dimension]) for row in rows})
        groups[dimension] = {
            value: summarize([row for row in rows if str(row[dimension]) == value])
            for value in values
        }
    return groups


def exact_unique_ids(specs: tuple[NoteSpec, ...], query: dict[str, Any]) -> set[str]:
    """Return IDs that the current exact primary-name/alias lookup would match uniquely.

    Args:
        specs: Frozen synthetic note specifications.
        query: Frozen query with reference and canonical type.

    Returns:
        Matching note IDs after the same NFC/case/whitespace normalization used by exact lookup.
    """
    normalized = " ".join(unicodedata.normalize("NFC", query["reference"]).casefold().split())
    matches = []
    for spec in specs:
        values = (spec.name, *spec.aliases)
        if spec.type == query["type"] and any(
            " ".join(unicodedata.normalize("NFC", value).casefold().split()) == normalized
            for value in values
        ):
            matches.append(spec.id)
    return set(matches)


def retrieve_projection_texts(
    repository: VaultRepository, schema: dict[str, Any]
) -> dict[str, str]:
    """Rebuild the exact useful candidate projection used by the semantic index.

    Args:
        repository: Disposable benchmark vault containing validated Markdown notes.
        schema: Canonical note schema used to validate source notes.

    Returns:
        Mapping from stable note ID to the current semantic retrieval projection.
    """
    projections = {}
    for path in repository.list_markdown_paths():
        note = parse_note(repository.read_text(path))
        projections[str(note.metadata["id"])] = build_semantic_retrieval_text(note, path)
    return projections


def rerank_top_candidates(
    rows: list[dict[str, Any]], projection_texts: dict[str, str], model_dir: Path, limit: int
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Rerank MiniLM candidates with the retained mMARCO Cross-Encoder.

    The model only sorts retrieved evidence. It never emits an identity decision or confidence.

    Args:
        rows: Dense rows containing complete candidate rankings.
        projection_texts: Current semantic evidence projection keyed by note ID.
        model_dir: Directory containing the exact Phase 11A tokenizer and ``model.onnx``.
        limit: MiniLM candidate breadth to rerank.

    Returns:
        Reranked rows and timing data for model load and all reranking calls.

    Raises:
        OSError: If the retained model files cannot be loaded.
        RuntimeError: If the local ONNX runtime cannot execute the model.
    """
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    load_started = time.perf_counter()
    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    session = ort.InferenceSession(
        str(model_dir / "model.onnx"), providers=["CPUExecutionProvider"]
    )
    load_seconds = time.perf_counter() - load_started
    rerank_latencies = []
    reranked_rows = []
    for row in rows:
        candidates = row["ranking"][:limit]
        query_text = f"Reference: {row['reference']}\nContext: {row['context']}"
        pairs = [(query_text, projection_texts[note_id]) for note_id in candidates]
        encodings = tokenizer.encode_batch(pairs)
        width = min(512, max(len(encoding.ids) for encoding in encodings))
        input_ids = np.zeros((len(encodings), width), dtype=np.int64)
        attention_mask = np.zeros_like(input_ids)
        for index, encoding in enumerate(encodings):
            ids = encoding.ids[:width]
            input_ids[index, : len(ids)] = ids
            attention_mask[index, : len(ids)] = 1
        started = time.perf_counter()
        logits = session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})[0]
        rerank_latencies.append(time.perf_counter() - started)
        reranked = sorted(
            zip(candidates, logits.reshape(-1), strict=True),
            key=lambda item: (-float(item[1]), item[0]),
        )
        reranked_rows.append(
            {
                **row,
                "ranking": [note_id for note_id, _ in reranked],
                "rerank_scores": {note_id: float(score) for note_id, score in reranked},
            }
        )
    return reranked_rows, {
        "model_load_seconds": load_seconds,
        "rerank_ms_median": statistics.median(rerank_latencies) * 1000,
        "rerank_ms_mean": statistics.mean(rerank_latencies) * 1000,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }


def run(
    queries_path: Path,
    schema_path: Path,
    cache_dir: Path | None,
    cross_encoder_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the frozen vault and measure unchanged dense retrieval at broad cutoffs."""
    queries = load_json(queries_path)["queries"]
    schema = load_json(schema_path)
    with tempfile.TemporaryDirectory(prefix="odyssey-phase11b1c-") as temporary_name:
        temporary = Path(temporary_name)
        vault = temporary / "vault"
        started = time.perf_counter()
        specs = create_vault(vault)
        embedder = FastEmbedTextEmbedder(cache_dir=cache_dir)
        index = SemanticEntityIndex(temporary / "runtime" / "semantic.sqlite3")
        count = index.rebuild(VaultRepository(vault), schema, embedder)
        indexing_seconds = time.perf_counter() - started

        repository = VaultRepository(vault)
        projection_texts = retrieve_projection_texts(repository, schema)
        dense_rows: list[dict[str, Any]] = []
        dense_latencies = []
        for query in queries:
            started = time.perf_counter()
            dense_candidates = index.find_candidates(
                embedder,
                query["reference"],
                context=query["context"],
                type=query["type"],
                limit=NOTE_COUNT,
            )
            dense_latencies.append(time.perf_counter() - started)
            dense_ranking = [candidate.id for candidate in dense_candidates]
            dense_rows.append({**query, "ranking": dense_ranking})

        contextual_rows = [
            row
            for row, query in zip(dense_rows, queries, strict=True)
            if exact_unique_ids(specs, query) != {query["expected_id"]}
        ]
        result = {
            "corpus": {
                "notes": count,
                "queries": len(queries),
                "languages": sorted({q["language"] for q in queries}),
                "categories": sorted({q["category"] for q in queries}),
            },
            "method": {
                "dense_model": embedder.model_name,
                "hybrid": "dense + name/alias overlap + NLTK WordNet/OMW same-language lemmas; RRF k=60",
                "cross_encoder": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 (reranking only)",
            },
            "performance": {
                "indexing_seconds": indexing_seconds,
                "dense_query_ms_median": statistics.median(dense_latencies) * 1000,
                "hybrid_query_ms_median": None,
                "max_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                "index_bytes": index.path.stat().st_size,
            },
            "dense": {
                "metrics": metrics(dense_rows),
                "contextual_only_count": len(contextual_rows),
                "contextual_only_metrics": metrics(contextual_rows),
                "top5_misses": [
                    {
                        "id": row["id"],
                        "expected_rank": (
                            row["ranking"].index(row["expected_id"]) + 1
                            if row["expected_id"] in row["ranking"]
                            else None
                        ),
                    }
                    for row in contextual_rows
                    if row["expected_id"] not in row["ranking"][:5]
                ],
                "rows": dense_rows,
            },
            "hybrid": {
                "status": "historical result preserved in phase11b1c_retrieval_stress_results.md; not rerun",
            },
        }
        if cache_dir is not None:
            result["performance"]["platform"] = platform.platform()
        if cross_encoder_dir is not None:
            reranked_results = {}
            for breadth in (20, 50, 100):
                reranked_rows, timing = rerank_top_candidates(
                    dense_rows, projection_texts, cross_encoder_dir, breadth
                )
                breadth_rows = reranked_rows
                reranked_contextual = [
                    row
                    for row, query in zip(breadth_rows, queries, strict=True)
                    if exact_unique_ids(specs, query) != {query["expected_id"]}
                ]
                reranked_results[f"top_{breadth}"] = {
                    "all_query_metrics": metrics(breadth_rows),
                    "contextual_only_metrics": metrics(reranked_contextual),
                    "top5_misses": [
                        row["id"]
                        for row in reranked_contextual
                        if row["expected_id"] not in row["ranking"][:5]
                    ],
                    "timing": timing,
                }
            result["cross_encoder_reranking"] = reranked_results
        return result


def main() -> None:
    """Parse paths, run the local benchmark, and emit stable JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path(__file__).with_name("phase11b1c_retrieval_queries.json"),
    )
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[1] / "config" / "note-schema.json"
    )
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--cross-encoder-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.queries, args.schema, args.cache_dir, args.cross_encoder_dir)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
