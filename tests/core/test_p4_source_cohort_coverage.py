"""A finite person's source-bound set cannot silently omit explicit names."""

import pytest

from odyssey_core.source_cohort_coverage import (
    SourceCohortCoverageError,
    require_explicit_cohort_coverage,
)


@pytest.mark.parametrize(
    "source, names",
    [
        ("Hoy he conocido a Ana Ejemplo y a Luis Ejemplo.", ("Ana Ejemplo", "Luis Ejemplo")),
        (
            "Ayer conocí a Clara Rivera, Hugo Martín y Nuria Serra.",
            ("Clara Rivera", "Hugo Martín", "Nuria Serra"),
        ),
        ("J'ai rencontré Claire Martin et Hugo Petit.", ("Claire Martin", "Hugo Petit")),
        ("I met Alice Smith and Bob Jones.", ("Alice Smith", "Bob Jones")),
    ],
)
def test_complete_explicit_quoted_set_preserved(source, names):
    require_explicit_cohort_coverage(source, names)


@pytest.mark.parametrize(
    "source, selected",
    [
        ("Hoy he conocido a Ana, a Luis y a Marta.", ("Ana", "Luis")),
        ("Ayer conocí a Ana, Luis y Marta.", ("Ana", "Luis")),
        ("I met Alice, Bob and Charlie.", ("Alice", "Bob")),
        ("Hoy conocí a Ana y Luis. También a Marta.", ("Ana", "Luis")),
    ],
)
def test_unselected_explicit_source_person_vetoes_incomplete_reviews(source, selected):
    with pytest.raises(SourceCohortCoverageError, match="Unreviewed"):
        require_explicit_cohort_coverage(source, selected)


def test_ambiguous_or_overlapping_name_quotes_rejected():
    with pytest.raises(SourceCohortCoverageError):
        require_explicit_cohort_coverage("Vi a Ana y a Ana.", ("Ana", "Luis"))


@pytest.mark.parametrize(
    "source, chosen",
    [
        ("Ana, Luis y Marta.", ("Luis", "Marta")),
        ("Ana y Luis y Marta.", ("Luis", "Marta")),
        ("Hoy he conocido a ana, a luis y a marta.", ("ana", "luis")),
        ("Hoy he conocido a ana, a luis, a marta.", ("ana", "luis")),
        ("Hoy conocí a ana, luis y marta.", ("ana", "marta")),
        ("J'ai rencontré claire, hugo et nuria.", ("claire", "hugo")),
        ("I met alice, bob and charlie.", ("alice", "bob")),
    ],
)
def test_coordinated_source_vetoes_lowercase_and_sentence_initial_omissions(source, chosen):
    with pytest.raises(SourceCohortCoverageError, match="Unreviewed"):
        require_explicit_cohort_coverage(source, chosen)


@pytest.mark.parametrize(
    "source, chosen",
    [
        ("Ana, Luis y Marta.", ("Ana", "Luis", "Marta")),
        ("Hoy he conocido a ana, a luis y a marta.", ("ana", "luis", "marta")),
        ("I met alice, bob and charlie.", ("alice", "bob", "charlie")),
        ("J'ai rencontré claire, hugo et nuria.", ("claire", "hugo", "nuria")),
    ],
)
def test_coordinated_explicit_lists_preserve_every_member(source, chosen):
    require_explicit_cohort_coverage(source, chosen)
