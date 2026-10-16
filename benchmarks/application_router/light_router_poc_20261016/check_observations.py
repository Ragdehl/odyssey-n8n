"""Transparent acceptance audit of genuine provider output; never re-labels errors as successes.

Scenario-specific expectations belong in TEST ORACLES only, not production prompts.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent
runs = json.loads((ROOT / "observations.json").read_text())["cases"]
by = {r["case"]: r for r in runs}
assert len(by) == 11 and all(not x["error"] for x in runs)

# Exactly grounded source evidence, no AI-fabricated stable note IDs in the schema.
for row in runs:
    source = row["original_source"]
    for fact in row["shared_plan"]["facts"]:
        assert fact["source_evidence"] in source, (row["case"], fact)
        index = fact["dependent_on_fact_index"]
        assert index is None or 0 <= index < row["shared_plan"]["facts"].index(fact)

oracle = {
    "maya_simple": 1,
    "guillermo_control": 1,
    "children_subject": 3,
    "two_dates": 2,
    "maya_pronoun": 2,
    "ana_luis": 3,
    "maite_cross_app": 2,
    "maite_variant": 2,
    "independent_apps": 2,
    "gender_disambiguated": 2,
    "ambiguous_two_males": 2,
}
assert all(len(by[name]["shared_plan"]["facts"]) == expected for name, expected in oracle.items())
children = by["children_subject"]["shared_plan"]["facts"]
assert all(set(x["participants"]) == {"Cloe", "Bruno"} for x in children)
maya = by["maya_pronoun"]["shared_plan"]["facts"]
assert all("Maya" in f["participants"] for f in maya)
assert [x["date"] for x in maya] == ["2026-10-15", "2026-10-16"]
dates = by["two_dates"]["shared_plan"]["facts"]
assert [x["date"] for x in dates] == ["2026-10-16", "2026-10-17"]
assert [x["date"] for x in by["ana_luis"]["shared_plan"]["facts"]] == [
    "2026-10-16",
    "2026-10-17",
    "2026-10-18",
]
for name in ("maite_cross_app", "maite_variant"):
    row = by[name]
    fact = row["shared_plan"]["facts"]
    assert [f["kind"] for f in fact] == ["record", "task"]
    assert fact[1]["dependent_on_fact_index"] == 0
    assert {"core", "tasks"}.issubset(set(row["router"]["capabilities"]))
    assert row["router"]["interpretation"] == "joint"
assert by["independent_apps"]["router"]["interpretation"] == "separable"
assert by["two_dates"]["shared_plan"]["facts"][1]["kind"] == "record"
assert by["ambiguous_two_males"]["shared_plan"]["facts"][1]["needs_clarification"]
assert by["ambiguous_two_males"]["shared_plan"]["unresolved"]

# Known systematic shortcomings must remain conspicuous and UNRESOLVED:
misrouted = [
    x["case"]
    for x in runs
    if any(f["kind"] == "task" for f in x["shared_plan"]["facts"])
    and "tasks" not in x["router"]["capabilities"]
]
overrouted = [
    x["case"]
    for x in runs
    if "tasks" in x["router"]["capabilities"]
    and not any(f["kind"] == "task" for f in x["shared_plan"]["facts"])
]
assert misrouted == []
assert "two_dates" in overrouted
unverified_names = [
    (row["case"], ent["canonical_name"])
    for row in runs
    for ent in row["shared_plan"]["entities"]
    if ent["canonical_name"]
    and ent["canonical_name"] not in {n["name"] for n in row["known_relevant_notes"]}
    and ent["canonical_name"] not in {x["name"] for x in row["verified_family"]}
]
integration = json.loads((ROOT / "integration_control.json").read_text())["cases"]
assert len(integration) == 3
assert all(not r["readback"] and not r["changes"] for r in integration)
assert all(r["status"] != "completed" for r in integration)
print(
    json.dumps(
        {
            "genuine_llm_semantic_cases": len(runs),
            "expected_fact_counts_checked": len(oracle),
            "correct_shared_children_mentions": True,
            "correct_shared_Maite_dependency": True,
            "ambiguous_two_males_clarification": True,
            "routing_omitted_required_tasks": misrouted,
            "routing_overclassified_tasks": overrouted,
            "unverified_claimed_canonical_names": unverified_names,
            "existing_full_source_writer_succeeded": 0,
            "existing_full_source_writer_attempts": 3,
            "ready_for_DEV": False,
        },
        ensure_ascii=False,
        indent=2,
    )
)
