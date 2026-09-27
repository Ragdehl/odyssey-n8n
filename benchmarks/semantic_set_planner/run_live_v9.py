"""Run the frozen v9 corrective gate only after separate provider authorization."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import benchmarks.semantic_set_planner.run_live_v8 as _v8  # noqa: E402
from benchmarks.semantic_set_planner.v9_gate import (  # noqa: E402
    load_v9_registry,
    load_v9_selector_registry,
    v9_preflight,
)

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-self-clarification-v9-luna-gate.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Reuse audited v8 execution mechanics with v9's frozen inputs and output path."""
    original: tuple[Path, Callable[..., Any], Callable[..., Any], Callable[..., Any]] = (
        _v8.OUTPUT_PATH,
        _v8.load_v8_registry,
        _v8.load_v8_selector_registry,
        _v8.v8_preflight,
    )
    try:
        _v8.OUTPUT_PATH = OUTPUT_PATH
        _v8.load_v8_registry = load_v9_registry
        _v8.load_v8_selector_registry = load_v9_selector_registry
        _v8.v8_preflight = v9_preflight
        return _v8.main(argv)
    except SystemExit as error:
        if str(error) == "Live v8 planner gate preflight refused":
            raise SystemExit("Live v9 planner gate preflight refused") from None
        raise
    finally:
        (
            _v8.OUTPUT_PATH,
            _v8.load_v8_registry,
            _v8.load_v8_selector_registry,
            _v8.v8_preflight,
        ) = original


if __name__ == "__main__":
    raise SystemExit(main())
