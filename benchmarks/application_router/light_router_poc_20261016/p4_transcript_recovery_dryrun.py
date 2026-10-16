"""DRY-RUN ONLY; rebuild DEV conversation + exact matched n8n answers IN TEMP CLONE.

No filesystem writing to DEV. Requires operator-supplied private evidence files.
Never log or commit raw user messages or exact retrieved reply text.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from odyssey_core.conversations import ConversationError
from odyssey_core.local_conversations import LocalConversationStore


def main():
    root = Path("/data/odyssey-dev/state/conversations")
    matches = [
        m for m in root.glob("*/main/manifest.json") if json.loads(m.read_text())["turn_count"] > 0
    ]
    if len(matches) != 1:
        raise ValueError("Expected one unambiguous populated DEV conversation")
    manifest_path = matches[0]
    manifest = json.loads(manifest_path.read_text())
    turns = []
    for chunk in manifest["chunks"]:
        doc = json.loads((manifest_path.parent / "chunks" / chunk["name"]).read_text())
        if len(doc["turns"]) != chunk["count"]:
            raise ValueError("Original manifest is inconsistent")
        turns.extend(doc["turns"])
    if len(turns) != manifest["turn_count"]:
        raise ValueError("Original turn count mismatch")
    answer_by_id = {t["request_id"] for t in turns if t["role"] == "assistant"}
    missing_by_id = {
        r["request_id"]: r
        for r in json.loads(Path("/tmp/odyssey-dev-missing-response-ids.json").read_text())
    }
    source_by_id = {t["request_id"]: t for t in turns if t["role"] == "user"}
    recovered = json.loads(Path("/tmp/odyssey-matched-replies-private.json").read_text())
    conflicts = {"e1-progress-gate-b23689b-20261013"}
    suggestions = {}
    rejected = []
    for candidate in recovered:
        rid = candidate["request_id"]
        user = source_by_id.get(rid)
        missing = missing_by_id.get(rid)
        if rid in conflicts or rid in suggestions or rid in answer_by_id or not user or not missing:
            rejected.append((rid, "duplicate/conflict/nonmissing"))
            continue
        if (
            not isinstance(candidate["message"], str)
            or not candidate["message"].strip()
            or not isinstance(candidate.get("status"), str)
            or candidate["status"] not in {"completed", "failed", "partial", "needs_attention"}
            or not isinstance(candidate.get("kind"), str)
            or len(candidate["message"].encode()) > 64 * 1024
            or hashlib.sha256(user["text"].encode()).hexdigest() != missing["source_sha256"]
        ):
            rejected.append((rid, "unsupported or source mismatch"))
            continue
        suggestions[rid] = candidate
    target_count = 50
    if len(suggestions) != target_count:
        raise AssertionError(
            f"Expected {target_count} private matched outputs, got {len(suggestions)}"
        )
    appended = 0
    diagnostic_fallbacks = 0
    chronology = []
    with tempfile.TemporaryDirectory(prefix="odyssey-reply-reconstruction-dryrun-") as tmp:
        replica = LocalConversationStore(Path(tmp) / "main")
        for t in turns:
            kwargs = {
                key: t.get(key) for key in ("request_id", "role", "text", "created_at", "status")
            }
            optional = {
                key: t[key] for key in ("request_detail", "note_result_snapshot") if key in t
            }
            try:
                replica.append_turn(**kwargs, **optional)
            except ConversationError as error:
                # Do not silently discard diagnostic history in a migration.
                raise AssertionError("Existing turn failed canonical reconstruction") from error
            chronology.append((t["role"], t["request_id"]))
            if t["role"] == "user" and t["request_id"] in suggestions:
                candidate = suggestions[t["request_id"]]
                kwargs = {
                    "request_id": t["request_id"],
                    "role": "assistant",
                    "text": candidate["message"],
                    "created_at": t["created_at"],
                    "status": candidate["status"],
                }
                optional = {
                    key: candidate[key]
                    for key in ("request_detail", "note_result_snapshot")
                    if isinstance(candidate.get(key), dict)
                }
                try:
                    replica.append_turn(**kwargs, **optional)
                except ConversationError:
                    replica.append_turn(**kwargs)
                    diagnostic_fallbacks += 1
                chronology.append(("assistant", t["request_id"]))
                appended += 1
        page = replica.load_main_page(limit=40)
        count = replica._manifest()["turn_count"]
        if count != len(turns) + appended:
            raise AssertionError("Unexpected cloned transcript length")
        if len(page["turns"]) != 40:
            raise AssertionError("Last page truncated")
        if not all(replica.has_turn(rid, "assistant") for rid in suggestions):
            raise AssertionError("One or more recoverable replies missing")
        if any(replica.has_turn(rid, "assistant") for rid in conflicts if rid in source_by_id):
            raise AssertionError("Conflicting historical response was incorrectly restored")
        print(
            json.dumps(
                {
                    "dry_run_pass": True,
                    "original_turns": len(turns),
                    "reconstructed_turns": count,
                    "matching_replies_recovered_on_clone": appended,
                    "invalid_diagnostic_fallbacks": diagnostic_fallbacks,
                    "excluded_conflicting_replies": len(rejected),
                    "missing_replies_still_after_dryrun": len(missing_by_id) - appended,
                    "new_browser_page_has_40_turns": len(page["turns"]) == 40,
                    "recent_32_recoverable": sum(
                        rid in suggestions
                        for rid, m in missing_by_id.items()
                        if m["created_at"] >= "2026-10-14"
                    ),
                    "original_dev_files_mutated": False,
                }
            )
        )


if __name__ == "__main__":
    main()
