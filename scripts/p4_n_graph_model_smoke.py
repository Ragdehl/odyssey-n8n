"""Opt-in N-dependent graph partition + independent audit with real GPT.

No canonical writes, no n8n/browser and no personal/user vault data.
Only synthetic four-scope source and two bounded JSON-schema calls.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from odyssey_core.dependent_group_graph import (
    DependentGroupGraphError,
    verify_dependent_group_graph,
)
from odyssey_runtime.whole_source_model_contract import (
    DEPENDENT_GRAPH_PARTITION_PROMPT,
    DEPENDENT_GRAPH_PARTITION_SCHEMA,
    DEPENDENT_GRAPH_REVIEW_PROMPT,
    DEPENDENT_GRAPH_REVIEW_SCHEMA,
)
from scripts.p4_mixed_independent_real_isolated import ObservedClient
from tests.runtime.test_p4_dependent_n_graph_execution import (
    BEFORE,
    FIRST_TASK,
    SECOND,
    _physical_runtime,
)

SOURCE = BEFORE + SECOND + FIRST_TASK


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Synthetic GPT N-dependency smoke is opt-in only")
    with tempfile.TemporaryDirectory(prefix="odyssey-n-graph-gpt-") as root:
        _, _, executor, _, _, _, _ = _physical_runtime(Path(root))
        executor.client = ObservedClient(OpenAI(max_retries=0, timeout=80))
        proposal = executor._ask(
            "gpt-5.6-luna",
            DEPENDENT_GRAPH_PARTITION_PROMPT,
            {"original_source": SOURCE},
            DEPENDENT_GRAPH_PARTITION_SCHEMA,
            "odyssey_dependent_graph_partition_v1",
        )
        review = executor._ask(
            "gpt-6-luna",
            DEPENDENT_GRAPH_REVIEW_PROMPT,
            {"original_source": SOURCE, "proposed_groups": proposal},
            DEPENDENT_GRAPH_REVIEW_SCHEMA,
            "odyssey_dependent_graph_review_v1",
        )
        try:
            graph = verify_dependent_group_graph(SOURCE, proposal, review)
        except DependentGroupGraphError:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "proposed_groups": len(proposal.get("groups", [])),
                        "review_complete": review.get("complete") is True,
                        "review_edges_verified": review.get("dependency_edges_verified") is True,
                        "review_group_match": review.get("groups") == proposal.get("groups"),
                        "source_full_match": proposal.get("full_source_quote") == SOURCE,
                        "proposed_caps": [p.get("capability") for p in proposal.get("groups", [])],
                        "reviewed_caps": [p.get("capability") for p in review.get("groups", [])],
                        "proposed_edges": [
                            [e.get("predecessor_index") for e in p.get("dependencies", [])]
                            for p in proposal.get("groups", [])
                        ],
                        "reviewed_edges": [
                            [e.get("predecessor_index") for e in p.get("dependencies", [])]
                            for p in review.get("groups", [])
                        ],
                    }
                )
            )
            return 2
        ok = (
            len(graph.groups) == 4
            and [group.capability for group in graph.groups] == ["core", "core", "tasks", "tasks"]
            and graph.edges
            == (
                (0, 2, "Preparar informe Atlas", "Preparar informe Atlas"),
                (0, 3, "Preparar informe Atlas", "Preparar informe Atlas"),
            )
        )
        print(
            json.dumps(
                {
                    "passed": ok,
                    "groups": len(graph.groups),
                    "capabilities": [group.capability for group in graph.groups],
                    "edge_predecessors": [row[0] for row in graph.edges],
                    "full_source_preserved": "".join(group.source for group in graph.groups)
                    == SOURCE,
                }
            )
        )
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
