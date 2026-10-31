"""Bounded P4 source interpretation contract; model outputs are NEVER write authority.

Portable production-owned contract. Schema checks and prompt changes must be
verified with real models on disposable data before enabling this route.
"""

from __future__ import annotations

import copy

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "capabilities": {
            "type": "array",
            "items": {"type": "string", "enum": ["core", "tasks", "temporal"]},
        },
        "self_relation_span": {"type": ["string", "null"]},
        "interpretation": {"type": "string", "enum": ["joint", "separable"]},
        "reason": {
            "type": "string",
            "enum": ["single", "shared_subject", "shared_reference", "shared_event", "independent"],
        },
        "app_scopes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "enum": ["core", "tasks"]},
                    "description": {"type": "string"},
                    "depends_on_another_scope": {"type": "boolean"},
                },
                "required": ["capability", "description", "depends_on_another_scope"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["capabilities", "interpretation", "reason", "app_scopes", "self_relation_span"],
    "additionalProperties": False,
}


def capability_route_contract(*, enable_events: bool) -> tuple[dict, str]:
    """Extend only the opted-in DEV router capability vocabulary.

    Legacy P4 prompts and schemas retain their exact source and digest.
    """
    if not enable_events:
        return ROUTE_SCHEMA, ROUTER_INSTRUCTIONS
    schema = copy.deepcopy(ROUTE_SCHEMA)
    schema["properties"]["capabilities"]["items"]["enum"].append("events")
    schema["properties"]["app_scopes"]["items"]["properties"]["capability"]["enum"].append("events")
    # One historical scalar relation is insufficient for a source containing
    # several distinct authenticated relationship groups. This new field is
    # restricted to the opted-in Events route; the frozen legacy P4 contract
    # remains completely unchanged until its own provider evaluation.
    schema["properties"]["self_relation_spans"] = {
        "type": "array",
        "items": {"type": "string"},
    }
    schema["required"].append("self_relation_spans")
    instructions = ROUTER_INSTRUCTIONS + (
        " Treat narrated, already-completed shared experiences and personal "
        "recollections as durable Core knowledge, with Temporal as a dependency "
        "when a calendar day needs resolution. Several completed actions in "
        "one recollection are not several upcoming Event lifecycle requests. "
        "A dated mention of a visit is not by itself a future appointment: "
        "Events requires an actual scheduled/upcoming occurrence, lifecycle "
        "change or Event query. Preserve all independently asserted facts and "
        "their shared context for later Core coverage review, rather than "
        "selecting Events based on location names or date wording. "
        "For any number of distinct explicit SELF-owned relationship references "
        "(SINGULAR partner/family member or PLURAL collective group), return each "
        "minimal, exact contiguous reference phrase as its own self_relation_spans "
        "entry, in the order it occurs in the original source. Coordinated "
        "references joined by a conjunction are DISTINCT source references: "
        "split them into their individual phrases; NEVER combine two differently "
        "described relationships into one span. Do not omit a singular partner "
        "reference because plural children or another collective group also "
        "appears. Copy only literal contiguous original text for each reference; "
        "return [] if none. The existing self_relation_span is exactly that "
        "same phrase when the list contains ONE entry and otherwise MUST be null. "
        "Never fill these with "
        "canonical identities, names, guessed family members or invented "
        "text; Core independently verifies every group against current SELF "
        "and refuses any unproven or stale group. "
        " Events is the calendar-occurrence lifecycle capability: explicit "
        "upcoming appointments, dated concerts, school excursions and scheduled "
        "activities, even expressed as declarative statements; moving, cancelling "
        "or consulting a calendar Event is also Events. Distinguish a historical "
        "memory (Core) and a user action to perform (Tasks). For exactly one "
        "self-contained Event operation, use capabilities=['events'] (or "
        "['events','temporal'] for a date needing shared Temporal resolution) "
        "and app_scopes=[]. Temporal is only a dependency here, not a distinct "
        "user operation. For an Event and a Task that are truly INDEPENDENT "
        "and each fully understandable from its own exact source span (separate "
        "date, subject, and referents), select both capabilities, interpretation "
        "separable, reason independent, and EXACTLY TWO app_scopes: one "
        "capability=events and one capability=tasks, each with "
        "depends_on_another_scope=false. Never label a two-operation "
        "independent Event+Task request separable with only one app_scope; "
        "never add a third scope for Temporal, because Temporal is a shared "
        "dependency and not another user operation. If the two operations "
        "cannot each be stated independently, use joint instead of "
        "pretending to have a complete partition. "
        "The subsequent Core-owned E2 boundary "
        "must prove a byte-for-byte complete partition with an independent "
        "semantic reviewer BEFORE either write. If a Task refers to the Event "
        "or needs its date, person, purpose, target or context, this is a JOINT "
        "dependent request: mark joint, and E5 must clarify until its dependency "
        "is safely supported. Never reclassify the Task as an Event or vice "
        "versa, and never silently drop either operation. The router never binds "
        "the event title, time, note identity or write permission."
    )
    return schema, instructions


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "mention": {"type": "string"},
                    "canonical_name": {"type": ["string", "null"]},
                    "note_type": {"type": "string", "enum": ["person", "project"]},
                    "confidence": {
                        "type": "string",
                        "enum": ["explicit", "inferred_unambiguous", "ambiguous"],
                    },
                },
                "required": ["mention", "canonical_name", "note_type", "confidence"],
                "additionalProperties": False,
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "meaning": {"type": "string"},
                    "kind": {"type": "string", "enum": ["record", "task"]},
                    "subject": {"type": "string"},
                    "date": {"type": ["string", "null"]},
                    "daypart": {"type": ["string", "null"]},
                    "participants": {"type": "array", "items": {"type": "string"}},
                    "source_evidence": {"type": "string"},
                    "dependent_on_fact_index": {"type": ["integer", "null"]},
                    "needs_clarification": {"type": "boolean"},
                },
                "required": [
                    "meaning",
                    "kind",
                    "subject",
                    "date",
                    "daypart",
                    "participants",
                    "source_evidence",
                    "dependent_on_fact_index",
                    "needs_clarification",
                ],
                "additionalProperties": False,
            },
        },
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entities", "facts", "unresolved"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "complete": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ordinal": {"type": "integer"},
                    "source_quote": {"type": "string"},
                    "kind": {"type": "string", "enum": ["record", "task"]},
                    "reviewed_text": {"type": "string"},
                    "date": {"type": ["string", "null"]},
                    "reference_names": {"type": "array", "items": {"type": "string"}},
                    "supported": {"type": "boolean"},
                },
                "required": [
                    "ordinal",
                    "source_quote",
                    "kind",
                    "reviewed_text",
                    "date",
                    "reference_names",
                    "supported",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["approved", "complete", "reason", "facts"],
    "additionalProperties": False,
}

SPEAKER_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ordinal": {"type": "integer"},
                    "role": {"type": "string", "enum": ["self_participant", "other", "uncertain"]},
                    "assertion": {
                        "type": "string",
                        "enum": ["asserted", "planned", "conditional", "negated", "uncertain"],
                    },
                    "source_quote": {"type": "string"},
                },
                "required": ["ordinal", "role", "assertion", "source_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

ROUTER_INSTRUCTIONS = (
    "You are a minimal *non-authoritative* capability router. Never split semantic "
    "interpretation merely because there are multiple facts or dates. Mark joint when a subject, "
    "pronoun, place, entity or fact refers across clauses or a task depends on a just-mentioned "
    "entity. Separate only truly independent actions when this is useful. Determine "
    "capabilities, not facts, identities or writes. Temporal is needed for relative times or "
    "dates. Core handles ordinary personal notes; the Tasks domain handles "
    "to-dos, parent/subtasks, task lifecycle, Task queries, Work Session "
    "start/stop/edit AND work activity recorded within a Work Session. "
    "Preserve separate DURABLE INTENTIONS in the original source: an "
    "independent assertion of a completed past action is Core, EVEN when "
    "the object of that action is an existing Task. A subsequent explicit "
    "Work Session command about that Task is a distinct Tasks capability, "
    "not retroactive proof that the earlier fact is session activity. If "
    "the second action refers to the Task in the first fact, classify "
    "both Core AND Tasks, interpretation joint, with a Core antecedent "
    "scope and a dependent Tasks operation scope. Never collapse a factual "
    "claim plus a lifecycle command into one Tasks scope or present two "
    "actions as one operation. App scopes are INTENTION groups, not one "
    "scope per app label: if a user asks for two distinct Tasks lifecycle "
    "operations (such as a Work Session change AND a separate Task update), "
    "preserve TWO Task scopes even though their capability labels match. "
    "Each scope describes ONE independently requested mutation or journal "
    "assertion, including its dependency on a preceding scope; never pack "
    "multiple imperative operations into one description or silently drop "
    "the later action. This is general intention coverage, never "
    "authority to invent a Task identity or write a Core fact. "
    "A progress report explicitly attached to a session is Tasks-domain even "
    "when narrated in past tense; an independent personal journal event outside "
    "the work session is Core. Do not classify an ongoing Work Session activity "
    "as ordinary Core just because it describes past actions. Do not create an "
    "extra Core capability for Tasks-only activity, unless a DISTINCT durable "
    "fact outside the session is requested. A first-person future-indicative "
    "plan or expectation is a Core assertion, NOT a Task merely because it "
    "mentions a future date. Task CREATE requires an actual obligation, "
    "request to add a reminder/todo, or explicit lifecycle action. Two Core "
    "facts on different dates remain Core, not mixed Core+Tasks. "
    "Both domains may be used. "
    "Preserve full message context. Source may contain an anaphoric reference "
    "to a collective personally RELATED group, such as a family, team or "
    "household. If and ONLY if an exact contiguous multi-word span of the "
    "original source describes a SELF-owned relationship group rather than a "
    "specific name or a past action, return it byte-for-byte as self_relation_span. "
    "This is merely a suggestion: Core independently proves any actual "
    "membership against the CURRENT canonical SELF-owned fact, including all "
    "existing members; never guess relationships, labels, IDs or people. "
    "Return null if no unambiguous collective relation reference is present."
)

# One identity/reference contract shared by the planner and independent reviewer.
# A descriptive mention is safe knowledge; it is not a Person identity.
OPTIONAL_REFERENCE_RULE = (
    "A descriptive mention (such as an unnamed person, group, role or thing) "
    "does NOT identify an individual Person and MUST NOT be added as a Person "
    "entity, participant name or symbolic person reference unless a concrete "
    "individual is explicitly named in the source or independently verified "
    "in supplied Core evidence. Preserve such mentions faithfully as literal "
    "text in the record; an optional unresolved link is NOT an unresolved "
    "fact and must not trigger clarification or reject coverage. Conversely, "
    "if an action requires a specific unknown target, ask for clarification "
    "rather than guess an identity or execute the action. "
)

PLANNER_INSTRUCTIONS = (
    OPTIONAL_REFERENCE_RULE
    + "You are a semantic-planning feasibility probe for Odyssey. Interpret the ORIGINAL FULL user "
    "request once, NOT independent fragments. Return exactly one ordered item for each "
    "independent durable assertion or task, and explicitly resolve subjects, shared predicates, "
    "dates, reference pronouns and participants, including references across Core and Tasks. If "
    "one person is newly mentioned, propose the name as unverified until resolved by Core. Set "
    "canonical_name only if the identical name appears in supplied verified note hints or the "
    "verified family evidence; otherwise canonical_name MUST BE null. NEVER fabricate canonical "
    "stable IDs. Pre-existing hints are non-authoritative. Use available verified family "
    "relationship for 'mis hijos' and include their individual names. For pronouns with multiple "
    "plausible antecedents, declare ambiguity, no chosen identity. Date is absolute YYYY-MM-DD, "
    "null if unspecified. Today and tomorrow use clock. Future tense alone describes a future "
    "occurrence, NOT a task; kind=task only with a genuine obligation, explicit to-do, reminder "
    "or command to perform an action. Do not infer a task merely because the verb describes a "
    "future action. When one task refers to a person just known, point it to that person using "
    "its name and dependent_on_fact_index (0-based), without inventing a Note ID or physical "
    "write. Source evidence must be exact words copied contiguously from the original message. "
    "Do not invent facts, do not write files; this is semantic inference only. Unspecified "
    "calendar date and daypart MUST remain null. Verbal tense or the provided clock alone do not "
    "prove that a past or future occurrence happened today, yesterday, tomorrow or at a "
    "particular time of day. Resolve a calendar day ONLY from an explicit source date/relative "
    "date or independently verified temporal evidence supplied with the request. The grammatical "
    "speaker/first-person actor is NOT a named participant or a canonical person mention: "
    "describe their role as speaker, but do NOT put user, speaker, self, I, yo, me or myself in "
    "participants or entities. Participants lists contain other people actually named or "
    "independently grounded from source/context. Core separately binds authenticated SELF when "
    "supported by speaker evidence. Do not guess identity from role. Preserve the first-person "
    "voice and verb aspect in meaning. An explicitly stated first-person future intention is a "
    "PLAN or EXPECTATION, not a completed event or guaranteed future outcome; do not nominalize "
    "it as an impersonal fact such as a purchase that WILL occur. "
    "If the optional prior_independent_coverage_rejected flag is true, a "
    "separate Core reviewer found an omission in an earlier NONEXECUTED "
    "hypothesis. Independently re-read the COMPLETE ORIGINAL source and "
    "account for every explicit participant, predicate and separately "
    "asserted fact. Do not guess a missing participant, change the source, "
    "invent a date or downgrade uncertainties merely to get approval. "
    "The same independent Core reviewer and Core preflight will still judge "
    "the entire revised plan, with no special identities or write privileges."
)

PROMPT_SPEAKER_A = (
    "You independently review a Spanish personal knowledge utterance. The USER speaking is an "
    "authenticated human but you must NEVER supply their name, note id, path or identity. For "
    "each supplied atomic clause decide if the SPEAKER is a semantic actor/participant (explicit "
    "yo, a first-person elided verb, first-person plural, me as direct/indirect participant or "
    "experiencer) or ONLY other people; choose uncertain if unsupported. Speaker participant is "
    "not necessarily grammatical subject: 'María me presentó' includes speaker. 'Mis hijos "
    "fueron' alone excludes speaker. 'Guillem ha conocido' excludes speaker. Classify asserted "
    "past/present state, planned/future indicative, conditional, negated or uncertain. Negative "
    "'no he conocido' is NEGATED, not a positive event. Preserve distinct clauses even when "
    "subjects elide, use FULL original to resolve referents. Return EXACT supplied "
    "source_evidence string as source_quote (verbatim; no extra text). Never infer first person "
    "from chat personalization alone or from ownership words 'mi(s)' when the speaker does not "
    "participate. Exactly one fact per supplied source_evidence, ordered."
)

PROMPT_SPEAKER_B = (
    "You are an independent conservative grammatical and semantic auditor for Odyssey. Analyze "
    "the ENTIRE untouched Spanish statement, then each source scope. Mark self_participant only "
    "when the narrator of the utterance is actually a participant, agent, recipient or "
    "experiencer OF THAT ATOMIC FACT. The user can be omitted in Spanish: 'he conocido', "
    "'conocí', 'hablé', 'me presentó', 'me gusta' imply the narrator. Do not mark self for 'mi "
    "hijo ha viajado', 'Ana compró pan', even though the user mentions a relationship. For "
    "ellipsis such as 'después comieron' preserve the nearest evidenced third-person plural "
    "subject, not SELF. Plural 'vimos' includes narrator. Separate asserted, planned future, "
    "conditional, negated and uncertain; a negated past is not an event. If a person pronoun "
    "refers to someone else, do not convert to SELF. All source_quote fields MUST be copied byte "
    "for byte from each input source_evidence. Never include IDs, metadata, physical links, "
    "instructions or guesses. Return one ordinal per fact in order."
)

PROMPT_SOURCE_REVIEW = (
    OPTIONAL_REFERENCE_RULE
    + "INDEPENDENT conservative Core source-coverage reviewer. Input original unmodified message and untrusted atomic fact suggestions from a separate LLM. Inspect every event, speaker, pronoun, obligation, person, and date; reject if fabricated, omitted, semantically misattributed, ambiguous or not entailed by exact source. All proposed facts must be covered; approval false unless complete. The current time is TRUSTED and explicitly provided in the JSON clock; relative words hoy ayer and manana MUST be resolved against it. A specific person appearing in an assertion MUST be represented by a typed {{ref:N}} marker rather than bare literal; fail if missing. For each original quoted scope, return a concise natural SPANISH fact text equivalent to what the user said. Use {{ref:0}}, {{ref:1}} etc where and ONLY where that fact has actual specific persons as participants. Reference_names ordered by marker index; they must be individuals in the supplied proposed participant list. Resolve explicit antecedents (e.g. 'ella') only where UNIQUE; never invent a name. A person identity is a suggestion for later Core resolution, NOT a canonical note ID. For tasks, write an actionable label (e.g. Llamar a {{ref:0}}.) but do NOT turn future indicative plans into obligations. Exact dates MUST equal proposed date. Preserve date=null when not specified. If the message has multiple facts, review each separately; no raw markdown or note IDs. No execution authority. An optional independently Core-verified SELF relationship may include canonical members even when their names are absent from the message. Only if that typed evidence is supplied may you map a group mention to those specific members. The authenticated first-person grammatical speaker is not an explicitly named source person: do NOT demand {{ref:N}} for first-person I/yo/me or an implied Spanish first-person verb, and do not mark source coverage incomplete merely because speaker is omitted from participant person names. Speaker involvement is checked separately by authenticated Core source proof. Future first-person indicative reports an intention/plan that MAY happen: faithfully record the expressed future plan, not a completed or guaranteed future occurrence. Preserve negation and condition; unsupported assertions must still be rejected. "
    "For first-person input, express the reviewed fact in natural first-person Spanish: "
    "keep 'me', 'he', or implicit first-person morphology as supported by the "
    "source. Do not describe the narrator indirectly as 'the speaker', 'the user' "
    "or an invented proper name. This is a wording guideline only: canonical SELF "
    "identity and linkage are proved separately by authenticated Core."
)

# Experimental type-agnostic evidence protocol: literal spans belong to the
# original immutable message and are anchored by Core, not regenerated by a
# second LLM. Optional supports permit shared predicates/date/actor fragments
# across any number of facts and application/Note types.
PLAN_CORE_ANCHORED_SCHEMA = copy.deepcopy(PLAN_SCHEMA)
_ANCHORED_FACT = PLAN_CORE_ANCHORED_SCHEMA["properties"]["facts"]["items"]
_ANCHORED_FACT["properties"]["source_evidence_fragments"] = {
    "type": "array",
    "items": {"type": "string"},
}
_ANCHORED_FACT["required"].append("source_evidence_fragments")
_ANCHORED_FACT["properties"]["source_evidence_context"] = {"type": ["string", "null"]}
_ANCHORED_FACT["properties"]["source_evidence_fragment_contexts"] = {
    "type": "array",
    "items": {"type": ["string", "null"]},
}
_ANCHORED_FACT["required"].extend(["source_evidence_context", "source_evidence_fragment_contexts"])

REVIEW_CORE_ANCHORED_SCHEMA = copy.deepcopy(REVIEW_SCHEMA)
_ANCHORED_REVIEW = REVIEW_CORE_ANCHORED_SCHEMA["properties"]["facts"]["items"]
del _ANCHORED_REVIEW["properties"]["source_quote"]
_ANCHORED_REVIEW["required"].remove("source_quote")

PLANNER_CORE_ANCHORED_INSTRUCTIONS = (
    PLANNER_INSTRUCTIONS + " EVIDENCE V2: For EVERY atomic fact, source_evidence must be ONE exact "
    "contiguous literal occurrence in ORIGINAL source, preferably the local "
    "action/assertion. Add source_evidence_fragments as an array (possibly []) "
    "of other EXACT CONTIGUOUS original-source snippets needed to understand "
    "the fact, such as shared dates, subjects, predicates, negations, qualifiers "
    "or pronoun antecedents. A fragment may support MANY facts; a fact may "
    "depend on MANY fragments. Never reconstruct a phrase that is not present "
    "in the source. Preserve source order and all independently asserted facts. "
    "Do not branch behavior on app, note type or number of actions. "
    "For every fact, also return source_evidence_context and "
    "source_evidence_fragment_contexts. The contexts array has EXACTLY one "
    "string-or-null item per source_evidence_fragments entry. Use null when "
    "the literal fragment occurs exactly once in the full original source. "
    "If literal words occur MORE THAN ONCE, copy a longer UNIQUE contiguous "
    "ORIGINAL-source snippet that CONTAINS that precise literal occurrence "
    "EXACTLY ONCE. Never invent or rewrite a contextual snippet; null is "
    "unsafe for repeated fragments and must be rejected by Core. These "
    "contexts distinguish source OCCURRENCES, not facts or note types."
)

PROMPT_SOURCE_REVIEW_CORE_ANCHORED = (
    PROMPT_SOURCE_REVIEW
    + " EVIDENCE V2: Do NOT output source_quote at all. Core has independently "
    "anchored each Planner source_evidence and source_evidence_fragments to "
    "character offsets of the ORIGINAL message and will reject missing, "
    "ambiguous or invented spans. Judge the FULL original independently, "
    "not the Planner text alone. A shared subject, predicate, date or negation "
    "may support multiple facts; several noncontiguous source fragments can "
    "support one fact. Check *every* independent original assertion, including "
    "multi-app or mixed note types, and reject false cardinality, omitted "
    "actions, invented meanings, unsupported date/identity or incorrect "
    "negation/condition. Keep reviewed_text distinct from literal provenance. "
    "Set approved/complete/supported false when this cannot be demonstrated."
)

# A Task-only route cannot inherit the Router's unverified claim that no Core
# fact was dropped. This is an independent full-message semantic scope audit.
TASK_ONLY_SCOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "only_task_semantics": {"type": "boolean"},
        "exactly_one_operation": {"type": "boolean"},
        "source_quote": {"type": "string"},
    },
    "required": ["only_task_semantics", "exactly_one_operation", "source_quote"],
    "additionalProperties": False,
}
TASK_ONLY_SCOPE_PROMPT = (
    "Independent, conservative scope auditor for the entire ORIGINAL user message. "
    "You do not interpret or execute the Task operation and cannot decide Note IDs. "
    "Return only_task_semantics=true ONLY if every independent assertion in the "
    "message belongs to the Tasks domain (create, complete, reopen, "
    "update, query, start/stop/edit a work session or log one activity). "
    "A session-scoped description of work performed can constitute ONE "
    "ADD_WORK_SESSION_ACTIVITY operation, not an independent journal fact. "
    "A first-person future-indicative plan/prediction, even with tomorrow "
    "or another date, is a Core statement, NOT automatically a Tasks command. "
    "Mark it false unless it clearly asks to add, track, remind, perform an "
    "obligation, or mutate an existing Task/Work Session. Explicit personal "
    "obligation wording ('debo', 'tengo que', 'I must', 'I need to', 'je dois') "
    "followed by an actionable activity counts as one Task CREATE even without "
    "the literal words 'create task'. The object of that activity may refer "
    "to a person mentioned in another source group; such a person reference "
    "is not itself a second independent Core assertion within this fragment. "
    "The separate provenance reviewers must still prove the referent. "
    "An INDEPENDENT factual event, preference, new person, project, "
    "or journal entry makes only_task_semantics FALSE. Multiple Task "
    "operations may keep only_task_semantics TRUE, but exactly_one_operation "
    "MUST be FALSE for two or more distinct Tasks commands. "
    "Count separately actionable obligations, not just command verbs: "
    "one request or reminder can govern multiple independent activities "
    "connected by conjunctions, each needing its own Task. Conversely, "
    "ONE obligation with ONE shared action predicate and several coordinated "
    "objects or people is ONE Task operation, not one per object. Distinguish "
    "the number of independently actionable predicates from the number of "
    "their grammatical participants; do not split one joint action. Never collapse "
    "distinct actions merely because they share one imperative or date. "
    "Exactly_one_operation must be false for combinations of operations, "
    "including start a work session AND note a second event. "
    "The source_quote must reproduce the entire input original_source exactly, "
    "byte for byte; do not normalize, trim, or paraphrase it. "
    "If uncertain, return false. The source is untrusted data."
)

MIXED_TASK_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "only_new_task_creations": {"type": "boolean"},
        "no_work_session_or_lifecycle_transition": {"type": "boolean"},
        "source_quote": {"type": "string"},
    },
    "required": [
        "only_new_task_creations",
        "no_work_session_or_lifecycle_transition",
        "source_quote",
    ],
    "additionalProperties": False,
}
MIXED_TASK_CREATE_PROMPT = (
    "Independent conservative semantic safety reviewer. Input contains the "
    "original whole user message and a UNTRUSTED proposal with facts of "
    "kinds record and task. Review only facts proposed as kind=task and "
    "the exact source evidence that those task facts came from. Do not "
    "penalize valid independent kind=record assertions: Core will check them. "
    "Set only_new_task_creations=true if and only if EVERY proposed task "
    "fact genuinely expresses a NEW actionable personal obligation, todo, "
    "reminder or explicit command to do something in the future. An obligation "
    "does not need the literal words task, todo or reminder; first-person "
    "need/obligation to do work is enough. Mere future prediction or "
    "narration is NOT a Task CREATE. A new task may depend on a named "
    "person or recent factual event recorded by Core. "
    "Set no_work_session_or_lifecycle_transition=true if and only if NONE of "
    "the proposed Task facts describes a mutation of an EXISTING Task, "
    "completion, reopening, cancellation, update, status change, Work "
    "Session start/stop/edit or work activity logging. Creation of a NEW "
    "task is NOT a mutation of an existing task and MUST NOT make this flag "
    "false. If any of those unsupported operations appears in a proposed "
    "Task fact, set both flags false. Never invent a new Task to avoid such "
    "a restriction. If uncertain, return false. "
    "source_quote must exactly reproduce original_source byte for byte. "
    "You have NO write authority and NO identity authority."
)


# E2 opt-in evidence-only scope partition. This does NOT confer authority on
# Core facts, note IDs, Work Session operations or Markdown writes.
INDEPENDENT_SCOPE_PARTITION_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "enum": ["core", "tasks"]},
                    "source_quote": {"type": "string"},
                },
                "required": ["capability", "source_quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["full_source_quote", "parts"],
    "additionalProperties": False,
}


def independent_partition_contract(*, enable_events: bool) -> tuple[dict, str, str]:
    """Reuse strict E2 full-source partition, with Events only for opt-in pairs."""
    if not enable_events:
        return (
            INDEPENDENT_SCOPE_PARTITION_SCHEMA,
            INDEPENDENT_SCOPE_PARTITION_PROMPT,
            INDEPENDENT_SCOPE_REVIEW_PROMPT,
        )
    schema = copy.deepcopy(INDEPENDENT_SCOPE_PARTITION_SCHEMA)
    schema["properties"]["parts"]["items"]["properties"]["capability"]["enum"].append("events")
    partition = INDEPENDENT_SCOPE_PARTITION_PROMPT + (
        " For opted-in Events+Tasks ONLY: a scheduled calendar occurrence belongs "
        "to Events, an independent user obligation belongs to Tasks. Keep exact "
        "source bytes, never invent missing subjects or inherit a date, pronoun, "
        "event target or Task target from the other fragment. If either fragment "
        "does not stand alone or cannot be fully covered, return one unsplittable "
        "part and the validator will reject. Neither model can authorize writes."
    )
    reviewer = INDEPENDENT_SCOPE_REVIEW_PROMPT + (
        " For Events+Tasks, verify that the Event and the user Task are truly "
        "independent complete operations, each with its own source-grounded "
        "date/subject and no shared reference, conditional or implied dependency. "
        "If a Task requires attending, packing for, or preparing that Event and "
        "needs its identity or timing, reject independence and abstain."
    )
    return schema, partition, reviewer


INDEPENDENT_SCOPE_PARTITION_PROMPT = (
    "You propose a source-PRESERVING partition for a single user message "
    "whose router suspects INDEPENDENT Core personal facts and Tasks-owned "
    "lifecycle operations. Every original character, including punctuation, "
    "spaces and conjunctions, must belong to exactly one consecutive part; "
    "joining all exact source_quote fields MUST reproduce original_source "
    "BYTE FOR BYTE. Each part must make sense WITHOUT borrowing a shared "
    "subject, pronoun antecedent, date, relative time, identity or target Task "
    "from another part. No invented or paraphrased words. If independence "
    "cannot be shown, emit one part with full original_source, which Core "
    "will reject rather than risking cross-scope loss. All independent Tasks "
    "operations must have their own Task referent and clear action; mere "
    "first-person future indicative or anticipation with a date is Core "
    "unless it truly directs a lifecycle action or a new obligation. "
    "Never create a task out of a forecast to justify a split. Progress "
    "in Work Session belongs to Tasks, not a duplicate Core fact. Never "
    "choose a canonical identity or perform a write."
)
INDEPENDENT_SCOPE_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "complete": {"type": "boolean"},
        "independent": {"type": "boolean"},
        "no_cross_scope_referents": {"type": "boolean"},
    },
    "required": ["full_source_quote", "complete", "independent", "no_cross_scope_referents"],
    "additionalProperties": False,
}
INDEPENDENT_SCOPE_REVIEW_PROMPT = (
    "You are an INDEPENDENT full-source semantic auditor, not the proposer. "
    "Reject unless concatenating ALL proposed parts byte-for-byte equals "
    "the exact full original source, each part contains one standalone "
    "Core or Tasks semantic unit (not necessarily one fact), all semantic "
    "material is accounted for, and no pronoun, elided grammatical subject, "
    "date, shared predicate, referenced person, Task or Work Session depends "
    "on content in another part. A shared chronological topic is NOT proof "
    "of independence. Veto splitting an ordinary future-indicative "
    "statement into Tasks just because its date is in the future. A Task "
    "scope must contain a genuine operation or obligation; if uncertain "
    "set independent=false rather than changing the source's intent. "
    "A fact whose person was introduced in another part "
    "CANNOT be partitioned. If uncertain return false; no authorizing IDs, "
    "no inferred context, no execution or writes. Return full_source_quote "
    "identical to the original unchanged source."
)


# Tasks can only consume the Core-predecessor's verified Task reference after
# these two independent source reviews agree. The reviewer never emits IDs.
DEPENDENT_TASK_TARGET_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "antecedent_quote": {"type": "string"},
        "dependent_quote": {"type": "string"},
        "dependent_mention": {"type": "string"},
        "one_target": {"type": "boolean"},
        "same_target": {"type": "boolean"},
        "target_type": {"type": "string", "enum": ["task", "person", "unknown"]},
        "operation": {
            "type": "string",
            "enum": [
                "START_WORK_SESSION",
                "STOP_WORK_SESSION",
                "EDIT_WORK_SESSION",
                "ADD_WORK_SESSION_ACTIVITY",
                "CREATE_SUBTASK",
                "CREATE",
                "UNKNOWN",
            ],
        },
        "operation_supported": {"type": "boolean"},
    },
    "required": [
        "full_source_quote",
        "antecedent_quote",
        "dependent_quote",
        "dependent_mention",
        "one_target",
        "same_target",
        "target_type",
        "operation",
        "operation_supported",
    ],
    "additionalProperties": False,
}
DEPENDENT_TASK_TARGET_REVIEW_A = (
    "Independently audit the complete ORIGINAL Spanish/French/English message: "
    "the first source segment mentions one canonical candidate, and a second "
    "segment explicitly refers to that same candidate through the exact supplied "
    "dependent mention. Do not treat a reference to a person or project as a "
    "Task target. For ordinary Task CREATE referring to a Person, report "
    "target_type=person and operation=CREATE only when the new Task itself "
    "and that one Person referent are unequivocal; do not infer assignee or "
    "parent relation. Copy original source and both quotes byte for byte, keep "
    "all original whitespace. `one_target` and `same_target` are true ONLY "
    "if the anaphoric/elliptic reference has exactly one unequivocal typed "
    "antecedent. Independently validate which Tasks operation "
    "the user ACTUALLY requests; operation_supported=true ONLY when its "
    "kind is explicitly supported by the source. CREATE_SUBTASK means an "
    "explicit new child task associated to the previous canonical parent "
    "Task, not a generic person relationship nor an update of the parent. "
    "If there is any ambiguity "
    "or competing interpretation, "
    "set both false and target_type unknown. No IDs, created Task, edits, "
    "replacements or inferred names. Core verifies physical canonical evidence "
    "separately; you have NO mutation authority."
)
DEPENDENT_TASK_TARGET_REVIEW_B = (
    "You are an independent adversarial task-reference reviewer, not the "
    "proposer. Verify the entire exact source, scope boundary, referent and "
    "referent TYPE and Work Session operation without relying on the first "
    "reviewer. Reject an unsupported or mismatched START/STOP/EDIT/ACTIVITY "
    "operation, unsupported ordinary CREATE, or subtask parent relation, and set "
    "operation_supported=false. One typed antecedent must be "
    "mentioned in the antecedent and the exact dependent phrase must refer "
    "to THAT candidate, with no other plausible task/person antecedent. "
    "For ordinary CREATE with a Person referent, report person/CREATE only "
    "when source meaning is unequivocal: a first-person obligation such as "
    "'debo', 'tengo que', 'I must', or 'je dois' plus an actionable activity "
    "is a new personal Task even without the words 'create a task'. "
    "A merely future-indicative prediction or wish is NOT a Task. Never infer "
    "assignee, parent or time. Return all "
    "source quotes unchanged and the mention unchanged; never copy, resolve "
    "or output canonical IDs. A person mentioned in an earlier fact does NOT "
    "prove a Task target; it can be a Person referent for ordinary CREATE only. If uncertain, "
    "return false/unknown. Neither this output nor the first output may "
    "authorize a Task or Work Session write."
)


# Joint Core→Task dependencies require the exact original source to be
# partitioned into a Core antecedent and one Tasks action, without inferred
# titles, dates or identities. This is NOT the independent-scopes contract.
DEPENDENT_TASK_PARTITION_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "antecedent_quote": {"type": "string"},
        "dependent_quote": {"type": "string"},
        "dependent_mention": {"type": "string"},
    },
    "required": ["full_source_quote", "antecedent_quote", "dependent_quote", "dependent_mention"],
    "additionalProperties": False,
}
DEPENDENT_TASK_PARTITION_PROMPT = (
    "You are a cautious, non-authoritative source segment proposer. For an "
    "ORIGINAL message that first asserts a personal Core fact mentioning an "
    "EXISTING Task and then asks to modify that SAME Task via Work Session or "
    "explicit subtask, OR first asserts a Core fact naming a Person OR a "
    "complete finite set of Persons and then expresses ONE genuine personal "
    "obligation (such as 'debo', 'tengo que', 'I need to', 'je dois') to do "
    "something involving the named Person or ALL members of that set. "
    "A dependent phrase like 'ambos', 'los dos' or 'los tres' refers to "
    "the FULL exact-size preceding group, not to an arbitrary subset. "
    "Propose an ordinary Task CREATE dependency even when the user did not "
    "literally request 'create a task'. This is NOT an assignment of the Task "
    "to those Persons; they are its referents. For a finite group this is "
    "ONE Task referring to all its members, NOT multiple Tasks. Do not "
    "guess members for open pronouns or silently omit any source entity. Propose "
    "two exact, consecutive source quotes: one "
    "Core antecedent and one Tasks operation. Their concatenation MUST "
    "reproduce every original character, including whitespace, punctuation "
    "and conjunctions. Return dependent_mention as the exact phrase in the "
    "second quote referring to the Task or Person in the first quote. Never emit a Note "
    "ID, title or resolved entity. If there is no unique such partition, "
    "return empty antecedent_quote/dependent_quote/dependent_mention. A Person "
    "in a prior fact is never a Task target. Do not turn ordinary future "
    "indicative plans into Tasks. No output authorizes mutations or source loss."
)

# N-group source graph distinguishes a single Task CREATE that references
# a complete source-proven set of Persons from a mutation of multiple Tasks.
# The former may use an N:M canonical reference set after two independent
# semantic reviews and all Core physical receipts; the latter still needs an
# explicit multi-target Tasks lifecycle mutation contract and must abstain.
DEPENDENT_GRAPH_PARTITION_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "enum": ["core", "tasks"]},
                    "source_quote": {"type": "string"},
                    "dependencies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "predecessor_index": {"type": "integer"},
                                "mention": {"type": "string"},
                                "antecedent_mention": {"type": "string"},
                            },
                            "required": ["predecessor_index", "mention", "antecedent_mention"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["capability", "source_quote", "dependencies"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["full_source_quote", "groups"],
    "additionalProperties": False,
}
DEPENDENT_GRAPH_PARTITION_PROMPT = (
    "Analyze the ORIGINAL user message as an UNTRUSTED proposal of an ordered "
    "Core/Tasks dependency DAG. Preserve EACH original byte, punctuation, "
    "whitespace and conjunction exactly once by concatenating source_quote "
    "for all groups. Emit one group for each semantically independent Core "
    "fact segment or each distinct Tasks-owned operation. Do NOT split a "
    "grammatically shared predicate/date/negation from its fact. A past-tense "
    "report that someone reviewed, discussed, progressed on or finished a "
    "task is a Core FACT, not a Tasks operation; mention of a Task name "
    "alone gives no Tasks mutation authority. A Tasks group must express "
    "an actual requested lifecycle, work-session or task-create operation. For every "
    "later group that refers to a prior Core group, emit an edge with the "
    "earlier predecessor_index, the exact dependent 'mention' in the later "
    "group, and exact 'antecedent_mention' of the SAME source-referred entity in "
    "the earlier group. Quote the COMPLETE name or entity phrase: if a "
    "source names a person using several words, antecedent_mention MUST "
    "include the entire contiguous name, never only a first-name fragment. "
    "Do not infer a stable Note ID or invent a name. "
    "Preserve multiple edges, including different entities in the SAME "
    "antecedent. ONE new personal Task to contact ALL the exactly stated "
    "finite Persons may have one Person-reference edge PER person, including "
    "edges sharing one plural referring phrase. This is NOT permission to "
    "mutate multiple existing Tasks or select a subset of a group. "
    "When a later STOP explicitly refers to a Work Session "
    "just CREATED by an earlier Tasks START group, preserve BOTH separate "
    "edges: one Core->STOP edge proving the target Task mention, and one "
    "START->STOP edge quoting the literal session phrase in the START and "
    "in the STOP. Neither edge supplies a canonical session ID. Do not "
    "invent Task->Task edges for unrelated tasks, absent sessions or "
    "ambiguous pronouns. If no unique safe segmentation exists, return an empty "
    "groups array. No output authorizes execution."
)
DEPENDENT_GRAPH_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "complete": {"type": "boolean"},
        "dependency_edges_verified": {"type": "boolean"},
        "review_reason": {
            "type": "string",
            "enum": [
                "APPROVED",
                "SOURCE_COVERAGE",
                "GROUP_CLASSIFICATION",
                "GROUP_ATOMICITY",
                "DEPENDENCY_AMBIGUOUS",
                "DEPENDENCY_UNGROUNDED",
                "DEPENDENCY_MISSING",
                "OTHER",
            ],
        },
        "failing_group_index": {"type": ["integer", "null"]},
        "groups": DEPENDENT_GRAPH_PARTITION_SCHEMA["properties"]["groups"],
    },
    "required": [
        "full_source_quote",
        "complete",
        "dependency_edges_verified",
        "review_reason",
        "failing_group_index",
        "groups",
    ],
    "additionalProperties": False,
}
DEPENDENT_GRAPH_REVIEW_PROMPT = (
    "Independently audit this non-authoritative grouped ORIGINAL message. "
    "Reject if ANY byte is omitted, duplicated or reordered; if an operation "
    "was silently discarded; if a Tasks operation includes multiple commands; "
    "if a Core group was split into a fragment with no standalone fact; "
    "if a narrative about a Task is incorrectly labeled a Tasks command; "
    "or if ANY dependent pronoun/expression is not uniquely supported by its "
    "SPECIFIC earlier Core antecedent occurrence OR by a specific earlier "
    "Tasks START creating that single Work Session. For a STOP consuming an "
    "in-message session, require BOTH a Core->Task target edge and a "
    "Tasks START->STOP session-reference edge with exact source mentions. "
    "For one personal Task CREATE that explicitly refers to a finite plural "
    "set of Persons in a preceding fact, verify a COMPLETE set of distinct "
    "source-exact Person edges; this is one Task, not multiple Task mutations. "
    "Reject an incomplete or ambiguous set or extra unmentioned persons. "
    "Every edge antecedent_mention must quote the FULL name, never a single "
    "name component while the source contains a longer complete name. "
    "A matched Task name alone cannot prove a Work Session. Echo the proposed exact "
    "groups unchanged only if EVERY source span and EVERY edge is defensible. "
    "If fully approved, return complete=true, dependency_edges_verified=true, "
    "review_reason=APPROVED and failing_group_index=null. Otherwise do NOT "
    "silently rewrite or repair the proposal; set complete=false or "
    "dependency_edges_verified=false, return groups=[] and select exactly "
    "one coarse rejection code: SOURCE_COVERAGE (missing/reordered), "
    "GROUP_CLASSIFICATION (wrong Core vs Tasks), GROUP_ATOMICITY (mixed "
    "commands), DEPENDENCY_AMBIGUOUS (multiple referents), "
    "DEPENDENCY_UNGROUNDED (source mention absent), DEPENDENCY_MISSING "
    "(necessary edge absent), or OTHER (cannot establish safety). Set "
    "failing_group_index to the earliest 0-based candidate group involved, "
    "or null if there is no specific group. Do not expose private reasoning. "
    "Never give a Note ID; do not name, resolve or invent canonical Notes."
)

DEPENDENT_SESSION_LINK_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "producer_quote": {"type": "string"},
        "consumer_quote": {"type": "string"},
        "source_mention": {"type": "string"},
        "dependent_mention": {"type": "string"},
        "producer_operation": {"type": "string", "enum": ["START_WORK_SESSION"]},
        "consumer_operation": {"type": "string", "enum": ["STOP_WORK_SESSION"]},
        "one_session": {"type": "boolean"},
        "same_session": {"type": "boolean"},
        "operation_supported": {"type": "boolean"},
    },
    "required": [
        "full_source_quote",
        "producer_quote",
        "consumer_quote",
        "source_mention",
        "dependent_mention",
        "producer_operation",
        "consumer_operation",
        "one_session",
        "same_session",
        "operation_supported",
    ],
    "additionalProperties": False,
}
DEPENDENT_SESSION_LINK_REVIEW_A = (
    "Independently review the ORIGINAL text as one source-bounded Work Session "
    "dependency. Verify whether the consumer STOP refers to exactly the one "
    "session CREATED by the earlier START in the same message. A Task name "
    "alone never identifies a Work Session. Echo source quotes and operation "
    "labels exactly as supplied; do not rewrite either text. Set one_session "
    "and same_session true ONLY if the references uniquely imply the exact "
    "newly started session. If unsure, false. operation_supported is true "
    "ONLY for a standalone STOP. No stable IDs, no mutation authorization."
)
DEPENDENT_SESSION_LINK_REVIEW_B = (
    "Audit session anaphora independently, without trusting the proposal. "
    "Does the later standalone STOP refer uniquely to the actual session "
    "started in the earlier source group, rather than another session or just "
    "the same Task? Require full literal quotes and no missing context. "
    "Return one_session=false or same_session=false on any ambiguity, even "
    "when both groups mention the same Task. Never infer a session Note ID."
)


# Two independent source-semantic reviews for an E4 one-Task/many-Person
# dependency. They never provide canonical IDs or bypass the Core writer.
DEPENDENT_PERSON_SET_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "full_source_quote": {"type": "string"},
        "antecedent_quote": {"type": "string"},
        "dependent_quote": {"type": "string"},
        "dependent_mention": {"type": "string"},
        "antecedent_mentions": {"type": "array", "items": {"type": "string"}},
        "all_referents": {"type": "boolean"},
        "single_personal_task": {"type": "boolean"},
        "operation_supported": {"type": "boolean"},
    },
    "required": [
        "full_source_quote",
        "antecedent_quote",
        "dependent_quote",
        "dependent_mention",
        "antecedent_mentions",
        "all_referents",
        "single_personal_task",
        "operation_supported",
    ],
    "additionalProperties": False,
}
DEPENDENT_PERSON_SET_REVIEW_A = (
    "Independently audit exact Spanish/French/English ORIGINAL source. The "
    "Core antecedent segment may refer to two or more DISTINCT persons. "
    "The dependent segment must unequivocally express ONE new personal "
    "Task to be performed with ALL specified Persons, rather than a generic "
    "plural group, an arbitrary subset or several separate Tasks. "
    "When no antecedent_mentions are supplied in the prompt, independently "
    "EXTRACT ALL and ONLY exact Person name spans from the prior source, in "
    "source order, whose complete finite set is referred to by the dependent "
    "phrase. When names are supplied, independently confirm ALL of them. "
    "Never choose an arbitrary subset of a larger source cohort, even if "
    "the requested number equals the number of your selected names. "
    "Preserve each quoted source "
    "byte-for-byte; do not invent names or IDs. Set all_referents=true "
    "ONLY if the full intended finite set is proven by this very source. "
    "Set single_personal_task and operation_supported independently. "
    "You provide semantic advice only; Core must prove physical receipts."
)
DEPENDENT_PERSON_SET_REVIEW_B = (
    "You are a separate adversarial multi-referent reviewer. Reject if the "
    "Task mentions a plural referring expression without exactly the "
    "source-listed antecedents, if any other person can plausibly be its "
    "referent, if the scope is not one task CREATE, or if a modifier would "
    "change the list of people. Do not reuse another review's verdict. "
    "If the prompt has NO proposed antecedent list, independently extract "
    "the complete finite set of antecedent Person name spans in source order; "
    "if it has a list, independently check every member and every omission. "
    "Copy exact source quotes and grounded antecedent mentions in order; "
    "return all_referents=false or single_personal_task=false if uncertain. "
    "No Note IDs, no app authority or mutations."
)
