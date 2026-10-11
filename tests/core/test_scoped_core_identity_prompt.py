"""Opt-in Core-proven dependent identity prompt must never leak to other routes."""

from __future__ import annotations

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.experimental_luna_planning import render_luna_experimental_prompt
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA


def test_scoped_core_predecessor_identity_explains_binding_only_when_verified():
    source = "Mañana iré al cine con él."
    day = DomainEvidence("temporal_reference", "Mañana", "2026-10-05")
    canonical = DomainEvidence("canonical_reference", "él", "person:Eric")
    ordinary = DomainInterpretation("temporal", source, "TEMPORAL_RESOLUTION", (day,))
    dependent = DomainInterpretation("temporal", source, "TEMPORAL_RESOLUTION", (day, canonical))

    standard_prompt = render_luna_experimental_prompt(SCHEMA, CLOCK, domain_interpretation=ordinary)
    verified_prompt = render_luna_experimental_prompt(
        SCHEMA, CLOCK, domain_interpretation=dependent
    )
    assert "Core predecessor reference context" not in standard_prompt
    assert "Core predecessor reference context" in verified_prompt
    assert '"source_text":"él","value":"person:Eric"' in verified_prompt
    assert "Never create a person whose name" in verified_prompt
    assert "The subsequent Core prewrite guard" in verified_prompt
    assert "El informe llegó ayer" not in verified_prompt
