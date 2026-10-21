"""Model campaign oracles must reject duplicate/missing targets and mutated replay."""

from types import SimpleNamespace

from scripts.odyssey_e4_plural_model_campaign import (
    inspect_physical_cohort,
    replay_is_exact,
)


def item(kind, name, note_id, content=""):
    return SimpleNamespace(metadata={"type": kind, "name": name, "id": note_id}, content=content)


def inventory():
    return {
        "self.md": item("person", "Persona local", "self-1"),
        "people/ana.md": item("person", "Ana", "ana-1"),
        "people/luis.md": item("person", "Luis", "luis-1"),
        "tasks/call.md": item(
            "task",
            "Llamar a los dos",
            "task-1",
            "Llamar a [[people/ana|Ana]] y [[people/luis|Luis]].",
        ),
    }


def test_exact_cohort_is_valid_only_with_all_canonical_person_links():
    x = inspect_physical_cohort(inventory(), ("Ana", "Luis"), expect_task=True)
    assert x["accepted"] and x["persons"] == 2 and x["links_complete"]


def test_duplicate_person_cannot_replace_an_omitted_member():
    x = inventory()
    x["people/luis.md"] = item("person", "Ana", "ana-2")
    result = inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=True)
    assert not result["accepted"] and not result["inventory_complete"]


def test_duplicate_id_and_extra_person_are_not_accepted():
    x = inventory()
    x["people/luis.md"].metadata["id"] = "ana-1"
    assert not inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=True)["accepted"]
    y = inventory()
    y["people/marta.md"] = item("person", "Marta", "marta-1")
    assert not inspect_physical_cohort(y, ("Ana", "Luis"), expect_task=True)["accepted"]


def test_missing_link_or_repeated_link_never_counts_as_complete():
    x = inventory()
    x["tasks/call.md"].content = "Llamar a [[people/ana|Ana]]"
    assert not inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=True)["accepted"]
    x["tasks/call.md"].content = "[[people/ana|Ana]] [[people/ana|Ana]] [[people/luis|Luis]]"
    assert not inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=True)["accepted"]


def test_ambiguous_negative_cannot_leave_person_or_task_write():
    x = {"self.md": item("person", "Persona local", "self-1")}
    assert inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=False)["accepted"]
    x["people/ana.md"] = item("person", "Ana", "ana-1")
    assert not inspect_physical_cohort(x, ("Ana", "Luis"), expect_task=False)["accepted"]


def test_replayed_flag_without_identical_markdown_bytes_is_not_success():
    original = {"a.md": b"first", "b.md": b"second"}
    assert replay_is_exact(original, dict(original), {"delivery_replayed": True})
    assert not replay_is_exact(
        original, {"a.md": b"mutated", "b.md": b"second"}, {"delivery_replayed": True}
    )
    assert not replay_is_exact(original, dict(original), {"delivery_replayed": False})
