#!/usr/bin/env python3
"""Fail-closed R0 browser campaign controller; provider-free unless explicitly armed.

This is intentionally a controller, not another Odyssey execution path.  A
case adapter must drive the existing isolated E4 Chromium -> throwaway n8n ->
runtime bridge and print one JSON object on stdout.  This controller freezes
the corpus input, budget, per-case vault/actor isolation evidence and durable
resume state around that adapter.

It never reads credentials, starts Docker, contacts OpenAI, Cloudflare, DEV or
PROD.  The paid adapter is deliberately external and must be invoked via the
approved transient systemd EnvironmentFile method described in
``odyssey-live-provider``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/full_message_corpus_v1/manifest.json"
DESIGN = ROOT / "benchmarks/application_router/fact_units_v2.design.json"
ADDITIONAL = ROOT / "tests/fixtures/odyssey_additional_regressions_v1.json"
# Immutable acceptance baseline. Appending R31+ is allowed; silently editing,
# removing or rewriting any prior source is not. These are test-data hashes,
# NEVER branches in the Odyssey runtime/semantic interpreter.
ORIGINAL_SOURCE_DIGEST = "350424ac788725911fe2c309ac1d0a90d6cbd3881f625f311280aed833bb8241"
ORIGINAL_ORACLE_DIGEST = "666a048dd0a4baf25ce8a0bdf9d54b30e2fbc79519d5cea3266d881f53f82008"
ADDITIONAL_ORACLE_PREFIX = (
    "0f45aa8764a0d6c06b38dedf543a16c23d7ad7985f1ef5654796d1d1148ef5bd",
    "0f15452efeb9388dec5a826177e0fb3953fdfb7e0312d8ddb40355e1c0439fd0",
    "ad33bfa516108c7884574d882ca2f155a8b43eb74be3bdd56d5219269086177a",
    "55580aa9fe058a789e0fcb0ce2bbdbe7bf8d00675f85c2fd8841b226cdbb91bd",
)


def _stable_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


ADDITIONAL_SOURCE_PREFIX = (
    "e107fe15284565462a40867437b32f3f8c0ed9eefdd7b7dc67d68ab4d5cecce3",
    "adcaf7b78d6c92e1169e335a486ef2e502f4ded4e74c884ae820aa3958763c48",
    "3453a74012626729a444323b7b4ce6d597c18eb8190e821bad4953d76da16769",
    "2c020f4d91a26cf1ab373cf2cf4fd899765c95a3a9d33986513dd8217bd538cb",
)


def verify_source_anchors(original_rows: list[dict], additional_rows: list[dict]) -> None:
    digest = hashlib.sha256(
        json.dumps(
            [(row["id"], row["source"]) for row in original_rows],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    extra_hashes = tuple(
        hashlib.sha256(row["source"].encode("utf-8")).hexdigest() for row in additional_rows
    )
    # Freeze the *meaning* of the oracle too. Otherwise an old test could be
    # made green by deleting expected facts while preserving its source text.
    unit_oracle = _stable_digest([(row["id"], row["expected_units"]) for row in original_rows])
    extra_oracles = tuple(
        _stable_digest(
            {
                key: row.get(key)
                for key in (
                    "id",
                    "source",
                    "expectation",
                    "offline_coverage",
                    "fixture_setup",
                    "expected_units",
                )
            }
        )
        for row in additional_rows
    )
    if (
        digest != ORIGINAL_SOURCE_DIGEST
        or unit_oracle != ORIGINAL_ORACLE_DIGEST
        or extra_hashes[: len(ADDITIONAL_SOURCE_PREFIX)] != ADDITIONAL_SOURCE_PREFIX
        or extra_oracles[: len(ADDITIONAL_ORACLE_PREFIX)] != ADDITIONAL_ORACLE_PREFIX
    ):
        raise CampaignError("Frozen 27-message sources or accepted additional prefix changed")
    if len(extra_hashes) < len(ADDITIONAL_SOURCE_PREFIX):
        raise CampaignError("Previously added regressions were removed")


SCHEMA = "odyssey-r0-browser-campaign-v1"
APPROVAL_FLAG = "ODYSSEY_R0_LIVE_APPROVED"
# The supplied history says five fresh calls were made for F11 but lacks an
# invoice/usage receipt.  Charge a deliberately larger fixed reserve, rather
# than treating that attempt as free or guessing an exact historical price.
PRIOR_UNCERTAIN_RESERVE_USD = 0.25
DEFAULT_CAP_USD = 2.00
DEFAULT_CASE_RESERVE_USD = 0.25


class CampaignError(ValueError):
    """A campaign cannot safely arm or accept the supplied evidence."""


@dataclass(frozen=True)
class Case:
    id: str
    source: str

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()


def frozen_cases() -> tuple[Case, ...]:
    """Load exactly the committed 27 original sources, rejecting drift."""
    manifest = json.loads(CORPUS.read_text(encoding="utf-8"))
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    expected = [f"F{i:02d}" for i in range(1, 28)]
    if (
        manifest.get("version") != 1
        or manifest.get("case_ids") != expected
        or manifest.get("case_design") != "benchmarks/application_router/fact_units_v2.design.json"
        or not isinstance(design.get("cases"), list)
        or [item.get("id") for item in design["cases"]] != expected
    ):
        raise CampaignError("R0 corpus manifest/design is not the immutable 27-case contract")
    # The original corpus is frozen independently from the extendable set.
    verify_source_anchors(
        design["cases"], json.loads(ADDITIONAL.read_text(encoding="utf-8"))["cases"]
    )
    cases = tuple(Case(item["id"], item["source"]) for item in design["cases"])
    if any(not case.source.strip() for case in cases):
        raise CampaignError("R0 corpus has an empty original source")
    return cases


def valid_fixture_setup(steps: object) -> bool:
    """Check test prerequisites before arming billable provider calls."""
    if not isinstance(steps, list) or len(steps) > 6:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        if step.get("kind") == "replace_self_facts":
            facts = step.get("facts")
            if (
                set(step) != {"kind", "facts"}
                or not isinstance(facts, list)
                or not 1 <= len(facts) <= 8
                or any(
                    not isinstance(f, str) or not f.endswith(".") or not 1 <= len(f) <= 180
                    for f in facts
                )
            ):
                return False
        elif step.get("kind") == "create_task":
            name, id_, path = step.get("name"), step.get("id"), step.get("path")
            if (
                set(step) != {"kind", "name", "id", "path"}
                or not isinstance(name, str)
                or not 1 <= len(name) <= 120
                or not isinstance(id_, str)
                or not id_.startswith("synthetic-")
                or not isinstance(path, str)
                or path != name + ".md"
                or "/" in path
                or "\\" in path
                or ".." in path
            ):
                return False
        else:
            return False
    return True


def additional_cases() -> tuple[Case, ...]:
    """Independent append-only real-journey regressions after the original 27."""
    value = json.loads(ADDITIONAL.read_text(encoding="utf-8"))
    rows = value.get("cases")
    if (
        value.get("schema") != "odyssey-additional-regressions-v1"
        or not isinstance(rows, list)
        or not rows
    ):
        raise CampaignError("Additional regression catalog missing or empty")
    ids = [f"R{i:02d}" for i in range(28, 28 + len(rows))]
    if [row.get("id") for row in rows if isinstance(row, dict)] != ids:
        raise CampaignError("Additional regressions must be append-only and sequential")
    if any(
        not isinstance(row.get("source"), str)
        or not row["source"].strip()
        or not isinstance(row.get("expectation"), str)
        or not row["expectation"].strip()
        or row.get("live_acceptance") != "pending"
        or not valid_fixture_setup(row.get("fixture_setup"))
        or not isinstance(row.get("expected_units"), list)
        or not row["expected_units"]
        or any(
            not isinstance(unit, dict)
            or unit.get("state") not in {"candidate", "ambiguous_identity"}
            or not isinstance(unit.get("reading"), str)
            or not unit["reading"].strip()
            or not isinstance(unit.get("source_anchors"), list)
            or not unit["source_anchors"]
            or any(
                not isinstance(anchor, str) or anchor not in row["source"]
                for anchor in unit["source_anchors"]
            )
            for unit in row["expected_units"]
        )
        or not isinstance(row.get("offline_coverage"), str)
        or not row["offline_coverage"].startswith("tests/")
        or not (ROOT / row["offline_coverage"]).is_file()
        for row in rows
    ):
        raise CampaignError("Additional regressions require a grounded test and expected behavior")
    verify_source_anchors(json.loads(DESIGN.read_text(encoding="utf-8"))["cases"], rows)
    return tuple(Case(row["id"], row["source"]) for row in rows)


def campaign_cases() -> tuple[Case, ...]:
    return (*frozen_cases(), *additional_cases())


def _money(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise CampaignError(f"Invalid {field}")
    return round(float(value), 8)


def receipt_path(receipts: Path, case: Case) -> Path:
    return receipts / f"{case.id}.json"


def _read_receipt(path: Path, case: Case) -> dict[str, Any]:
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CampaignError(f"Unreadable receipt for {case.id}") from error
    if (
        not isinstance(item, dict)
        or item.get("schema") != SCHEMA
        or item.get("case") != case.id
        or item.get("source_sha256") != case.source_sha256
    ):
        raise CampaignError(f"Receipt source identity mismatch for {case.id}")
    return item


def accounted_spend(receipts: Path, cases: Iterable[Case]) -> float:
    """Charge every armed attempt before a new provider invocation.

    An interrupted/unknown attempt has already consumed its entire reservation.
    This is intentionally conservative and makes a missing usage response stop
    the campaign rather than create an unaccounted retry.
    """
    total = PRIOR_UNCERTAIN_RESERVE_USD
    known = {case.id: case for case in cases}
    if not receipts.exists():
        return total
    for path in receipts.glob("*.json"):
        if path.stem not in known:
            raise CampaignError("Unknown receipt in R0 campaign directory")
        item = _read_receipt(path, known[path.stem])
        reserved = _money(item.get("reserved_usd"), "reserved_usd")
        charged = item.get("charged_usd", reserved)
        charged = _money(charged, "charged_usd")
        # An adapter may report usage-derived cost only when it can prove it;
        # otherwise the preflight reservation remains charged.
        if item.get("usage_complete") is not True:
            charged = reserved
        if charged > reserved:
            raise CampaignError("Receipt charges more than its preflight reservation")
        total += charged
    return round(total, 8)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def arm_case(receipts: Path, case: Case, reserve_usd: float) -> Path:
    """Durably reserve a fresh isolated attempt before launching its adapter."""
    target = receipt_path(receipts, case)
    if target.exists():
        raise CampaignError(f"Case {case.id} already has a durable receipt; never silently retry")
    _atomic_json(
        target,
        {
            "schema": SCHEMA,
            "case": case.id,
            "source_sha256": case.source_sha256,
            "fixture_manifest_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "reserved_usd": reserve_usd,
            "charged_usd": reserve_usd,
            "usage_complete": False,
            "outcome": "armed",
        },
    )
    return target


def validate_adapter_trace(trace: object, case: Case) -> dict[str, Any]:
    """Accept only an observed isolated visible-browser trace, never a claim alone."""
    if not isinstance(trace, dict):
        raise CampaignError("Case adapter did not emit a JSON object")
    required_true = {
        "visible_ui_submitted",
        "real_n8n_single_throwaway_container",
        "isolated_actor_vault",
        "fresh_vault_per_case",
        "original_fixture_13_notes",
        "fixed_original_clock",
        "source_preserved",
        "markdown_source_readback",
        "ui_reload_readback",
        "replay_checked",
        "cloudflare_public_access_used",
    }
    if trace.get("case") != case.id or trace.get("source_sha256") != case.source_sha256:
        raise CampaignError("Adapter trace does not belong to the armed original source")
    # A failed adapter MUST retain its forensic trace. Requiring successful
    # n8n/Markdown evidence on a failed attempt hides the actual first blocker
    # and turns a one-off paid failure into an unrepeatable opaque error.
    if trace.get("outcome") == "failed":
        return trace
    if trace.get("cloudflare_public_access_used") is not False:
        raise CampaignError("R0 isolated harness must not use external Cloudflare Access")
    if any(trace.get(key) is not True for key in required_true - {"cloudflare_public_access_used"}):
        raise CampaignError("Adapter trace lacks required browser/n8n/vault readback evidence")
    outcome = trace.get("outcome")
    if outcome not in {"passed", "deferred", "failed"}:
        raise CampaignError("Adapter outcome must be passed, deferred, or failed")
    usage = trace.get("provider_usage")
    if not isinstance(usage, list) or not usage:
        raise CampaignError("Live adapter trace has no provider usage evidence")
    if any(not isinstance(row, dict) or not isinstance(row.get("model"), str) for row in usage):
        raise CampaignError("Provider usage entries are incomplete")
    return trace


def run_case_adapter(command: list[str], case: Case, receipt: Path) -> dict[str, Any]:
    """Run an explicitly supplied adapter without shell interpolation or retries."""
    completed = subprocess.run(
        [
            *command,
            "--case",
            case.id,
            "--source-sha256",
            case.source_sha256,
            "--receipt",
            str(receipt),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=600,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise CampaignError("Case adapter emitted no trace")
    try:
        trace = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise CampaignError("Case adapter final line is not JSON") from error
    if completed.returncode:
        raise CampaignError(
            f"Case adapter failed before a valid trace (exit {completed.returncode})"
        )
    return validate_adapter_trace(trace, case)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument(
        "--case", action="append", dest="case_ids", choices=[x.id for x in campaign_cases()]
    )
    parser.add_argument(
        "--live", action="store_true", help="arm and invoke an external approved case adapter"
    )
    parser.add_argument(
        "--case-command", nargs="+", help="external case adapter argv; never evaluated by a shell"
    )
    parser.add_argument("--cap-usd", type=float, default=DEFAULT_CAP_USD)
    parser.add_argument("--case-reserve-usd", type=float, default=DEFAULT_CASE_RESERVE_USD)
    args = parser.parse_args()
    cases = campaign_cases()
    selected = [case for case in cases if not args.case_ids or case.id in args.case_ids]
    total = accounted_spend(args.receipts, cases)
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "offline",
                    "cases": [x.id for x in selected],
                    "provider_calls": 0,
                    "prior_reserved_usd": PRIOR_UNCERTAIN_RESERVE_USD,
                    "accounted_usd": total,
                    "remaining_usd": round(args.cap_usd - total, 8),
                }
            )
        )
        return 0
    if os.environ.get(APPROVAL_FLAG) != "1":
        raise CampaignError("Live R0 campaign requires its explicit approval flag")
    if not args.case_command:
        raise CampaignError("Live R0 campaign requires an explicit isolated browser case adapter")
    reserve = _money(args.case_reserve_usd, "case_reserve_usd")
    cap = _money(args.cap_usd, "cap_usd")
    results = []
    for case in selected:
        if total + reserve > cap:
            results.append({"case": case.id, "outcome": "pending", "reason": "budget_cap"})
            continue
        path = arm_case(args.receipts, case, reserve)
        try:
            trace = run_case_adapter(args.case_command, case, path)
            stored = _read_receipt(path, case)
            stored.update({"outcome": trace["outcome"], "trace": trace})
            _atomic_json(path, stored)
            results.append({"case": case.id, "outcome": trace["outcome"]})
        except Exception as error:
            stored = _read_receipt(path, case)
            stored.update({"outcome": "failed", "controller_error": str(error)[:200]})
            _atomic_json(path, stored)
            results.append({"case": case.id, "outcome": "failed", "reason": type(error).__name__})
        total = accounted_spend(args.receipts, cases)
    print(
        json.dumps(
            {
                "mode": "live",
                "results": results,
                "accounted_usd": total,
                "remaining_usd": round(cap - total, 8),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CampaignError as error:
        print("R0_CAMPAIGN_REFUSED: " + str(error), file=sys.stderr)
        sys.exit(2)
