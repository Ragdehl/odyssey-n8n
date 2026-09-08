"""Regression checks for the reviewed Phase 20.2B product workflow source."""

from pathlib import Path

SOURCE = Path(__file__).parents[1] / "workflows" / "odyssey-online.ts"


def test_direct_product_response_omits_internal_route_marker() -> None:
    """Keep direct n8n routing metadata out of the browser response contract."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "const { request_id, status, kind, message }" in source
    assert "Return deterministic product response" in source


def test_partial_write_unit_success_routes_to_acknowledgement() -> None:
    """Recognize Core's bounded succeeded unit status without changing Core semantics."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "u.status === 'completed' || u.status === 'succeeded'" in source
    assert "kind: wrote ? 'acknowledgement' : 'empty'" in source


def test_valid_insufficient_evidence_is_a_normal_empty_response() -> None:
    """Map the frozen answerer insufficient-evidence outcome without exposing its enum."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "a.outcome === 'INSUFFICIENT_EVIDENCE' && !a.supporting_item_ids.length" in source
    assert "kind: 'empty', message: a.answer" in source


def test_provider_reads_only_explicit_route_evidence() -> None:
    """Keep the frozen provider payload independent of post-Switch item shape."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "JSON.stringify($('Route bounded product result').item.json.answer_input)" in source
    assert "JSON.stringify($json.answer_input)" not in source
    assert (
        "items: items.map(i => ({ id: i.id, type: i.type, path: i.path, content: i.content }))"
        in source
    )


def test_invalid_browser_request_bypasses_runtime_and_answerer() -> None:
    """Reject malformed browser input through the same narrow direct-response boundary."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "Validate browser request" in source
    assert "La solicitud no es válida." in source
    assert "valid.output(1).to(direct).to(respond)" in source


def test_runtime_timeout_routes_to_the_narrow_safe_error_boundary() -> None:
    """Keep private-runtime transport failures inside the deterministic product boundary."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "options: { timeout: 120000 }" in source
    assert "onError: 'continueErrorOutput'" in source
    assert ".add(runtime.onError(route))" in source


def test_planner_clarification_bypasses_answerer_with_deterministic_text() -> None:
    """Map only Core's allowlisted clarification to the direct product response."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "r.clarification_code === 'UNRECOGNIZED_REQUEST'" in source
    assert "kind: 'clarification'" in source
    assert "Reformúlala con más detalle." in source


def test_frozen_answerer_keeps_the_language_instruction_for_live_sentinels() -> None:
    """Retain the frozen user-language instruction after the English live regression."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "Reply in the user's language unless the request explicitly asks otherwise." in source
