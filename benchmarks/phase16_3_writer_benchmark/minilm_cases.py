"""Frozen evaluation wrapper for MiniLM-selected writer context; provider inputs stay label-free."""

from __future__ import annotations

from typing import Any

from benchmarks.phase16_3_writer_benchmark.benchmark import load_cases
from benchmarks.phase16_3_writer_benchmark.supplemental import load_supplemental_cases

_TARGETS = {
    "L01_buried_update_beginning": "- Marta trabaja en Airbus en planificación industrial.",
    "L02_buried_update_middle": "- Nora trabaja en Airbus en planificación industrial.",
    "L03_buried_update_end": "- Diego trabaja en Airbus en planificación industrial.",
    "L04_buried_semantic_duplicate": "- Sara trabaja en Airbus en planificación industrial.",
    "L07_buried_explicit_remove": "- Inés tiene una suscripción a una revista de diseño.",
    "L08_multi_update_and_append": "- Bruno trabaja en Airbus en planificación industrial.",
    "L09_mixed_markdown_distractors": "- Claire travaille chez Airbus en planificación industrial.",
    "L10_es_fr_semantic_duplicate": "- Élodie travaille chez Airbus en planificación industrial.",
    "VL01_very_long_buried_update": "Actualmente, Marta trabaja en Airbus. Esta información laboral es vigente y debe prevalecer sobre menciones históricas a empleadores anteriores.",
    "U04_employer_update": "- Marta trabaja en Airbus.",
    "U05_location_update": "- Marta vive en Toulouse.",
    "U07_negation": "- Nora habla francés.",
    "U08_stopped_habit": "- Diego va al gimnasio tres veces por semana.",
    "U28_french_spanish_update": "- Marta travaille chez Airbus.",
    "U23_multi_update_new": "- Marta vive en Toulouse.",
}


def load_pipeline_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return twelve primary cases and eight frozen adversarial existing-note cases."""
    primary = [_decorate(case) for case in load_supplemental_cases()]
    wanted = {
        "U04_employer_update",
        "U05_location_update",
        "U07_negation",
        "U08_stopped_habit",
        "U15_dog_shelter_independent",
        "U17_airbus_museum_independent",
        "U28_french_spanish_update",
        "U23_multi_update_new",
    }
    extra = [_decorate(case) for case in load_cases() if case["id"] in wanted]
    return primary, extra


def _decorate(case: dict[str, Any]) -> dict[str, Any]:
    """Add runtime identity and evaluation-only target labels without changing frozen source cases."""
    result = dict(case)
    result["identity"] = case["facts"][0].split()[0].rstrip(".")
    result["target_fragment"] = _TARGETS.get(case["id"])
    return result
