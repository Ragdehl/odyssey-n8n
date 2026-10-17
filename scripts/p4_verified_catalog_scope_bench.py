"""Provider-free multi-lookup benchmark; synthetic canonical Markdown only."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import perf_counter

from odyssey_core.identity import find_exact_entity_candidates_batch
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_metadata_catalog import scoped_verified_metadata_catalog
from tests.core.test_temporal import canonical_note


def main():
    with tempfile.TemporaryDirectory(prefix="odyssey-verified-catalog-") as tmp:
        repo = VaultRepository(tmp)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "config/note-schema.json").read_text()
        )
        for i in range(250):
            repo.create_text(
                f"Person {i:04d}.md",
                canonical_note(
                    note_id=f"person-{i:04d}", note_type="person", name=f"Person {i:04d}"
                ),
            )
        cases = tuple(((f"Person {i * 25:04d}", "person"),) for i in range(10))

        def run(with_catalog):
            calls = [0]
            real = repo.read_text

            def read(path):
                calls[0] += 1
                return real(path)

            repo.read_text = read
            try:
                start = perf_counter()
                with repo.scoped_unchanged_reads():
                    if with_catalog:
                        with scoped_verified_metadata_catalog():
                            result = [
                                find_exact_entity_candidates_batch(repo, schema, q)[0]
                                for q in cases
                            ]
                    else:
                        result = [
                            find_exact_entity_candidates_batch(repo, schema, q)[0] for q in cases
                        ]
                elapsed = round((perf_counter() - start) * 1000, 2)
            finally:
                repo.read_text = real
            assert all(len(item) == 1 for item in result)
            return {"request_catalog": with_catalog, "ms": elapsed, "read_calls": calls[0]}

        a = run(False)
        b = run(True)
        print(json.dumps({"baseline": a, "catalog": b}, ensure_ascii=False))


if __name__ == "__main__":
    main()
