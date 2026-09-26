"""Bounded choice interpretation for an already grounded clarification decision."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_CANCEL_WORDS = frozenset(
    {
        "cancel",
        "cancel it",
        "cancel this",
        "cancelar",
        "cancela",
        "cancélalo",
        "never mind",
        "forget it",
        "olvídalo",
        "olvidalo",
        "déjalo",
        "dejalo",
    }
)
_CLASSIFIER_DECISIONS = frozenset({"CANCEL", "NEW_REQUEST", "UNRESOLVED"})


@dataclass(frozen=True, slots=True)
class ClarificationOption:
    """Carry one Core-supplied opaque identity and its user-safe displayed label."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class PendingClarification:
    """Hold one actor/conversation-scoped decision without becoming knowledge authority."""

    original_request: str
    original_request_id: str
    pending_record_id: str
    options: tuple[ClarificationOption, ...]
    evidence_guards: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClarificationChoice:
    """Bind a user's selected stable identity to its canonical revision guard."""

    stable_id: str
    evidence_guard: str


class ClarificationClassifier(Protocol):
    """Classify only among the bounded options and three control outcomes."""

    def classify(
        self, reply: str, original_request: str, options: tuple[ClarificationOption, ...]
    ) -> str:
        """Return one supplied option ID, CANCEL, NEW_REQUEST, or UNRESOLVED."""


class OpenAILunaClarificationClassifier:
    """Classify a reply without giving the model identity or mutation authority."""

    model = "gpt-5.6-luna"
    reasoning_effort = "low"

    def __init__(self) -> None:
        """Keep only bounded telemetry from the most recent classification call."""
        self.last_called = False
        self.last_usage: dict[str, int] | None = None
        self.last_error_category: str | None = None
        self.last_response_id: str | None = None

    def classify(
        self, reply: str, original_request: str, options: tuple[ClarificationOption, ...]
    ) -> str:
        """Return only an allowlisted decision from one strict, non-retried Luna call."""
        self.last_called = False
        self.last_usage = None
        self.last_error_category = None
        self.last_response_id = None
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            self.last_error_category = "MissingCredentials"
            return "UNRESOLVED"
        allowed = [item.id for item in options] + ["CANCEL", "NEW_REQUEST", "UNRESOLVED"]
        payload = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": 128,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Interpret the next message only as a reply to the pending choice. "
                        "Select a supplied option ID only when uniquely intended; CANCEL for an "
                        "explicit cancellation; NEW_REQUEST for a clearly unrelated new request; "
                        "otherwise UNRESOLVED. Never invent an option, identity, or fact."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "original_request": original_request,
                            "reply": reply,
                            "options": [{"id": item.id, "label": item.label} for item in options],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_clarification_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"decision": {"type": "string", "enum": allowed}},
                        "required": ["decision"],
                        "additionalProperties": False,
                    },
                }
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            self.last_called = True
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            from .observability import normalize_provider_usage

            self.last_usage = normalize_provider_usage(body)
            response_id = body.get("id")
            if isinstance(response_id, str) and len(response_id) <= 128:
                self.last_response_id = response_id
            content = next(
                part["text"]
                for item in body["output"]
                if item.get("type") == "message"
                for part in item["content"]
                if part.get("type") == "output_text"
            )
            parsed = json.loads(content)
            if (
                not isinstance(parsed, dict)
                or set(parsed) != {"decision"}
                or parsed["decision"] not in allowed
            ):
                self.last_error_category = "InvalidResponse"
                return "UNRESOLVED"
            return parsed["decision"]
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            StopIteration,
        ) as error:
            self.last_error_category = type(error).__name__
            return "UNRESOLVED"


class LocalClarificationStore:
    """Persist at most one active clarification beneath one isolated conversation root."""

    def __init__(self, root: Path, conversation_id: str) -> None:
        """Bind the store to a trusted actor root and bounded conversation identity."""
        if not isinstance(root, Path) or _SAFE_ID.fullmatch(conversation_id) is None:
            raise ValueError("clarification scope is invalid")
        self._path = root / "clarifications" / f"{conversation_id}.json"

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize read/consume/execute across runtime processes for this conversation."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(".lock")
        if lock_path.is_symlink():
            raise ValueError("clarification lock is invalid")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def read(self) -> PendingClarification | None:
        """Load a validated active decision or return None when no decision is pending."""
        if not self._path.exists():
            return None
        if self._path.is_symlink() or self._path.stat().st_size > 32_768:
            raise ValueError("clarification record is invalid")
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("clarification record is unreadable") from error
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "version",
                "original_request",
                "original_request_id",
                "pending_record_id",
                "options",
                "evidence_guards",
            }
            or payload["version"] != 1
        ):
            raise ValueError("clarification record is invalid")
        if (
            not isinstance(payload["original_request"], str)
            or not payload["original_request"].strip()
            or len(payload["original_request"].encode("utf-8")) > 16_384
            or any(
                not isinstance(payload[key], str) or _SAFE_ID.fullmatch(payload[key]) is None
                for key in ("original_request_id", "pending_record_id")
            )
            or not isinstance(payload["options"], list)
            or not isinstance(payload["evidence_guards"], list)
        ):
            raise ValueError("clarification record is invalid")
        try:
            options = tuple(ClarificationOption(**item) for item in payload["options"])
        except (TypeError, ValueError) as error:
            raise ValueError("clarification options are invalid") from error
        match_clarification_reply("", options)
        guards = tuple(payload["evidence_guards"])
        if len(guards) != len(options) or any(
            not isinstance(guard, str) or re.fullmatch(r"[0-9a-f]{64}", guard) is None
            for guard in guards
        ):
            raise ValueError("clarification evidence guards are invalid")
        return PendingClarification(
            payload["original_request"],
            payload["original_request_id"],
            payload["pending_record_id"],
            options,
            guards,
        )

    def replace(self, pending: PendingClarification) -> None:
        """Atomically replace the sole pending decision after validating its bounded shape."""
        if not isinstance(pending, PendingClarification):
            raise ValueError("clarification record is invalid")
        match_clarification_reply("", pending.options)
        if (
            not pending.original_request.strip()
            or len(pending.original_request.encode("utf-8")) > 16_384
            or any(
                _SAFE_ID.fullmatch(value) is None
                for value in (pending.original_request_id, pending.pending_record_id)
            )
            or len(pending.evidence_guards) != len(pending.options)
            or any(
                re.fullmatch(r"[0-9a-f]{64}", guard) is None for guard in pending.evidence_guards
            )
        ):
            raise ValueError("clarification record is invalid")
        payload = {
            "version": 1,
            "original_request": pending.original_request,
            "original_request_id": pending.original_request_id,
            "pending_record_id": pending.pending_record_id,
            "options": [{"id": item.id, "label": item.label} for item in pending.options],
            "evidence_guards": list(pending.evidence_guards),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 32_768:
            raise ValueError("clarification record is too large")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=self._path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.read()

    def clear(self) -> None:
        """Forget the active decision without touching the immutable pending-work evidence."""
        self._path.unlink(missing_ok=True)


def resolve_clarification_reply(
    reply: str,
    options: tuple[ClarificationOption, ...],
    classifier: ClarificationClassifier | None = None,
    original_request: str = "",
) -> str:
    """Apply deterministic choice, cancellation, then optional bounded classification."""
    selected = match_clarification_reply(reply, options)
    if selected is not None:
        return selected
    if reply.strip().casefold() in _CANCEL_WORDS:
        return "CANCEL"
    if classifier is None:
        return "UNRESOLVED"
    try:
        candidate = classifier.classify(reply, original_request, options)
    except Exception:
        return "UNRESOLVED"
    return (
        candidate
        if candidate in ({option.id for option in options} | _CLASSIFIER_DECISIONS)
        else "UNRESOLVED"
    )


def evidence_digest(markdown: str) -> str:
    """Bind a supplied choice to current canonical Markdown without persisting its content."""
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def match_clarification_reply(reply: str, options: tuple[ClarificationOption, ...]) -> str | None:
    """Choose only a numeric or exact unique displayed option; otherwise stay unresolved.

    Args:
        reply: The next user message, never treated as canonical identity authority.
        options: The complete bounded options previously supplied by Core.

    Returns:
        The selected supplied opaque ID, or ``None`` when no unique decision is proven.

    Raises:
        ValueError: If the purported option set is malformed or has duplicate identities.
    """
    if not isinstance(reply, str) or not isinstance(options, tuple) or not 1 < len(options) <= 4:
        raise ValueError("Clarification reply or option set is invalid")
    if any(
        not isinstance(option, ClarificationOption)
        or not isinstance(option.id, str)
        or not option.id
        or not isinstance(option.label, str)
        or not option.label.strip()
        or len(option.label) > 160
        for option in options
    ) or len({option.id for option in options}) != len(options):
        raise ValueError("Clarification options are invalid")
    normalized = reply.strip()
    if normalized.isascii() and normalized.isdecimal():
        index = int(normalized)
        return options[index - 1].id if 1 <= index <= len(options) else None
    matches = [option.id for option in options if option.label.casefold() == normalized.casefold()]
    return matches[0] if len(matches) == 1 else None


def validate_bounded_classifier_choice(
    proposed_id: str | None, options: tuple[ClarificationOption, ...]
) -> str | None:
    """Constrain any optional language-model classifier to one supplied option or unresolved."""
    if proposed_id is None:
        return None
    return proposed_id if proposed_id in {option.id for option in options} else None
