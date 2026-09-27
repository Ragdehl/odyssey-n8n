# Semantic set resolution and evidence — architecture challenge

Status: **#142 merged; corrective #140/#137 implementation and deterministic verification are on
`fix/semantic-self-clarification`; the first frozen Luna gate failed and the corrected-prompt
successor gate is prepared, pending separate authorization**. The earlier semantic-intent gates
below are historical evidence for their frozen contracts. This follows
[Reference & Relationship Resolution v1](post-ui2-note-creation-and-schema-evolution.md).
Issues: [#140](https://github.com/Ragdehl/odyssey-n8n/issues/140),
[#137](https://github.com/Ragdehl/odyssey-n8n/issues/137),
[#138](https://github.com/Ragdehl/odyssey-n8n/issues/138), and
[#136](https://github.com/Ragdehl/odyssey-n8n/issues/136). Future Notes editing
[#134](https://github.com/Ragdehl/odyssey-n8n/issues/134) is a compatibility constraint,
not implementation scope.

## Corrective architecture challenge after real DEV evidence (#140/#137)

**REVISE; human decision required: NO.** The merged #142 contract remains the compatibility
baseline, but its collection selection loses the authenticated subject and its global candidate
limits make vault growth a functional limit. DEV evidence found 22 source Notes, 55 visible facts,
and 13,162 serialized bytes, within the current 64/64/16 KiB bounds. That particular failure
therefore does not establish a scan-overflow cause. The observed singular and collection failures
have different boundaries: duplicate facts are rejected before their target identities are
compared; a multi-target fact becomes an opaque singular error; collection planning forbids all
selectors, including self scope; and the collection selector receives no authenticated self
binding. `PlannerEscalation` is also projected as `UNRECOGNIZED_REQUEST`, which misstates a safely
understood but unrepresentable request.

### Phase contract

**Objective.** Resolve direct self-relative identities and finite collections from current
canonical facts, while preserving generic query-subject collections, one bounded clarification
path, exact provenance, and an honest incomplete result when evidence cannot be fully scanned.

**Acceptance.** Multiple current facts supporting one stable target corroborate it. A singular
read with exactly one safely grounded target proceeds; with 2–4 distinct safe targets it offers
those identities through the existing pending clarification and re-grounds on continuation; with
no safe bounded choice it explains the bounded reason. Self collections use only evidence whose
relationship to the authenticated self is established by Core, and generic collections remain
available. A vault with more than 64 sources/facts or 16 KiB of facts can be scanned in bounded
batches without treating a prefix as complete. Missing evidence, ambiguous scope, stale evidence,
planner inability, and operational failure remain distinguishable in the product projection.

**Out of scope.** No family/relationship ontology or synonym registry, graph recursion,
transitive/co-occurrence inference, Note creation for literals, Notes CRUD, new service, new
clarification engine, browser/n8n semantic authority, provider execution, or deployment.
Existing singular self, note-set, write, and relational complete-set mutation contracts retain
their current authority and fail-closed rules.

**Open product decisions.** None for this corrective slice. The approved #140 contract already
permits a grounded set qualified by its current-note scope or a focused clarification when its
semantic boundary is materially uncertain. It does not authorize a real-world exhaustive claim.
Large final answers remain subject to a bounded presentation limit; exceeding that limit must
give a specific incomplete/too-large reason and a scope-narrowing suggestion, not a partial list
presented as complete. Pagination of very large answers is deferred.

### Minimal data and control flow

```text
validated plan: action + lossless query + single/collection + collection subject(self|query)
    -> Core binds self through authenticated actor + SelfBindingRepository, if requested
    -> Core enumerates eligible current canonical fact batches in stable order
    -> existing bounded selector proposes relevant supplied facts/occurrences
    -> Core projects full selected facts, resolves exact links, deduplicates stable identities
    -> Core checks all batches and canonical inventory/revisions, then ANSWER / CLARIFY / UNAVAILABLE
```

The only new planner-visible collection semantic is `subject_kind=self | query` (field name is an
implementation detail). `query` uses the complete `SelectionCriteria.query`; it needs no separate
planner-generated subject/member wording. `self` contains no user ID, Note ID, path, name, or
identity assertion. It does not reuse `self_target`, which already means the directly selected
person Note. Core resolves `self` from the authenticated actor and supplies only the bound self
Note's current facts plus existing one-hop incoming facts that literally link that Note when those
facts directly support the requested relation. A third-party fact is not eligible merely because
it contains a family-like word, and co-occurrence of two people does not establish a relation.
For `query`, source Notes remain evidence containers; a requested kit or concept need not be a
Note. The selector sees only opaque batch candidate IDs and text; Core alone owns identity and
canonical re-grounding.

For singular relational **reads**, select relevant canonical facts with the existing bounded
fact-selection capability, then project every selected fact's complete exact target set. Group
facts by stable target identity/set before deciding ambiguity. Multiple facts converging on one
identity corroborate it; distinct relevant target identities form the safe option set. A selected
fact with two links contributes both, so the selector cannot silently choose one child from a
complete `Mis hijos...` fact. Incoming one-hop evidence retains the existing source-identity
projection rule. Incomplete links or uncertain relevance fail closed. Keep existing relational
write and complete-set mutation preflight behavior until separately justified; this correction
must not weaken it. Selection remains semantic proposal, not identity authority.

Extend the current `ActionResult.candidate_note_ids` / pending-work projection to carry 2–4
grounded relational identity options and the source fact locator/revision guard. Reuse
`LocalClarificationStore`, `PendingClarification`, `ClarificationOption`, `ClarificationChoice`,
numeric/exact-label matching, and the optional bounded free-text classifier. The one-action
continuation validator should accept a relational singular read, re-resolve the original plan
against current self binding and Markdown, require the chosen identity to remain a safe candidate,
and verify both source and target guards before retrieval. Preserve existing version-1 pending
records or fail closed on incompatible data. One remaining identity proceeds automatically;
more than four, zero, or unsafe identities produce a structured unavailable reason. Arbitrary
scope questions are not squeezed into the identity-choice store.

### Removing the global scan cliff

The 64-source, 64-fact, and 16 KiB limits become **per-selector-batch payload limits**, not total
vault eligibility limits. Core traverses the complete eligible canonical inventory in stable
order; a fact larger than one batch is an explicit `EVIDENCE_ITEM_TOO_LARGE`, never skipped.
Every batch returns only supplied fact IDs/occurrences. Core merges members by stable ID (or exact
literal occurrence), retains each supporting source locator, and re-reads selected facts and link
targets. Before claiming `COMPLETE_WITHIN_SCANNED_SCOPE`, Core verifies that the eligible
canonical path/revision inventory is unchanged and that every batch finished validly. Any added,
removed, modified, unreadable, invalid, or unprocessed eligible source yields stale, incomplete,
or operational status; a selector's empty batch is not global no-evidence. Derived indexes may
accelerate ordering/discovery only after their coverage is checked against canonical inventory;
Top-K recall cannot establish completeness. Batches are finite and individually bounded, with no
fixed total vault count. Existing request time/cost and bounded response limits still fail closed
with a specific reason; they never turn a processed prefix into a complete set. The implementation
should avoid holding every fact and repeated full-vault link reparses when it adds batch iteration.

### Deterministic and live acceptance matrix

| Boundary | Regression cases |
| --- | --- |
| Singular corroboration | Two `Mi mujer` facts -> one Beatriz; semantic `mi pareja` -> same identity; conflicting grounded targets -> 2–4 options, never first-target guessing. |
| Singular multi-member | One `Mis hijos` fact -> Cloe/Bruno clarification; one safe target -> automatic answer; 0, >4, malformed/dangling links -> bounded unavailable reason. |
| Clarification continuation | Number, exact label, bounded free text, unresolved, cancel, new request, duplicate label, stale source/target, changed self binding, actor isolation, and same-ID replay. |
| Self collections | `mis hijos`, `mis padres`, `mi familia` aggregate current self evidence; many third-party distractors never enter self scope; one-hop incoming evidence is literal and direct. |
| Generic collections | Kit literals, mixed links/literals, query subject without a Note, note-set presentation, and existing ordinary single/relational/write paths. |
| Batching/completeness | More than each former global limit, multiple relevant batches, duplicate members across batches, late relevant fact, empty early batch, source mutation/addition/deletion during scan, oversized single fact, output member bound, selector invalid span/timeout. |
| Product reasons | Missing knowledge, ambiguous scope without safe identity options, understood planner escalation, unintelligible input, and operational/provider failure produce distinct safe user messages and developer diagnostics. |

Use disposable fixtures for deterministic Core/runtime E2E tests and the real DEV queries only
after a later authorized deployment. A change to the production planner prompt/schema to emit
collection subject scope is **material model-facing work**. Any changed selector instructions or
structured output are model-facing too. Keep deterministic schema/fail-closed checks, diff the
inherited strongest prompt, and later run a focused `gpt-5.6-luna`/low live gate with frozen
collection, singular, note-set, write, and escalation sentinels plus the new self/query and
multi-fact cases. A deterministic suite or earlier #142 live result cannot validate this changed
contract. No provider call belongs to this challenge.

### v8 failed live evidence and v9 successor gate

At behavior-bearing HEAD `32585c47bab0a90159ce2fc05339aa1c1c22ce5b`, the explicitly authorized
frozen v8 gate ran once with `gpt-5.6-luna` / low. It made two Luna calls and stopped fail-fast:
`SSET01` passed; `SSET02` failed because the planner emitted `collection_subject=self` where the
unchanged frozen oracle requires `collection_subject=query`. The `SSET02` request is a collection
whose member-defining subject is another subject referenced in first-person context; a possessive
does not make the authenticated human its membership anchor. This is a planner-contract failure,
not an oracle failure. No selector row was reached, no retry or Sol fallback occurred, and no
rerun is authorized. The approximate pricing-snapshot cost is `$0.0023114`.

The immutable two-row evidence artifact remains
`benchmarks/.live-results/semantic-self-clarification-v8-luna-gate.jsonl` with SHA-256
`cf4b5b9295f35149840105cca8fc02a2fae6abc066bdfb3307a83123bc7fe35e`; it must never be overwritten,
edited, replaced, or reused.

The smallest inherited prompt correction now defines `self` only when the authenticated human is
the semantic membership anchor. First-person possession, ownership, association, or contextual
reference to another subject is insufficient. When another object, concept, source, or set defines
membership, the planner emits `query` and retains the full self-related wording in the lossless
query. This changes neither schema nor Core semantics and adds no domain vocabulary, relation
ontology, identity assertion, or benchmark-derived example.

`run_live_v9.py` is the distinct successor gate. It reuses the exact byte-checked v8 planner and
selector cases/oracles, including SSET02 unchanged and all four relational selector rows, while
using output path `semantic-self-clarification-v9-luna-gate.jsonl`. It retains confirmation,
exclusive output reservation, per-row flush, fail-fast execution, zero automatic retries, no Sol
fallback, and 25 maximum Luna calls. Recalculation against the revised inherited prompt retains the
conservative no-cache ceiling of `$0.41144` because the fixed 70,000-token per-call bound remains
unchanged. The v9 gate is prepared only and needs new explicit provider-call authorization.

**Packaging.** One coherent corrective PR is reviewable: the planner subject bit, Core
selection/projection/batching, existing clarification continuation, and user-safe outcome mapping
are one end-to-end safety contract. Keep commits/slices narrow inside that PR. Split only if
batching exposes a separate migration or security boundary, which current evidence does not show.

## Merged #142 retrieval boundary (compatibility baseline)

The planner chooses the action, preserves a complete useful `SelectionCriteria.query`, and marks a
`RetrieveAction` as `result_shape=single` or `result_shape=collection`. It does not produce a
subject/member ontology, type prediction, member list, identity, or evidence locator. The existing
`presentation_intent=note_set`/`answer_and_note_set` remains the request for matching **Notes as
objects**; it is not a semantic-member collection. Several matching Notes or several grounded
collection members are results, not an ambiguity. Clarification is reserved for a genuinely
unresolved identity, scope, source, or reference decision.

Core enumerates the complete bounded candidate-fact scope before a collection selector sees it.
The selector receives only the lossless query and visible supplied fact IDs/text and may propose
only those IDs and exact occurrences. Core re-reads current Markdown, resolves links into canonical
identities, retains literal values and source provenance, and fails closed on overflow, stale or
invalid evidence. Source Notes contain evidence; they need not be the semantic subject. A bound
overflow or absent/unsafe evidence maps to `CANNOT_ANSWER`, not a fabricated clarification.
The public outcome vocabulary is `ANSWER`, `CLARIFY`, `CANNOT_ANSWER`; detailed Core outcomes remain
internal. Ordinary single-note answers continue through the established grounded answerer, while
complete collection members and note-set snapshots take bounded deterministic presentation paths.

The #142 planner change required its own focused Luna/low live gate; earlier v3/v4/v5/v6 evidence
remains historical rather than validation of the merged contract. That #142 gate is closed, as
recorded in the roadmap and PR history. One actor/conversation-scoped clarification decision is
retained without a wall-clock TTL. Numeric and exact unique displayed labels resolve first;
explicit cancel clears it. An optional constrained Luna classification can return only a supplied
option, `CANCEL`, `NEW_REQUEST`, or `UNRESOLVED`. A new request supersedes the decision, while an
unresolved reply keeps the original request and asks again. The state contains no hidden reasoning.
For resumed writes, the original explicit request supplies intent, but the selected identity is
re-resolved and its current canonical Markdown is checked before mutation; no extra confirmation
is required. Resumed singular reads likewise re-ground the selected Note. A stale or no-longer-safe
choice cannot authorize a write. The current bounded continuation handles one incomplete
single-target action; larger staged plans remain fail-closed rather than replaying completed work.
The corrective subject/selection changes above need their own later focused live gate; #142's
completed gate does not validate them.

### Historical planner-only live evidence during #142

The first two frozen v3 planner-only attempts each stopped on the first case with an opaque
`APIConnectionError`; their one-row evidence artifacts remain immutable and establish no semantic
or model conclusion. Direct unauthenticated transport diagnostics currently succeed, so no
persistent connectivity defect is established. The experiment now records a bounded chain of
exception **type names only** for a future failure; it retains no exception message, request,
prompt, header, credential, or response content. This changes no semantic/model contract.

Retry2 subsequently reached semantic evidence: SSET01 passed, while SSET02 retained its complete
literal-set meaning and exhaustive request but misclassified the contained-object subject as
`self`. The frozen v3 oracle remains correct: possession by the user does not make the user the
semantic subject. A narrow generic possessive-object versus self rule and a non-evaluation
emergency-bag teaching example are frozen in unexecuted v4; no Core semantic behavior changed.
The separate historical-regression gate remains pending. DEV and PROD remain untouched.

## Objective and acceptance boundary

Answer a request for a finite semantic group from several **current canonical facts**. The semantic
subject in the request and the canonical Notes that contain supporting facts are distinct: a subject
may exist only in fact text and need not resolve to a Note. Include members that are linked Notes,
literal values, or both. Preserve
the exact fact and source Note used. Ask a focused question when identity, group scope, or required
evidence remains ambiguous. Carry validated decisions across several clarification turns, while
re-grounding before every resumed read or write. Show the Notes actually used by a final answer and
real, user-safe progress on long requests.

The acceptance cases are the multi-fact family, literal kit, mixed set, two Martas, uncertain
in-laws, absent kit evidence, changed fact during clarification, long staged request, Bruno/Cena
source navigation, literal-only Kit source navigation, and later manual fact/edit/delete/rename
compatibility. These are **contract scenarios**, not evidence that the model follows a new prompt.

| Scenario | Required result and guard |
| --- | --- |
| A. Family across facts | One self semantic subject; choose relevant current facts across spouse, parents, sibling and children; return their exact linked IDs with source pointers, or ask the smallest material scope question. |
| B. Kit literals | Return `tornillo M4`, `arandela`, `llave Allen` as grounded text spans; create zero Notes. |
| C. Mixed set | One result may contain a linked stable ID and literal values; every member retains its fact occurrence. |
| D. Two Martas | `AMBIGUOUS_REFERENCE`; offer bounded identities, preserve request, then resume after a validated answer. |
| E. In-laws | `AMBIGUOUS_SET_SCOPE` only when current evidence and wording leave inclusion materially unresolved; ask once for that decision. |
| F. No kit evidence | Complete eligible scan with no relevant fact gives `NO_RELEVANT_EVIDENCE`, not a fabricated ambiguity or source button. |
| G. Changed paused evidence | Re-ground on resume; stale source or target invalidates the old decision and causes zero writes. |
| H. Long request | Display only real ordered stage events; no invented timers, prompts, or hidden reasoning. |
| I. Bruno/Cena | Support IDs used by the final answer map to those two exact source Note IDs, deduplicated, and each opens UI-2 detail. |
| J. Literal-only kit | The Kit Note is a valid source row even though its listed pieces have no Note IDs. |
| K. Later Notes CRUD | Fact edit, backlink-choice delete and stable-ID rename enter the same Core pending, preflight, mutation and audit boundaries; no operation is added in this stage. |

The current `SelectionCriteria.relational_reference` is source-relative but chooses one fact and
projects its literal wikilinks as identity members. `RelationshipEvidenceProjector` already reads
current Markdown and can enumerate source facts and one-hop incoming linked facts. Its
`project_targets()` cannot derive a multi-fact set or a literal member. `ContextPackage.related_items`
retains the actual source for related evidence. The answerer already returns
`supporting_item_ids`, but the n8n final response currently discards them. Phase 17B pending work
is durable and create-only; it cannot resume a staged decision. The browser/n8n/runtime product path
is synchronous request/response.

## Architecture challenge

**RECONSIDER** extending v1's one-fact `complete_set` projector or its singular contextual
decision unchanged.

Material concern: one selected fact and wikilinks alone cannot represent multiple relevant facts,
literal members, or a mixed set. Letting a model supply arbitrary IDs or unverified text would
make it an alternate knowledge authority. Calling a ranked Top-K context result a complete set
would silently omit members.

Simpler alternative: keep one `RetrieveAction` and add an optional semantic-set selection intent.
Core receives user semantics only, enumerates a bounded, complete candidate scope from current Markdown,
accepts only selected candidate fact locators and exact member occurrences, and re-grounds those
occurrences before presenting them. Use the established contextual candidate/validator pattern, but
a distinct multi-selection contract because `ContextualResolutionRequest` returns one identity.

Trade-offs: a narrow set selector and completeness guard add one model-facing contract and possible
latency. A broader graph/ontology would add authority and maintenance without proving the product
cases. This design cannot establish a closed-world claim about all real-world members.

Recommendation: **REVISE v1's selection shape and proceed with the bounded set-evidence contract**,
subject to the open decisions below and a later production-model gate. Human decision required
before implementation of any unsettled product scope/retention policy: **YES**. The architecture
review itself changes no schema, service, or data.

Rejected alternatives: family/work/travel-specific handlers; a relation registry; graph traversal;
transitive, inverse, or co-occurrence inference; automatic Note creation for literals; copied facts
for discoverability; a separate Notes-UI mutation path; and a realtime service. Existing v1
`relational_reference` remains backward compatible and is not silently reinterpreted.

## 1–5. Set selection, grounding, members, and completeness

### Lossless planner and typed-member refinement

`SelectionCriteria.query` is the complete normalized human-readable semantic query passed to the
semantic selector. `SemanticSetIntent` is supplemental execution information, never a lossy
replacement: material relation, scope, time, place, state, purpose, possession, context, and
exhaustiveness survive in fields Core consumes. A schema-derived optional `member_type` narrows
the universe of possible **members**, not the Note types that may contain evidence. Core enumerates
the complete bounded current set of that type, then admits a member only through its own applicable
facts or existing one-hop incoming backlink evidence. Any source Note type may supply that evidence;
there is no graph recursion, transitive/inverse/co-occurrence inference, generic Note type, or
automatic creation. Untyped/literal requests retain the bounded canonical fact scan and can return
literal spans alongside linked typed identities. Every final member is re-read and exact-grounded
against current Markdown; scope/evidence overflow is `INCOMPLETE_EVIDENCE` rather than Top-K
truncation or a completeness claim.

`subject_kind=self` means a direct relationship to the authenticated human defines membership (for
example, friends, relatives, travel companions, or colleagues met by that human). A possessive
object, container, or concept is not self-targeting merely because the wording says “my”: when it
owns or contains the requested members, use `subject_kind=query` with bounded subject text. The
possessive word alone never selects the subject kind, and a query subject need not resolve to a
Note.

An optional `SelectionCriteria.semantic_set` describes the **intent**, not the result: a semantic
subject (`self` or bounded user wording), requested members in the user's words, explicit qualifiers, and
whether the request demands an exhaustive set. It is valid initially on `RetrieveAction`; a later
write can reuse the same selection evidence under its ordinary mutation preflight. It is mutually
exclusive with v1 `relational_reference` until a separately evaluated compatibility migration.
There is no new top-level action and no relation-type ontology. Planner output contains no stable
IDs, paths, fact locators, member list, or authority to create Notes.

The proposed wire/domain shape is deliberately narrow (names are illustrative; exact schemas
belong to an implementation review):

```text
SemanticSetIntent {
  subject_kind: self | query,
  subject_query: null | nonempty_text,
  member_query: nonempty_text,
  explicit_qualifiers: bounded_text,
  asks_exhaustive: bool
}
SetEvidenceSelection {
  supplied_fact_ids: bounded_list<opaque_candidate_id>,
  member_occurrences: bounded_list<fact_id + exact_text_span_or_link_occurrence>,
  scope_uncertain: bool
}
GroundedSet {
  semantic_subject, declared_scan_scope,
  members: bounded_list<identity | literal>,
  evidence: bounded_list<source_note_id + fact_locator + source_hash + occurrence>,
  completeness: COMPLETE_WITHIN_SCANNED_SCOPE | INCOMPLETE | UNKNOWN_SCOPE
}
```

The selector's `supplied_fact_ids` must be a subset of the enumerated candidate IDs; it cannot
name facts that Core did not supply. Core retains the candidate-to-source mapping. Neither a
model-selected fact nor a selected occurrence proves semantic relevance on its own: the answer
remains constrained to what its current canonical text directly supports, and focused live
regressions must measure false inclusion as well as omission.

The planner never asserts that a semantic subject resolves to an existing Note. In Slice 1, Core
enumerates **all current visible fact blocks** from the bounded canonical source scope before
selection. This permits a request such as “what is in my emergency bag?” to find a fact in an
unrelated project Note even when neither the bag nor its items has a Note. Candidate discovery may
use a derived index later, but admission always re-reads, parses, validates, and checks canonical
Markdown. Dedupe candidates by source Note ID and fact locator. Never walk from a member to its
neighbors. A project participant or fellow traveler must be explicitly supported by a candidate
fact; shared employer or co-presence alone does not assert a relationship.

Source Notes are provenance containers, not semantic-subject records. Slice 1 introduces no
generic or untyped Note, no subject or member promotion, and no automatic CREATE path. Arbitrary
durable fact text remains queryable as literal evidence under this bounded read-only contract.

The candidate scope has a fixed, measurable limit on source Notes, facts, bytes, and proposed
members. It must be fully enumerated **before** semantic selection or final context Top-K ranking.
Overflow returns `INCOMPLETE_EVIDENCE`; truncation must not produce a seemingly complete set.
The model may propose a subset of supplied fact IDs and exact member occurrences (bounded text
spans or literal wikilinks), and flag uncertain scope. Semantic matching may recognize paraphrase
between the requested subject and fact wording, but it is never canonical proof: only the selected
exact span or literal wikilink is grounded. Core rejects unknown IDs, overlapping or
out-of-fact spans, duplicate unsupported proposals, or any output beyond limits. Core then re-reads
each source and verifies its source hash/revision, fact locator and exact text. Existing
Odyssey-owned atomic facts can use `(note_id, request_id, ordinal)` as the stable locator with an
expected content hash; legacy visible blocks retain a source-hash-bound locator. A changed or
missing fact is `STALE_EVIDENCE`, never a reason to trust the old model selection.

`SetMember` is a tagged value:

| Kind | Value admitted by Core | Evidence and behavior |
| --- | --- | --- |
| `identity` | Existing stable Note ID resolved from a literal link occurrence | Exact canonical source Note/fact/span plus current target identity; eligible for Notes navigation when it actually supplies the answer. |
| `literal` | Exact visible text/value span of the current fact | Exact canonical source Note/fact/span; rendered as text, with no synthesized Note or forced entity resolution. |

The same source fact can supply both kinds. Identity members dedupe by stable ID; literal duplicates
may be normalized only within the same justified scope and retain every contributing fact pointer.
Names and paths are presentation metadata, never identity. Malformed, dangling, ambiguous, deleted,
or stale links in a selected fact make the required set incomplete rather than yielding a partial
identity set. A literal may later be independently resolved under the usual identity contract,
without changing its status in the original fact.

Completeness is explicit: `COMPLETE_WITHIN_SCANNED_SCOPE` means every admitted candidate in the
declared bounded current-fact scope was examined and each selected member was grounded. It does **not**
claim that the user's real-world group is exhaustive. `INCOMPLETE` means a relevant fact/member
cannot be safely projected or the scan bound was reached. `UNKNOWN_SCOPE` means materially different
group interpretations remain plausible. Only an explicit canonical closed-list assertion can
justify a stronger claim that a particular list itself is complete. Ordinary answers use wording
such as “Según tus notas...” and must not assert absent members do not exist.

## 6–7. Resolution outcomes and staged clarification

Core returns a bounded `ResolutionOutcome` independent of final prose:

| Outcome | Core meaning | Normal presentation |
| --- | --- | --- |
| `ANSWERABLE` | Requested members and support are grounded within declared scope | Answer, with scope qualifier when needed. |
| `AMBIGUOUS_REFERENCE` | More than one safe identity/reference candidate where a later interaction needs identity binding | Ask which named candidate the user means. |
| `AMBIGUOUS_SET_SCOPE` | Distinct relevant inclusion rules remain plausible | Ask the smallest scope question, e.g. include in-laws? |
| `INCOMPLETE_EVIDENCE` | Relevant fact cannot produce a safe full member set, or bound exceeded | Explain the missing/partial basis; ask only if a bounded choice can resolve it. |
| `NO_RELEVANT_EVIDENCE` | The completed eligible scan found no relevant fact | Say no relevant information was found. |
| `STALE_EVIDENCE` | Canonical source changed before use/resume/commit | Recheck current evidence; re-clarify if the old choice no longer holds. |

An operational failure remains a separate bounded failure, not `NO_RELEVANT_EVIDENCE`. Reason
codes, counts, and stages may go to advanced telemetry; no hidden reasoning, prompt, candidate
payload, or provider internals go to the normal user. If two plausible Martas remain, ask; if the
current family facts include a plausible in-law boundary not specified by the question, ask scope;
if the kit has no eligible facts, report absence. A single valid candidate after deterministic
filtering continues without an unnecessary question. Answers must never silently omit unresolved
members or commit a required write while a decision is open.

Extend actor-local `state/pending` as a **versioned clarification state machine**, retaining v1
records through explicit compatibility reading. One logical request retains its original request ID
and validated plan, one currently unresolved decision key/stage, bounded candidate IDs and safe
labels, accepted deterministic choices, and source revision/hash guards. It stores neither model
reasoning nor canonical fact copies as a second authority. The user may choose an offered option or
reply in free text; free text is interpreted under the same bounded candidate and validation rules.
Persist each stage/response with an idempotency key and compare-and-swap version under a per-record
lock; reject duplicate conflicting answers and cross-actor access. A second ambiguity creates a
new stage after the first validated decision. Reuse the plan and still-valid decisions where safe;
re-ground **all** affected facts, identities, revisions, schema and permissions before any resumed
read or mutation. On drift, invalidate the affected decision and re-clarify or return
`STALE_EVIDENCE`. Existing pending serialization must preserve every validated selection field,
including v1 `relational_reference`; unknown versions fail closed. The stage response shape is
`{original_request_id, stage_id, stage_version, choice_id | free_text, response_request_id}`;
Core checks that it addresses the one open stage for the authenticated actor and that replaying the
same response is idempotent.

If any required decision affects a write, **all writes in that logical request** wait until the
decision sequence is complete. The whole logical mutation group is preflighted before its first
write; clarification cannot follow a partial commit of that group. Independent action completion under today's
`ApplicationResult.partial` contract is a different, explicitly reported condition and must not be
misrepresented as atomic group success.

## 8–9. Answer sources and Notes navigation

Add a bounded final `evidence_sources` presentation field, distinct from `ContextPackage` (which
contains candidates) and `note_result_snapshot` (which represents a Notes result/affected set).
Each row contains stable `note_id`, display label, note type, and optional source revision/hash or
bounded evidence ID. No filesystem path or arbitrary URL is needed for navigation. Core supplies
the mapping from each grounded evidence item ID to its canonical source Note ID. After the grounded
answerer returns `supporting_item_ids`, the presentation boundary validates them against the exact
submitted evidence set, selects only supported items, deduplicates their source Note IDs, and
projects the corresponding Core-supplied safe metadata. n8n can perform this narrow mapping; it
does not decide semantics from answer text. Unsupported IDs, missing source metadata, or an answer
with no valid support fail closed. The normal result and durable assistant turn retain the bounded
field for reload; the advanced inspector can keep richer support IDs separately.

Thus Bruno Test plus Cena relacional de prueba appear only if evidence from both actually supports
the final answer. A literal-only kit answer can show its Kit source Note. No contributing Note means
no provenance control. The browser renders `Ver nota usada` / `Ver notas usadas · N`, lists these
rows, and invokes the existing UI-2 `detail(note_id)` operation for the chosen stable ID. It never
searches by name, parses answer prose, constructs a path, or creates a Note. If a source is later
deleted/renamed, detail resolves the current stable ID or displays unavailable; the historical
answer's provenance is not silently rebound to a similarly named Note. Inline entity hyperlinks
remain optional later work.

## 10–11. Real progress and transport

Emit coarse, enumerated progress events from actual application stage boundaries: request
accepted, planning, retrieving, examining related facts, resolving, awaiting clarification,
validating mutation, applying change, refreshing projections, preparing answer, and terminal
completed/failed where the owning component can truthfully observe them. Each event carries
request ID, monotonic sequence, event code, timestamp and only bounded safe metadata such as a
count. Core/runtime own Core stages; n8n owns answerer start/end and public completion. UI-1's
timings/provider diagnostics stay a separate advanced record. Neither frontend timers nor raw
model output become progress evidence.

Recommend **bounded polling** after a short browser delay through an authenticated same-origin n8n
operation and a read-only runtime status view. Keep the per-request event ring ephemeral, size/TTL
bounded, actor/root scoped, available outside the serial product execution lock, and keyed by the
existing request ID plus authenticated context. Return only events after a sequence cursor; stop
polling when the product response arrives. A fast request may show none. Unknown/expired status
after restart is normal; the final response and same-ID retry contract remain authoritative. The
answerer boundary must publish its own truthful event if its interval is shown. SSE through the
existing synchronous n8n workflow would add streaming, connection and auth behavior at several
boundaries without a demonstrated need; do not add a realtime service. Prefer reusing an existing
protected same-origin route with a narrow operation if its ingress contract permits it; any new
public path requires a separate full ingress/Access coverage review before implementation.

The browser controls only display. It never selects facts, resolves identities, authorizes a
clarification, infers evidence sources, or decides whether a write can commit.

## 12–13. Correctness, atomicity, and future Notes CRUD

Key risks are false semantic inclusion, missing candidates due to a hidden Top-K cutoff, an
unverified literal span, stale source/target identity, scope drift across clarifications,
cross-actor pending/progress access, replay of an old decision, unsupported provenance IDs, and a
partial multi-note mutation. Fail closed at each Core boundary; bound all candidate and response
payloads; use stable IDs and exact revisions/hashes; never treat `request_id` alone as authorization.

Today a validated single-note replacement can be atomic at the filesystem rename boundary, with
revision/stale-write checks. A complete-set shared fact stored once on a natural source can use
that single-note boundary after **all** member bindings are prepared. Current ordered actions and
bulk operations do not supply a true multi-file transaction: a later failure may follow an earlier
Markdown write. Request-correlated Git is an audit/recovery aid after mutation and can fail without
rolling Markdown back; index refresh is rebuildable and may lag. Do not claim ACID across Notes,
Git and indexes. For any future logical multi-note operation requiring all-or-nothing semantics,
design a Core-owned prepare/validate, guarded commit, durable recovery/compensation protocol before
enabling that operation; a preflight alone does not make a crash-safe batch. Do not silently cascade
reference deletion. Idempotent request IDs and current revision guards must prevent duplicate facts
or repeated destructive writes where the operation promises retry safety.

Issue #134 remains a **later stage**. Its direct UI commands would submit typed intent into the
same Core mutation path as chat:

| Future operation | Reused boundary; remaining later decision |
| --- | --- |
| Create fact in selected Note | UI provides stable target ID; Core splits/validates text, resolves explicit or natural references, binds links and checks revision. |
| Edit/delete fact | Exact stable Note ID + fact locator + expected revision; same staged clarification and preflight, then guarded mutation. |
| `@` picker | Selection passes an existing stable ID into normal `KnowledgeReference` binding; display label is not authority. |
| Multi-select delete | Explicit selected stable IDs and backlink inventory; ask for cleanup/preserve choice, verify broken-link policy, then use the future transaction/recovery boundary. No implicit cascade. |
| Rename | Preserve stable ID; validate collisions, aliases, path/link implications and stale revision through Core before mutation. Do not equate title/path with identity. |

The future UI must not write Markdown directly or introduce another mutation system. This design
does not decide whether Notes deletion becomes permanent, whether broken links may be preserved, or
whether a new entity may be created from the picker. Those #134 product decisions remain open.

## Migration and compatibility risks

The optional `semantic_set` selection must parse as absent for old plans and coexist with the
unchanged v1 relational reference contract; unknown new fields and contradictory intents fail
closed. A new pending-record version must read existing v1 records without inventing missing
clarification state. Current pending projection appears to omit the v1 `relational_reference` field,
so its round-trip must be corrected before any staged resume assumes persisted plans are complete.
The final product response adds optional `evidence_sources` and resolution metadata; old clients
can ignore them, while the updated browser validates count, shape, IDs and safe labels before
rendering. Saved UI-0 turns without sources remain valid and show no provenance control. New Notes
navigation resolves stable IDs at click time, so path/name changes do not redirect a historic
answer by guesswork. Existing UI-1 telemetry retains its separate advanced shape. A later progress
operation must be compatible with the current request/response flow and effective authenticated
ingress, including any alternate host; it is not inferred from a local route declaration alone.

## 14. Proposed implementation slices and verification

1. **Core set evidence and outcomes.** Add optional retrieval intent, bounded candidate admission,
   multi-fact selection, identity/literal projection and explicit completeness/reason outcomes.
   Preserve v1 behavior. Deterministic A/B/C/E/F/G cases and overflow/stale/malformed-link guards
   belong here. Any planner or selector prompt/schema change uses inheritance from the validated
   prompt and needs a focused production-model gate before adoption.
2. **Staged clarification and mutation gate.** Version pending work, resume/CAS semantics,
   repeated smallest decisions, re-grounding, and no mutation before all required decisions. Test
   D/E/G/K, concurrent replies, idempotent retry and stale write. Keep #134 operations deferred.
3. **Answer source navigation.** Carry validated support IDs into bounded `evidence_sources`,
   persist with the assistant turn, and navigate to UI-2 detail by stable ID. Test I/J, duplicate
   support, fabricated ID, no Note source, renamed/deleted source and browser reload. If answerer
   instructions/output schema change materially, evaluate source attribution live.
4. **Progress surface.** Add actual event emission, authenticated bounded polling and ephemeral UI.
   Test H plus fast/no-events, cross-actor denial, restart/expiry, sequence, n8n answerer boundary,
   and transport failure. Review every effective public ingress before adding a path.

Deterministic regression also covers ordinary singular v1 resolution, source writes, pending v1
readability, conversation retry, UI-1 telemetry, UI-2 detail/backlinks, schema validation,
request-result serialization, and Git/index failure boundaries. Focused live evaluation belongs
only to later implementation PRs that materially change model-facing instructions/contracts:
use the production Luna planner and current reasoning configuration, the chosen bounded selector,
and existing answerer configuration with frozen representative and regression sentinel cases.
Include family/work/travel/project/recipe/kit, literal/mixed sets, ambiguous names/scope, no
evidence and stale authority; compare unsafe false answers and partial sets, not just pass rate.
No provider/model call is part of this design challenge.

### Slice 1 approved deterministic bounds

Slice 1 fixes only the evidence-selection ceilings needed before a selector receives candidates:

| Limit | Value | Deterministic rationale |
| --- | ---: | --- |
| source Notes | 64 | Aligns generic source discovery with the existing 64-ID result budget while keeping a complete snapshot feasible. |
| candidate facts | 64 | Bounds fragmented visible fact blocks without reusing final retrieval Top-K reduction. |
| serialized candidate bytes | 16 KiB | Matches the existing bounded `note_result_snapshot` encoded-payload ceiling, including Core-owned source ID and locator framing. |
| proposed members | 64 | Matches the candidate-fact ceiling and rejects output expansion beyond the supplied evidence. |

The resolver performs the complete all-current-visible-facts scan before testing any of these ceilings.
If any ceiling is exceeded it returns `INCOMPLETE_EVIDENCE`; it does not select from a prefix. The
later Slice 2/3/4 retention, provenance-row and progress limits remain open as stated below.

The inherited Luna planner prompt/schema grows from 9,932 to 10,358 serialized compact-schema
bytes for the active registry. The old frozen relationship live-run authorizations therefore fail
their deterministic pre-provider cost guard (`$0.469024 > $0.46` for the ten-case run and
`$0.3785896 > $0.37` for its continuation). Slice 1 performs zero provider calls and does not
replace either authorization; a later focused gate needs fresh explicit cost authority.

The corrected subject-independent contract measures 25,742 production prompt bytes and 10,361
compact planner-schema bytes for the fixed context, versus 25,525 and 10,358 before this correction.
Its dedicated future six-case Luna gate uses one generic textual-subject teaching example, has a
27,203-byte rendered Luna prompt, a 10,685-byte Luna output schema, and a 37,938-byte maximum
serialized request. The checked-in pricing snapshot still yields a conservative no-cache ceiling of
`$0.0987456`; the gate remains unexecuted and requires new explicit authorization.

## Open decisions before implementation approval

- Confirm the current issue #140 body and reconcile any additional acceptance rule with this
  proposal. The design review could not verify that body under the no-API-call constraint.
- Choose user wording/confirmation policy for an observed but non-exhaustive set when the question
  implies “all”; never promise real-world completeness from an open-world vault.
- Set exact candidate, source-byte, member, provenance-row, and progress ceilings using
  deterministic budget evidence, not an arbitrary unbounded default. Clarification v1 has no TTL.
- Before #134 implementation, decide broken-link preservation, soft versus permanent deletion,
  and the transaction/recovery contract for multi-note mutations.

No production behavior, schema migration, provider choice, deployment, Notes CRUD, Cloudflare,
workflow semantics, or vault/state mutation is authorized by this document alone.
