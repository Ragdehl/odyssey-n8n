# Phase 11A.1 local benchmark results

This compact artifact preserves the synthetic benchmark's frozen evaluation labels and the first-run
decision returned by each local method. `RESOLVED:<id>` records the selected candidate. The 48 English,
Spanish, and French cases are blocking; the three Catalan cases are non-blocking. Calibration cases,
candidate text, categories, and references remain in
[`phase11a_contextual_resolution_cases.json`](phase11a_contextual_resolution_cases.json). Runtime and
aggregate measurements are recorded in [ADR 0002](../docs/decisions/0002-phase-11a-contextual-resolution-benchmark.md).

| Case | Expected | Expected ID | Cosine | Cross-Encoder | Qwen3 0.6B | Llama 3.2 1B |
| --- | --- | --- | --- | --- | --- | --- |
| en-wife-school | RESOLVED | beatriz-alonso | UNRESOLVED | UNRESOLVED | RESOLVED:beatriz-alonso | RESOLVED:clara-martin |
| en-xavi-partner | RESOLVED | beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:xavi-pujol | RESOLVED:xavi-pujol |
| en-former-mercury-colleague | RESOLVED | beatriz-martin | AMBIGUOUS | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin | RESOLVED:lucia-ferrer |
| en-climbing-xavi | RESOLVED | xavi-pujol | RESOLVED:xavi-pujol | RESOLVED:xavi-pujol | RESOLVED:xavi-pujol | RESOLVED:xavi-pujol |
| en-xavi-client-or-friend | AMBIGUOUS | — | AMBIGUOUS | AMBIGUOUS | RESOLVED:xavier-pons | RESOLVED:xavier-pons |
| en-running-doctor | RESOLVED | clara-ruiz | UNRESOLVED | UNRESOLVED | RESOLVED:clara-ruiz | RESOLVED:clara-ruiz |
| en-central-small-carrefour | RESOLVED | carrefour-market-capitole | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole |
| en-not-discount-balma | RESOLVED | carrefour-balma | AMBIGUOUS | AMBIGUOUS | RESOLVED:lidl-balma | RESOLVED:lidl-balma |
| en-markdown-project | UNRESOLVED | — | RESOLVED:odyssey | RESOLVED:odyssey | UNRESOLVED | RESOLVED:odyssey |
| en-beatriz-meeting | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin |
| en-lu-alias | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:lucia-ferrer | RESOLVED:lucia-garcia |
| en-project-generic | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:atlas | RESOLVED:atlas |
| en-toulouse-supermarket | AMBIGUOUS | — | AMBIGUOUS | AMBIGUOUS | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole |
| en-plumber | UNRESOLVED | — | UNRESOLVED | UNRESOLVED | RESOLVED:lucia-ferrer | RESOLVED:beatriz-costa |
| en-cardiologist-pediatrician | UNRESOLVED | — | AMBIGUOUS | UNRESOLVED | RESOLVED:clara-martin | RESOLVED:clara-martin |
| en-labege-hardware | UNRESOLVED | — | UNRESOLVED | RESOLVED:carrefour-labege | RESOLVED:carrefour-labege | RESOLVED:carrefour-labege |
| es-esposa-hijos | RESOLVED | beatriz-alonso | AMBIGUOUS | RESOLVED:beatriz-alonso | RESOLVED:beatriz-alonso | RESOLVED:beatriz-alonso |
| es-beti-restaura | RESOLVED | beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa |
| es-companera-mercury | RESOLVED | lucia-ferrer | AMBIGUOUS | RESOLVED:lucia-ferrer | RESOLVED:lucia-ferrer | RESOLVED:lucia-ferrer |
| es-vecino-bicis | RESOLVED | marc-dubois | RESOLVED:marc-dubois | RESOLVED:marc-dubois | RESOLVED:marc-dubois | RESOLVED:marc-dubois |
| es-marc-atlas | RESOLVED | marc-vidal | AMBIGUOUS | AMBIGUOUS | RESOLVED:marc-vidal | RESOLVED:marc-vidal |
| es-clara-mensaje | AMBIGUOUS | — | AMBIGUOUS | UNRESOLVED | RESOLVED:clara-ruiz | RESOLVED:clara-martin |
| es-carrefour-cine | RESOLVED | carrefour-labege | RESOLVED:carrefour-labege | RESOLVED:carrefour-labege | RESOLVED:carrefour-labege | RESOLVED:carrefour-labege |
| es-mercurio-astronomia | UNRESOLVED | — | RESOLVED:mercury | RESOLVED:mercury | RESOLVED:mercury | RESOLVED:mercury |
| es-cuenta-barcelona | RESOLVED | delta | RESOLVED:delta | RESOLVED:delta | RESOLVED:atlas | RESOLVED:delta |
| es-xavi-sin-contexto | AMBIGUOUS | — | AMBIGUOUS | AMBIGUOUS | RESOLVED:xavier-pons | RESOLVED:xavier-pons |
| es-clara | AMBIGUOUS | — | AMBIGUOUS | UNRESOLVED | RESOLVED:clara-ruiz | RESOLVED:clara-martin |
| es-otro-marc | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:marc-vidal | RESOLVED:marc-vidal |
| es-supermercado-balma | AMBIGUOUS | — | RESOLVED:lidl-balma | AMBIGUOUS | RESOLVED:lidl-balma | RESOLVED:lidl-balma |
| es-fisioterapeuta | UNRESOLVED | — | UNRESOLVED | UNRESOLVED | RESOLVED:clara-ruiz | RESOLVED:clara-martin |
| es-dentista-madrid | UNRESOLVED | — | RESOLVED:lucia-garcia | AMBIGUOUS | RESOLVED:lucia-garcia | RESOLVED:lucia-garcia |
| es-proyecto-atlas-mapas | UNRESOLVED | — | RESOLVED:atlas | RESOLVED:atlas | UNRESOLVED | RESOLVED:atlas |
| fr-epouse-enfants | RESOLVED | beatriz-alonso | UNRESOLVED | RESOLVED:beatriz-alonso | RESOLVED:beatriz-alonso | RESOLVED:beatriz-alonso |
| fr-compagne-xavi | RESOLVED | beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:xavi-pujol |
| fr-ancienne-mercury | RESOLVED | beatriz-martin | AMBIGUOUS | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin |
| fr-voisine-course | RESOLVED | clara-ruiz | RESOLVED:clara-ruiz | UNRESOLVED | RESOLVED:clara-ruiz | RESOLVED:clara-martin |
| fr-clara-comptes | RESOLVED | clara-martin | AMBIGUOUS | RESOLVED:clara-martin | RESOLVED:clara-martin | RESOLVED:clara-martin |
| fr-dentiste-capitole | RESOLVED | lucia-garcia | RESOLVED:lucia-garcia | RESOLVED:lucia-garcia | RESOLVED:lucia-garcia | RESOLVED:lucia-garcia |
| fr-fromagerie-victor-hugo | UNRESOLVED | — | RESOLVED:marche-victor-hugo | RESOLVED:marche-victor-hugo | RESOLVED:marche-victor-hugo | RESOLVED:marche-victor-hugo |
| fr-carrefour-habituel | RESOLVED | carrefour-balma | AMBIGUOUS | AMBIGUOUS | RESOLVED:lidl-balma | RESOLVED:lidl-balma |
| fr-projet-generique | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:atlas | RESOLVED:atlas |
| fr-beatriz | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin |
| fr-marc | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:marc-vidal | RESOLVED:marc-vidal |
| fr-carrefour | AMBIGUOUS | — | AMBIGUOUS | UNRESOLVED | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole |
| fr-projet-client | AMBIGUOUS | — | AMBIGUOUS | RESOLVED:delta | RESOLVED:delta | RESOLVED:delta |
| fr-veterinaire | UNRESOLVED | — | UNRESOLVED | UNRESOLVED | RESOLVED:lucia-garcia | RESOLVED:xavier-pons |
| fr-pediatre-paris | UNRESOLVED | — | RESOLVED:lucia-garcia | RESOLVED:lucia-garcia | RESOLVED:clara-martin | RESOLVED:lucia-garcia |
| fr-librairie-capitole | UNRESOLVED | — | RESOLVED:carrefour-market-capitole | UNRESOLVED | RESOLVED:carrefour-market-capitole | RESOLVED:carrefour-market-capitole |
| ca-dona-xavi | RESOLVED | beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa | RESOLVED:xavi-pujol |
| ca-beatriz | AMBIGUOUS | — | UNRESOLVED | UNRESOLVED | RESOLVED:beatriz-martin | RESOLVED:beatriz-martin |
| ca-desconegut | UNRESOLVED | — | UNRESOLVED | UNRESOLVED | RESOLVED:beatriz-costa | RESOLVED:beatriz-costa |

The raw runtime JSON contains repeated-run details, candidate scores, timings, and memory measurements.
It is intentionally not committed because this table and the synthetic dataset preserve the architectural
evidence without binding the repository to machine-specific runtime artifacts.
