"""Private stdio endpoint for optional out-of-process local embeddings.

No HTTP server, no note writer, no user IDs, and no network/model downloads.
One JSON request and result per line, in the original input order.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from odyssey_core.semantic import FastEmbedTextEmbedder


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    model_name, cache_root = sys.argv[1:]
    if not Path(cache_root).is_dir():
        return 2
    # A fresh disposable process owns the ONNX weights. When stdin closes or
    # the parent terminates us, the entire model/buffer RSS is reclaimed.
    embedder = FastEmbedTextEmbedder(
        model_name=model_name, cache_dir=Path(cache_root), local_files_only=True
    )
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            mode, texts = request["mode"], request["texts"]
            if (
                mode not in ("documents", "queries")
                or not isinstance(texts, list)
                or not texts
                or not all(isinstance(text, str) for text in texts)
            ):
                return 2
            vectors = (
                embedder.embed_documents(texts)
                if mode == "documents"
                else embedder.embed_queries(texts)
            )
            answer = json.dumps(
                {"vectors": [[float(value) for value in vector] for vector in vectors]},
                separators=(",", ":"),
                allow_nan=False,
            )
            sys.stdout.buffer.write((answer + "\n").encode())
            sys.stdout.buffer.flush()
        except (ValueError, KeyError, TypeError, RuntimeError):
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
