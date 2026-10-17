"""Opt-in bounded provider validation for a 4-group Core→START→STOP session DAG.

No user files, no production writes, no browser or n8n. Never promote model
agreement to canonical IDs; this probes interpretation ONLY.
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
    DEPENDENT_SESSION_LINK_REVIEW_A,
    DEPENDENT_SESSION_LINK_REVIEW_B,
    DEPENDENT_SESSION_LINK_REVIEW_SCHEMA,
)
from scripts.p4_mixed_independent_real_isolated import ObservedClient
from tests.runtime.test_p4_dependent_n_graph_execution import (
    BEFORE,
    SECOND,
    _physical_runtime,
)

SOURCE = (
    BEFORE
    + SECOND
    + " Por favor, inicia una sesión de trabajo en Preparar informe Atlas."
    + " Después termina esa sesión recién iniciada en Preparar informe Atlas."
)


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Live synthetic session-link review is opt-in only")
    with tempfile.TemporaryDirectory(prefix="odyssey-session-link-gpt-") as root:
        _, _, executor, _, _, _, _ = _physical_runtime(Path(root))
        executor.client = ObservedClient(OpenAI(max_retries=0, timeout=70))
        proposed = executor._ask(
            "gpt-5.6-luna",
            DEPENDENT_GRAPH_PARTITION_PROMPT,
            {"original_source": SOURCE},
            DEPENDENT_GRAPH_PARTITION_SCHEMA,
            "odyssey_session_graph_partition_v1",
        )
        reviewed = executor._ask(
            "gpt-6-luna",
            DEPENDENT_GRAPH_REVIEW_PROMPT,
            {"original_source": SOURCE, "proposed_groups": proposed},
            DEPENDENT_GRAPH_REVIEW_SCHEMA,
            "odyssey_session_graph_review_v1",
        )
        try:
            graph = verify_dependent_group_graph(SOURCE, proposed, reviewed)
        except DependentGroupGraphError:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "stage": "graph_auditor",
                        "proposal_count": len(proposed.get("groups", [])),
                        "proposal_capabilities": [
                            p.get("capability") for p in proposed.get("groups", [])
                        ],
                        "review_reason": reviewed.get("review_reason"),
                        "review_index": reviewed.get("failing_group_index"),
                        "source_preserved": proposed.get("full_source_quote") == SOURCE,
                    }
                )
            )
            return 2
        if (
            len(graph.groups) != 4
            or [g.capability for g in graph.groups] != ["core", "core", "tasks", "tasks"]
            or any(
                len(g.dependencies) != count
                for g, count in zip(graph.groups, (0, 0, 1, 2), strict=True)
            )
        ):
            print(json.dumps({"passed": False, "stage": "topology", "count": len(graph.groups)}))
            return 2
        consumer = graph.groups[3]
        session_edges = [d for d in consumer.dependencies if d.predecessor_index == 2]
        if len(session_edges) != 1:
            print(json.dumps({"passed": False, "stage": "session_edge_missing"}))
            return 2
        edge = session_edges[0]
        payload = {
            "full_source": SOURCE,
            "producer_source": graph.groups[2].source,
            "consumer_source": consumer.source,
            "source_mention": edge.antecedent_mention,
            "dependent_mention": edge.mention,
            "producer_operation": "START_WORK_SESSION",
            "consumer_operation": "STOP_WORK_SESSION",
        }
        reviews = [
            executor._ask(
                model,
                instruction,
                payload,
                DEPENDENT_SESSION_LINK_REVIEW_SCHEMA,
                f"odyssey_session_link_semantic_{suffix}_v1",
            )
            for model, instruction, suffix in (
                ("gpt-5.6-luna", DEPENDENT_SESSION_LINK_REVIEW_A, "a"),
                ("gpt-6-luna", DEPENDENT_SESSION_LINK_REVIEW_B, "b"),
            )
        ]
        accepted = all(
            review["one_session"] is True
            and review["same_session"] is True
            and review["operation_supported"] is True
            for review in reviews
        )
        print(
            json.dumps(
                {
                    "passed": accepted,
                    "stage": "session_semantics",
                    "groups": len(graph.groups),
                    "session_edge_present": True,
                    "attestations": [
                        {
                            "one": r["one_session"],
                            "same": r["same_session"],
                            "supported": r["operation_supported"],
                        }
                        for r in reviews
                    ],
                }
            )
        )
        return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
