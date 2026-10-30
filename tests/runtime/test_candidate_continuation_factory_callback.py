"""Production-built E5 continuation callback with disposable Markdown, real E3.

Freeze ONLY provider responses. Do not replace the production closure or Core Writer.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core import create_entity
from odyssey_core.candidate_continuation_context import prepare_selected_candidate_continuation
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import (
    TemporalInterpreterError,
    parse_temporal_interpretation,
)
from odyssey_runtime import composition
from odyssey_runtime.whole_source_light import WholeSourceLightExecutor
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW, _ready, _reply
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, ConstantEmbedder, _linked_day_plan

ACTOR = AuthenticatedActorContext("33333333-3333-4333-8333-333333333333")


def _factory(tmp_path: Path, monkeypatch, *, undated: bool, temporal_mode: str):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    preview, _, vault, _ = _ready(fixture, captured_timezone="Europe/Paris")
    if undated:
        old = preview.pending[0]
        clause = "He estado con él en el parque."
        source = preview.original_request[: old.source_start] + clause
        index = old.source_start + clause.index("él")
        preview = replace(
            preview,
            original_request=source,
            pending=(
                replace(
                    old,
                    source_text=clause,
                    source_end=len(source),
                    reference_start=index,
                    reference_end=index + len("él"),
                ),
            ),
        )
    runtime_dir = tmp_path / "derived"
    state_root = tmp_path / "actor-state"
    for path in (runtime_dir, state_root / "pending"):
        path.mkdir(parents=True)
    create_entity(
        vault,
        SCHEMA,
        path="fixture-self.md",
        entity_id="fixture-self-e5",
        metadata={"name": "Persona de prueba", "type": "person"},
        content="",
        actor="synthetic",
        now=NOW,
    )
    SelfBindingRepository(state_root, vault, SCHEMA).bind(ACTOR.stable_user_id, "fixture-self-e5")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-unused-key")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_E5_CANDIDATE_CONTINUATION_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_ENABLED_APPLICATIONS", "tasks")
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", str(vault.root))
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(runtime_dir))
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(state_root))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(state_root / "pending"))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "fake-embedding-cache"))
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **_: ConstantEmbedder())
    monkeypatch.setattr(composition, "_build_contextual_reasoner", UnresolvedReasoner)
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda _root: None)
    trace = {"temporal": 0, "planner": 0, "review": 0}

    class FrozenTemporal:
        model = "recorded-temporal"
        reasoning_effort = "low"
        last_usage = None
        last_call = None

        def interpret(self, source: str, _prior=()):
            trace["temporal"] += 1
            if temporal_mode == "unavailable":
                raise TemporalInterpreterError("synthetic Temporal outage")
            if temporal_mode == "wrong_empty" or undated:
                return parse_temporal_interpretation(
                    {"mentions": []},
                    source,
                    timezone="Europe/Paris",
                    allow_empty_mentions=True,
                )
            raise AssertionError("unwanted temporal case")

    class FrozenPlanner:
        def plan(self, source: str, _prior=()):
            trace["planner"] += 1
            assert source == preview.pending[0].source_text
            date = "2026-10-04"
            fact = (
                "He estado con {{ref:0}} en el parque." if undated else "Iré al cine con {{ref:0}}."
            )
            day = _linked_day_plan(date, fact, "él", date, target_name="Luis")
            writer, helper = day.actions[0].units
            return RequestPlan(
                (WriteAction((replace(writer, fact_temporal_anchors=()), helper)),), ()
            )

    monkeypatch.setattr(
        composition.OpenAITemporalInterpreter,
        "from_environment",
        classmethod(lambda cls, *_args, **_kwargs: FrozenTemporal()),
    )
    monkeypatch.setattr(
        composition.OpenAIRequestPlanner,
        "from_environment",
        classmethod(lambda cls, *_args, **_kwargs: FrozenPlanner()),
    )

    def fake_ask(self, model, instructions, payload, schema, name):
        trace["review"] += 1
        assert name == "odyssey_e5_candidate_continuation_v1"
        proposed = payload["proposed_facts"]
        assert len(proposed) == 1
        entry = proposed[0]
        allowed = undated
        return {
            "approved": allowed,
            "complete": allowed,
            "reason": None if allowed else "Unsupported source-time claim",
            "facts": [
                {
                    "ordinal": entry["ordinal"],
                    "kind": "record",
                    "reviewed_text": entry["text"],
                    "date": None,
                    "reference_names": ["Luis"],
                    "supported": allowed,
                }
            ],
        }

    monkeypatch.setattr(WholeSourceLightExecutor, "_ask", fake_ask)
    product = composition.build_runtime_from_environment()
    product.refresh_indexes()
    assert product.candidate_continuation_execute is not None
    actor_pending_root = (
        ConversationRootResolver(state_root).resolve(ACTOR.stable_user_id) / "pending"
    )
    actor_pending_root.mkdir(parents=True, exist_ok=True)
    pending = CandidatePendingRepository(actor_pending_root)
    pending.record(
        preview,
        conversation_id="chat-1",
        created_at=NOW,
        created_timezone="Europe/Paris",
        options=(ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis")),
        vault=vault,
        schema=SCHEMA,
    )
    assert _reply(pending, vault, "Con Luis").outcome == "choice_recorded"
    context = prepare_selected_candidate_continuation(
        pending,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    return product, vault, pending, context, trace


@pytest.mark.parametrize(
    ("undated", "mode", "expected"),
    [(True, "empty", True), (False, "wrong_empty", False), (True, "unavailable", False)],
)
def test_actual_composition_callback_temporal_review_and_e3(
    tmp_path: Path, monkeypatch, undated: bool, mode: str, expected: bool
):
    product, vault, pending, context, trace = _factory(
        tmp_path, monkeypatch, undated=undated, temporal_mode=mode
    )
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    if not expected:
        from odyssey_runtime.candidate_continuation_delivery import (
            CandidateContinuationPrewriteError,
        )

        with pytest.raises(CandidateContinuationPrewriteError):
            product.candidate_continuation_execute(context, ACTOR.stable_user_id)
        assert before == {path: vault.read_text(path) for path in vault.list_markdown_paths()}
        assert pending.read(context.original_request_id)["status"] == "selected"
        assert trace["temporal"] == 1
        assert trace["planner"] == (0 if mode == "unavailable" else 1)
        assert trace["review"] == (0 if mode == "unavailable" else 1)
    else:
        result = product.candidate_continuation_execute(context, ACTOR.stable_user_id)
        assert result["status"] == "completed"
        assert result["facts"][0]["note_id"] == "date:2026-10-04"
        day = vault.read_text("calendar/days/2026-10-04.md")
        assert day.count("He estado con [[Luis|Luis]] en el parque.") == 1
        replay = product.candidate_continuation_execute(context, ACTOR.stable_user_id)
        assert replay["delivery_replayed"] is True
        assert vault.read_text("calendar/days/2026-10-04.md") == day
        assert trace == {"temporal": 2, "planner": 2, "review": 2}


def test_reviewed_e3_accepts_only_exact_canonical_schema_copy(tmp_path: Path) -> None:
    """Projection deepcopy is legitimate; any content or vault swap is not."""
    from copy import deepcopy

    from odyssey_core.application import WritePreflightGuardError
    from odyssey_core.storage import VaultRepository
    from tests.runtime.test_candidate_continuation_reviewed_core_e3 import _prepared

    _preview, _pending, vault, _context, plan, guard = _prepared(tmp_path)
    same_schema = deepcopy(SCHEMA)
    assert same_schema == SCHEMA and same_schema is not SCHEMA
    # No fabricated preflight: the expected next rejection proves that
    # the legitimate schema copy crossed the context-boundary check.
    with pytest.raises(WritePreflightGuardError, match="ACTION_CHANGED"):
        guard(plan.actions[0], (), vault, same_schema)
    changed_schema = deepcopy(SCHEMA)
    changed_schema["schema_version"] += 1
    with pytest.raises(WritePreflightGuardError, match="CONTEXT_MISMATCH"):
        guard(plan.actions[0], (), vault, changed_schema)
    other_root = tmp_path / "another-vault"
    other_root.mkdir()
    with pytest.raises(WritePreflightGuardError, match="CONTEXT_MISMATCH"):
        guard(plan.actions[0], (), VaultRepository(other_root), same_schema)
