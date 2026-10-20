# E4 Core Person → Task CREATE: reparación de procedencia, 20-10-2026

Rama aislada `agent/e4-closure-review-fixed-20261020`; base fuente
`2055148f6ca97dd7575a1d6bfd966eba20a6628e`. Los cambios de reparación
están **sin commit**: `git add` no pudo crear el index lock bajo el Git común
de solo lectura (`Read-only file system`). No se intentó eludir esa restricción.
Sin push, merge ni deploy.

## Hecho

- `ActionResult` conserva una vinculación Core independiente de cada recibo linked:
  unidad fuente, índice de referencia, mención, ID canónico y operación del Writer.
  Ambos handoffs exigen esa vinculación y guards actuales del Markdown. Un recibo
  directo CREATE y un backlink materializado distintos pueden corroborar el mismo ID.
- La búsqueda de la mención antecedente admite variación de mayúsculas y sigue
  exigiendo un único span original completo. No transforma la fuente ni concede
  autoridad de identidad a Router o Tasks.
- Nuevos centinelas alteran índice, unidad, acción y operación del recibo linked
  en los carriers de ambos handoffs; el replay de la fábrica de producción usa
  fuente `marta` y Note canónica `Marta` en un vault sintético. El selector
  de Person tiene variantes con 1, 3, 5 y 7 identidades Core.
- Un centinela del supervisor obliga a `codex()` con presupuesto de job cero
  a respetar el rechazo del pacing diario antes de lanzar el proceso modelo.

## Evidencia y límites

- `python -m compileall -q` sobre los módulos y tests modificados: PASS.
- Importación del módulo de procedencia y smoke del vínculo de índice/target:
  PASS, sin pytest.
- `git diff --check`: PASS. Escaneo de patrones de credenciales en diff: PASS.
- El sandbox Codex carece de pytest y Ruff (`No module named pytest/ruff`), por
  lo que **los tests nuevos todavía no tienen ejecución verificada**.
- El recibo host anterior informa acceptance, cross-surface y Ruff PASS en
  `5bf798c`; ese árbol precede esta reparación y no se reutiliza como gate final.
- El host de revisión es ARM64 con 4049 MiB RAM; una lectura puntual mostró
  2438 MiB disponibles y 1277 MiB de swap usados. El gate host anterior tardó
  58,34 s y dejó ~2020 MiB disponibles. Estas cifras no miden latencia E4
  fría/caliente, p50/p95, CPU, concurrencia ni temperatura.
- Falta el gate host fresco completo Python/Node/ledger/Ruff y las cuatro
  revisiones independientes sobre un snapshot inmutable. La aceptación de
  producto exige aparte navegador autenticado → n8n → modelo vivo → Writer →
  Markdown persistido → consulta → navegador en datos desechables. RecordedClient
  y pruebas aisladas no sustituyen esa evidencia.

## Próximo paso

Permitir al supervisor registrar el cambio en un snapshot Git del worktree,
ejecutar una sola vez el gate host sobre ese snapshot y revisar sus recibos;
después Generality, Quality, Testing y Performance. Conservar DEV/PROD y el
vault privado sin cambios. Sin autorización del E2E real no declarar user-ready.
