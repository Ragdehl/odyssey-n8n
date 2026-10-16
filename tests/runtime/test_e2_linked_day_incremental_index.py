"""A linked, automatically materialized Calendar Day belongs to index refresh.

Replays a Project-like fact from actual DEV using a disposable canonical vault.
No provider calls. Unrelated drift still blocks incremental refresh.
"""

from __future__ import annotations

import pytest

from odyssey_core.context import ContextIndexError
from odyssey_core.persistence import create_entity
from odyssey_core.temporal import (
    materialize_calendar_day_links,
    materialized_day_link_index_ids,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

DAY = "2026-10-16"
PROJECT_ID = "fixture-linked-project"
ACTOR = "fixture-incremental-index"
NOW = "2026-10-15T23:28:37+02:00"
PROJECT_BODY = (
    "# Added [[calendar/days/2026-10-15|15-10-2026]]\n"
    "- [[calendar/days/2026-10-16|16-10-2026]] es el fin de sprint.\n"
)


def _write_linked_project(repo):
    days = materialize_calendar_day_links(
        PROJECT_BODY, repository=repo, schema=SCHEMA, actor=ACTOR, now=NOW
    )
    result = create_entity(
        repo,
        SCHEMA,
        path="Synthetic-XBOM.md",
        entity_id=PROJECT_ID,
        metadata={"name": "Synthetic XBOM", "type": "project"},
        content=PROJECT_BODY,
        actor=ACTOR,
        now=NOW,
    )
    assert result.id == PROJECT_ID
    assert {day.id for day in days} == {"date:2026-10-15", "date:2026-10-16"}


def test_incremental_indexes_include_all_materialized_day_link_targets(tmp_path):
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    _write_linked_project(repo)
    extra = materialized_day_link_index_ids(repo, SCHEMA, (PROJECT_ID,))
    assert set(extra) == {"date:2026-10-15", "date:2026-10-16"}
    batch = (PROJECT_ID, *extra)

    documents_embedded = []
    old = embedder.embed_documents

    def record(items):
        documents_embedded.append(len(items))
        return old(items)

    embedder.embed_documents = record
    assert context.refresh_notes(repo, SCHEMA, embedder, note_ids=batch) == 3
    assert semantic.refresh_notes(repo, SCHEMA, embedder, note_ids=batch) >= 1
    assert documents_embedded and max(documents_embedded) <= len(batch)
    assert all(x > 0 for x in documents_embedded)


def test_unrelated_note_drift_remains_rejected_even_with_related_day_links(tmp_path):
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    _write_linked_project(repo)
    create_entity(
        repo,
        SCHEMA,
        path="Unrelated.md",
        entity_id="fixture-other-new",
        metadata={"name": "Unrelated", "type": "document"},
        content="A distinct unrelated note.",
        actor=ACTOR,
        now=NOW,
    )
    batch = (PROJECT_ID, *materialized_day_link_index_ids(repo, SCHEMA, (PROJECT_ID,)))
    assert "fixture-other-new" not in batch
    with pytest.raises(ContextIndexError, match="unrelated index drift"):
        context.refresh_notes(repo, SCHEMA, embedder, note_ids=batch)
