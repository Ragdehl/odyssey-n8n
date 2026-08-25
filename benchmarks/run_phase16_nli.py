"""Benchmark a local multilingual NLI judge after MiniLM unit retrieval.

This is Phase 16.2A.3 evidence only.  It deliberately has no production import or write action.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import resource
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.run_phase16_adversarial_novelty import body_units, load_cases
from benchmarks.run_phase16_novelty import cosine_similarity
from odyssey_core.semantic import FastEmbedTextEmbedder

MODEL_ID = "MoritzLaurer/multilingual-MiniLMv2-L12-mnli-xnli"
LABELS = frozenset({"entailment", "neutral", "contradiction"})
# Chosen before the NLI run from the factual relation in the labelled corpus, not model scores.
ORACLE_UNIT_INDEX = {
    "A01": 1,
    "A02": 1,
    "A03": 0,
    "A04": 1,
    "A05": 1,
    "A06": 1,
    "A07": 0,
    "A08": 1,
    "A09": 1,
    "A10": 1,
    "A11": 3,
    "A12": 0,
    "A13": 1,
    "A14": 1,
    "A15": 1,
    "A16": 0,
    "A17": 0,
    "A18": 0,
    "A19": 2,
    "A20": 2,
    "A21": 0,
    "A22": 0,
    "A23": 0,
    "A24": 0,
    "A25": 0,
    "A26": 0,
    "A27": 2,
    "A28": 0,
    "A29": 0,
    "A30": 0,
    "A31": 0,
    "A32": 0,
    "A33": 1,
    "A34": 0,
    "A35": 0,
    "A36": 1,
    "A37": 1,
    "A38": 0,
    "A39": 0,
    "A40": 0,
    "A41": 2,
    "A42": 1,
    "A43": 0,
    "A44": 3,
    "A45": 0,
    "A46": 4,
}


def label_mapping(id2label: dict[int | str, str]) -> dict[int, str]:
    """Validate and normalize a sequence-classifier's required NLI labels.

    Args:
        id2label: Model configuration mapping from output index to label text.

    Returns:
        Output-index mapping with lowercase NLI labels.

    Raises:
        ValueError: If the model does not expose exactly entailment, neutral, and contradiction.
    """
    mapped = {int(key): value.casefold() for key, value in id2label.items()}
    if set(mapped.values()) != LABELS or len(mapped) != 3:
        raise ValueError("NLI model config must expose entailment, neutral, and contradiction")
    return mapped


def normalize_probabilities(values: Sequence[float]) -> dict[str, float]:
    """Return named finite probabilities after requiring a normalized NLI distribution.

    Args:
        values: Entailment, neutral, contradiction probabilities in that order.

    Returns:
        Named probability distribution.

    Raises:
        ValueError: If the distribution is malformed or not normalized.
    """
    if len(values) != 3 or any(value < 0 or value > 1 for value in values):
        raise ValueError("NLI probabilities must be three values in [0, 1]")
    if abs(sum(values) - 1) > 1e-5:
        raise ValueError("NLI probabilities must sum to one")
    return dict(zip(("entailment", "neutral", "contradiction"), values, strict=True))


class LocalNli:
    """Run the approved local sequence-classification model in both NLI directions."""

    def __init__(self, model_path: Path):
        """Load tokenizer and safetensors model from an already-local snapshot.

        Args:
            model_path: Offline Hugging Face snapshot directory.

        Raises:
            ImportError: If the optional benchmark runtime is absent.
            ValueError: If the snapshot has incompatible NLI labels.
        """
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as error:
            raise ImportError(
                "install requirements-nli-benchmark.txt for this local benchmark"
            ) from error
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True, use_safetensors=True
        )
        self.model.eval()
        self.labels = label_mapping(self.model.config.id2label)

    def pairs(self, pairs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
        """Classify premise/hypothesis pairs and retain every class probability.

        Args:
            pairs: Ordered premise and hypothesis texts.

        Returns:
            One labelled probability record per input pair.
        """
        if not pairs:
            return []
        encoded = self.tokenizer(
            *zip(*pairs, strict=True), padding=True, truncation=True, return_tensors="pt"
        )
        with self.torch.inference_mode():
            probabilities = self.torch.softmax(self.model(**encoded).logits, dim=-1).tolist()
        return [
            {self.labels[index]: probability for index, probability in enumerate(row)}
            for row in probabilities
        ]


def bidirectional(nli: LocalNli, existing: str, proposed: str) -> dict[str, Any]:
    """Measure both directional NLI readings for one existing/proposed fact pair.

    Args:
        nli: Loaded local NLI runtime.
        existing: Existing body unit.
        proposed: Proposed atomic fact.

    Returns:
        Both named distributions and conservative maximum overlap evidence.
    """
    forward, reverse = nli.pairs([(existing, proposed), (proposed, existing)])
    return {
        "existing_premise": normalize_probabilities(
            [forward[key] for key in ("entailment", "neutral", "contradiction")]
        ),
        "proposed_premise": normalize_probabilities(
            [reverse[key] for key in ("entailment", "neutral", "contradiction")]
        ),
        "max_entailment": max(forward["entailment"], reverse["entailment"]),
        "max_contradiction": max(forward["contradiction"], reverse["contradiction"]),
        "max_non_neutral": max(1 - forward["neutral"], 1 - reverse["neutral"]),
        "min_neutral": min(forward["neutral"], reverse["neutral"]),
    }


def independent(
    evidence: dict[str, Any], neutral: float, entailment: float, contradiction: float
) -> bool:
    """Apply one deliberately conservative exploratory neutral-zone policy.

    Args:
        evidence: Bidirectional or aggregated NLI evidence.
        neutral: Required minimum neutral probability.
        entailment: Allowed maximum entailment probability.
        contradiction: Allowed maximum contradiction probability.

    Returns:
        Whether every measured direction/candidate is neutral enough to be an append candidate.
    """
    return (
        evidence["min_neutral"] >= neutral
        and evidence["max_entailment"] <= entailment
        and evidence["max_contradiction"] <= contradiction
    )


def policy_results(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate a small predeclared grid without fitting individual scenario errors.

    Args:
        records: Labelled records containing aggregated NLI evidence.

    Returns:
        Safety-oriented overlap recall and independent escalation evidence per policy.
    """
    output = []
    for neutral in (0.50, 0.70, 0.85):
        for cap in (0.10, 0.20, 0.30):
            dangerous = [
                item["id"]
                for item in records
                if item["expected"] == "OVERLAP"
                and independent(item["evidence"], neutral, cap, cap)
            ]
            escalated = [
                item["id"]
                for item in records
                if item["expected"] == "INDEPENDENT"
                and not independent(item["evidence"], neutral, cap, cap)
            ]
            overlap_count = sum(item["expected"] == "OVERLAP" for item in records)
            independent_count = sum(item["expected"] == "INDEPENDENT" for item in records)
            output.append(
                {
                    "neutral_min": neutral,
                    "entailment_max": cap,
                    "contradiction_max": cap,
                    "overlap_recall": 1 - len(dangerous) / overlap_count,
                    "dangerous_false_independent_ids": dangerous,
                    "independent_escalation_rate": len(escalated) / independent_count,
                    "independent_escalated_ids": escalated,
                }
            )
    return output


def aggregate(items: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Aggregate retrieved-pair evidence so any overlap-like candidate blocks independence.

    Args:
        items: Bidirectional NLI evidence for retrieved units.

    Returns:
        Conservative evidence extrema across candidates.
    """
    return {
        "max_entailment": max(item["max_entailment"] for item in items),
        "max_contradiction": max(item["max_contradiction"] for item in items),
        "max_non_neutral": max(item["max_non_neutral"] for item in items),
        "min_neutral": min(item["min_neutral"] for item in items),
    }


def run_benchmark(
    data: dict[str, Any], nli: LocalNli, embedder: FastEmbedTextEmbedder
) -> dict[str, Any]:
    """Run separate oracle-unit and retrieval-plus-NLI evidence over adversarial scenarios.

    Args:
        data: Validated Phase 16.2A.2 scenarios.
        nli: Approved local sequence-classification runtime.
        embedder: Existing local embedding MiniLM used only for candidate retrieval.

    Returns:
        Machine-readable oracle, retrieval, directional, policy, and timing evidence.
    """
    start = time.perf_counter()
    records = []
    for scenario in data["scenarios"]:
        units = body_units(scenario["note_body"])
        oracle_index = ORACLE_UNIT_INDEX[scenario["id"]]
        vectors = list(embedder.embed_documents([scenario["proposed"], *units]))
        scores = [cosine_similarity(vectors[0], vector) for vector in vectors[1:]]
        order = sorted(range(len(units)), key=scores.__getitem__, reverse=True)
        oracle = bidirectional(nli, units[oracle_index], scenario["proposed"])
        retrieved = []
        for index in order[:5]:
            retrieved.append(
                {
                    "unit_index": index,
                    "unit": units[index],
                    "similarity": scores[index],
                    "evidence": bidirectional(nli, units[index], scenario["proposed"]),
                }
            )
        record = {
            **scenario,
            "body_units": units,
            "oracle_unit_index": oracle_index,
            "oracle_unit": units[oracle_index],
            "oracle_evidence": oracle,
            "retrieval_order": order,
            "top_candidates": retrieved,
        }
        for k in (1, 3, 5):
            picked = retrieved[:k]
            record[f"top_{k}_evidence"] = aggregate([item["evidence"] for item in picked])
        if scenario.get("raw_request"):
            record["raw_request_oracle_evidence"] = bidirectional(
                nli, units[oracle_index], scenario["raw_request"]
            )
        records.append(record)
    oracle_records = [
        {"id": r["id"], "expected": r["expected"], "evidence": r["oracle_evidence"]}
        for r in records
    ]
    pipeline = {
        str(k): [
            {"id": r["id"], "expected": r["expected"], "evidence": r[f"top_{k}_evidence"]}
            for r in records
        ]
        for k in (1, 3, 5)
    }
    overlap = [record for record in records if record["expected"] == "OVERLAP"]
    recall = {
        str(k): sum(
            record["oracle_unit_index"] in record["retrieval_order"][:k] for record in overlap
        )
        / len(overlap)
        for k in (1, 3, 5)
    }
    return {
        "format_version": 1,
        "model_id": MODEL_ID,
        "scenario_count": len(records),
        "class_counts": dict(Counter(r["expected"] for r in records)),
        "runtime": {
            "transformers": importlib.metadata.version("transformers"),
            "torch": importlib.metadata.version("torch"),
            "safetensors": importlib.metadata.version("safetensors"),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "elapsed_seconds": time.perf_counter() - start,
        },
        "scenarios": records,
        "oracle_unit_policy_results": policy_results(oracle_records),
        "pipeline_policy_results": {key: policy_results(value) for key, value in pipeline.items()},
        "retrieval_recall": recall,
    }


def main() -> None:
    """Run the optional local-only benchmark and save reviewable evidence JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--embedding-cache-dir", type=Path, required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("phase16_adversarial_novelty_cases.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("phase16_nli_results.json")
    )
    args = parser.parse_args()
    results = run_benchmark(
        load_cases(args.cases),
        LocalNli(args.model_path),
        FastEmbedTextEmbedder(cache_dir=args.embedding_cache_dir, local_files_only=True),
    )
    args.output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
