"""Frozen synthetic long-note cases for the Luna-only Phase 16.3 follow-up."""

from __future__ import annotations

from typing import Any

from benchmarks.phase16_3_writer_benchmark.benchmark import BenchmarkContractError


def _facts(person: str) -> list[str]:
    """Return fifty realistic, distinct factual units for one synthetic person note."""
    return [
        f"- {person} vive en Toulouse desde 2016.",
        f"- {person} trabaja en Airbus en planificación industrial.",
        f"- {person} colabora con el equipo de seguridad de la planta.",
        f"- {person} va a la oficina en bicicleta tres días por semana.",
        f"- {person} habla español y francés con fluidez.",
        f"- {person} practica italiano con una vecina los jueves.",
        f"- {person} tiene un perro llamado Sol.",
        f"- {person} pasea a Sol junto al canal los domingos.",
        f"- {person} dona comida una vez al trimestre al refugio municipal.",
        f"- {person} hace voluntariado en la biblioteca del barrio.",
        f"- {person} tiene una hermana que vive en Zaragoza.",
        f"- {person} visita a su padre en Bilbao cada otoño.",
        f"- {person} prefiere el té verde por la mañana.",
        f"- {person} cocina paella para amistades el último sábado del mes.",
        f"- {person} cultiva tomates, menta y romero en el balcón.",
        f"- {person} compra verduras en el mercado de Saint-Cyprien.",
        f"- {person} corre cinco kilómetros los miércoles.",
        f"- {person} nada los martes en la piscina municipal.",
        f"- {person} hace fotografías de arquitectura industrial.",
        f"- {person} colecciona mapas de ciudades portuarias.",
        f"- {person} lee novela histórica antes de dormir.",
        f"- {person} escucha jazz mientras trabaja desde casa.",
        f"- {person} toca el piano en clases semanales.",
        f"- {person} usa un cuaderno azul para ideas de viajes.",
        f"- {person} viajó a Oporto en abril de 2025.",
        f"- {person} quiere visitar Nantes en tren este otoño.",
        f"- {person} conserva una bicicleta roja para excursiones.",
        f"- {person} compró una cámara analógica en 2024.",
        f"- {person} prepara un proyecto de huerto comunitario.",
        f"- {person} coordina las reuniones del proyecto los lunes.",
        f"- {person} trabaja con Léa en el presupuesto del huerto.",
        f"- {person} prefiere reuniones cortas por la mañana.",
        f"- {person} tiene una suscripción a una revista de diseño.",
        f"- {person} estudia historia local de Toulouse.",
        f"- {person} visita museos pequeños durante los viajes.",
        f"- {person} compra postales para su sobrina Emma.",
        f"- {person} usa gafas para leer por la noche.",
        f"- {person} reserva agosto para vacaciones familiares.",
        f"- {person} trabaja desde casa los viernes.",
        f"- {person} aprende a reparar muebles sencillos.",
        f"- {person} tiene una planta de limón en la cocina.",
        f"- {person} prepara sopa de verduras los domingos.",
        f"- {person} prefiere trenes nocturnos para viajes largos.",
        f"- {person} mantiene contacto con colegas de Renault.",
        f"- {person} participó en una conferencia en Lyon en 2023.",
        f"- {person} guarda recibos de compras grandes en una carpeta.",
        f"- {person} considera aprender alemán el próximo año.",
        f"- {person} tiene una tarifa mensual de transporte público.",
        f"- {person} se reúne con amistades para cenar los viernes.",
        f"- {person} evita programar trabajo después de las 19:00.",
    ]


def _long_prose(person: str, *, employer: str, include_independent: bool) -> str:
    """Build a 1,500–3,000-word factual profile with varied, meaningful detail."""
    paragraphs = []
    topics = [
        (
            "Trabajo",
            "coordina revisiones de producción",
            "comparte el seguimiento con equipos de calidad",
        ),
        ("Familia", "llama a su hermana cada domingo", "prepara viajes para ver a sus sobrinos"),
        ("Idiomas", "practica francés en reuniones", "anota expresiones italianas en una libreta"),
        ("Movilidad", "prefiere desplazarse en tren", "compara horarios antes de reservar"),
        ("Hogar", "cuida plantas aromáticas", "repara pequeños muebles cuando puede"),
        ("Cocina", "elige productos de temporada", "comparte recetas con amistades"),
        ("Deporte", "nada temprano los martes", "sale a correr cerca del canal"),
        ("Lecturas", "lee ensayos de historia urbana", "guarda recomendaciones de librerías"),
        (
            "Fotografía",
            "fotografía puentes y fábricas",
            "clasifica negativos al volver de un viaje",
        ),
        (
            "Viajes",
            "visita barrios fuera de las rutas principales",
            "lleva un cuaderno para apuntar detalles",
        ),
    ]
    for index in range(1, 10):
        sentences = []
        for topic, action, detail in topics:
            sentences.append(
                f"En {topic.lower()}, {person} {action} durante el ciclo {index} y {detail}; "
                f"este hábito le ayuda a organizar decisiones concretas sin sustituir otros compromisos."
            )
        paragraphs.append(" ".join(sentences))
    middle = (
        f"Actualmente, {person} trabaja en {employer}. Esta información laboral es vigente y "
        "debe prevalecer sobre menciones históricas a empleadores anteriores."
    )
    paragraphs.insert(5, middle)
    paragraphs.append(
        f"{person} tiene un perro llamado Sol, hace voluntariado en una asociación local, dona comida "
        "a un refugio municipal y participa en campañas de adopción responsables. Estas actividades "
        "están relacionadas, pero cada una describe una acción distinta y no debe reemplazarse por otra."
    )
    if include_independent:
        paragraphs.append(
            f"{person} está valorando aprender cerámica en un taller del barrio. Esta posibilidad no "
            "cambia sus actividades de voluntariado, sus donaciones ni el cuidado de Sol."
        )
    return "# Perfil de " + person + "\n\n" + "\n\n".join(paragraphs)


def load_supplemental_cases() -> list[dict[str, Any]]:
    """Return the twelve predeclared long-context mutation cases without provider-dependent changes."""
    cases: list[dict[str, Any]] = []
    labels = [
        (
            "L01_buried_update_beginning",
            "Marta",
            "Marta trabaja en Thales desde enero.",
            ["REPLACE"],
            2,
            "beginning",
        ),
        (
            "L02_buried_update_middle",
            "Nora",
            "Nora trabaja en Thales desde enero.",
            ["REPLACE"],
            24,
            "25_percent",
        ),
        (
            "L03_buried_update_end",
            "Diego",
            "Diego trabaja en Thales desde enero.",
            ["REPLACE"],
            45,
            "near_end",
        ),
        (
            "L04_buried_semantic_duplicate",
            "Sara",
            "Sara es empleada de Airbus en planificación industrial.",
            ["NO_CHANGE"],
            30,
            "50_percent",
        ),
        (
            "L05_independent_fact",
            "Lucía",
            "Lucía ha empezado clases de cerámica los sábados.",
            ["APPEND"],
            40,
            "75_percent",
        ),
        (
            "L06_same_vocabulary_independent",
            "Pablo",
            "Pablo visita el museo de Airbus con su sobrino en verano.",
            ["APPEND"],
            18,
            "25_percent",
        ),
        (
            "L07_buried_explicit_remove",
            "Inés",
            "Elimina que Inés tiene una suscripción a una revista de diseño.",
            ["REMOVE"],
            33,
            "50_percent",
        ),
        (
            "L08_multi_update_and_append",
            "Bruno",
            "Bruno trabaja en Thales desde enero.",
            ["REPLACE", "APPEND"],
            10,
            "beginning",
        ),
        (
            "L09_mixed_markdown_distractors",
            "Claire",
            "Claire travaille chez Thales depuis janvier.",
            ["REPLACE"],
            36,
            "75_percent",
        ),
        (
            "L10_es_fr_semantic_duplicate",
            "Élodie",
            "Élodie trabaja en Airbus en planificación industrial.",
            ["NO_CHANGE"],
            25,
            "50_percent",
        ),
    ]
    for case_id, person, fact, expected, target, position in labels:
        body_facts = _facts(person)
        old = body_facts[1]
        body_facts.insert(target, body_facts.pop(1))
        body = "\n".join(body_facts)
        facts = [fact]
        if case_id == "L08_multi_update_and_append":
            facts.append("Bruno ha empezado clases de cerámica los sábados.")
        if case_id == "L09_mixed_markdown_distractors":
            body = (
                "# Claire\n\n## Travail\n\n"
                + body.replace("Claire trabaja", "Claire travaille").replace(
                    "en Airbus", "chez Airbus"
                )
                + "\n\n## Notes\n\nClaire prépare ses voyages en train."
            )
            old = "- Claire travaille chez Airbus en planificación industrial."
        if case_id == "L10_es_fr_semantic_duplicate":
            body = body.replace("Élodie trabaja", "Élodie travaille").replace(
                "en Airbus", "chez Airbus"
            )
        cases.append(
            {
                "id": case_id,
                "mode": "UPDATE",
                "note_type": "person",
                "intent": "amend"
                if "update" in case_id
                or case_id in {"L08_multi_update_and_append", "L09_mixed_markdown_distractors"}
                else ("remove" if "remove" in case_id else "record"),
                "facts": facts,
                "current_body": body,
                "expected_families": expected,
                "factual_unit_count": 50,
                "target_old": old,
                "target_position": position,
                "reduced_context": "\n".join(
                    [
                        old,
                        body_facts[max(0, target - 1)],
                        body_facts[min(len(body_facts) - 1, target + 1)],
                    ]
                )
                if case_id not in {"L04_buried_semantic_duplicate", "L10_es_fr_semantic_duplicate"}
                else body,
            }
        )
    for case_id, person, fact, expected, independent in [
        (
            "VL01_very_long_buried_update",
            "Marta",
            "Marta trabaja en Thales desde enero.",
            ["REPLACE"],
            False,
        ),
        (
            "VL02_very_long_related_independent",
            "Nora",
            "Nora organiza paseos mensuales para perros adoptados.",
            ["APPEND"],
            True,
        ),
    ]:
        body = _long_prose(person, employer="Airbus", include_independent=independent)
        old = f"Actualmente, {person} trabaja en Airbus."
        cases.append(
            {
                "id": case_id,
                "mode": "UPDATE",
                "note_type": "person",
                "intent": "amend" if not independent else "record",
                "facts": [fact],
                "current_body": body,
                "expected_families": expected,
                "factual_unit_count": 90,
                "target_old": old if not independent else None,
                "target_position": "final_third" if not independent else "near_end",
                "word_count": len(body.split()),
                "reduced_context": old + "\n\n" + body.split("\n\n")[-1],
            }
        )
    # The eight selected contexts are frozen before execution. Other cases remain full-note only
    # so the comparison is representative rather than a universal fragment assumption.
    reduced_ids = {
        "L01_buried_update_beginning",
        "L02_buried_update_middle",
        "L04_buried_semantic_duplicate",
        "L06_same_vocabulary_independent",
        "L08_multi_update_and_append",
        "L09_mixed_markdown_distractors",
        "VL01_very_long_buried_update",
        "VL02_very_long_related_independent",
    }
    for case in cases:
        if case["id"] not in reduced_ids:
            case.pop("reduced_context", None)
    _validate(cases)
    return cases


def _validate(cases: list[dict[str, Any]]) -> None:
    """Reject accidental drift from the frozen supplemental coverage contract."""
    if len(cases) != 12 or len({case["id"] for case in cases}) != 12:
        raise BenchmarkContractError("Supplemental suite requires twelve unique cases")
    factual = [case for case in cases if case["id"].startswith("L")]
    if len(factual) < 8 or not all(40 <= case["factual_unit_count"] <= 60 for case in factual[:8]):
        raise BenchmarkContractError("Supplemental suite lacks 40–60 fact coverage")
    very_long = [case for case in cases if case["id"].startswith("VL")]
    if len(very_long) != 2 or not all(1500 <= case["word_count"] <= 3000 for case in very_long):
        raise BenchmarkContractError("Supplemental suite lacks genuine very-long notes")
    probes = [case for case in cases if "reduced_context" in case]
    if len(probes) != 8 or not all(isinstance(case["reduced_context"], str) for case in probes):
        raise BenchmarkContractError("Supplemental reduced contexts must be frozen")
