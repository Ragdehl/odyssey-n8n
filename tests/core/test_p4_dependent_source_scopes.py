"""Generic E2 byte ownership of an explicitly dependent Core→Tasks pair."""

from __future__ import annotations

import pytest

from odyssey_core.dependent_source_scopes import (
    DependentSourceScopesError,
    verify_dependent_source_scopes,
)

SOURCE = "Hoy hablé de Informe Atlas. Luego inicia sesión en esa tarea."
BEFORE = "Hoy hablé de Informe Atlas."
AFTER = " Luego inicia sesión en esa tarea."
PROPOSAL = {
    "full_source_quote": SOURCE,
    "antecedent_quote": BEFORE,
    "dependent_quote": AFTER,
    "dependent_mention": "esa tarea",
}


def test_valid_exact_unmodified_whole_source_is_only_provenance_not_authority():
    proof = verify_dependent_source_scopes(SOURCE, PROPOSAL)
    assert proof.original == proof.antecedent + proof.dependent
    assert proof.mention == "esa tarea"
    assert not hasattr(proof, "canonical_note_id")
    assert not hasattr(proof, "write")


@pytest.mark.parametrize(
    "changes",
    [
        {"full_source_quote": SOURCE + " Extra"},
        {"antecedent_quote": BEFORE[:-1]},
        {"dependent_quote": AFTER.lstrip().replace("inicia", "termina")},
        {"dependent_quote": AFTER + " y otra cosa"},
        {"dependent_mention": "otra tarea"},
        {"dependent_mention": ""},
        {"extra_identity": "task-stable-id"},
        {"antecedent_quote": ""},
        {"dependent_quote": ""},
        {"antecedent_quote": AFTER, "dependent_quote": BEFORE},
    ],
)
def test_missing_overlapping_invented_or_reordered_source_is_rejected(changes):
    with pytest.raises(DependentSourceScopesError):
        verify_dependent_source_scopes(SOURCE, PROPOSAL | changes)


def test_only_missing_boundary_whitespace_is_restored_from_source():
    proof = verify_dependent_source_scopes(SOURCE, PROPOSAL | {"dependent_quote": AFTER.lstrip()})
    assert proof.dependent == AFTER
    assert proof.antecedent + proof.dependent == SOURCE


def test_repeated_dependent_reference_does_not_select_first_occurrence():
    after = " La revisé en esa tarea y después volví a esa tarea."
    source = BEFORE + after
    with pytest.raises(DependentSourceScopesError):
        verify_dependent_source_scopes(
            source,
            {
                "full_source_quote": source,
                "antecedent_quote": BEFORE,
                "dependent_quote": after,
                "dependent_mention": "esa tarea",
            },
        )


@pytest.mark.parametrize("original", ["", " ", "a" * 4097, None, 55])
def test_invalid_original_is_rejected(original):
    with pytest.raises(DependentSourceScopesError):
        verify_dependent_source_scopes(original, PROPOSAL)


def test_distinct_languages_and_no_string_heuristics():
    for before, after, mention in (
        ("Je me suis occupé de tâche Alpha.", " Continue-la maintenant.", "la"),
        ("I reviewed Atlas today.", " Start working on that task.", "that task"),
        ("Hablé de Atlas.", " Empieza con esa tarea.", "esa tarea"),
    ):
        whole = before + after
        result = verify_dependent_source_scopes(
            whole,
            {
                "full_source_quote": whole,
                "antecedent_quote": before,
                "dependent_quote": after,
                "dependent_mention": mention,
            },
        )
        assert result.original == whole
