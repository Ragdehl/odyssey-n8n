"""Run the frozen v10 corrective gate only after separate provider authorization."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import benchmarks.semantic_set_planner.run_live_v9 as _v9  # noqa: E402
from benchmarks.semantic_set_planner.v10_gate import (  # noqa: E402
    load_v10_registry,
    load_v10_selector_registry,
    v10_preflight,
)

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-self-clarification-v10-luna-gate.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Reuse audited v9 execution mechanics with v10's frozen output reservation."""
    original: tuple[Path, Callable[..., Any], Callable[..., Any], Callable[..., Any]] = (
        _v9.OUTPUT_PATH,
        _v9.load_v9_registry,
        _v9.load_v9_selector_registry,
        _v9.v9_preflight,
    )
    try:
        _v9.OUTPUT_PATH = OUTPUT_PATH
        _v9.load_v9_registry = load_v10_registry
        _v9.load_v9_selector_registry = load_v10_selector_registry
        _v9.v9_preflight = v10_preflight
        return _v9.main(argv)
    except SystemExit as error:
        if str(error) == "Live v9 planner gate preflight refused":
            raise SystemExit("Live v10 planner gate preflight refused") from None
        raise
    finally:
        (
            _v9.OUTPUT_PATH,
            _v9.load_v9_registry,
            _v9.load_v9_selector_registry,
            _v9.v9_preflight,
        ) = original


if __name__ == "__main__":
    raise SystemExit(main())
