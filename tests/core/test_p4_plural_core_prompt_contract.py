"""Core plans distinct physically proved members of one source-bounded Task link set."""

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.request_planning import _render_domain_interpretation_section


def test_multiple_canonical_links_are_each_mandatory_without_copied_ids():
    interp = DomainInterpretation(
        "core",
        "Llamar a los dos",
        "CANONICAL_REFERENCE",
        (
            DomainEvidence("canonical_reference", "los dos", "person:Ana Prototipo"),
            DomainEvidence("canonical_reference", "los dos", "person:Luis Prototipo"),
        ),
    )
    instruction = _render_domain_interpretation_section(interp, semantic_write_mode=True)
    assert "Preserve EACH" in instruction
    assert "SAME source-owned write action" in instruction
    assert "every canonical target" in instruction
    assert "Do not invent Note IDs" in instruction
    assert "person:Ana Prototipo" in instruction
    assert "person:Luis Prototipo" in instruction


def test_one_or_no_canonical_reference_does_not_expand_domain_prompt():
    for evidence in ((), (DomainEvidence("canonical_reference", "ella", "person:Ana"),)):
        interpretation = DomainInterpretation(
            "core", "Llamar a ella", "CANONICAL_REFERENCE", evidence
        )
        result = _render_domain_interpretation_section(interpretation, semantic_write_mode=True)
        assert "SAME source-owned write action" not in result


def test_independent_evidence_never_groups_multiple_actions():
    interpretation = DomainInterpretation(
        "fictional_app",
        "Consultar a Marta y preparar el dossier de Luis.",
        "COMPOSITE",
        (
            DomainEvidence("canonical_reference", "Marta", "person:Marta"),
            DomainEvidence("canonical_reference", "Luis", "person:Luis"),
        ),
    )
    prompt = _render_domain_interpretation_section(interpretation, semantic_write_mode=True)
    assert "SAME source-owned write action" not in prompt
    assert "never split a single shared operation" not in prompt
