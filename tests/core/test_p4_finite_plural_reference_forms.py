"""E2 closed-class plural numerals cannot silently choose subset of Persons."""

import pytest

from odyssey_core.dependent_reference_form import (
    referenced_finite_cardinality,
    supported_anaphoric_form,
)


@pytest.mark.parametrize(
    "mention, cardinal",
    [
        ("a los dos", 2),
        ("a ambos", 2),
        ("à les deux", 2),
        ("to the two", 2),
        ("los dos", 2),
        ("las dos", 2),
        ("ambos", 2),
        ("ambas", 2),
        ("les deux", 2),
        ("the two", 2),
        ("both", 2),
        ("los tres", 3),
        ("les quatre", 4),
        ("the five", 5),
        ("los ocho", 8),
    ],
)
def test_closed_cardinal_anaphora_is_typed_not_names(mention, cardinal):
    assert referenced_finite_cardinality(mention) == cardinal
    assert supported_anaphoric_form(mention)


@pytest.mark.parametrize(
    "mention",
    [
        "Juan",
        "Ana y Luis",
        "lxs dos",
        "los veinte",
        "los 2",
        "los ocho y medio",
        "mis amigos",
        "todos los alumnos",
        "los nueve",
        "las Ana",
        "los Luis",
        "la dos",
        "los tres personas",
        "los DOS de Ana",
        " ambos ",
    ],
)
def test_unproven_arbitrary_names_and_open_group_are_not_cardinal_anaphora(mention):
    assert referenced_finite_cardinality(mention) is None
    assert not supported_anaphoric_form(mention)
