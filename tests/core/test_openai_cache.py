"""Deterministic transport tests for explicit OpenAI cache boundaries."""

from odyssey_core.openai_cache import (
    CONSERVATIVE_EXPLICIT_PREFIX_BYTES,
    explicit_cache_transport,
    explicit_system_content,
)


def test_explicit_boundary_preserves_flattened_text_and_excludes_dynamic_suffix() -> None:
    """Mark exactly one long caller-proven stable prefix without changing prompt text."""
    stable = "stable instruction " * 600
    dynamic = "\nrequest-specific personal evidence"

    transport, diagnostics = explicit_cache_transport(
        model="gpt-5.6-luna",
        capability="unit-test-v1",
        stable_prefix=stable,
        proven_reusable=True,
    )
    content = explicit_system_content(stable, dynamic)

    assert transport is not None
    assert transport["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert transport["prompt_cache_key"].startswith("odyssey-unit-test-v1-")
    assert "personal evidence" not in content[0]["text"]
    assert "".join(block["text"] for block in content) == stable + dynamic
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert diagnostics.outcome == "explicit"


def test_short_or_unproven_prefixes_remain_implicit_without_content_diagnostics() -> None:
    """Avoid explicit-only mode when the stable portion lacks sufficient evidence."""
    transport, short = explicit_cache_transport(
        model="gpt-5.6-luna",
        capability="short-v1",
        stable_prefix="x" * (CONSERVATIVE_EXPLICIT_PREFIX_BYTES - 1),
        proven_reusable=True,
    )
    _, unproven = explicit_cache_transport(
        model="gpt-5.6-luna",
        capability="unproven-v1",
        stable_prefix="x" * CONSERVATIVE_EXPLICIT_PREFIX_BYTES,
        proven_reusable=False,
    )

    assert transport is None
    assert short.outcome == "implicit_prefix_too_short"
    assert unproven.outcome == "implicit_unproven_stability"
    assert "x" * 20 not in str(short.as_safe_mapping())


def test_gpt_55_or_earlier_never_enables_explicit_only_caching() -> None:
    """Retain implicit provider behavior for models without explicit breakpoint support."""
    transport, diagnostics = explicit_cache_transport(
        model="gpt-5.5-luna",
        capability="legacy-v1",
        stable_prefix="x" * CONSERVATIVE_EXPLICIT_PREFIX_BYTES,
        proven_reusable=True,
    )

    assert transport is None
    assert diagnostics.outcome == "implicit_model_unsupported"
