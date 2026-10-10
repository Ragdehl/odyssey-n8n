"""Versioned pending *source* state beside approved Phase-17B pending plans.

The existing Phase-17B v1 JSON files remain untouched. This v2 sibling is
operational workflow state, not canonical Markdown, a plan, an identity resolver,
or authorization to execute the unfinished source candidate.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .atomic_facts import AtomicFactError, normalize_atomic_fact, parse_atomic_facts
from .candidate_pending_projection import CandidatePendingPreview
from .clarification import (
    _CANCEL_WORDS,
    ClarificationClassifier,
    ClarificationOption,
    resolve_clarification_reply,
)
from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .reference_preflight import (
    ReferencePreflightError,
    _find_existing_identity,
    current_identity_guard,
)
from .storage import VaultRepository

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_GUARD = re.compile(r"[0-9a-f]{64}\Z")
_FORMAT = "odyssey_pending_work"
_VERSION = 2
_MAX_RECORD_BYTES = 65536
_MAX_RECORDS = 500


class CandidatePendingStateError(ValueError):
    """Reject unsafe, stale or conflicting durable candidate workflow state."""


@dataclass(frozen=True, slots=True)
class CandidateReplyResult:
    """Return a bounded decision, without Core-plan or Markdown write authority."""

    outcome: str
    request_id: str | None = None
    selected_note_id: str | None = None
    selected_guard: str | None = None
    pending_source_text: str | None = None
    captured_at: str | None = None
    may_execute: bool = False


class CandidatePendingRepository:
    """Manage v2 candidate-pending records under the existing state/pending root.

    Its v1 sibling, `PendingWorkRepository`, continues to own pending *planned*
    actions. Source-candidate v2 files live beneath the existing
    ``state/pending/candidates/`` subdirectory to avoid changing the v1 list
    and reader contracts; request IDs still correlate both records.
    All file mutations are serialized by one root-local flock; the selected
    answer never becomes an automatic `RequestPlan` or completion receipt.
    """

    def __init__(self, root: Path | str) -> None:
        """Bind to an already existing, root-isolated durable state directory."""
        path = Path(root)
        if not path.is_dir() or path.is_symlink():
            raise CandidatePendingStateError("Pending workflow state root is invalid")
        self._root = path.resolve() / "candidates"
        if self._root.is_symlink():
            raise CandidatePendingStateError("Candidate state root is not trusted")
        self._root.mkdir(mode=0o700, exist_ok=True)

    def _path(self, request_id: str) -> Path:
        """Resolve one contained request ID, never arbitrary filesystem paths."""
        if not isinstance(request_id, str) or _SAFE_ID.fullmatch(request_id) is None:
            raise CandidatePendingStateError("Unsafe candidate pending request ID")
        return self._root / f"{request_id}.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize transitions across processes while excluding symlink locks."""
        lock = self._root / ".candidate-pending.lock"
        if lock.is_symlink():
            raise CandidatePendingStateError("Pending state lock is not trusted")
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self, request_id: str) -> dict[str, Any]:
        """Validate exact v2 durable fields; never parse old v1 as a candidate."""
        path = self._path(request_id)
        if path.is_symlink():
            raise CandidatePendingStateError("Pending record is a symlink")
        try:
            if path.stat().st_size > _MAX_RECORD_BYTES:
                raise CandidatePendingStateError("Pending record exceeds bound")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CandidatePendingStateError("Candidate pending record is unreadable") from error
        self._validate(payload, request_id)
        return payload

    @staticmethod
    def _validate(payload: Any, request_id: str) -> None:
        """Keep replay state closed, bounded, versioned, and source grounded."""
        fields = {
            "format",
            "format_version",
            "request_id",
            "conversation_id",
            "created_at",
            "status",
            "original_request",
            "pending",
            "physically_verified_fact_count",
            "completed_fact_markers",
            "options",
            "selected_note_id",
            "selected_guard",
            "answer_id",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != fields
            or (payload["format"], payload["format_version"], payload["request_id"])
            != (_FORMAT, _VERSION, request_id)
        ):
            raise CandidatePendingStateError("Candidate pending record format mismatch")
        if (
            not isinstance(payload["conversation_id"], str)
            or _SAFE_ID.fullmatch(payload["conversation_id"]) is None
            or not isinstance(payload["created_at"], str)
            or not 1 <= len(payload["created_at"]) <= 64
            or not _valid_capture_time(payload["created_at"])
            or not isinstance(payload["original_request"], str)
            or not payload["original_request"].strip()
            or len(payload["original_request"].encode("utf-8")) > 16384
            or payload["status"] not in {"open", "selected", "cancelled"}
            or not isinstance(payload["physically_verified_fact_count"], int)
            or isinstance(payload["physically_verified_fact_count"], bool)
            or not 0 <= payload["physically_verified_fact_count"] <= 128
        ):
            raise CandidatePendingStateError("Candidate pending metadata invalid")
        markers = payload["completed_fact_markers"]
        if (
            not isinstance(markers, list)
            or len(markers) != payload["physically_verified_fact_count"]
        ):
            raise CandidatePendingStateError("Completed Core fact marker count invalid")
        seen_ordinals: set[int] = set()
        for marker in markers:
            if (
                not isinstance(marker, dict)
                or set(marker) != {"ordinal", "note_id", "fact_digest"}
                or not isinstance(marker["ordinal"], int)
                or isinstance(marker["ordinal"], bool)
                or not 0 <= marker["ordinal"] < 128
                or marker["ordinal"] in seen_ordinals
                or not isinstance(marker["note_id"], str)
                or not 0 < len(marker["note_id"]) <= 256
                or not isinstance(marker["fact_digest"], str)
                or _GUARD.fullmatch(marker["fact_digest"]) is None
            ):
                raise CandidatePendingStateError("Completed Core fact provenance invalid")
            seen_ordinals.add(marker["ordinal"])
        pending = payload["pending"]
        if not isinstance(pending, list) or not 1 <= len(pending) <= 26:
            raise CandidatePendingStateError("Candidate pending source count invalid")
        seen: set[str] = set()
        for item in pending:
            if not isinstance(item, dict) or set(item) != {
                "id",
                "start",
                "end",
                "text",
                "reason",
                "reference_text",
                "reference_start",
                "reference_end",
            }:
                raise CandidatePendingStateError("Candidate pending source shape invalid")
            start, end, text = item["start"], item["end"], item["text"]
            if (
                not isinstance(item["id"], str)
                or re.fullmatch(r"candidate-[1-9]\d*", item["id"]) is None
                or item["id"] in seen
                or not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or not 0 <= start < end <= len(payload["original_request"])
                or payload["original_request"][start:end] != text
                or item["reason"]
                not in {
                    "ambiguous_identity",
                    "needs_clarification",
                    "needs_capability",
                    "unsupported_scope",
                }
            ):
                raise CandidatePendingStateError("Candidate pending source is not grounded")
            reference_text = item["reference_text"]
            if reference_text is None:
                if item["reference_start"] is not None or item["reference_end"] is not None:
                    raise CandidatePendingStateError("Pending reference offsets lack text")
            else:
                ref_start, ref_end = item["reference_start"], item["reference_end"]
                if (
                    not isinstance(reference_text, str)
                    or not isinstance(ref_start, int)
                    or isinstance(ref_start, bool)
                    or not isinstance(ref_end, int)
                    or isinstance(ref_end, bool)
                    or not start <= ref_start < ref_end <= end
                    or payload["original_request"][ref_start:ref_end] != reference_text
                ):
                    raise CandidatePendingStateError("Pending reference has no exact source span")
            seen.add(item["id"])
        options = payload["options"]
        if not isinstance(options, list) or len(options) > 4:
            raise CandidatePendingStateError("Candidate option count invalid")
        option_ids: set[str] = set()
        for item in options:
            if (
                not isinstance(item, dict)
                or set(item) != {"id", "label", "guard"}
                or (
                    not isinstance(item["id"], str)
                    or not item["id"]
                    or not isinstance(item["label"], str)
                    or not 0 < len(item["label"]) <= 160
                    or not isinstance(item["guard"], str)
                    or _GUARD.fullmatch(item["guard"]) is None
                    or item["id"] in option_ids
                )
            ):
                raise CandidatePendingStateError("Candidate option is invalid")
            option_ids.add(item["id"])
        if options and (
            len(options) < 2 or len(pending) != 1 or pending[0]["reason"] != "ambiguous_identity"
        ):
            raise CandidatePendingStateError("Multiple pending facts cannot own one scalar choice")
        selected, guard, answer_id = (
            payload[key] for key in ("selected_note_id", "selected_guard", "answer_id")
        )
        if payload["status"] == "selected":
            if (
                selected not in option_ids
                or not isinstance(guard, str)
                or _GUARD.fullmatch(guard) is None
                or not isinstance(answer_id, str)
                or _SAFE_ID.fullmatch(answer_id) is None
                or not any(o["id"] == selected and o["guard"] == guard for o in options)
            ):
                raise CandidatePendingStateError("Selected choice lacks original identity evidence")
        elif any(value is not None for value in (selected, guard, answer_id)):
            raise CandidatePendingStateError("Pending state carries an unexpected choice")

    def _write(self, payload: dict[str, Any], *, exclusive: bool) -> None:
        """Use one same-root fsynced temporary and an atomic publish operation."""
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        if len(encoded) > _MAX_RECORD_BYTES:
            raise CandidatePendingStateError("Candidate pending record is too large")
        path = self._path(payload["request_id"])
        if path.is_symlink():
            raise CandidatePendingStateError("Pending record symlink is forbidden")
        fd, name = tempfile.mkstemp(prefix=".candidate-", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive:
                os.link(name, path)
            else:
                os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def record(
        self,
        preview: CandidatePendingPreview,
        *,
        conversation_id: str,
        created_at: str,
        options: tuple[ClarificationOption, ...] = (),
        vault: VaultRepository | None = None,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Persist source-only pending work without ever constructing a Core plan.

        An optional, Core-supplied choice set requires current canonical
        identity guards at time of record; provider/Router guesses are not IDs.
        """
        if (
            not isinstance(preview, CandidatePendingPreview)
            or preview.persisted
            or preview.resumable
            or preview.candidate_semantics_verified
            or not isinstance(conversation_id, str)
            or _SAFE_ID.fullmatch(conversation_id) is None
            or not isinstance(options, tuple)
        ):
            raise CandidatePendingStateError(
                "Only untrusted source preview can become pending state"
            )
        if options:
            if not isinstance(vault, VaultRepository) or not isinstance(schema, dict):
                raise CandidatePendingStateError("Canonical evidence required for choice options")
            if len(preview.pending) != 1 or preview.pending[0].reason != "ambiguous_identity":
                raise CandidatePendingStateError("Choice options require one ambiguous source")
        guarded = []
        for option in options:
            if not isinstance(option, ClarificationOption):
                raise CandidatePendingStateError("Option must be Core-owned")
            try:
                guard = current_identity_guard(vault, schema, option.id)
                _path, canonical_name = _find_existing_identity(vault, schema, option.id)
                if option.label.casefold() != canonical_name.casefold():
                    raise CandidatePendingStateError("Choice label differs from canonical name")
            except (ReferencePreflightError, ValueError, OSError) as error:
                raise CandidatePendingStateError("Canonical option evidence unavailable") from error
            guarded.append({"id": option.id, "label": option.label, "guard": guard})
        payload = {
            "format": _FORMAT,
            "format_version": _VERSION,
            "request_id": preview.request_id,
            "conversation_id": conversation_id,
            "created_at": created_at,
            "status": "open",
            "original_request": preview.original_request,
            "pending": [
                {
                    "id": i.candidate_id,
                    "start": i.source_start,
                    "end": i.source_end,
                    "text": i.source_text,
                    "reason": i.reason,
                    "reference_text": i.reference_text,
                    "reference_start": i.reference_start,
                    "reference_end": i.reference_end,
                }
                for i in preview.pending
            ],
            "physically_verified_fact_count": preview.physically_verified_fact_count,
            "completed_fact_markers": [
                {"ordinal": ordinal, "note_id": note_id, "fact_digest": fact_digest}
                for ordinal, note_id, fact_digest in preview.completed_fact_markers
            ],
            "options": guarded,
            "selected_note_id": None,
            "selected_guard": None,
            "answer_id": None,
        }
        self._validate(payload, preview.request_id)
        with self._locked():
            try:
                existing = self._read(preview.request_id)
            except CandidatePendingStateError:
                if self._path(preview.request_id).exists():
                    raise
            else:
                # Creation time is not semantic evidence on an exact same-request
                # replay. Refuse to reset selected/cancelled workflow state.
                old = {key: value for key, value in existing.items() if key != "created_at"}
                new = {key: value for key, value in payload.items() if key != "created_at"}
                if old != new:
                    raise CandidatePendingStateError(
                        "Request ID already has different pending state"
                    )
                return preview.request_id
            if len(tuple(self._root.glob("*.json"))) >= _MAX_RECORDS:
                raise CandidatePendingStateError("Pending root requires capacity review")
            try:
                self._write(payload, exclusive=True)
            except FileExistsError as error:
                raise CandidatePendingStateError("Request ID already exists") from error
        return preview.request_id

    def read(self, request_id: str) -> dict[str, Any]:
        """Read one validated source pending workflow record, not a knowledge note."""
        return self._read(request_id)

    def open_requests(self, conversation_id: str) -> tuple[str, ...]:
        """Find only v2 open records in one trusted conversation, never other actors."""
        if not isinstance(conversation_id, str) or _SAFE_ID.fullmatch(conversation_id) is None:
            raise CandidatePendingStateError("Conversation ID invalid")
        matches: list[str] = []
        paths = tuple(self._root.glob("*.json"))
        if len(paths) > _MAX_RECORDS:
            raise CandidatePendingStateError("Pending root exceeds capacity budget")
        for path in paths:
            if path.is_symlink():
                raise CandidatePendingStateError("Untrusted pending state path")
            try:
                record = self._read(path.stem)
            except CandidatePendingStateError as error:
                # Version 1 planned-action records share this directory and
                # must remain managed exclusively by the Phase-17B reader.
                try:
                    if path.stat().st_size > _MAX_RECORD_BYTES:
                        raise error
                    header = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError) as inner:
                    raise CandidatePendingStateError(
                        "Invalid pending state in shared root"
                    ) from inner
                if (
                    isinstance(header, dict)
                    and header.get("format_version") == 1
                    and header.get("format") == _FORMAT
                ):
                    continue
                raise
            if record["conversation_id"] == conversation_id and record["status"] == "open":
                matches.append(record["request_id"])
        return tuple(sorted(matches))

    @staticmethod
    def _completed_facts_still_valid(
        record: dict[str, Any], vault: VaultRepository, schema: dict[str, Any]
    ) -> bool:
        """Require all previously stored Core markers before accepting a reply.

        An edited/removed fact must not be treated as a reason to re-execute
        the *whole* original request or silently double-create its content.
        """
        markers = record["completed_fact_markers"]
        if not markers:
            return True
        if len(markers) > 128:
            return False
        observed: dict[tuple[int, str], list[str]] = {
            (marker["ordinal"], marker["note_id"]): [] for marker in markers
        }
        counts: dict[str, int] = {}
        paths = vault.list_markdown_paths()
        if len(paths) > 5000:
            return False
        for path in paths:
            try:
                note = parse_note(vault.read_text(path))
                validate_note(note, schema)
            except (NoteFormatError, NoteValidationError, OSError, ValueError):
                continue
            stable_id = note.metadata.get("id")
            if not isinstance(stable_id, str) or not any(
                marker["note_id"] == stable_id for marker in markers
            ):
                continue
            counts[stable_id] = counts.get(stable_id, 0) + 1
            try:
                facts = parse_atomic_facts(note.content)
            except (AtomicFactError, ValueError):
                continue
            for fact in facts:
                if fact.request_id != record["request_id"]:
                    continue
                key = (fact.ordinal, stable_id)
                if key in observed:
                    observed[key].append(
                        hashlib.sha256(normalize_atomic_fact(fact.text).encode("utf-8")).hexdigest()
                    )
        return all(
            counts.get(marker["note_id"]) == 1
            and observed[(marker["ordinal"], marker["note_id"])] == [marker["fact_digest"]]
            for marker in markers
        )

    def selected_for_core_review(
        self,
        *,
        conversation_id: str,
        request_id: str,
        vault: VaultRepository,
        schema: dict[str, Any],
    ) -> CandidateReplyResult:
        """Revalidate a stored choice before a *separate* Core semantic review.

        This is neither a normalized event nor an executable `RequestPlan`;
        original captured time is returned so relative dates are not silently
        interpreted against the follow-up's later wall-clock day.
        """
        with self._locked():
            record = self._read(request_id)
            if record["conversation_id"] != conversation_id or record["status"] != "selected":
                return CandidateReplyResult("unavailable", request_id)
            chosen = record["selected_note_id"]
            try:
                current = current_identity_guard(vault, schema, chosen)
            except (ReferencePreflightError, ValueError, OSError):
                return CandidateReplyResult("stale_choice", request_id)
            if current != record["selected_guard"]:
                return CandidateReplyResult("stale_choice", request_id)
            if not self._completed_facts_still_valid(record, vault, schema):
                return CandidateReplyResult("stale_written_facts", request_id)
            return CandidateReplyResult(
                "choice_ready_for_core_review",
                request_id,
                chosen,
                current,
                record["pending"][0]["text"],
                record["created_at"],
            )

    def reply(
        self,
        *,
        conversation_id: str,
        reply: str,
        answer_id: str,
        vault: VaultRepository,
        schema: dict[str, Any],
        immediate_followup: bool,
        request_id: str | None = None,
        classifier: ClarificationClassifier | None = None,
    ) -> CandidateReplyResult:
        """Handle bounded user choice/cancel without re-executing earlier writes.

        Implicit replies are allowed only for a trusted immediately preceding
        clarification, and only when precisely one request is open. A separate
        conversation, unrelated turn, or multiple open requests must provide
        an explicit pending request ID. No user reply executes a plan here.
        """
        if (
            not isinstance(reply, str)
            or not reply.strip()
            or not isinstance(answer_id, str)
            or _SAFE_ID.fullmatch(answer_id) is None
            or not isinstance(vault, VaultRepository)
            or not isinstance(schema, dict)
        ):
            raise CandidatePendingStateError("Bounded continuation inputs required")
        with self._locked():
            open_ids = self.open_requests(conversation_id)
            if request_id is None:
                if not immediate_followup:
                    return CandidateReplyResult("explicit_request_required")
                if len(open_ids) != 1:
                    return CandidateReplyResult("multiple_or_no_pending")
                request_id = open_ids[0]
            if request_id not in open_ids:
                try:
                    existing = self._read(request_id)
                except CandidatePendingStateError:
                    return CandidateReplyResult("unavailable")
                if existing["conversation_id"] != conversation_id:
                    return CandidateReplyResult("unavailable")
                if existing["status"] == "selected" and existing["answer_id"] == answer_id:
                    return CandidateReplyResult("already_selected", request_id)
                if existing["status"] == "selected" and reply.strip().casefold() in _CANCEL_WORDS:
                    cancelled = {
                        **existing,
                        "status": "cancelled",
                        "selected_note_id": None,
                        "selected_guard": None,
                        "answer_id": None,
                    }
                    self._validate(cancelled, request_id)
                    self._write(cancelled, exclusive=False)
                    return CandidateReplyResult("cancelled", request_id)
                return CandidateReplyResult("already_closed", request_id)
            record = self._read(request_id)
            options = tuple(ClarificationOption(o["id"], o["label"]) for o in record["options"])
            if not options and reply.strip().casefold() in _CANCEL_WORDS:
                updated = {**record, "status": "cancelled"}
                self._validate(updated, request_id)
                self._write(updated, exclusive=False)
                return CandidateReplyResult("cancelled", request_id)
            if not options:
                return CandidateReplyResult("needs_core_options", request_id)
            # Accept only an exact preposition plus one option label, never
            # open-ended free-text coreference or compound participant lists.
            trimmed = reply.strip()
            lowered = trimmed.casefold()
            for prefix in ("con ", "avec "):
                if lowered.startswith(prefix):
                    trimmed = trimmed[len(prefix) :].strip()
                    break
            decision = resolve_clarification_reply(
                trimmed, options, classifier=classifier, original_request=record["original_request"]
            )
            if decision == "UNRESOLVED":
                return CandidateReplyResult("unresolved", request_id)
            if decision == "NEW_REQUEST":
                return CandidateReplyResult("new_request", request_id)
            if decision == "CANCEL":
                updated = {**record, "status": "cancelled"}
                self._validate(updated, request_id)
                self._write(updated, exclusive=False)
                return CandidateReplyResult("cancelled", request_id)
            selected = next((o for o in record["options"] if o["id"] == decision), None)
            if selected is None:
                return CandidateReplyResult("unresolved", request_id)
            try:
                current = current_identity_guard(vault, schema, selected["id"])
            except (ReferencePreflightError, ValueError, OSError):
                return CandidateReplyResult("stale_choice", request_id)
            if current != selected["guard"]:
                return CandidateReplyResult("stale_choice", request_id)
            if not self._completed_facts_still_valid(record, vault, schema):
                return CandidateReplyResult("stale_written_facts", request_id)
            updated = {
                **record,
                "status": "selected",
                "selected_note_id": selected["id"],
                "selected_guard": current,
                "answer_id": answer_id,
            }
            self._validate(updated, request_id)
            self._write(updated, exclusive=False)
            return CandidateReplyResult(
                "choice_recorded",
                request_id,
                selected["id"],
                current,
                record["pending"][0]["text"],
                record["created_at"],
            )


def _valid_capture_time(value: str) -> bool:
    """Require an explicit offset so resumed 'mañana' keeps its original day."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None
