# Dirección futura: adopción incremental de Clean Architecture

**Estado: DIRECCIÓN APROBADA, TRABAJO DIFERIDO (13-10-2026).**
No iniciar reescritura ni refactorización transversal. El usuario pidió
aprovechar futuras modificaciones de módulos para adoptar Clean Architecture
poco a poco, sin retrasar las pruebas de DEV.

## Principios

El dominio de Odyssey (Note, Fact, Identity, NoteSchema, procedencia,
Temporal, validación y escritura canónica) no debe depender directamente
de OpenAI, n8n, HTTP, UI o el motor de almacenamiento. La dirección deseada
es: dominio y casos de uso al interior; contratos tipados hacia adaptadores
de proveedor IA, reloj, repositorio, índices y Apps.

Cuando haya que tocar un módulo por motivos funcionales:
1. Comprobar si mezcla decisiones de dominio con efectos externos.
2. Extraer solo los puertos o reglas puros que reduzcan acoplamiento real.
3. Mantener pruebas del contrato, regresiones y readback de Markdown;
   no tocar los datos de PROD.
4. Evitar capas vacías, duplicar semántica, nuevas infraestructuras y
   migraciones grandes en la Raspberry.
5. Respetar la arquitectura híbrida aprobada y la separación DEV/PROD.

## Oportunidades futuras, sin autorización para ejecutarlas ahora

- Aislar los clientes y prompts de Router, Temporal, Planner y Reviewer.
- Consolidar la validación de procedencia, actores, hechos y referencias
  alrededor de contratos de dominio generales, no frases concretas.
- Separar orquestación de grupos y pruebas canónicas de escritura.
- Usar puertos estrechos para contexto, datos, LLM, tiempo e integraciones.

**Prioridad actual: corregir el validador especializado, completar los
casos pendientes y habilitar pruebas de usuario en DEV.**
