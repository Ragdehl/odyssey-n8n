"""Exact canonical Day readback permits only Core-added terminal punctuation."""

from __future__ import annotations

import pytest

from odyssey_core.atomic_facts import AtomicFact
from odyssey_core.whole_source_readback import _exact_text


@pytest.mark.parametrize(
    ("actual", "expected", "speaker", "allowed"),
    [
        ("Hoy han venido mis padres.", "Hoy han venido mis padres", False, True),
        (
            "Hoy han venido mis padres (yo: [[self|Persona]]).",
            "Hoy han venido mis padres",
            True,
            True,
        ),
        (
            "Hoy han venido mis padres (yo: [[self|Persona]]).",
            "Hoy han venido mis padres.",
            True,
            True,
        ),
        ("Hoy han venido mis padres y hermanos.", "Hoy han venido mis padres", False, False),
        ("Hoy han venido mis padres..", "Hoy han venido mis padres", False, False),
        ("Hoy han venido mis padres.", "Hoy han venido mis padres?", False, False),
        ("Hoy han venido mis padres.", "Hoy han venido mis padres!", False, False),
    ],
)
def test_day_readback_accepts_only_canonical_final_period(actual, expected, speaker, allowed):
    fact = AtomicFact(actual, "synthetic", 0, 0, len(actual))
    review = {
        "reviewed_text": expected,
        "reference_names": [],
        "kind": "record",
        "date": "2026-10-30",
    }
    assert _exact_text(fact, review, speaker) is allowed
