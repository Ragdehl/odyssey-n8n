"""DEV-only content-free reasons for prewrite abstentions.

Diagnostic records never contain source text, identifiers, notes, model output,
paths, prompts or actor details. Never change a write decision on logging failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

_ALLOWED_GATES = frozenset(
    {
        "proposal",
        "coverage_verdict",
        "coverage_rejected",
        "coverage_retry_exhausted",
        "coverage_contract",
        "identity_collision",
        "speaker_contract",
        "prewrite_accepted",
        "compile_rejected",
        "task_scope_verdict",
        "task_scope_rejected",
        "task_batch_plan_rejected",
        "speaker_count_retry",
    }
)
_ALLOWED_COUNTS = frozenset(
    {"attempt", "facts", "entities", "reviewed_facts", "reason_code", "expected_facts"}
)
_ALLOWED_FLAGS = frozenset(
    {
        "unresolved",
        "approved",
        "complete",
        "overlapping",
        "task_only",
        "one_operation",
        "source_aligned",
    }
)


def record_dev_p4_prewrite_gate(delivery: str, gate: str, values: dict[str, int | bool]) -> None:
    if (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_LIGHT_SOURCE_V1") != "1"
        or not isinstance(delivery, str)
        or not 1 <= len(delivery) <= 160
        or gate not in _ALLOWED_GATES
        or not isinstance(values, dict)
    ):
        return
    root_str = os.environ.get("ODYSSEY_RUNTIME_ROOT")
    if not root_str:
        return
    filtered: dict[str, int | bool] = {}
    for key, value in values.items():
        if key in _ALLOWED_FLAGS and type(value) is bool:
            filtered[key] = value
        elif key in _ALLOWED_COUNTS and type(value) is int and 0 <= value <= 1000:
            filtered[key] = value
    event = {
        "request_digest": hashlib.sha256(delivery.encode("utf-8")).hexdigest()[:16],
        "gate": gate,
        **filtered,
    }
    try:
        root = Path(root_str).resolve()
        prod = Path("/data/odyssey").resolve()
        if not root.is_dir() or root == prod or root.is_relative_to(prod):
            return
        target = root / "p4-prewrite-gates.jsonl"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return
            os.fchmod(fd, 0o600)
            if info.st_size > 262_144:
                os.ftruncate(fd, 0)
            os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass
