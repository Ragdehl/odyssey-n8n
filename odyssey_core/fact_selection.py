"""Bounded model selection of an existing marked atomic fact locator."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Protocol

FACT_SELECTOR_MODEL = "gpt-5.6-luna"
FACT_SELECTOR_REASONING_EFFORT = "medium"


class FactSelectionError(RuntimeError):
    """Indicate an unusable bounded atomic-fact selector result."""


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """Expose one validated existing atomic fact to the bounded selector."""

    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class FactSelection:
    """Represent a validated MATCH, NO_MATCH, or AMBIGUOUS selector outcome."""

    outcome: str
    locator: str | None = None


class AtomicFactSelector(Protocol):
    """Select one existing fact from supplied candidates without body-edit authority."""

    def select(
        self, note_id: str, description: str, candidates: tuple[FactCandidate, ...]
    ) -> object:
        """Return an untrusted structured result for the bounded candidate set."""


class OpenAILunaFactSelector:
    """Call Luna only to choose one supplied atomic-fact locator."""

    def select(
        self, note_id: str, description: str, candidates: tuple[FactCandidate, ...]
    ) -> object:
        """Return raw strict JSON selector output for one resolved note and candidate list."""
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise FactSelectionError("OPENAI_API_KEY is required for fact selection")
        payload = {
            "model": FACT_SELECTOR_MODEL,
            "store": False,
            "reasoning": {"effort": FACT_SELECTOR_REASONING_EFFORT},
            "input": [
                {
                    "role": "system",
                    "content": "Select only one supplied atomic fact locator. Return MATCH only for one candidate, otherwise NO_MATCH or AMBIGUOUS. Never return Markdown, edits, metadata, or prose.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "note_id": note_id,
                            "description": description,
                            "candidates": [asdict(candidate) for candidate in candidates],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_fact_selection",
                    "strict": True,
                    "schema": fact_selection_schema(),
                }
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode())
            text = next(
                content["text"]
                for item in body["output"]
                if item.get("type") == "message"
                for content in item["content"]
                if content.get("type") == "output_text"
            )
            return json.loads(text)
        except (
            urllib.error.URLError,
            TimeoutError,
            KeyError,
            StopIteration,
            json.JSONDecodeError,
        ) as error:
            raise FactSelectionError("Fact selector provider response was unusable") from error


def fact_selection_schema() -> dict[str, Any]:
    """Return the closed Structured Output schema for bounded locator selection."""
    return {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["MATCH", "NO_MATCH", "AMBIGUOUS"]},
            "locator": {"type": ["string", "null"]},
        },
        "required": ["outcome", "locator"],
        "additionalProperties": False,
    }


def validate_fact_selection(value: object, candidates: tuple[FactCandidate, ...]) -> FactSelection:
    """Validate that a MATCH selects exactly one supplied locator and nothing else."""
    if not isinstance(value, dict) or set(value) != {"outcome", "locator"}:
        raise FactSelectionError("Fact selector output schema is invalid")
    outcome, locator = value["outcome"], value["locator"]
    if outcome not in {"MATCH", "NO_MATCH", "AMBIGUOUS"}:
        raise FactSelectionError("Fact selector outcome is invalid")
    if outcome == "MATCH" and (
        not isinstance(locator, str)
        or locator not in {candidate.locator for candidate in candidates}
    ):
        raise FactSelectionError("Fact selector chose an unknown locator")
    if outcome != "MATCH" and locator is not None:
        raise FactSelectionError("Non-match selector output must not contain a locator")
    return FactSelection(outcome, locator)
