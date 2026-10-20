# E4: evidencia de rendimiento observada en Raspberry Pi (20-10-2026)

## Alcance / medición honesta
Mediciones reproducibles con **datos sintéticos**, sin secretos ni vault real ni despliegue. Son una comprobación parcial de coste de búsquedas deterministas y del entorno Pi; **no** sustituyen aceptación de rendimiento del producto con GPT vivo, embeddings reales e índices de escala.

En Raspberry Pi Debian/arm64, ejecutar doce veces `PYTHONPATH=. /home/ragdehl/projects/odyssey/.venv/bin/python scripts/p4_verified_catalog_scope_bench.py`. Cada proceso prepara 250 notas sintéticas y efectúa diez búsquedas. Captura JSON bruta `/tmp/odyssey-e4-pi-perf-20261020.json`, con 12 muestras de cada modalidad.

| Modalidad | p50 mediana observada | p95 empírico (12 casos) | Lecturas Markdown por lote |
|---|---:|---:|---:|
| Lectura sin catálogo por petición | 286,06 ms | 306,28 ms | 2500 |
| Catálogo determinista verificado acotado | 113,02 ms | 128,75 ms | 250 |

El p95 se calcula como el valor en la posición `ceil(0.95*n)` de las doce muestras y NO predice el p95 de producción. Coste completo del proceso de medición: 9,187 segundos; no incluye latencia GPT, cold-start n8n, acceso remoto ni embeddings. Observación de host previa a carga: `free -m` mostraba aproximadamente 2,5 GiB MemAvailable y 1,4 GiB de swap usado sobre 2 GiB totales. A las 17:09 CEST se observó temperatura Pi 45,5 °C y load 0,00/0,00/0,00, en reposo. No inferir datos de ventilador.

## FastEmbed cold / warm
La prueba de carga **offline y sin descarga** de `FastEmbedTextEmbedder(cache_dir=Path.home()/'.cache/fastembed', local_files_only=True)` terminó con `SemanticIndexError: Unable to load embedding model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: no existe copia utilizable en esa ruta de caché aislada. Es un resultado **no medido** para cold/warm; no significa que el modelo esté ausente de todos los entornos DEV, y no se debe acceder al cache protegido de producción para convertirlo en PASS. El ensayo de browser/n8n E4 grabado usó `ConstantEmbedder` y terminó en 40,99 s, incluyendo n8n aislado y arranque Chromium. El E2E con GPT vivo anterior se completó en 72,24 s en una ejecución. Las muestras usan entornos/modelos distintos y no se pueden combinar en percentiles.

## Aceptación pendiente
**No existe objetivo SLA acordado** para p50/p95 de la petición, memoria máxima del proceso, tiempo cold/warm de FastEmbed en el entorno real o indexación de 250/1000/5000 notas. En consecuencia, la aceptación completa de Performance queda pendiente de medir un entorno preparado con embeddings reales y datos sintéticos a escala, disponer de una distribución suficiente de solicitudes vivas, y contrastarla con objetivos acordados. El auditor debe revisar esta evidencia, señalar limitaciones y no presentar un PASS global de rendimiento sin esas verificaciones. No es una razón para modificar seguridad o activar PROD.
