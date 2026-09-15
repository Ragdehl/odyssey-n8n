"""Regression checks for the reviewed Phase 20.2B product workflow source."""

from pathlib import Path

SOURCE = Path(__file__).parents[1] / "workflows" / "odyssey-online.ts"
DEV_FIXTURE = Path(__file__).parents[1] / "scripts" / "prepare_odyssey_dev_identity.py"


def _answerer_key(request_id: str) -> str:
    return f"odyssey-answer-{request_id}"


def test_direct_product_response_omits_internal_route_marker() -> None:
    """Keep direct n8n routing metadata out of the browser response contract."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "const { request_id, status, kind, message, request_detail }" in source
    assert "Return deterministic product response" in source


def test_request_detail_projection_excludes_retrieval_payloads() -> None:
    """Project only bounded operational and change evidence to the browser surface."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "const request_detail =" in source
    assert "r.operational" in source
    assert "affected_stable_note_ids" in source
    assert "const request_detail = withAnswerer(source.request_detail)" in source


def test_request_cost_uses_one_bounded_call_record_per_provider_call() -> None:
    """Aggregate runtime and answerer usage without double-counting stage totals."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "const pricingSnapshotText = process.env.ODYSSEY_PRICING_SNAPSHOT" in source
    assert "if (Array.isArray(stage.provider_calls) && stage.provider_calls.length)" in source
    assert "else if (stage.model && stage.usage)" in source
    assert "provider_calls: [answererCall]" in source
    assert "estimated_cost: requestCost(enriched.operational, pricing)" in source


def test_request_cost_handles_cached_input_and_fails_closed() -> None:
    """Keep cached pricing explicit and never represent missing evidence as zero."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "usage.cached_input_tokens > usage.input_tokens" in source
    assert "rates.cached_input_per_million" in source
    assert "status: 'unavailable', amount_usd: null" in source
    assert "cacheWrite > 0" in source


def test_request_cost_supports_luna_and_bounded_sol_calls() -> None:
    """Use the dated snapshot for every allowlisted provider model, including Sol fallback."""
    source = SOURCE.read_text(encoding="utf-8")
    snapshot = (Path(__file__).parents[1] / "benchmarks/phase20_answerer/pricing_snapshot.json").read_text(
        encoding="utf-8"
    )
    assert '"gpt-5.6-luna"' in snapshot
    assert '"gpt-5.6-sol"' in snapshot
    assert "pricing.as_of" in source


def test_synthetic_self_read_keeps_grounded_evidence_on_the_answer_route() -> None:
    """Keep the DEV SELF fixture and grounded evidence projection available to the answerer."""
    source = SOURCE.read_text(encoding="utf-8")
    fixture = DEV_FIXTURE.read_text(encoding="utf-8")
    assert "Works at Synthetic Systems." in fixture
    assert "route: 'answer'" in source
    assert (
        "items: items.map(i => ({ id: i.id, type: i.type, path: i.path, content: i.content }))"
        in source
    )


def test_failed_result_retains_existing_bounded_request_detail() -> None:
    """Keep safe operational/change evidence visible when Core returns a failed result."""
    source = SOURCE.read_text(encoding="utf-8")
    assert (
        "const hasOperationalEvidence = r.operational && typeof r.operational === 'object'"
        in source
    )
    assert (
        "const hasChangeEvidence = Array.isArray(r.affected_stable_note_ids) || Array.isArray(r.actions)"
        in source
    )
    assert "request_detail ? { ...error, request_detail } : error" in source


def test_failure_without_bounded_evidence_fails_closed() -> None:
    """Do not fabricate a request-detail object for transport/runtime failures without evidence."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "} : undefined;" in source
    assert "if (!id || !r || r.request_id !== id) return [{ json: error }];" in source
    assert "stage: 'runtime'" not in source


def test_completed_response_and_answerer_failure_keep_existing_detail_contract() -> None:
    """Leave completed responses unchanged and retain detail on bounded answerer failures."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "status: r.status === 'partial' ? 'partial' : 'completed'" in source
    assert "request_detail } }]; } catch { return [{ json: { request_id: source.request_id" in source


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


def test_workflow_rendering_requires_an_explicit_safe_target() -> None:
    """Reject an omitted deployment target rather than silently selecting production."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "ODYSSEY_WORKFLOW_ENVIRONMENT must be DEV or PROD" in source
    assert "ODYSSEY_WORKFLOW_RUNTIME_URL is required" in source
    assert "ODYSSEY_WORKFLOW_RUNTIME_URL ??" not in source
    assert "ODYSSEY_WORKFLOW_RUNTIME_URL ||" not in source


def test_dev_identity_is_render_time_only_and_not_browser_controlled() -> None:
    """Project only the synthetic DEV actor configured at render time into the runtime payload."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "ODYSSEY_DEV_STABLE_USER_ID is required for DEV rendering" in source
    assert "ODYSSEY_DEV_STABLE_USER_ID is forbidden for PROD rendering" in source
    assert "authenticated_actor: { stable_user_id:" in source
    assert "authenticated_actor: $json" not in source
    assert "ODYSSEY_DEV_STABLE_USER_ID" in source


def test_prod_projects_only_trusted_access_issuer_and_subject() -> None:
    """Project validated Access claims while excluding the raw assertion and other claims."""
    source = SOURCE.read_text(encoding="utf-8")

    assert "headers['cf-access-jwt-assertion']" in source
    assert "headers['Cf-Access-Jwt-Assertion']" in source
    assert "Buffer.from(segments[1], 'base64url')" in source
    assert "external_principal = { issuer: claims.iss, subject: claims.sub }" in source
    assert "external_principal: $json.external_principal" in source
    assert "assertion: $json" not in source
    assert "email: claims" not in source
    assert "aud: claims" not in source
    assert "token: claims" not in source


def test_prod_access_projection_fails_closed_before_runtime_for_bad_assertion() -> None:
    """Keep missing or malformed trusted Access material on the direct safe-error route."""
    source = SOURCE.read_text(encoding="utf-8")

    assert "if (typeof assertion !== 'string' || !assertion.trim())" in source
    assert "if (segments.length !== 3)" in source
    assert "Odyssey no ha podido autenticar esta solicitud." in source
    assert "external_principal" in source


def test_answerer_credential_name_is_environment_scoped() -> None:
    """Keep the DEV answerer credential distinct from the production workflow credential."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "Odyssey DEV OpenAI Answerer" in source
    assert "Odyssey Phase 20.2B OpenAI Answerer" in source
    assert "newCredential(answererCredentialName)" in source


def test_dev_answerer_credential_requires_a_rendered_isolated_id() -> None:
    """Keep DEV workflow credential resolution bound to the isolated n8n record."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "newCredential(answererCredentialName)" in source


def test_planner_clarification_bypasses_answerer_with_deterministic_text() -> None:
    """Map only Core's allowlisted clarification to the direct product response."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "r.clarification_code === 'UNRECOGNIZED_REQUEST'" in source
    assert "kind: 'clarification'" in source
    assert "Reformúlala con más detalle." in source
    clarification = source.index("r.clarification_code === 'UNRECOGNIZED_REQUEST'")
    answer_routing = source.index("const items = actions.flatMap")
    assert clarification < answer_routing
    assert "route: 'direct', request_id: id, status: 'needs_attention'" in source


def test_frozen_answerer_keeps_the_language_instruction_for_live_sentinels() -> None:
    """Retain the frozen user-language instruction after the English live regression."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "Reply in the user's language unless the request explicitly asks otherwise." in source


def test_answerer_uses_request_id_idempotency_header() -> None:
    """Bind provider replay identity to the validated logical delivery only."""
    source = SOURCE.read_text(encoding="utf-8")
    assert "sendHeaders: true" in source
    assert "name: 'Idempotency-Key'" in source
    assert "'odyssey-answer-' + $('Route bounded product result').item.json.request_id" in source


def test_answerer_idempotency_key_is_stable_per_delivery() -> None:
    """The bounded provider key is deterministic and distinct for new deliveries."""
    first_key = _answerer_key("delivery-a")
    second_key = _answerer_key("delivery-b")
    assert first_key == "odyssey-answer-delivery-a"
    assert second_key == "odyssey-answer-delivery-b"
    assert first_key != second_key
    assert len(_answerer_key("a" * 128)) <= 256


def test_answerer_idempotency_key_excludes_request_and_identity_data() -> None:
    """Keep request text, claims, and Odyssey identity outside provider replay identity."""
    expression = "'odyssey-answer-' + $('Route bounded product result').item.json.request_id"
    assert ".item.json.request +" not in expression
    for forbidden in ("issuer", "subject", "email", "stable_user_id", "person_note_id", "aud"):
        assert forbidden not in expression
