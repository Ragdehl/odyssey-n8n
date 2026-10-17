"""Tasks-owned, source-only E2 semantic link for a later session operation.

This does not select a Note or a Work Session. The physical handoff is built
ONLY from the preceding domain START receipt, with a second current CAS gate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .interpretation import TaskInterpretation, TaskOperation


class SessionDependencyError(ValueError):
    """An operation's relationship to one newly created session is unproven."""


@dataclass(frozen=True, slots=True)
class ReviewedSessionDependency:
    producer_index: int
    consumer_index: int
    source_mention: str
    dependent_mention: str
    consumer_operation: TaskOperation


def verify_session_dependency(
    *,
    full_source: str,
    producer_source: str,
    consumer_source: str,
    source_mention: str,
    dependent_mention: str,
    producer_index: int,
    consumer_index: int,
    producer: TaskInterpretation,
    consumer: TaskInterpretation,
    reviews: Sequence[Mapping[str, object]],
) -> ReviewedSessionDependency:
    """Require two identical independent source/operation attestations.

    Group identity and exact contiguous original spans are checked separately
    by the N-group DAG verifier; this boundary cannot grant a physical ID.
    """
    if (
        not isinstance(full_source, str)
        or not full_source.strip()
        or not isinstance(producer_index, int)
        or isinstance(producer_index, bool)
        or not isinstance(consumer_index, int)
        or isinstance(consumer_index, bool)
        or not 0 <= producer_index < consumer_index <= 15
        or not isinstance(producer, TaskInterpretation)
        or not isinstance(consumer, TaskInterpretation)
        or producer.operation is not TaskOperation.START_WORK_SESSION
        or consumer.operation not in (TaskOperation.STOP_WORK_SESSION,)
        or producer.source_text != producer_source.strip()
        or consumer.source_text != consumer_source.strip()
        or not isinstance(source_mention, str)
        or not source_mention.strip()
        or not isinstance(dependent_mention, str)
        or not dependent_mention.strip()
        or producer_source.casefold().count(source_mention.casefold()) != 1
        or consumer_source.casefold().count(dependent_mention.casefold()) != 1
        or not isinstance(reviews, (tuple, list))
        or len(reviews) != 2
    ):
        raise SessionDependencyError("Missing exact source or compatible session operation")
    expected = {
        "full_source_quote": full_source,
        "producer_quote": producer_source,
        "consumer_quote": consumer_source,
        "source_mention": source_mention,
        "dependent_mention": dependent_mention,
        "producer_operation": producer.operation.value,
        "consumer_operation": consumer.operation.value,
        "one_session": True,
        "same_session": True,
        "operation_supported": True,
    }
    if any(not isinstance(item, Mapping) or dict(item) != expected for item in reviews):
        raise SessionDependencyError("Session anaphora was not independently supported")
    return ReviewedSessionDependency(
        producer_index,
        consumer_index,
        source_mention,
        dependent_mention,
        consumer.operation,
    )
