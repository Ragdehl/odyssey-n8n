# Phase 14 retrieval-plan benchmark summary

Run: `20260820T_PHASE14_INITIAL`
Original experiment Git SHA: `e51f92bec959a017ad8c4e904c4dc321ba0a68d7`
Evaluator version: `2.1.0`
Evaluator source Git SHA: `90faa5106d0cb0e17722b7bc75aafb41deff857b`
Raw API results: unchanged from the historical v1 run; zero additional API requests.
Fixed context: `{"current_date": "2026-08-20", "current_time": "10:30", "timezone": "Europe/Madrid"}`

## Configuration overview

| Model | Effort | Tests | Critical | Major | Minor | Semantic review | Repeat stability | Avg latency | Tokens | Cost already spent |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | none | 45/45 | 4 | 6 | 3 | 3 | not repeated | 1.695s | 104687 | $0.007947 |
| `gpt-5.6-luna` | low | 45/45 | 3 | 5 | 2 | 4 | 7/17 stable | 2.202s | 228180 | $0.021060 |
| `gpt-5.6-terra` | low | 45/45 | 0 | 4 | 1 | 7 | not repeated | 1.676s | 104238 | $0.068979 |
| `gpt-5.6-sol` | low | 45/45 | 0 | 1 | 0 | 4 | 42/45 stable | 2.817s | 422761 | $0.838557 |

API failures are reported separately and are not counted as model-quality failures.
Total measured API usage: 366 requests; $0.936543380 estimated.

## Per-test comparison

| Test | gpt-5.6-luna/none | gpt-5.6-luna/low | gpt-5.6-terra/low | gpt-5.6-sol/low |
| --- | --- | --- | --- | --- |
| T01 | PASS | PASS | PASS | PASS |
| T02 | MINOR | MAJOR | PASS | PASS |
| T03 | CRITICAL | CRITICAL | HUMAN REVIEW | PASS |
| T04 | PASS | PASS | PASS | PASS |
| T05 | PASS | PASS | PASS | PASS |
| T06 | PASS | PASS | PASS | PASS |
| T07 | PASS | PASS | PASS | PASS |
| T08 | PASS | PASS | PASS | PASS |
| T09 | PASS | PASS | PASS | PASS |
| T10 | PASS | PASS | PASS | PASS |
| T11 | PASS | PASS | PASS | PASS |
| T12 | PASS | PASS | PASS | PASS |
| T13 | PASS | PASS | PASS | PASS |
| T14 | CRITICAL | CRITICAL | PASS | PASS |
| T15 | PASS | PASS | HUMAN REVIEW | PASS |
| T16 | PASS | PASS | PASS | PASS |
| T17 | PASS | PASS | PASS | PASS |
| T18 | MAJOR | MINOR | PASS | PASS |
| T19 | PASS | PASS | PASS | PASS |
| T20 | PASS | PASS | PASS | PASS |
| T21 | MINOR | MINOR | PASS | PASS |
| T22 | MAJOR | MAJOR | MAJOR | MAJOR |
| T23 | PASS | PASS | PASS | PASS |
| T24 | CRITICAL | CRITICAL | HUMAN REVIEW | PASS |
| T25 | PASS | PASS | PASS | PASS |
| T26 | PASS | PASS | PASS | PASS |
| T27 | MAJOR | PASS | PASS | PASS |
| T28 | PASS | PASS | HUMAN REVIEW | PASS |
| T29 | PASS | PASS | MINOR | PASS |
| T30 | PASS | PASS | PASS | PASS |
| T31 | PASS | PASS | PASS | PASS |
| T32 | PASS | PASS | PASS | PASS |
| T33 | PASS | PASS | PASS | PASS |
| T34 | PASS | PASS | PASS | PASS |
| T35 | MAJOR | MAJOR | MAJOR | PASS |
| T36 | PASS | PASS | PASS | PASS |
| T37 | MINOR | PASS | PASS | PASS |
| T38 | PASS | PASS | PASS | PASS |
| T39 | HUMAN REVIEW | HUMAN REVIEW | HUMAN REVIEW | HUMAN REVIEW |
| T40 | CRITICAL | PASS | HUMAN REVIEW | PASS |
| T41 | PASS | PASS | PASS | PASS |
| T42 | MAJOR | MAJOR | MAJOR | PASS |
| T43 | MAJOR | MAJOR | MAJOR | PASS |
| T44 | PASS | PASS | PASS | PASS |
| T45 | PASS | PASS | PASS | PASS |

## Critical and major differences

### T02

Question:

¿Qué ideas había tenido para Odyssey y para reformar la cocina?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [
    "idea"
  ],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "cocina",
      "reformar la cocina",
      "reforma de la cocina"
    ]
  ],
  "unrepresented_groups": []
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"ideas que había tenido para Odyssey y para reformar la cocina","type":null,"required_tags":["idea"],"filters":[]},"unrepresented_constraints":["La solicitud pide dos temas independientes (Odyssey y reformar la cocina); no se puede representar una condición OR entre ambos temas en un único filtro determinista."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"ideas que había tenido para Odyssey y para reformar la cocina","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos temas independientes (Odyssey y reformar la cocina) y pide ideas para ambos; no se puede representar como una sola consulta con una condición OR o como ramas independientes."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"Odyssey y reformar la cocina","type":null,"required_tags":["idea"],"filters":[]},"unrepresented_constraints":[]}`

gpt-5.6-sol/low:

`{"plan":{"query":"Odyssey y reformar la cocina","type":null,"required_tags":["idea"],"filters":[]},"unrepresented_constraints":[]}`

Why a result is unsafe or inferior:

Safe requested deterministic tags were omitted: ['idea']

### T03

Question:

¿Qué decisiones tomé sobre Odyssey y n8n en julio de 2026?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [
    "decision"
  ],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "n8n"
    ],
    [
      "julio",
      "2026-07"
    ]
  ],
  "unrepresented_groups": [
    [
      "decision",
      "fecha"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"decisiones que tomé sobre Odyssey y n8n en julio de 2026","type":null,"required_tags":["decision"],"filters":[{"field":"created_at","op":"gte","value":"2026-07-01T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-01T00:00:00+02:00"}]},"unrepresented_constraints":["La fecha en que se tomó una decisión no tiene un campo disponible; se usa el período de creación de la nota como aproximación segura."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"decisiones que tomé sobre Odyssey y n8n en julio de 2026","type":null,"required_tags":["decision"],"filters":[{"field":"created_at","op":"gte","value":"2026-07-01T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-01T00:00:00+02:00"}]},"unrepresented_constraints":["La fecha de toma de una decisión no está representada por ningún campo disponible; el intervalo aplicado corresponde a la creación de la nota en Odyssey."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"Odyssey y n8n","type":null,"required_tags":["decision"],"filters":[]},"unrepresented_constraints":["Las decisiones tomadas en julio de 2026 no pueden filtrarse por fecha porque no existe un campo de fecha de decisión."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"decisiones que tomé sobre Odyssey y n8n en julio de 2026","type":null,"required_tags":["decision"],"filters":[]},"unrepresented_constraints":["La fecha en que se tomó la decisión debe estar en julio de 2026, pero no existe un campo de fecha de decisión."]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['julio', '2026-07'] was not found in generated query 'Odyssey y n8n'; Unjustified hard filter can reduce recall (1x): ('created_at', 'gte', '2026-07-01T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('created_at', 'lt', '2026-08-01T00:00:00+02:00')

### T14

Question:

¿Qué compras hice en julio en Carrefour y Lidl?

Expected safe behavior:

```json
{
  "types": [
    "purchase"
  ],
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "carrefour"
    ],
    [
      "lidl"
    ],
    [
      "julio",
      "2026-07"
    ]
  ],
  "unrepresented_groups": [
    [
      "compra",
      "fecha"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"compras hechas en julio en Carrefour y Lidl","type":"purchase","required_tags":[],"filters":[{"field":"created_at","op":"gte","value":"2026-07-01T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-01T00:00:00+02:00"}]},"unrepresented_constraints":["La fecha de compra no tiene un campo determinista; se usa created_at como aproximación a cuándo se registró la compra en Odyssey."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"compras en Carrefour y Lidl hechas en julio de 2026","type":"purchase","required_tags":[],"filters":[]},"unrepresented_constraints":["La fecha de compra no está representada por ningún campo de fecha disponible; no se puede filtrar directamente por compras realizadas en julio de 2026."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"compras que hice en julio en Carrefour y Lidl","type":"purchase","required_tags":[],"filters":[]},"unrepresented_constraints":["La fecha de la compra no se puede filtrar: no existe un campo de fecha de compra."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"compras realizadas en julio de 2026 en Carrefour y Lidl","type":"purchase","required_tags":[],"filters":[]},"unrepresented_constraints":["La fecha de realización de la compra en julio de 2026 no puede filtrarse porque no existe un campo de fecha de compra."]}`

Why a result is unsafe or inferior:

Unjustified hard filter can reduce recall (1x): ('created_at', 'gte', '2026-07-01T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('created_at', 'lt', '2026-08-01T00:00:00+02:00')

### T15

Question:

¿Qué ideas y decisiones tengo sobre Odyssey?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "idea"
    ],
    [
      "decision"
    ]
  ],
  "unrepresented_groups": [
    [
      "tag",
      "etiquet"
    ],
    [
      " or ",
      " o ",
      "disyunt"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"ideas y decisiones sobre Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud combina ideas y decisiones, que requieren una condición OR entre las etiquetas `idea` y `decision`, no representable con `required_tags` ni con los filtros disponibles."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"ideas y decisiones sobre Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud combina ideas y decisiones, que implica una disyunción entre las etiquetas `idea` y `decision`; no puede representarse como un filtro OR en un único plan."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"sobre Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["Notas con etiqueta idea O etiqueta decision: la disyunción entre etiquetas no se puede representar como un único filtro global."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"Odyssey; ideas y decisiones","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La condición de etiqueta idea O decisión no puede representarse como un OR determinista en un único plan."]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['decision'] was not found in generated query 'sobre Odyssey'; Semantic preservation needs human review; lexical oracle group ['idea'] was not found in generated query 'sobre Odyssey'

### T18

Question:

¿Qué ideas marcadas para explorar y revisar tengo sobre inteligencia artificial y automatización?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [
    "explore",
    "idea",
    "review"
  ],
  "filters": [],
  "query_groups": [
    [
      "inteligencia artificial"
    ],
    [
      "automatiz"
    ]
  ],
  "unrepresented_groups": []
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"inteligencia artificial y automatización","type":null,"required_tags":["explore","review"],"filters":[]},"unrepresented_constraints":[]}`

gpt-5.6-luna/low:

`{"plan":{"query":"inteligencia artificial y automatización","type":null,"required_tags":["idea","explore","review"],"filters":[]},"unrepresented_constraints":["La solicitud puede implicar ideas que tengan la etiqueta «explore» o la etiqueta «review», pero required_tags solo permite exigir que todas las etiquetas estén presentes; no se puede representar OR entre etiquetas."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"inteligencia artificial y automatización","type":null,"required_tags":["idea","explore","review"],"filters":[]},"unrepresented_constraints":[]}`

gpt-5.6-sol/low:

`{"plan":{"query":"inteligencia artificial y automatización","type":null,"required_tags":["idea","explore","review"],"filters":[]},"unrepresented_constraints":[]}`

Why a result is unsafe or inferior:

Safe requested deterministic tags were omitted: ['idea']

### T22

Question:

¿Qué documentos actualicé esta semana sobre el alquiler y qué personas estaban relacionadas con ellos?

Expected safe behavior:

```json
{
  "types": [
    "document",
    "person"
  ],
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "document"
    ],
    [
      "persona"
    ],
    [
      "alquiler"
    ],
    [
      "actualiz"
    ],
    [
      "relacion"
    ]
  ],
  "unrepresented_groups": [
    [
      "actualiz"
    ],
    [
      "document"
    ],
    [
      "scope",
      "scoped",
      "solo",
      "only",
      "rama"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"documentos sobre el alquiler actualizados esta semana y qué personas estaban relacionadas con esos documentos","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud combina dos ramas con alcance distinto: documentos actualizados esta semana y personas relacionadas con esos documentos; no se puede aplicar globalmente el filtro de actualización ni representar la relación entre personas y documentos en un único plan."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"documentos actualizados esta semana sobre el alquiler y qué personas estaban relacionadas con ellos","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud combina una rama de documentos actualizados esta semana con una rama de personas relacionadas con esos documentos; no se pueden representar relaciones genéricas ni aplicar la condición de actualización solo a los documentos en un único plan."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"documentos que actualicé esta semana sobre el alquiler y las personas relacionadas con ellos","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La actualización esta semana se aplica solo a los documentos, no a las personas relacionadas; requiere ramas o planes con restricciones independientes.","La relación entre las personas y esos documentos no dispone de un filtro estructural."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"documentos sobre el alquiler actualizados esta semana y personas relacionadas con esos documentos","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La condición updated_at durante esta semana se aplica solo a los documentos, no a las personas; esta restricción por rama y la vinculación entre ambos tipos requieren planes independientes o relaciones no disponibles."]}`

Why a result is unsafe or inferior:

Missing requested types: ['document', 'person']; Semantic preservation needs human review; lexical oracle group ['actualiz'] was not found in generated query 'documentos que actualicé esta semana sobre el alquiler y las personas relacionadas con ellos'; Semantic preservation needs human review; lexical oracle group ['actualiz'] was not found in generated query 'documentos sobre el alquiler que actualicé esta semana y las personas relacionadas con esos documentos'; Unsupported-constraint wording needs human review; lexical oracle group ['actualiz'] was not found in generated output ['El filtro updated_at de esta semana se aplica solo a los documentos y no puede limitarse a una rama dentro de un único plan.']; Unsupported-constraint wording needs human review; lexical oracle group ['actualiz'] was not found in generated output ['El intervalo de updated_at de esta semana (desde 2026-08-17T00:00:00+02:00 hasta antes de 2026-08-24T00:00:00+02:00) debe aplicarse solo a los documentos, no a las personas; un único plan no permite filtros por rama o tipo.']; Unsupported-constraint wording needs human review; lexical oracle group ['actualiz'] was not found in generated output ['El intervalo de updated_at de esta semana se aplica solo a los documentos, no a las personas; este alcance por tipo no puede representarse en un único plan.']; Unsupported-constraint wording needs human review; lexical oracle group ['actualiz'] was not found in generated output ['La condición updated_at durante esta semana se aplica solo a los documentos, no a las personas; esta restricción por rama y la vinculación entre ambos tipos requieren planes independientes o relaciones no disponibles.']

### T24

Question:

¿Qué cosas sobre Odyssey creé ayer o modifiqué hoy?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "cre",
      "created"
    ],
    [
      "modific",
      "updated"
    ],
    [
      "ayer",
      "yesterday"
    ],
    [
      "hoy",
      "today"
    ]
  ],
  "unrepresented_groups": [
    [
      "created_at",
      "cread"
    ],
    [
      "updated_at",
      "modific"
    ],
    [
      " or ",
      " o ",
      "disyunt"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"cosas sobre Odyssey","type":null,"required_tags":[],"filters":[{"field":"created_at","op":"gte","value":"2026-08-19T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-20T00:00:00+02:00"},{"field":"updated_at","op":"gte","value":"2026-08-20T00:00:00+02:00"},{"field":"updated_at","op":"lt","value":"2026-08-21T00:00:00+02:00"}]},"unrepresented_constraints":["La solicitud requiere una condición OR entre dos ramas independientes: creado ayer O modificado hoy; los filtros globales no pueden representar esa alternativa sin excluir resultados relevantes."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"cosas sobre Odyssey","type":null,"required_tags":[],"filters":[{"field":"created_at","op":"gte","value":"2026-08-19T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-20T00:00:00+02:00"},{"field":"updated_at","op":"gte","value":"2026-08-20T00:00:00+02:00"},{"field":"updated_at","op":"lt","value":"2026-08-21T00:00:00+02:00"}]},"unrepresented_constraints":["La solicitud requiere una condición OR entre dos ramas: (creado ayer) o (modificado hoy). Los filtros se aplican globalmente y no pueden representar esa alternativa sin excluir resultados relevantes."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"cosas sobre Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["created_at yesterday OR updated_at today cannot be represented as a single globally conjunctive filter set."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"cosas sobre Odyssey que creé ayer o modifiqué hoy","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["OR entre created_at durante 2026-08-19 y updated_at durante 2026-08-20 no puede representarse en un único plan"]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['ayer', 'yesterday'] was not found in generated query 'cosas sobre Odyssey'; Semantic preservation needs human review; lexical oracle group ['cre', 'created'] was not found in generated query 'cosas sobre Odyssey'; Semantic preservation needs human review; lexical oracle group ['hoy', 'today'] was not found in generated query 'cosas sobre Odyssey'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'Cosas sobre Odyssey que creé ayer o modifiqué hoy'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'Odyssey; cosas que creé ayer o modifiqué hoy'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'cosas sobre Odyssey que creé ayer o modifiqué hoy'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'cosas sobre Odyssey'; Unjustified hard filter can reduce recall (1x): ('created_at', 'gte', '2026-08-19T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('created_at', 'lt', '2026-08-20T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('updated_at', 'gte', '2026-08-20T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('updated_at', 'lt', '2026-08-21T00:00:00+02:00'); Unsupported-constraint wording needs human review; lexical oracle group [' or ', ' o ', 'disyunt'] was not found in generated output ['OR entre created_at durante 2026-08-19 y updated_at durante 2026-08-20 no puede representarse en un único plan']

### T27

Question:

¿Qué decisiones tomé después de crear Odyssey pero antes de empezar a usar n8n?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [
    "decision"
  ],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "n8n"
    ],
    [
      "después",
      "despues",
      "after"
    ],
    [
      "antes",
      "before"
    ]
  ],
  "unrepresented_groups": [
    [
      "temporal",
      "fecha",
      "date",
      "orden",
      "ordering"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"decisiones que tomé después de crear Odyssey pero antes de empezar a usar n8n","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["Se solicita un intervalo temporal definido por dos eventos («después de crear Odyssey» y «antes de empezar a usar n8n»), pero el esquema no tiene campos para fechas de creación o inicio de uso de esas entidades ni un campo de fecha de decisión."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"Decisiones que tomé después de crear Odyssey pero antes de empezar a usar n8n","type":null,"required_tags":["decision"],"filters":[]},"unrepresented_constraints":["El intervalo temporal relativo entre crear Odyssey y empezar a usar n8n no puede representarse con los campos de fecha disponibles.","La fecha en que se tomó cada decisión no está disponible como filtro determinista."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"decisiones que tomé después de crear Odyssey pero antes de empezar a usar n8n","type":null,"required_tags":["decision"],"filters":[]},"unrepresented_constraints":["El intervalo temporal relativo entre la creación de Odyssey y el inicio de uso de n8n no puede representarse con los campos de fecha disponibles."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"decisiones que tomé después de crear Odyssey pero antes de empezar a usar n8n","type":null,"required_tags":["decision"],"filters":[]},"unrepresented_constraints":["El intervalo temporal relativo —después de crear Odyssey y antes de empezar a usar n8n— no puede filtrarse porque no existe un campo de fecha de decisión ni de eventos genéricos."]}`

Why a result is unsafe or inferior:

Safe requested deterministic tags were omitted: ['decision']

### T28

Question:

¿Qué ideas, reflexiones o preguntas tengo sobre cómo mejorar Odyssey?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "idea"
    ],
    [
      "reflex"
    ],
    [
      "pregunt",
      "question"
    ]
  ],
  "unrepresented_groups": [
    [
      "tag",
      "etiquet"
    ],
    [
      " or ",
      " o ",
      "disyunt"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"ideas, reflexiones o preguntas sobre cómo mejorar Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud pide una OR entre las etiquetas idea, reflection y question, que no puede representarse con required_tags, ya que sus etiquetas tienen semántica AND."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"ideas, reflexiones o preguntas sobre cómo mejorar Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud pide ideas O reflexiones O preguntas; esta disyunción de etiquetas no puede representarse como un filtro determinista único."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"cómo mejorar Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["tag idea OR reflection OR question cannot be represented as required_tags, which has AND semantics."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"ideas, reflexiones o preguntas sobre cómo mejorar Odyssey","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La condición de etiqueta idea OR reflection OR question no puede representarse como un único filtro determinista."]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['idea'] was not found in generated query 'cómo mejorar Odyssey'; Semantic preservation needs human review; lexical oracle group ['pregunt', 'question'] was not found in generated query 'cómo mejorar Odyssey'; Semantic preservation needs human review; lexical oracle group ['reflex'] was not found in generated query 'cómo mejorar Odyssey'

### T35

Question:

¿Qué personas nacidas después de 1990 y qué entradas de diario de agosto tengo?

Expected safe behavior:

```json
{
  "types": [
    "journal_entry",
    "person"
  ],
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "persona"
    ],
    [
      "1990"
    ],
    [
      "diario",
      "journal"
    ],
    [
      "agosto",
      "august"
    ]
  ],
  "unrepresented_groups": [
    [
      "rama",
      "branch",
      "planes",
      "plans",
      "scope"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"personas nacidas después de 1990 y entradas de diario de agosto","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes: personas nacidas después de 1990 y entradas de diario de agosto. No se pueden representar en un único plan porque el filtro birth_date solo aplica a personas y entry_date solo a entradas de diario; se requieren planes independientes."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"personas nacidas después de 1990 y entradas de diario de agosto de 2026","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["person","journal_entry"]}]},"unrepresented_constraints":["La condición de nacimiento posterior a 1990 solo debe aplicarse a personas, mientras que la condición de entradas de diario de agosto de 2026 solo debe aplicarse a entradas de diario; no pueden expresarse como filtros globales en un único plan. Se requieren planes independientes."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"personas nacidas después de 1990 y entradas de diario de agosto","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud combina ramas con filtros independientes: personas con birth_date posterior a 1990 y entradas de diario de agosto; un único plan no puede aplicar esos filtros de forma condicionada por tipo."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"personas nacidas después de 1990 y entradas de diario de agosto de 2026","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["person","journal_entry"]}]},"unrepresented_constraints":["Las condiciones están vinculadas a ramas distintas: birth_date posterior a 1990 solo para personas y entry_date de agosto de 2026 solo para entradas de diario; requieren planes independientes."]}`

Why a result is unsafe or inferior:

Missing requested types: ['journal_entry', 'person']

### T39

Question:

¿Qué cosas modifiqué hoy sobre Odyssey y qué cosas escribí ayer sobre n8n?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "n8n"
    ],
    [
      "hoy",
      "today"
    ],
    [
      "ayer",
      "yesterday"
    ],
    [
      "modific",
      "updated"
    ],
    [
      "escrib",
      "wrote",
      "created"
    ]
  ],
  "unrepresented_groups": [
    [
      "rama",
      "branch",
      "planes",
      "plans"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"cosas sobre Odyssey que modifiqué hoy; cosas sobre n8n que escribí ayer","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes: notas sobre Odyssey modificadas hoy y notas sobre n8n creadas/escritas ayer; requieren planes separados porque los filtros de fecha no pueden aplicarse globalmente a ambas ramas."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"cosas que modifiqué hoy sobre Odyssey y cosas que escribí ayer sobre n8n","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes con fechas y campos distintos: Odyssey requiere updated_at para hoy, mientras que n8n requiere created_at para ayer. No pueden representarse conjuntamente en un único conjunto de filtros globales; se requieren planes independientes."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"cosas modificadas hoy sobre Odyssey y cosas escritas ayer sobre n8n","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas con restricciones temporales independientes: elementos actualizados hoy sobre Odyssey y elementos creados ayer sobre n8n; requeriría planes separados para aplicar los filtros de fecha sin excluir resultados relevantes."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"Cosas sobre Odyssey modificadas hoy (2026-08-20) y cosas sobre n8n escritas ayer (2026-08-19)","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes con restricciones temporales distintas: updated_at durante 2026-08-20 solo para Odyssey y created_at durante 2026-08-19 solo para n8n; un único plan no puede aplicar filtros por rama."]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['escrib', 'wrote', 'created'] was not found in generated query 'Cosas sobre Odyssey modificadas hoy (2026-08-20) y cosas sobre n8n escritas ayer (2026-08-19)'; Semantic preservation needs human review; lexical oracle group ['escrib', 'wrote', 'created'] was not found in generated query 'cosas modificadas hoy sobre Odyssey y cosas escritas ayer sobre n8n'; Semantic preservation needs human review; lexical oracle group ['escrib', 'wrote', 'created'] was not found in generated query 'cosas sobre Odyssey modificadas hoy (2026-08-20) y cosas sobre n8n escritas ayer (2026-08-19)'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'Cosas que modifiqué hoy sobre Odyssey; cosas que escribí ayer sobre n8n'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'Qué cosas modifiqué hoy sobre Odyssey y qué cosas escribí ayer sobre n8n'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'cosas que modifiqué hoy sobre Odyssey y cosas que escribí ayer sobre n8n'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'cosas sobre Odyssey que modifiqué hoy y cosas sobre n8n que escribí ayer'; Semantic preservation needs human review; lexical oracle group ['modific', 'updated'] was not found in generated query 'cosas sobre Odyssey que modifiqué hoy; cosas sobre n8n que escribí ayer'

### T40

Question:

¿Qué proyectos, tareas y conceptos sobre Odyssey fueron creados o actualizados esta semana?

Expected safe behavior:

```json
{
  "types": [
    "concept",
    "project",
    "task"
  ],
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "odyssey"
    ],
    [
      "cread",
      "created"
    ],
    [
      "actualiz",
      "updated"
    ],
    [
      "semana",
      "week"
    ]
  ],
  "unrepresented_groups": [
    [
      "created_at",
      "cread"
    ],
    [
      "updated_at",
      "actualiz"
    ],
    [
      " or ",
      " o ",
      "disyunt"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"Odyssey","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["project","task","concept"]},{"field":"created_at","op":"gte","value":"2026-08-17T00:00:00+02:00"},{"field":"created_at","op":"lt","value":"2026-08-24T00:00:00+02:00"},{"field":"updated_at","op":"gte","value":"2026-08-17T00:00:00+02:00"},{"field":"updated_at","op":"lt","value":"2026-08-24T00:00:00+02:00"}]},"unrepresented_constraints":["La solicitud pide creados esta semana O actualizados esta semana; no se puede representar la disyunción entre los intervalos de created_at y updated_at en un único plan sin excluir resultados."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"Odyssey, creados o actualizados esta semana","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["project","task","concept"]}]},"unrepresented_constraints":["La condición temporal es una alternativa: creados esta semana O actualizados esta semana. No puede representarse con un único conjunto de filtros globales sin convertirla incorrectamente en una condición AND."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"Odyssey","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["project","task","concept"]}]},"unrepresented_constraints":["La condición temporal es una alternativa entre created_at esta semana y updated_at esta semana, que no puede representarse como filtros globales AND en un único plan."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"sobre Odyssey, creados o actualizados esta semana (del 17 al 23 de agosto de 2026)","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["project","task","concept"]}]},"unrepresented_constraints":["La condición created_at durante esta semana OR updated_at durante esta semana no puede representarse con un único RetrievalPlan."]}`

Why a result is unsafe or inferior:

Semantic preservation needs human review; lexical oracle group ['actualiz', 'updated'] was not found in generated query 'Odyssey'; Semantic preservation needs human review; lexical oracle group ['cread', 'created'] was not found in generated query 'Odyssey'; Semantic preservation needs human review; lexical oracle group ['semana', 'week'] was not found in generated query 'Odyssey'; Unjustified hard filter can reduce recall (1x): ('created_at', 'gte', '2026-08-17T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('created_at', 'lt', '2026-08-24T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('updated_at', 'gte', '2026-08-17T00:00:00+02:00'); Unjustified hard filter can reduce recall (1x): ('updated_at', 'lt', '2026-08-24T00:00:00+02:00'); Unsupported-constraint wording needs human review; lexical oracle group [' or ', ' o ', 'disyunt'] was not found in generated output ['La condición temporal es una alternativa entre created_at esta semana y updated_at esta semana, que no puede representarse como filtros globales AND en un único plan.']

### T42

Question:

¿Qué personas tienen relationship_to_user igual a "familia" o "amigo"?

Expected safe behavior:

```json
{
  "types": [
    "person"
  ],
  "required_tags": [],
  "filters": [
    {
      "field": "relationship_to_user",
      "op": "in",
      "value": [
        "familia",
        "amigo"
      ]
    }
  ],
  "query_groups": [],
  "unrepresented_groups": []
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"personas cuyo relationship_to_user sea igual a \"familia\" o \"amigo\"","type":"person","required_tags":[],"filters":[]},"unrepresented_constraints":["La condición OR entre relationship_to_user = \"familia\" y relationship_to_user = \"amigo\" no puede representarse en un único plan; se preserva semánticamente."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"Personas cuyo relationship_to_user es \"familia\" o \"amigo\"","type":"person","required_tags":[],"filters":[{"field":"relationship_to_user","op":"in","value":["familia","amigo"]}]},"unrepresented_constraints":[]}`

gpt-5.6-terra/low:

`{"plan":{"query":"personas con relationship_to_user igual a \"familia\" o \"amigo\"","type":"person","required_tags":[],"filters":[]},"unrepresented_constraints":["relationship_to_user = \"familia\" OR relationship_to_user = \"amigo\" no puede representarse como una disyunción de predicados deterministas en un único plan."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"personas cuya relación con el usuario sea familia o amigo","type":"person","required_tags":[],"filters":[{"field":"relationship_to_user","op":"in","value":["familia","amigo"]}]},"unrepresented_constraints":[]}`

Why a result is unsafe or inferior:

Safe requested filter was omitted (1x): ('relationship_to_user', 'in', ('amigo', 'familia'))

### T43

Question:

¿Qué personas con relationship_to_user = "familia" y qué proyectos tengo relacionados con Toulouse?

Expected safe behavior:

```json
{
  "types": [
    "person",
    "project"
  ],
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "familia"
    ],
    [
      "proyecto",
      "project"
    ],
    [
      "toulouse"
    ]
  ],
  "unrepresented_groups": [
    [
      "scope",
      "scoped",
      "solo",
      "only",
      "rama"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes: personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse; no pueden aplicarse conjuntamente en un único plan global. Se requieren planes de recuperación independientes.","La relación de los proyectos con Toulouse es semántica y no existe un filtro determinista de relación de proyecto."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene dos ramas independientes: personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse; requiere planes separados para aplicar correctamente los filtros por tipo y relación."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La solicitud contiene ramas independientes: el filtro relationship_to_user = \"familia\" solo aplica a personas, mientras que Toulouse solo aplica a proyectos; un único plan no puede aplicar filtros por rama."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"personas con relationship_to_user = \"familia\" y proyectos relacionados con Toulouse","type":null,"required_tags":[],"filters":[{"field":"type","op":"in","value":["person","project"]}]},"unrepresented_constraints":["La condición relationship_to_user = \"familia\" se aplica únicamente a las personas y no puede representarse como filtro global sin excluir los proyectos; se requieren ramas o planes con filtros independientes."]}`

Why a result is unsafe or inferior:

Missing requested types: ['person', 'project']

### T44

Question:

¿Qué notas tienen el alias "Ody" o el alias "Proyecto Odyssey"?

Expected safe behavior:

```json
{
  "types": null,
  "required_tags": [],
  "filters": [],
  "query_groups": [
    [
      "ody"
    ],
    [
      "proyecto odyssey"
    ]
  ],
  "unrepresented_groups": [
    [
      "alias"
    ],
    [
      " or ",
      " o ",
      "disyunt"
    ]
  ]
}
```

gpt-5.6-luna/none:

`{"plan":{"query":"notas con el alias \"Ody\" o el alias \"Proyecto Odyssey\"","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La condición OR entre los alias \"Ody\" y \"Proyecto Odyssey\" no puede representarse con los filtros disponibles; se conserva en la consulta semántica."]}`

gpt-5.6-luna/low:

`{"plan":{"query":"notas con el alias \"Ody\" o el alias \"Proyecto Odyssey\"","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["La condición alias = \"Ody\" OR alias = \"Proyecto Odyssey\" no puede representarse como un filtro OR en un único plan."]}`

gpt-5.6-terra/low:

`{"plan":{"query":"notas con el alias \"Ody\" o el alias \"Proyecto Odyssey\"","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["Alias metadata requires an OR condition (aliases contains \"Ody\" OR aliases contains \"Proyecto Odyssey\"), which cannot be represented in one plan."]}`

gpt-5.6-sol/low:

`{"plan":{"query":"notas con el alias \"Ody\" o el alias \"Proyecto Odyssey\"","type":null,"required_tags":[],"filters":[]},"unrepresented_constraints":["OR entre aliases: aliases contiene \"Ody\" o aliases contiene \"Proyecto Odyssey\""]}`

Why a result is unsafe or inferior:

Unsupported-constraint wording needs human review; lexical oracle group [' or ', ' o ', 'disyunt'] was not found in generated output ['OR entre aliases contains "Ody" y aliases contains "Proyecto Odyssey" no puede representarse en un único RetrievalPlan']

## Recommendations

Cheapest observed configuration with zero deterministic critical failures: `gpt-5.6-terra:low`. This is a cost recommendation, not a claim of statistically proven perfect reliability; semantic-review diagnostics remain separate.
Best observed quality among complete zero-critical configurations: `gpt-5.6-sol:low`.
Repeatability evidence is configuration-specific: Terra/low was observed once per case, while Sol/low was repeated across its cases.

The v1 evaluator was too pessimistic: substring checks on natural-language query and diagnostic prose cannot establish lost meaning. V2 retains strict structural candidate-set checks, and preserves lexical mismatches as an auditable human-review queue instead.
