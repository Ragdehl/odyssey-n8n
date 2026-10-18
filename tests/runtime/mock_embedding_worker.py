"""Fake local embedding worker used by subprocess boundary tests (no ONNX)."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # Even a local child must not inherit cloud API credentials.
    if "OPENAI_API_KEY" in os.environ or "TEST_PASSWORD" in os.environ:
        return 7
    for line in sys.stdin:
        request = json.loads(line)
        texts = request["texts"]
        if "FAIL_WORKER" in texts:
            return 8
        vectors = [[float(len(text)), float(sum(map(ord, text)) % 1000 + 1)] for text in texts]
        sys.stdout.write(json.dumps({"vectors": vectors}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
