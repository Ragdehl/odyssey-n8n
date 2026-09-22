"""Authorization gate for a future isolated-DEV P1 baseline executor.

The network executor and reviewed per-case envelopes must be supplied after P1A review. This
entry point deliberately cannot make provider calls from the contract branch alone.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from .runner import CaseResult


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Require explicit human live-call confirmation and one new evidence path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.add_argument("--evidence-path", required=True, type=Path)
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    executor: Callable[[dict], CaseResult] | None = None,
) -> int:
    """Fail closed until a reviewed isolated-DEV executor and cost envelopes are wired."""
    args = parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if args.evidence_path.exists():
        raise SystemExit("Refusing to overwrite existing P1 evidence")
    if executor is None:
        raise SystemExit("P1 live executor and verified request envelopes are not configured")
    raise SystemExit("P1 live executor wiring requires reviewed envelope configuration")


if __name__ == "__main__":
    raise SystemExit(main())
