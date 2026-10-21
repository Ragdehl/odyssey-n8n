# E4 — Cierre funcional acotado y adopción DEV (21-10-2026)

## Decisión del usuario: sustituir el ciclo de cuatro auditores

El usuario aceptó **dejar de exigir cuatro dictámenes PASS de Codex para E4**
después de las rondas repetitivas v7, v9 y v12 y sus costes.
Los informes FAIL/BLOCKED anteriores **se preservan como historia**, no se
reescriben como PASS. Los defectos funcionales concretos que motivaron v12
están corregidos en `6065499`, y el E2E GPT+n8n+Chromium postcommit está
anclado a esa versión en
`e4-v14-postcommit-browser-receipt-20261021.json`.
El gate ahora es **aceptación funcional verificable**, sin Builder ni nuevas
auditorías de cuatro especialistas, y no constituye aprobación automática
para PROD.

### Invariantes que deben pasar

| Caso | Criterio físico / negativo | Regresiones reproducibles |
| --- | --- | --- |
| Dos / tres personas | 1 Task y conjunto completo de enlaces | `test_p4_plural_person_full_vertical.py`, `test_p4_finite_plural_reference_forms.py` |
| Nombres compuestos y minúsculas | No truncar ni dividir «ana maría» en «ana»+«maría» | `test_p4_source_cohort_coverage.py`, `test_p4_verified_plural_source_path.py`, `test_p4_dependent_group_graph.py` |
| Alias y persona extra | No aceptar una cohorte incompleta o una referencia adicional | `test_p4_aliased_prior_person.py`, `test_p4_multi_reference_set_guard.py` |
| Ambigüedad | Abstenerse, sin Task incorrecta | `test_p4_e4_campaign_oracle.py`, `test_p4_verified_plural_source_path.py` |
| Markdown posterior | EXACTAMENTE un enlace por persona y ningún Person adicional; pérdida, duplicado o inserción → PARTIAL | `test_p4_composition_plural_postwrite_loss.py`, `test_p4_e4_campaign_oracle.py` |
| Idempotencia | Segunda entrega byte-idéntica, sin crear notas | `test_p4_plural_person_full_vertical.py` y recibo E2E |
| UI desde consulta real | Respuesta HTTP y nuevo render comprobados; búsquedas de Task y Persons; backlinks reales | Recibo Chromium `e4-v14-postcommit-browser-receipt-20261021.json` |

### Método

`python scripts/odyssey_e4_functional_acceptance.py --json`:
comprueba hash SHA-256 del log y ausencia de cambios en el código producto
posteriores al commit del ensayo, verifica los campos realmente observados
de GPT/n8n/Chromium, búsqueda del Task y cada persona, backlinks, progreso y
replay; ejecuta los tests adversariales existentes. Falla si falta alguna
evidencia, no trata un ejemplo positivo como prueba universal.

**Evidencia:** pruebas focales 181 PASS sobre `9203b1b`;
gate transversal previo 1.567 Python + 179 JS + 7 subtests PASS;
GPT real con «Ana María y Luis» postcommit 2 Personas + 1 Task,
2 backlinks, tres búsquedas HTTP verificadas, replay idéntico.
38,30 s hasta respuesta; 74,28 s ensayo entero.
El script además tiene 11 tests adversariales que alteran recibos
para detectar falsos PASS.

### Lo que NO se declara

- No hay p95 certificado ni objetivo de latencia del usuario aprobado.
  Performance queda como seguimiento separado; el último revisor v12
  dio BLOCKED estadístico, **no** una regresión demostrada.
- Una ejecución sintética local no es prueba de Cloudflare Access ni de
  un despliegue DEV/PROD. No se tocan notas personales.
- No hay aceptación de E5: continúa en su rama específica.
- El histórico de nueve fallos del full-suite en el baseline congelado
  sigue documentado y no se presenta como suite íntegra verde.
- DEV requiere su propio rollout verificable, con entorno y bóveda
  separados, rollback al SHA anterior y comprobación posterior a deploy.
  PROD exige autorización y promoción independientes.

## DEV aceptado funcionalmente — prueba observada el 21-10-2026

Desplegado exclusivamente en DEV con SHA completo
`d03737fec07ad222b8dd5c8cd80e29060633cb4c`, desde la instalación
anterior `b0fc9b21da613bff4aeccf5466a18da8b18426e2`. Se verificó
coherencia de fuente+despliegue, runtime y n8n HTTP 200. Copias locales
privadas de vault/estado y volumen n8n creadas y comprobadas antes del
rollout, SHA de rollback preservado, sin alterar PROD.

Chromium real mediante proxy DEV **solo lectura PASS** en móvil y escritorio:
20 vistas técnicas y SVG por superficie, errores JS 0, cuatro intentos de
mutación rechazados con 403. Luego mensaje nuevo con GPT real y datos
sintéticos «Irene Varela y Pablo Sanz»: **HTTP 200 / completed, 58,87 s**,
exactamente **2 Person + 1 Task + 2 wikilinks canónicos**, 3 notas añadidas,
1 nota del día actualizada, 0 notas eliminadas. La misma entrega reintentada
después respondió completed y conservó **idénticos los hashes de 133 archivos
Markdown**. La consulta al endpoint DEV de Notes también devolvió resultados
para ambas personas. Recibo redigido [DEV](e4-dev-functional-adoption-receipt-20261021.json)
y reportes internos de rollback en el host, nunca subidos con datos privados.

El mismo comando de aceptación funcional ejecutado desde el checkout
**realmente desplegado en DEV** (`d03737f`) dio también
**FUNCTIONAL_ACCEPTANCE_PASS, 181 pruebas dirigidas**; la aceptación no
depende solo de la rama experimental.

**Resultado: E4 funcionalmente aceptada en DEV.** No se presenta como
certificación de p95, Cloudflare, E5 ni aprobación para PROD. La siguiente
etapa funcional vuelve a E5; antes de promover a PROD se requiere una
acción de despliegue independiente.
