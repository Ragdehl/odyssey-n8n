"""Benchmark conservative contextual decisions over Phase 10 semantic candidates."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import resource
import statistics
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUTCOMES = {"RESOLVED", "AMBIGUOUS", "UNRESOLVED"}
LOCAL_SERVER_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_local_server_url(value: str) -> str:
    """Validate a benchmark server URL is an unauthenticated local HTTP endpoint.

    Args:
        value: Candidate URL supplied to the local model-server benchmark.

    Returns:
        The unchanged URL when it targets loopback over HTTP.

    Raises:
        ValueError: If the URL has credentials, a non-HTTP scheme, a malformed
            port, or a non-loopback host.
    """
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or 0
    except (AttributeError, ValueError) as error:
        raise ValueError("server URL is malformed") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or hostname not in LOCAL_SERVER_HOSTS
        or not 0 <= port <= 65535
    ):
        raise ValueError("server URL must be an HTTP loopback URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("server URL must not contain credentials")
    return value


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace a benchmark result without exposing a partial JSON document.

    Args:
        path: Final result path.
        payload: JSON-compatible benchmark state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def system_memory() -> dict[str, int]:
    """Read host RAM and swap counters from Linux procfs in KiB.

    Returns:
        Available memory counters, or an empty mapping off Linux.
    """
    path = Path("/proc/meminfo")
    if not path.exists():
        return {}
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, value = line.split(":", maxsplit=1)
        if name in wanted:
            values[f"{name.lower()}_kib"] = int(value.strip().split()[0])
    return values


def process_memory(pid: int) -> dict[str, int]:
    """Read peak RSS and swap counters for a local model-server process.

    Args:
        pid: Linux process identifier for the benchmark server.

    Returns:
        Available procfs counters in KiB, or an empty mapping if the process ended.
    """
    path = Path(f"/proc/{pid}/status")
    if not path.exists():
        return {}
    names = {"VmHWM": "peak_rss_kib", "VmRSS": "rss_kib", "VmSwap": "swap_kib"}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, value = line.split(":", maxsplit=1)
        if name in names:
            values[names[name]] = int(value.strip().split()[0])
    return values


def package_versions() -> dict[str, str]:
    """Return exact installed versions relevant to this benchmark."""
    versions = {}
    for package in ("fastembed", "numpy", "onnxruntime", "tokenizers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def artifact_bytes(path: Path) -> int:
    """Measure a model file or recursively total a model directory in bytes.

    Args:
        path: Existing benchmark artifact.

    Returns:
        File size or sum of regular files below a directory.
    """
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def load_dataset(path: Path) -> dict[str, Any]:
    """Load the synthetic notes and labelled contextual-reference cases.

    Args:
        path: JSON dataset path.

    Returns:
        Parsed benchmark dataset.

    Raises:
        OSError: If the dataset cannot be read.
        json.JSONDecodeError: If its content is invalid JSON.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    note_ids = {note["id"] for note in data["notes"]}
    case_ids = [case["id"] for case in data["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark case IDs must be unique")
    for case in data["cases"]:
        if case["expected"] not in OUTCOMES:
            raise ValueError(f"invalid expected outcome in {case['id']}")
        expected_id = case.get("expected_id")
        if case["expected"] == "RESOLVED" and expected_id not in note_ids:
            raise ValueError(f"resolved case {case['id']} needs a known expected_id")
        if case["expected"] != "RESOLVED" and expected_id is not None:
            raise ValueError(f"abstention case {case['id']} cannot set expected_id")
    return data


def build_phase10_candidates(
    data: dict[str, Any], limit: int = 5, cache_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Create the current Phase 10 cosine-ranked evidence for every case.

    Args:
        data: Benchmark dataset containing notes and cases.
        limit: Maximum candidates retained after canonical-type filtering.
        cache_dir: Existing local FastEmbed artifact directory.

    Returns:
        Cases augmented with candidate documents and cosine scores.
    """
    import numpy as np
    from fastembed import TextEmbedding

    model = TextEmbedding(
        model_name=EMBEDDING_MODEL,
        cache_dir=str(cache_dir) if cache_dir else None,
        local_files_only=True,
    )
    notes = data["notes"]
    note_vectors = np.asarray(list(model.embed([note["text"] for note in notes])))
    note_vectors /= np.linalg.norm(note_vectors, axis=1, keepdims=True)
    texts = [
        f"Reference: {case['reference']}\nContext: {case['context']}" for case in data["cases"]
    ]
    query_vectors = np.asarray(list(model.query_embed(texts)))
    query_vectors /= np.linalg.norm(query_vectors, axis=1, keepdims=True)
    results = []
    for case, query_vector in zip(data["cases"], query_vectors, strict=True):
        scored = [
            {**note, "score": float(note_vector @ query_vector)}
            for note, note_vector in zip(notes, note_vectors, strict=True)
            if note["type"] == case["type"]
        ]
        scored.sort(key=lambda item: (-item["score"], item["id"]))
        results.append({**case, "candidates": scored[:limit]})
    return results


def rerank_onnx(cases: list[dict[str, Any]], model_dir: Path) -> list[dict[str, Any]]:
    """Rerank Phase 10 candidates with a local Hugging Face ONNX cross-encoder.

    Args:
        cases: Cases containing Phase 10 candidate evidence.
        model_dir: Directory with ``tokenizer.json`` and ``model.onnx``.

    Returns:
        Cases with cross-encoder logits replacing cosine scores.

    Raises:
        OSError: If model artifacts cannot be loaded.
    """
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    session = ort.InferenceSession(
        str(model_dir / "model.onnx"), providers=["CPUExecutionProvider"]
    )
    results = []
    for case in cases:
        query = f"Reference: {case['reference']} Context: {case['context']}"
        pairs = [(query, candidate["text"]) for candidate in case["candidates"]]
        encodings = tokenizer.encode_batch(pairs)
        width = min(512, max(len(encoding.ids) for encoding in encodings))
        input_ids = np.zeros((len(encodings), width), dtype=np.int64)
        attention_mask = np.zeros_like(input_ids)
        for row, encoding in enumerate(encodings):
            ids = encoding.ids[:width]
            input_ids[row, : len(ids)] = ids
            attention_mask[row, : len(ids)] = 1
        logits = session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})[0]
        reranked = [
            {**candidate, "phase10_score": candidate["score"], "score": float(logit)}
            for candidate, logit in zip(case["candidates"], logits.reshape(-1), strict=True)
        ]
        reranked.sort(key=lambda item: (-item["score"], item["id"]))
        results.append({**case, "candidates": reranked})
    return results


def classify_scores(case: dict[str, Any], threshold: float, margin: float) -> dict[str, Any]:
    """Turn ranked scores into a conservative three-way identity decision.

    Args:
        case: Labelled case with descending candidate scores.
        threshold: Minimum top score for any resolved or ambiguous decision.
        margin: Minimum top-to-runner-up separation required to resolve.

    Returns:
        Predicted outcome, optional identity, and score evidence.
    """
    top = case["candidates"][0]
    runner_up = case["candidates"][1]
    score_margin = top["score"] - runner_up["score"]
    if top["score"] < threshold:
        outcome, identity = "UNRESOLVED", None
    elif score_margin < margin:
        outcome, identity = "AMBIGUOUS", None
    else:
        outcome, identity = "RESOLVED", top["id"]
    return {
        "outcome": outcome,
        "id": identity,
        "top_score": top["score"],
        "margin": score_margin,
    }


def select_conservative_policy(cases: list[dict[str, Any]]) -> tuple[float, float]:
    """Choose score rules on calibration cases with false resolution weighted first.

    Args:
        cases: Ranked cases including a ``calibration`` split.

    Returns:
        Score threshold and score-margin threshold. Ties prefer the more conservative
        policy, followed by more correct decisions.
    """
    calibration = [case for case in cases if case["split"] == "calibration"]
    tops = sorted({case["candidates"][0]["score"] for case in calibration})
    margins = sorted(
        {case["candidates"][0]["score"] - case["candidates"][1]["score"] for case in calibration}
    )
    epsilon = 1e-6
    thresholds = [tops[0] - epsilon, *[value + epsilon for value in tops]]
    margin_values = [0.0, *[value + epsilon for value in margins]]
    choices = []
    for threshold in thresholds:
        for margin in margin_values:
            predictions = [classify_scores(case, threshold, margin) for case in calibration]
            false_resolved = sum(
                prediction["outcome"] == "RESOLVED"
                and (case["expected"] != "RESOLVED" or prediction["id"] != case.get("expected_id"))
                for case, prediction in zip(calibration, predictions, strict=True)
            )
            correct = sum(
                prediction["outcome"] == case["expected"]
                and (
                    prediction["outcome"] != "RESOLVED"
                    or prediction["id"] == case.get("expected_id")
                )
                for case, prediction in zip(calibration, predictions, strict=True)
            )
            resolved = sum(prediction["outcome"] == "RESOLVED" for prediction in predictions)
            choices.append(
                ((false_resolved, -correct, resolved, -threshold, -margin), threshold, margin)
            )
    _, threshold, margin = min(choices)
    return threshold, margin


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object from a model response.

    Args:
        text: Raw assistant response.

    Returns:
        Parsed JSON object.

    Raises:
        ValueError: If no JSON object is present.
        json.JSONDecodeError: If the delimited object is invalid.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model response contained no JSON object")
    return json.loads(text[start : end + 1])


def llm_decision(
    case: dict[str, Any], url: str, model: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Request one deterministic contextual identity decision from llama.cpp.

    Args:
        case: Case with Phase 10 candidate evidence.
        url: OpenAI-compatible chat-completions endpoint.
        model: Served model identifier recorded in the request.

    Returns:
        Normalized prediction and server usage/timing metadata.

    Raises:
        OSError: If the local server request fails.
        ValueError: If the response violates the decision contract.
    """
    candidates = "\n".join(
        f"- id={candidate['id']}\n{candidate['text']}" for candidate in case["candidates"]
    )
    prompt = f"""Decide whether a reference uniquely identifies one candidate.
Wrong RESOLVED is worse than AMBIGUOUS or UNRESOLVED.
RESOLVED: exactly one candidate is supported by the reference and context.
AMBIGUOUS: two or more candidates remain plausible.
UNRESOLVED: no candidate is plausibly the referenced entity.
Never infer missing relationships. Return JSON only. Set id to an exact candidate id
only for RESOLVED; otherwise set id to null.

Reference: {case["reference"]}
Context: {case["context"]}
Expected entity type: {case["type"]}
Candidates:
{candidates}"""
    candidate_ids = [candidate["id"] for candidate in case["candidates"]]
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 40,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "entity_resolution",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "outcome": {"type": "string", "enum": sorted(OUTCOMES)},
                            "id": {"type": ["string", "null"], "enum": [*candidate_ids, None]},
                        },
                        "required": ["outcome", "id"],
                    },
                },
            },
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.load(response)
    latency = time.perf_counter() - started
    raw_content = body["choices"][0]["message"]["content"]
    parse_error = None
    try:
        parsed = parse_json_object(raw_content)
        outcome = str(parsed.get("outcome", "")).upper()
        identity = parsed.get("id")
    except (ValueError, json.JSONDecodeError) as error:
        outcome, identity = "UNRESOLVED", None
        parse_error = str(error)
    candidate_id_set = set(candidate_ids)
    if outcome not in OUTCOMES or (outcome == "RESOLVED" and identity not in candidate_id_set):
        parse_error = f"invalid decision: outcome={outcome!r}, id={identity!r}"
        outcome, identity = "UNRESOLVED", None
    if outcome != "RESOLVED":
        identity = None
    usage = body.get("usage", {})
    timings = body.get("timings", {})
    return {
        "outcome": outcome,
        "id": identity,
        "latency_seconds": latency,
        "parse_error": parse_error,
    }, {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "tokens_per_second": timings.get("predicted_per_second"),
    }


def summarize(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize held-out quality with false resolutions called out explicitly.

    Args:
        cases: Labelled cases.
        predictions: Corresponding normalized predictions.

    Returns:
        Overall and per-language quality counts plus case-level outcomes.
    """
    evaluation = [
        (case, prediction)
        for case, prediction in zip(cases, predictions, strict=True)
        if case["split"] == "evaluation"
    ]

    def metrics(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
        correct_resolved = sum(
            case["expected"] == "RESOLVED"
            and prediction["outcome"] == "RESOLVED"
            and prediction["id"] == case.get("expected_id")
            for case, prediction in rows
        )
        false_resolved = sum(
            prediction["outcome"] == "RESOLVED"
            and (case["expected"] != "RESOLVED" or prediction["id"] != case.get("expected_id"))
            for case, prediction in rows
        )
        predicted_resolved = correct_resolved + false_resolved
        correct_ambiguous = sum(
            case["expected"] == prediction["outcome"] == "AMBIGUOUS" for case, prediction in rows
        )
        correct_unresolved = sum(
            case["expected"] == prediction["outcome"] == "UNRESOLVED" for case, prediction in rows
        )
        count = len(rows)
        return {
            "cases": len(rows),
            "correct_resolved": correct_resolved,
            "false_resolved": false_resolved,
            "false_resolved_rate": false_resolved / count if count else 0.0,
            "correct_ambiguous": correct_ambiguous,
            "correct_unresolved": correct_unresolved,
            "resolution_coverage": predicted_resolved / count if count else 0.0,
            "accuracy_when_resolved": (
                correct_resolved / predicted_resolved if predicted_resolved else None
            ),
            "overall_accuracy": (
                (correct_resolved + correct_ambiguous + correct_unresolved) / count
                if count
                else 0.0
            ),
        }

    by_language = defaultdict(list)
    by_category = defaultdict(list)
    for row in evaluation:
        by_language[row[0]["language"]].append(row)
        by_category[row[0]["category"]].append(row)
    retrieval_failures = [
        case["id"]
        for case, _ in evaluation
        if case["expected"] == "RESOLVED"
        and case.get("expected_id") not in {candidate["id"] for candidate in case["candidates"]}
    ]
    return {
        "overall": metrics(evaluation),
        "blocking_languages": metrics([row for row in evaluation if row[0]["language"] != "ca"]),
        "per_language": {language: metrics(rows) for language, rows in sorted(by_language.items())},
        "per_category": {category: metrics(rows) for category, rows in sorted(by_category.items())},
        "phase10_retrieval": {
            "resolved_cases_missing_expected_candidate": len(retrieval_failures),
            "case_ids": retrieval_failures,
        },
        "cases": [
            {
                "case_id": case["id"],
                "language": case["language"],
                "expected": case["expected"],
                "expected_id": case.get("expected_id"),
                "category": case["category"],
                "phase10_candidate_ids": [candidate["id"] for candidate in case["candidates"]],
                "phase10_candidate_scores": [
                    candidate.get("phase10_score", candidate["score"])
                    for candidate in case["candidates"]
                ],
                **prediction,
            }
            for case, prediction in evaluation
        ],
    }


def main() -> None:
    """Run one benchmark method and emit a reproducible JSON result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=("cosine", "cross-encoder", "llm"))
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("phase11a_contextual_resolution_cases.json"),
    )
    parser.add_argument("--cross-encoder-dir", type=Path)
    parser.add_argument(
        "--server-url",
        type=validate_local_server_url,
        default="http://127.0.0.1:8080/v1/chat/completions",
    )
    parser.add_argument("--model", default="local-gguf")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-version")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--quantization")
    parser.add_argument("--model-load-seconds", type=float)
    parser.add_argument("--server-peak-rss-kib", type=int)
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--embedding-cache-dir", type=Path)
    args = parser.parse_args()
    memory_before = system_memory()
    started = time.perf_counter()
    dataset = load_dataset(args.cases)
    cases = build_phase10_candidates(dataset, cache_dir=args.embedding_cache_dir)
    if args.max_cases is not None:
        cases = cases[: args.max_cases]
    load_and_candidate_seconds = time.perf_counter() - started
    method_started = time.perf_counter()
    metadata: dict[str, Any] = {}
    if args.method == "cross-encoder":
        if args.cross_encoder_dir is None:
            parser.error("--cross-encoder-dir is required")
        cases = rerank_onnx(cases, args.cross_encoder_dir)
    if args.method in {"cosine", "cross-encoder"}:
        threshold, margin = select_conservative_policy(cases)
        predictions = [classify_scores(case, threshold, margin) for case in cases]
        metadata["policy"] = {"threshold": threshold, "margin": margin}
        summaries = [summarize(cases, predictions)]
    else:
        summaries = []
        repeat_usage = []
        for repeat in range(args.repeats):
            predictions = []
            usages = []
            for case in cases:
                prediction, usage = llm_decision(case, args.server_url, args.model)
                predictions.append(prediction)
                usages.append(usage)
                write_json_atomic(
                    args.output,
                    {
                        "status": "in_progress",
                        "method": args.method,
                        "model": args.model,
                        "completed_repeats": repeat,
                        "current_repeat_completed_cases": len(predictions),
                        "current_repeat_predictions": predictions,
                    },
                )
            summaries.append(summarize(cases, predictions))
            repeat_usage.append(usages)
        comparable = [
            tuple(
                (case["case_id"], case["outcome"], case.get("id"), case.get("parse_error"))
                for case in summary["cases"]
            )
            for summary in summaries
        ]
        metadata["repeatability_identical"] = len(set(comparable)) == 1
        for field in ("input_tokens", "output_tokens", "tokens_per_second"):
            values = [
                usage[field]
                for usages in repeat_usage
                for usage in usages
                if usage[field] is not None
            ]
            if values:
                metadata[field] = {"total": sum(values), "mean": statistics.mean(values)}
    elapsed = time.perf_counter() - method_started
    latencies = [case.get("latency_seconds") for summary in summaries for case in summary["cases"]]
    latencies = [value for value in latencies if value is not None]
    artifact = None
    if args.artifact is not None:
        artifact = {
            "path": str(args.artifact),
            "bytes": artifact_bytes(args.artifact),
            "quantization": args.quantization,
        }
    result = {
        "status": "complete",
        "method": args.method,
        "model": args.model
        if args.method == "llm"
        else (
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
            if args.method == "cross-encoder"
            else EMBEDDING_MODEL
        ),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "package_versions": package_versions(),
        "runtime_version": args.runtime_version,
        "artifact": artifact,
        "repeats": args.repeats,
        "dataset": {
            "path": str(args.cases),
            "notes": len(dataset["notes"]),
            "cases": len(dataset["cases"]),
            "calibration_cases": sum(case["split"] == "calibration" for case in dataset["cases"]),
            "evaluation_cases": sum(case["split"] == "evaluation" for case in dataset["cases"]),
        },
        "phase10_load_and_candidate_seconds": load_and_candidate_seconds,
        "model_load_seconds": args.model_load_seconds,
        "method_total_seconds": elapsed,
        "evaluation_latency_seconds": {
            "mean": statistics.mean(latencies) if latencies else elapsed / len(cases),
            "median": statistics.median(latencies) if latencies else math.nan,
            "max": max(latencies) if latencies else math.nan,
        },
        "memory": {
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "server_peak_rss_kib": args.server_peak_rss_kib,
            "server_process": process_memory(args.server_pid) if args.server_pid else None,
            "system_before": memory_before,
            "system_after": system_memory(),
        },
        **metadata,
        "runs": summaries,
    }
    write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
