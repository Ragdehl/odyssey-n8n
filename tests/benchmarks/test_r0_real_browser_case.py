"""Provider-free refusal tests for the paid R0 case adapter."""

from __future__ import annotations

import json
import subprocess
import sys

from scripts.odyssey_r0_browser_campaign import frozen_cases


def test_adapter_refuses_before_importing_or_calling_provider_without_transient_approval(tmp_path):
    case = frozen_cases()[0]
    receipt = tmp_path / "F01.json"
    receipt.write_text(
        json.dumps(
            {
                "case": case.id,
                "source_sha256": case.source_sha256,
                "outcome": "armed",
                "reserved_usd": 0.25,
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/odyssey_r0_real_browser_case.py",
            "--case",
            case.id,
            "--source-sha256",
            case.source_sha256,
            "--receipt",
            str(receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    trace = json.loads(completed.stdout.splitlines()[-1])
    assert trace["outcome"] == "failed"
    assert trace["provider_usage"] == []
    assert trace["forensics"]["error"] == "Refused"
