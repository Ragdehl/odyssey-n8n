"""Isolated ONNX adapter correctness, lifecycle, confidentiality, and fail-closed."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from odyssey_core.semantic import SemanticIndexError
from odyssey_runtime.isolated_embeddings import IsolatedFastEmbedTextEmbedder

WORKER = "tests.runtime.mock_embedding_worker"


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-secret")
    monkeypatch.setenv("TEST_PASSWORD", "not-for-inference")
    monkeypatch.setattr("odyssey_runtime.isolated_embeddings.version", lambda _key: "0.7.3")
    with IsolatedFastEmbedTextEmbedder(
        cache_dir=tmp_path,
        worker_module=WORKER,
        idle_seconds=0.2,
        request_timeout_seconds=3,
    ) as value:
        yield value


def test_worker_start_is_lazy_and_preserves_cardinality_and_versions(adapter):
    assert adapter._worker is None
    assert adapter.model_version == "fastembed-0.7.3"
    assert adapter.embed_documents([]) == []
    assert adapter._worker is None
    assert adapter.embed_documents(["ab", "c"]) == [[2.0, 195.0 + 1], [1.0, 99.0 + 1]]
    assert adapter.embed_queries(["hola"]) == [[4.0, 420.0 + 1]]


def test_parent_serializes_simultaneous_calls_without_mixups(adapter):
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(adapter.embed_documents, [["ab"], ["abc"], ["d"], ["z"]]))
    assert [row[0][0] for row in outputs] == [2.0, 3.0, 1.0, 1.0]


def test_worker_reaps_after_inactivity_and_respawns(adapter):
    assert adapter.embed_documents(["old"])[0][0] == 3
    first = adapter._worker
    assert first is not None
    deadline = time.monotonic() + 2
    while adapter._worker is not None and time.monotonic() < deadline:
        time.sleep(0.03)
    assert adapter._worker is None
    assert first.poll() is not None
    assert adapter.embed_documents(["new"])[0][0] == 3
    assert adapter._worker is not None and adapter._worker.pid != first.pid


def test_worker_failure_is_not_silently_accepted(adapter):
    with pytest.raises(SemanticIndexError, match="worker"):
        adapter.embed_documents(["FAIL_WORKER"])
    assert adapter._worker is None
    assert adapter.embed_documents(["fresh"])[0][0] == 5


def test_close_releases_process_and_rejects_new_requests(adapter):
    assert adapter.embed_documents(["hi"])[0][0] == 2
    process = adapter._worker
    assert process is not None
    adapter.close()
    assert process.poll() is not None
    with pytest.raises(SemanticIndexError, match="closed"):
        adapter.embed_documents(["bad"])


def test_batches_large_source_without_crossing_ipc_budget(adapter):
    payload = ["x" * (1 + n % 5) for n in range(130)]
    results = adapter.embed_documents(payload)
    assert len(results) == 130
    assert [row[0] for row in results] == [len(s) for s in payload]


def test_isolated_embedding_factory_is_restricted_to_dev(tmp_path, monkeypatch):
    from odyssey_runtime import composition
    from tests.runtime.test_dev_index_refresh_diagnostics import _runtime

    _runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("ODYSSEY_EMBEDDING_SUBPROCESS", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    with pytest.raises(ValueError, match="requires DEV light source"):
        composition.build_runtime_from_environment()


def test_isolated_embedding_adapter_can_be_composed_with_existing_indexes(tmp_path, monkeypatch):
    from odyssey_runtime import composition, isolated_embeddings
    from tests.core.test_context import KeywordEmbedder
    from tests.runtime.test_dev_index_refresh_diagnostics import _runtime

    _runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("ODYSSEY_EMBEDDING_SUBPROCESS", "1")
    monkeypatch.setenv("ODYSSEY_EMBEDDING_IDLE_SECONDS", "5")
    monkeypatch.setattr(
        isolated_embeddings,
        "IsolatedFastEmbedTextEmbedder",
        lambda **kwargs: KeywordEmbedder(),
    )
    runtime = composition.build_runtime_from_environment()
    assert isinstance(runtime.notes_embedder, KeywordEmbedder)
