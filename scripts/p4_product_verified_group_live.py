"""One real-model end-to-end Core group expansion over synthetic family only.

No actual Odyssey note, user, identity, browser or n8n access. The model
proposes a relation span; trusted Core proves it from a self-owned canonical
Markdown fact before source interpretation and rechecks it before writing.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from odyssey_core.notes import parse_note
from tests.runtime.test_p4_verified_group_e2 import _family


def main():
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Synthetic GPT provider execution requires opt-in")
    with tempfile.TemporaryDirectory(prefix="p4-real-family-") as tmp:
        repo, actor, service, runtime = _family(Path(tmp))
        service.client = OpenAI(max_retries=0, timeout=80)
        try:
            result = runtime.execute_product(
                "Mis hijos comieron helado hoy.", "family-live", "main", actor
            )
            facts = []
            for path in repo.list_markdown_paths():
                note = parse_note(repo.read_text(path))
                if "odyssey:fact request=family-live" in note.content:
                    facts.append(
                        {
                            "type": note.metadata["type"],
                            "canonical_links": sum(
                                name in note.content for name in ("[[Cloe", "[[Bruno")
                            ),
                            "has_source_fact": True,
                        }
                    )
            accepted = (
                result["status"] == "completed"
                and len(facts) == 1
                and facts[0]["canonical_links"] == 2
                and len(
                    [
                        p
                        for p in repo.list_markdown_paths()
                        if parse_note(repo.read_text(p)).metadata["type"] == "person"
                    ]
                )
                == 3
            )
            replay = runtime.execute_product(
                "Mis hijos comieron helado hoy.", "family-live", "main", actor
            )
            accepted = accepted and replay.get("delivery_replayed") is True
            print(
                json.dumps(
                    {
                        "accepted": accepted,
                        "status": result["status"],
                        "facts": facts,
                        "replay": replay.get("delivery_replayed"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 0 if accepted else 1
        except Exception as exc:
            print(json.dumps({"accepted": False, "error_type": type(exc).__name__}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
