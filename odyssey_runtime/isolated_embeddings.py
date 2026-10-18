"""On-demand out-of-process FastEmbed adapter for memory-constrained local hosts.

The canonical Writer and derived SQLite indexes stay in Odyssey. The worker
only computes embeddings; it never sees filesystem roots, identity, or network
credentials. It is an opt-in runtime adapter, not a persistent application server.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from odyssey_core.semantic import DEFAULT_EMBEDDING_MODEL, SemanticIndexError


class IsolatedFastEmbedTextEmbedder:
    """Use local, offline ONNX in a disposable process, reaped when idle."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        idle_seconds: float = 120,
        request_timeout_seconds: float = 120,
        worker_module: str = "odyssey_runtime.embedding_worker",
    ) -> None:
        if not cache_dir.is_dir() or idle_seconds <= 0 or request_timeout_seconds <= 0:
            raise ValueError("Invalid isolated embeddings configuration")
        self.model_name = model_name
        self.model_version = f"fastembed-{version('fastembed')}"
        self._cache_dir = cache_dir
        self._worker_module = worker_module
        self._idle_seconds = idle_seconds
        self._request_timeout = request_timeout_seconds
        self._lock = threading.RLock()
        self._worker: subprocess.Popen[bytes] | None = None
        # Volatile foreground browser leases, not canonical user state.
        self._sessions: dict[tuple[str, str], float] = {}
        self._warm_pending = False
        self._closed = False
        self._last_used = time.monotonic()
        self._reaper = threading.Thread(
            target=self._idle_reaper, daemon=True, name="odyssey-embedding-idle-reaper"
        )
        self._reaper.start()

    def presence(self, actor: str, session_id: str, state: str) -> None:
        """An authenticated browser tab keeps ONNX hot; leaving starts the idle grace.

        A lost pagehide/connection is bounded by a two-minute heartbeat lease.
        The browser never blocks on the first model load.
        """
        if state not in ("active", "heartbeat", "inactive"):
            raise ValueError("Invalid presence state")
        with self._lock:
            if self._closed:
                raise SemanticIndexError("Embedding worker is closed")
            key = (actor, session_id)
            now = time.monotonic()
            self._prune_sessions(now)
            if state == "inactive":
                removed = self._sessions.pop(key, None)
                if removed is not None and not self._sessions:
                    self._last_used = now
                return
            if key not in self._sessions and len(self._sessions) >= 32:
                raise ValueError("Too many open Odyssey sessions")
            self._sessions[key] = now
            if (self._worker is None or self._worker.poll() is not None) and not self._warm_pending:
                self._warm_pending = True
                threading.Thread(
                    target=self._prewarm_in_background,
                    daemon=True,
                    name="odyssey-embedding-browser-prewarm",
                ).start()

    def _prune_sessions(self, now: float) -> None:
        if not self._sessions:
            return
        for key, last_ping in tuple(self._sessions.items()):
            if now - last_ping > 150:
                del self._sessions[key]
        if not self._sessions:
            self._last_used = now

    def _prewarm_in_background(self) -> None:
        try:
            self._call("warm", ())
        except SemanticIndexError:
            # A failed optimization never suppresses later normal embedding errors.
            pass
        finally:
            with self._lock:
                self._warm_pending = False

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute canonical document vectors, preserving order."""
        return self._in_batches("documents", texts)

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute canonical query vectors, preserving order."""
        return self._in_batches("queries", texts)

    def _in_batches(self, mode: str, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        vectors: list[list[float]] = []
        # Bounded IPC, including initial full-vault index rebuilds.
        for start in range(0, len(values), 64):
            vectors.extend(self._call(mode, values[start : start + 64]))
        return vectors

    def _call(self, mode: str, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        if not values and mode != "warm":
            return []
        if not all(isinstance(item, str) for item in values):
            raise ValueError("Embedding texts must be strings")
        with self._lock:
            if self._closed:
                raise SemanticIndexError("Embedding worker is closed")
            try:
                process = self._worker
                if process is None or process.poll() is not None:
                    process = self._start_worker()
                assert process.stdin is not None and process.stdout is not None
                payload = (json.dumps({"mode": mode, "texts": values}) + "\n").encode()
                if len(payload) > 16_777_216:
                    raise SemanticIndexError("Embedding batch exceeds local IPC budget")
                process.stdin.write(payload)
                process.stdin.flush()
                deadline = time.monotonic() + self._request_timeout
                response = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Embedding worker exceeded local inference deadline")
                    readable, _, _ = select.select(
                        [process.stdout.fileno()], [], [], min(remaining, 1.0)
                    )
                    if not readable:
                        if process.poll() is not None:
                            raise BrokenPipeError("Embedding worker exited")
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise BrokenPipeError("Embedding worker ended response early")
                    response.extend(chunk)
                    if len(response) > 128_000_000:
                        raise ValueError("Embedding worker response exceeded budget")
                    if response.endswith(b"\n"):
                        break
                outcome = json.loads(response)
                if mode == "warm":
                    if outcome != {"ready": True}:
                        raise ValueError("Embedding worker warmup failed")
                    return []
                vectors = outcome["vectors"]
                if not isinstance(vectors, list) or len(vectors) != len(values):
                    raise ValueError("Embedding worker returned incorrect vector cardinality")
                if not all(
                    isinstance(vector, list)
                    and vector
                    and all(isinstance(x, (int, float)) for x in vector)
                    for vector in vectors
                ):
                    raise ValueError("Embedding worker returned invalid vector type")
                return vectors
            except (OSError, ValueError, KeyError, TimeoutError, BrokenPipeError) as error:
                self._stop_worker()
                raise SemanticIndexError(
                    "Isolated embedding worker could not supply canonical vectors"
                ) from error
            finally:
                self._last_used = time.monotonic()

    def _start_worker(self) -> subprocess.Popen[bytes]:
        # A local model needs no client/API secrets. Do not inherit user
        # credentials into a process whose only authority is inferencing.
        safe_keys = {
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "LD_LIBRARY_PATH",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "OMP_NUM_THREADS",
            "TZ",
        }
        env = {key: value for key, value in os.environ.items() if key in safe_keys}
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                self._worker_module,
                self.model_name,
                str(self._cache_dir),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            close_fds=True,
        )
        self._worker = process
        return process

    def _stop_worker(self) -> None:
        process = self._worker
        self._worker = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()

    def _idle_reaper(self) -> None:
        while True:
            time.sleep(min(1.0, self._idle_seconds / 2))
            with self._lock:
                if self._closed:
                    return
                now = time.monotonic()
                self._prune_sessions(now)
                if (
                    self._worker is not None
                    and not self._sessions
                    and now - self._last_used >= self._idle_seconds
                ):
                    self._stop_worker()

    def close(self) -> None:
        """Reclaim local ONNX memory, and permanently close this adapter."""
        with self._lock:
            self._closed = True
            self._stop_worker()

    def __enter__(self) -> IsolatedFastEmbedTextEmbedder:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
