"""Opt-in source-free DEV timings for boundaries missing from operational receipts.

This sink is never an execution authority and cannot block the user request.
No message, prompt, note identity, model response or principal is written.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from math import isfinite
from pathlib import Path
from time import perf_counter

_ALLOWED_STAGES = frozenset(
    {
        "conversation.entry",
        "conversation.classify",
        "p4.source",
        "p4.router",
        "p4.task_scope_primary",
        "p4.task_scope_independent",
        "tasks.delegate",
        "runtime.finish_product",
    }
)


def _record_dev_hot_path_timing(
    request_id: str, stage: str, duration_ms: float, *, failed: bool
) -> None:
    if (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_HOT_PATH_TIMING_ENABLED") != "1"
        or not isinstance(request_id, str)
        or not 1 <= len(request_id) <= 160
        or stage not in _ALLOWED_STAGES
        or type(duration_ms) not in (int, float)
        or not isfinite(duration_ms)
        or not 0 <= duration_ms <= 120_000
        or type(failed) is not bool
    ):
        return
    runtime_root = os.environ.get("ODYSSEY_RUNTIME_ROOT")
    if not runtime_root:
        return
    try:
        root = Path(runtime_root).resolve()
        prod = Path("/data/odyssey").resolve()
        if not root.is_dir() or root == prod or root.is_relative_to(prod):
            return
        entry = {
            "request_digest": hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16],
            "stage": stage,
            "duration_ms": round(duration_ms, 2),
            "failed": failed,
        }
        target = root / "hot-path-timing.jsonl"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode):
                return
            os.fchmod(fd, 0o600)
            if details.st_size > 131_072:
                os.ftruncate(fd, 0)
            os.write(fd, (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except (OSError, ValueError):
        # Non-authoritative timing must never change execution or write results.
        pass


@contextmanager
def timed_dev_hot_path(request_id: str, stage: str) -> Iterator[None]:
    """Measure one existing synchronous boundary; preserve its result and exceptions."""
    enabled = (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
        and os.environ.get("ODYSSEY_HOT_PATH_TIMING_ENABLED") == "1"
        and stage in _ALLOWED_STAGES
    )
    if not enabled:
        yield
        return
    started = perf_counter()
    try:
        yield
    except Exception:
        _record_dev_hot_path_timing(
            request_id, stage, (perf_counter() - started) * 1000, failed=True
        )
        raise
    else:
        _record_dev_hot_path_timing(
            request_id, stage, (perf_counter() - started) * 1000, failed=False
        )
