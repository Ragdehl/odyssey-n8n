import { expr, newCredential, node, trigger, workflow } from '@n8n/workflow-sdk';

const deploymentEnvironment = process.env.ODYSSEY_WORKFLOW_ENVIRONMENT;
const runtimeUrl = process.env.ODYSSEY_WORKFLOW_RUNTIME_URL;
const devStableUserId = process.env.ODYSSEY_DEV_STABLE_USER_ID;
if (deploymentEnvironment !== 'DEV' && deploymentEnvironment !== 'PROD') {
  throw new Error('ODYSSEY_WORKFLOW_ENVIRONMENT must be DEV or PROD');
}
if (!runtimeUrl) throw new Error('ODYSSEY_WORKFLOW_RUNTIME_URL is required');
const runtimeBaseUrl = runtimeUrl.replace(/\/execute$/, '');
if (deploymentEnvironment === 'DEV' && !devStableUserId) {
  throw new Error('ODYSSEY_DEV_STABLE_USER_ID is required for DEV rendering');
}
if (deploymentEnvironment === 'PROD' && devStableUserId) {
  throw new Error('ODYSSEY_DEV_STABLE_USER_ID is forbidden for PROD rendering');
}
const pricingSnapshotText = process.env.ODYSSEY_PRICING_SNAPSHOT;
if (!pricingSnapshotText) throw new Error('ODYSSEY_PRICING_SNAPSHOT is required');
let pricingSnapshot;
try {
  pricingSnapshot = JSON.parse(pricingSnapshotText);
} catch {
  throw new Error('ODYSSEY_PRICING_SNAPSHOT is invalid JSON');
}
if (!pricingSnapshot || typeof pricingSnapshot !== 'object' ||
    typeof pricingSnapshot.as_of !== 'string' || !pricingSnapshot.as_of.trim() ||
    typeof pricingSnapshot.models !== 'object' || !pricingSnapshot.models) {
  throw new Error('ODYSSEY_PRICING_SNAPSHOT has an invalid shape');
}
for (const rates of Object.values(pricingSnapshot.models)) {
  if (!rates || typeof rates !== 'object' ||
      ['input_per_million', 'cached_input_per_million', 'output_per_million']
        .some((key) => typeof rates[key] !== 'number' || rates[key] < 0)) {
    throw new Error('ODYSSEY_PRICING_SNAPSHOT has invalid model rates');
  }
}
const pricingSnapshotLiteral = JSON.stringify(pricingSnapshot);

const costHelpers = String.raw`
function providerUsage(value) {
  const usage = value && typeof value === 'object' && value.usage && typeof value.usage === 'object' ? value.usage : value;
  if (!usage || typeof usage !== 'object') return undefined;
  return {
    input_tokens: usage.input_tokens,
    cached_input_tokens: usage.cached_input_tokens ?? usage.input_tokens_details?.cached_tokens,
    cache_write_tokens: usage.cache_write_tokens ?? usage.input_tokens_details?.cache_write_tokens,
    output_tokens: usage.output_tokens,
    reasoning_tokens: usage.reasoning_tokens ?? usage.output_tokens_details?.reasoning_tokens
  };
}

function providerCost(usage, model, pricing) {
  const rates = pricing.models[model];
  if (!rates || !usage) return undefined;
  const required = ['input_tokens', 'cached_input_tokens', 'output_tokens'];
  if (required.some((key) => !Number.isInteger(usage[key]) || usage[key] < 0)) return undefined;
  const cacheWrite = usage.cache_write_tokens === undefined ? 0 : usage.cache_write_tokens;
  if (!Number.isInteger(cacheWrite) || cacheWrite < 0 || cacheWrite > 0) return undefined;
  if (usage.cached_input_tokens > usage.input_tokens) return undefined;
  const ordinary = usage.input_tokens - usage.cached_input_tokens - cacheWrite;
  return (ordinary * rates.input_per_million + usage.cached_input_tokens * rates.cached_input_per_million + usage.output_tokens * rates.output_per_million) / 1000000;
}

function requestCost(operational, pricing) {
  if (!operational || !Array.isArray(operational.stages)) return { status: 'unavailable', amount_usd: null, pricing_basis: pricing.as_of };
  const calls = [];
  for (const stage of operational.stages) {
    if (Array.isArray(stage.provider_calls) && stage.provider_calls.length) {
      for (const call of stage.provider_calls) calls.push({ model: call.model, usage: call.usage });
    } else if (stage.model && stage.usage) {
      calls.push({ model: stage.model, usage: stage.usage });
    }
  }
  if (!calls.length) return { status: 'unavailable', amount_usd: null, pricing_basis: pricing.as_of };
  const costs = calls.map((call) => providerCost(call.usage, call.model, pricing));
  if (costs.some((cost) => cost === undefined)) return { status: 'unavailable', amount_usd: null, pricing_basis: pricing.as_of };
  return { status: 'estimated', amount_usd: Number(costs.reduce((total, cost) => total + cost, 0).toFixed(9)), pricing_basis: pricing.as_of };
}

function safeUsage(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const allowed = ['input_tokens', 'cached_input_tokens', 'cache_write_tokens', 'output_tokens', 'reasoning_tokens'];
  const result = {};
  for (const key of allowed) {
    if (value[key] === undefined || value[key] === null) continue;
    if (!Number.isInteger(value[key]) || value[key] < 0) return undefined;
    result[key] = value[key];
  }
  return result;
}

const safeMs = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
function safeCoverage(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const fields = ['attributed_ms', 'unattributed_ms', 'coverage_pct', 'overlapping_ms'];
  if (fields.some(key => safeMs(value[key]) === undefined) || value.coverage_pct > 100) return undefined;
  return Object.fromEntries(fields.map(key => [key, value[key]]));
}
function safeSpans(value) {
  if (!Array.isArray(value) || value.length > 128) return undefined;
  const result = value.map(span => {
    if (!span || typeof span !== 'object' || Array.isArray(span) || typeof span.name !== 'string' || span.name.length > 80 || typeof span.outcome !== 'string' || span.outcome.length > 80 || safeMs(span.start_offset_ms) === undefined || safeMs(span.duration_ms) === undefined) return undefined;
    const error = span.error_category;
    if (error !== null && error !== undefined && (typeof error !== 'string' || error.length > 120)) return undefined;
    return { name: span.name, outcome: span.outcome, start_offset_ms: span.start_offset_ms, duration_ms: span.duration_ms, error_category: error ?? null };
  });
  return result.some(item => item === undefined) ? undefined : result;
}
function safeInputSizes(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length > 12) return undefined;
  const allowed = new Set(['fixed_instructions_bytes', 'retrieval_capabilities_bytes', 'write_capabilities_bytes', 'recent_context_bytes', 'luna_rules_examples_bytes', 'user_request_bytes', 'structured_output_schema_bytes']);
  if (Object.entries(value).some(([key, number]) => !allowed.has(key) || !Number.isInteger(number) || number < 0)) return undefined;
  return value;
}
function safeDetailStage(value, nested = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || typeof value.name !== 'string' || typeof value.outcome !== 'string') return undefined;
  const text = (key, maximum) => value[key] === null || value[key] === undefined || (typeof value[key] === 'string' && value[key].length <= maximum) ? value[key] ?? null : undefined;
  const duration = value.duration_ms === null || value.duration_ms === undefined || (typeof value.duration_ms === 'number' && Number.isFinite(value.duration_ms) && value.duration_ms >= 0) ? value.duration_ms ?? null : undefined;
  const model = text('model', 120); const reasoning = text('reasoning_effort', 120); const error = text('error_category', 120);
  if (value.name.length > 80 || value.outcome.length > 80 || model === undefined || reasoning === undefined || error === undefined || duration === undefined) return undefined;
  const usage = safeUsage(value.usage);
  if (value.usage !== null && value.usage !== undefined && usage === undefined) return undefined;
  const calls = nested ? [] : Array.isArray(value.provider_calls) ? value.provider_calls.map((call) => safeDetailStage(call, true)) : undefined;
  if (calls === undefined || calls.some((call) => call === undefined) || calls.length > 32) return undefined;
  const start = value.start_offset_ms === undefined || value.start_offset_ms === null ? undefined : safeMs(value.start_offset_ms);
  const spans = value.substeps === undefined ? undefined : safeSpans(value.substeps);
  const coverage = value.coverage === undefined || value.coverage === null ? undefined : safeCoverage(value.coverage);
  const sizes = value.input_sizes === undefined || value.input_sizes === null ? undefined : safeInputSizes(value.input_sizes);
  if ((value.start_offset_ms != null && start === undefined) || (value.substeps !== undefined && spans === undefined) || (value.coverage != null && coverage === undefined) || (value.input_sizes != null && sizes === undefined)) return undefined;
  const result = { name: value.name, outcome: value.outcome, duration_ms: duration, model, reasoning_effort: reasoning, error_category: error, ...(usage ? { usage } : {}), provider_calls: calls };
  if (start !== undefined) result.start_offset_ms = start;
  if (spans !== undefined) result.substeps = spans;
  if (coverage !== undefined) result.coverage = coverage;
  if (sizes !== undefined) result.input_sizes = sizes;
  if (nested) {
    const fields = ['validation_stage', 'validation_code', 'provider_status', 'incomplete_reason', 'parse_status', 'result_kind'];
    for (const key of fields) { const item = text(key, 120); if (item === undefined) return undefined; if (item !== null) result[key] = item; }
    for (const key of ['ordinal', 'attempt_count', 'output_text_chars', 'output_text_bytes']) { const item = value[key]; if (item == null) continue; if (!Number.isInteger(item) || item < 0) return undefined; result[key] = item; }
  }
  return result;
}

function safeOperational(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray(value.stages) || value.stages.length > 16) return { total_duration_ms: null, stages: [] };
  const total = value.total_duration_ms === null || value.total_duration_ms === undefined || (typeof value.total_duration_ms === 'number' && Number.isFinite(value.total_duration_ms) && value.total_duration_ms >= 0) ? value.total_duration_ms ?? null : null;
  const stages = value.stages.map((stage) => safeDetailStage(stage));
  if (stages.some(stage => stage === undefined)) return { total_duration_ms: null, stages: [] };
  const coverage = value.coverage == null ? undefined : safeCoverage(value.coverage);
  const product = value.product_execution_duration_ms == null ? undefined : safeMs(value.product_execution_duration_ms);
  return { total_duration_ms: total, stages, ...(coverage ? { coverage } : {}), ...(product !== undefined ? { product_execution_duration_ms: product } : {}) };
}
`;

const routeCode = `const r = $input.first().json; const id = $('Odyssey product request').item.json.body?.request_id; const pricing = ${pricingSnapshotLiteral}; ${costHelpers}
const error = { route: 'direct', request_id: id, status: 'failed', kind: 'error', message: 'Odyssey no ha podido procesar esta solicitud.' };
const safeSearchSnapshot = value => value && typeof value === 'object' && !Array.isArray(value) && value.version === 1 && typeof value.query === 'string' && value.query.length > 0 && value.query.length <= 512 && Array.isArray(value.filters) && value.filters.length <= 16 && Array.isArray(value.note_ids) && value.note_ids.length <= 64 && new Set(value.note_ids).size === value.note_ids.length && value.note_ids.every(id => typeof id === 'string' && id.length > 0 && id.length <= 128) && Number.isInteger(value.total) && value.total >= value.note_ids.length && typeof value.truncated === 'boolean' && value.truncated === (value.total > value.note_ids.length) && typeof value.sort === 'string' && typeof value.ranking_version === 'string' && typeof value.executed_at === 'string';
const safeAffectedSnapshot = value => value && typeof value === 'object' && !Array.isArray(value) && value.version === 2 && value.kind === 'affected_notes' && typeof value.executed_at === 'string' && Array.isArray(value.note_ids) && value.note_ids.length <= 64 && new Set(value.note_ids).size === value.note_ids.length && value.note_ids.every(id => typeof id === 'string' && id.length > 0 && id.length <= 128) && Number.isInteger(value.total) && value.total >= 1 && value.total >= value.note_ids.length && typeof value.truncated === 'boolean' && value.truncated === (value.total > value.note_ids.length);
const safeSnapshot = value => safeSearchSnapshot(value) || safeAffectedSnapshot(value) ? value : undefined;
if (!id || !r || r.request_id !== id) return [{ json: error }]; const hasOperationalEvidence = r.operational && typeof r.operational === 'object'; const hasChangeEvidence = Array.isArray(r.affected_stable_note_ids) || Array.isArray(r.actions); const request_detail_base = hasOperationalEvidence || hasChangeEvidence ? { request_id: id, operational: hasOperationalEvidence ? safeOperational(r.operational) : { total_duration_ms: null, stages: [] }, changes: { affected_stable_note_ids: Array.isArray(r.affected_stable_note_ids) ? r.affected_stable_note_ids.filter((item) => typeof item === 'string' && item.length <= 128).slice(0, 64) : [], units: Array.isArray(r.actions) ? r.actions.flatMap(a => Array.isArray(a.units) ? a.units.map(u => ({ stable_note_id: typeof u.stable_note_id === 'string' && u.stable_note_id.length <= 128 ? u.stable_note_id : null, operation: typeof u.operation === 'string' && u.operation.length <= 80 ? u.operation : null, status: typeof u.status === 'string' && u.status.length <= 80 ? u.status : 'unknown' })) : []).slice(0, 64) : [] } } : undefined; const request_detail = request_detail_base ? { ...request_detail_base, estimated_cost: requestCost(request_detail_base.operational, pricing) } : undefined;
if (r.status === 'needs_attention' && r.clarification_code === 'UNRECOGNIZED_REQUEST') return [{ json: { route: 'direct', request_id: id, status: 'needs_attention', kind: 'clarification', message: 'No he podido interpretar la solicitud. Reformúlala con más detalle.', request_detail } }]; if (r.status === 'failed') return [{ json: request_detail ? { ...error, request_detail } : error }];
const snapshot = safeSnapshot(r.note_result_snapshot); const intent = r.presentation_intent === 'note_set' || r.presentation_intent === 'answer_and_note_set' ? r.presentation_intent : 'answer'; if (intent !== 'answer' && !snapshot) return [{ json: request_detail ? { ...error, request_detail } : error }]; if (intent === 'note_set') return [{ json: { route: 'direct', request_id: id, status: r.status === 'partial' ? 'partial' : 'completed', kind: 'note_set', message: snapshot.total ? 'He encontrado notas para revisar.' : 'No hay notas que coincidan.', request_detail, note_result_snapshot: snapshot } }];
const actions = Array.isArray(r.actions) ? r.actions : []; const items = actions.flatMap(a => Array.isArray(a.retrieval?.items) ? a.retrieval.items : []).filter(i => i && typeof i.id === 'string' && typeof i.type === 'string' && typeof i.path === 'string' && typeof i.content === 'string'); if (items.length) return [{ json: { route: 'answer', request_id: id, status: r.status === 'partial' ? 'partial' : 'completed', request_detail, note_result_snapshot: snapshot, answerer_started_ms: Date.now(), answer_input: { request: $('Odyssey product request').item.json.body.request, status: r.status === 'partial' ? 'partial' : 'completed', retrieval_query: actions.find(a => Array.isArray(a.retrieval?.items))?.retrieval?.query || '', items: items.map(i => ({ id: i.id, type: i.type, path: i.path, content: i.content })) } } }]; const wrote = actions.some(a => Array.isArray(a.units) && a.units.some(u => u.status === 'completed' || u.status === 'succeeded')); return [{ json: { route: 'direct', request_id: id, status: r.status === 'partial' ? 'partial' : 'completed', kind: wrote ? 'acknowledgement' : 'empty', message: wrote ? 'La información se ha guardado.' : 'No hay evidencia suficiente en Odyssey para responder.', request_detail, ...(snapshot ? { note_result_snapshot: snapshot } : {}) } }];`;

const finishCode = `const source = $('Route bounded product result').item.json;
const answerResponse = $json.body && typeof $json.body === 'object' ? $json.body : $json;
const pricing = ${pricingSnapshotLiteral}; ${costHelpers}
const elapsed = Number.isInteger(source.answerer_started_ms) ? Date.now() - source.answerer_started_ms : null;
const duration = elapsed !== null && elapsed >= 0 ? elapsed : null;
function withAnswerer(detail, outcome, errorCategory, parseStatus) {
  if (!detail) return undefined;
  const usage = providerUsage(answerResponse);
  const answererCall = { name: 'answerer', outcome, duration_ms: duration, model: 'gpt-5.6-luna', reasoning_effort: 'none', usage, error_category: errorCategory, parse_status: parseStatus };
  const answererStage = { name: 'answerer', outcome, duration_ms: duration, model: 'gpt-5.6-luna', reasoning_effort: 'none', usage, error_category: errorCategory, provider_calls: [answererCall] };
  const enriched = { ...detail, operational: { ...detail.operational, stages: [...detail.operational.stages, answererStage] } };
  return { ...enriched, estimated_cost: requestCost(enriched.operational, pricing) };
}
const text = answerResponse.output?.flatMap(o => o.content || []).find(c => c.type === 'output_text')?.text;
try {
  if ($json.statusCode && $json.statusCode >= 400) throw new Error('provider');
  const a = JSON.parse(text);
  const known = new Set(source.answer_input.items.map(i => i.id));
  if (!a.answer || !Array.isArray(a.supporting_item_ids) || !Array.isArray(a.limitations) || a.supporting_item_ids.some(i => !known.has(i))) throw new Error('validation');
  const request_detail = withAnswerer(source.request_detail, 'completed', null, 'succeeded');
  if (a.outcome === 'INSUFFICIENT_EVIDENCE' && !a.supporting_item_ids.length) return [{ json: { request_id: source.request_id, status: source.status, kind: 'empty', message: a.answer, request_detail, note_result_snapshot: source.note_result_snapshot } }];
  if (a.outcome !== 'ANSWER' || !a.supporting_item_ids.length) throw new Error('validation');
  return [{ json: { request_id: source.request_id, status: source.status, kind: 'answer', message: a.answer, request_detail, note_result_snapshot: source.note_result_snapshot } }];
} catch (error) {
  const category = error?.message === 'provider' ? 'AnswerProviderFailure' : error?.message === 'validation' ? 'AnswerValidationError' : 'AnswerParseError';
  const request_detail = withAnswerer(source.request_detail, 'failed', category, category === 'AnswerParseError' ? 'failed' : category === 'AnswerValidationError' ? 'succeeded' : null);
  return [{ json: { request_id: source.request_id, status: 'failed', kind: 'error', message: 'Odyssey no ha podido procesar esta solicitud.', request_detail } }];
}`;
const authenticatedActor = deploymentEnvironment === 'DEV'
  ? `, authenticated_actor: { stable_user_id: ${JSON.stringify(devStableUserId)} }`
  : '';
const runtimeIdentity = deploymentEnvironment === 'DEV'
  ? `${authenticatedActor}, conversation_id: 'main'`
  : `, external_principal: $json.external_principal, conversation_id: 'main'`;
const productionPrincipalProjection = deploymentEnvironment === 'PROD'
  ? `
const headers = $input.first().json.headers;
const assertion = headers && typeof headers === 'object'
  ? headers['cf-access-jwt-assertion'] ?? headers['Cf-Access-Jwt-Assertion']
  : null;
let external_principal;
try {
  if (typeof assertion !== 'string' || !assertion.trim()) throw new Error();
  const segments = assertion.split('.');
  if (segments.length !== 3) throw new Error();
  JSON.parse(Buffer.from(segments[0], 'base64url').toString('utf8'));
  const claims = JSON.parse(Buffer.from(segments[1], 'base64url').toString('utf8'));
  if (
    !claims ||
    typeof claims.iss !== 'string' ||
    !claims.iss.trim() ||
    typeof claims.sub !== 'string' ||
    !claims.sub.trim()
  ) throw new Error();
  external_principal = { issuer: claims.iss, subject: claims.sub };
} catch {
  return [{ json: { valid: false, route: 'direct', request_id: request_id || 'invalid-request', status: 'failed', kind: 'error', message: 'Odyssey no ha podido autenticar esta solicitud.' } }];
}
`
  : '';
const answererCredentialName = deploymentEnvironment === 'DEV'
  ? 'Odyssey DEV OpenAI Answerer'
  : 'Odyssey Phase 20.2B OpenAI Answerer';
const workflowName = deploymentEnvironment === 'DEV'
  ? 'Odyssey — DEV Online product boundary'
  : 'Odyssey — Online product boundary';

const request = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey product request', parameters: { httpMethod: 'POST', path: 'request', responseMode: 'responseNode' }, position: [0, 0] }, output: [{ body: { request: '¿Dónde trabaja Marta?', request_id: 'web-example' } }] });
const validate = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Validate browser request', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const body = $input.first().json.body || {}; const request = typeof body.request === 'string' ? body.request.trim() : ''; const request_id = typeof body.request_id === 'string' ? body.request_id : ''; const valid = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(request_id) && request.length > 0; if (!valid) return [{ json: { valid: false, route: 'direct', request_id: request_id || 'invalid-request', status: 'failed', kind: 'error', message: 'La solicitud no es válida.' } }]; ${productionPrincipalProjection} return [{ json: { valid, request, request_id${deploymentEnvironment === 'PROD' ? ', external_principal' : ''} } }];` }, position: [220, 0] }, output: [{ valid: true, request: '¿Dónde trabaja Marta?', request_id: 'web-example' }] });
const valid = node({ type: 'n8n-nodes-base.switch', version: 3.2, config: { name: 'Browser request valid?', parameters: { mode: 'expression', numberOutputs: 2, output: expr('{{ $json.valid ? 0 : 1 }}') }, position: [440, 0] }, output: [{ valid: true, request: '¿Dónde trabaja Marta?', request_id: 'web-example' }, { valid: false, route: 'direct', request_id: 'invalid-request', status: 'failed', kind: 'error', message: 'La solicitud no es válida.' }] });
const runtime = node({ type: 'n8n-nodes-base.httpRequest', version: 4.5, config: { name: 'Execute private Odyssey runtime', parameters: { method: 'POST', url: runtimeUrl, sendBody: true, contentType: 'json', specifyBody: 'json', jsonBody: expr(`{{ { request: $json.request, request_id: $json.request_id${runtimeIdentity} } }}`), options: { timeout: 120000 }, response: { response: { neverError: true, responseFormat: 'json' } } }, onError: 'continueErrorOutput', position: [660, 0] }, output: [{ request_id: 'web-example', status: 'completed', actions: [] }] });
const route = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Route bounded product result', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: routeCode }, position: [520, 0] }, output: [{ route: 'answer', request_id: 'web-example', status: 'completed', request_detail: { request_id: 'web-example', operational: { total_duration_ms: 100, stages: [] }, changes: { affected_stable_note_ids: [], units: [] } }, answer_input: { request: '¿Dónde trabaja Marta?', status: 'completed', retrieval_query: 'Marta', items: [{ id: 'marta', type: 'person', path: 'marta.md', content: 'Marta trabaja en Thales.' }] } }] });
const select = node({ type: 'n8n-nodes-base.switch', version: 3.2, config: { name: 'Need grounded answer?', parameters: { mode: 'expression', numberOutputs: 2, output: expr("{{ $json.route === 'answer' ? 0 : 1 }}") }, position: [760, 0] }, output: [{ route: 'answer', answer_input: { request: '¿Dónde trabaja Marta?', status: 'completed', retrieval_query: 'Marta', items: [{ id: 'marta', type: 'person', path: 'marta.md', content: 'Marta trabaja en Thales.' }] } }, { route: 'direct', response: { request_id: 'web-example', status: 'completed', kind: 'empty', message: 'No hay evidencia suficiente en Odyssey para responder.' } }] });
const answer = node({ type: 'n8n-nodes-base.httpRequest', version: 4.5, config: { name: 'Luna grounded answerer', parameters: { method: 'POST', url: 'https://api.openai.com/v1/responses', authentication: 'genericCredentialType', genericAuthType: 'httpBearerAuth', sendHeaders: true, headerParameters: { parameters: [{ name: 'Idempotency-Key', value: expr("{{ 'odyssey-answer-' + $('Route bounded product result').item.json.request_id }}") }] }, sendBody: true, contentType: 'json', specifyBody: 'json', jsonBody: expr("{{ { model: 'gpt-5.6-luna', reasoning: { effort: 'none' }, store: false, input: [{ role: 'system', content: \"You are Odyssey's bounded answerer. Answer only from the supplied Odyssey evidence; never use outside knowledge or fill missing facts from memory. Reply in the user's language unless the request explicitly asks otherwise. Preserve names, numbers, dates, and domain terms exactly when they matter. For ANSWER, cite every supplied evidence item you rely on in supporting_item_ids and do not cite irrelevant items. If the supplied evidence cannot answer the request, return INSUFFICIENT_EVIDENCE, explain that briefly, and use no support IDs. If Odyssey status is partial, include PARTIAL_RESULT in limitations and do not imply that the overall Odyssey operation was fully complete.\" }, { role: 'user', content: JSON.stringify($('Route bounded product result').item.json.answer_input) }], text: { format: { type: 'json_schema', name: 'odyssey_grounded_answer', strict: true, schema: { type: 'object', properties: { outcome: { type: 'string', enum: ['ANSWER', 'INSUFFICIENT_EVIDENCE'] }, answer: { type: 'string', minLength: 1 }, supporting_item_ids: { type: 'array', items: { type: 'string' } }, limitations: { type: 'array', items: { type: 'string', enum: ['PARTIAL_RESULT'] } } }, required: ['outcome', 'answer', 'supporting_item_ids', 'limitations'], additionalProperties: false } } } } }}"), options: { timeout: 60000 }, response: { response: { fullResponse: true, neverError: true, responseFormat: 'json' } } }, credentials: { httpBearerAuth: newCredential(answererCredentialName) }, position: [1020, -100] }, output: [{ statusCode: 200, body: {} }] });
const finish = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Return narrow product response', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: finishCode }, position: [1260, 0] }, output: [{ request_id: 'web-example', status: 'completed', kind: 'answer', message: 'Marta trabaja en Thales.', request_detail: { request_id: 'web-example', operational: { total_duration_ms: 100, stages: [] }, changes: { affected_stable_note_ids: [], units: [] } } }] });
const direct = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Return deterministic product response', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: "const { request_id, status, kind, message, request_detail, note_result_snapshot } = $input.first().json; return [{ json: { request_id, status, kind, message, request_detail, ...(note_result_snapshot ? { note_result_snapshot } : {}) } }];" }, position: [1020, 100] }, output: [{ request_id: 'web-example', status: 'completed', kind: 'empty', message: 'No hay evidencia suficiente en Odyssey para responder.', request_detail: { request_id: 'web-example', operational: { total_duration_ms: 100, stages: [] }, changes: { affected_stable_note_ids: [], units: [] } } }] });
const respond = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'Respond to Odyssey browser', parameters: { respondWith: 'json', responseBody: expr('{{ $json }}') }, position: [1500, 0] }, output: [{}] });

const conversationRequest = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey conversation request', parameters: { httpMethod: 'POST', path: 'conversation', responseMode: 'responseNode' }, position: [0, 700] }, output: [{ body: { operation: 'main' } }] });
const conversationIdentity = deploymentEnvironment === 'DEV'
  ? `const authenticated_actor = { stable_user_id: ${JSON.stringify(devStableUserId)} };`
  : `const headers = $input.first().json.headers; const assertion = headers && typeof headers === 'object' ? headers['cf-access-jwt-assertion'] ?? headers['Cf-Access-Jwt-Assertion'] : null; let external_principal; try { if (typeof assertion !== 'string' || !assertion.trim()) throw new Error(); const segments = assertion.split('.'); if (segments.length !== 3) throw new Error(); JSON.parse(Buffer.from(segments[0], 'base64url').toString('utf8')); const claims = JSON.parse(Buffer.from(segments[1], 'base64url').toString('utf8')); if (!claims || typeof claims.iss !== 'string' || !claims.iss.trim() || typeof claims.sub !== 'string' || !claims.sub.trim()) throw new Error(); external_principal = { issuer: claims.iss, subject: claims.sub }; } catch { return [{ json: { invalid: true, error: 'invalid conversation identity' } }]; }`;
const conversationValidate = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Validate conversation request', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const body = $input.first().json.body || {}; const operation = typeof body.operation === 'string' ? body.operation : ''; const validOperation = ['main', 'turn'].includes(operation); const request_id = typeof body.request_id === 'string' ? body.request_id : undefined; const role = typeof body.role === 'string' ? body.role : undefined; const text = typeof body.text === 'string' ? body.text : undefined; const limit = Number.isInteger(body.limit) ? body.limit : undefined; const before = typeof body.before === 'string' ? body.before : undefined; const request_detail = body.request_detail; const note_result_snapshot = body.note_result_snapshot; const safeSnapshot = note_result_snapshot === undefined || (note_result_snapshot && typeof note_result_snapshot === 'object' && !Array.isArray(note_result_snapshot)); if (!validOperation || !safeSnapshot || (operation === 'main' && ((limit !== undefined && (limit < 1 || limit > 50)) || (before !== undefined && !before))) || (operation === 'turn' && (!request_id || !['user', 'assistant'].includes(role) || !text))) return [{ json: { invalid: true, error: 'invalid conversation request' } }]; ${conversationIdentity} return [{ json: { operation, ...(operation === 'turn' ? { conversation_id: 'main' } : {}), request_id, role, text, limit, before, request_detail, note_result_snapshot${deploymentEnvironment === 'DEV' ? ', authenticated_actor' : ', external_principal'} } }];` }, position: [240, 700] }, output: [{ operation: 'main' }] });
const conversationCall = node({ type: 'n8n-nodes-base.httpRequest', version: 4.5, config: { name: 'Execute conversation operation', parameters: { method: 'POST', url: expr(`${runtimeBaseUrl}/conversation/{{ $json.operation }}`), sendBody: true, contentType: 'json', specifyBody: 'json', jsonBody: expr('{{ $json }}'), options: { timeout: 10000 }, response: { response: { neverError: true, responseFormat: 'json' } } }, onError: 'continueErrorOutput', position: [520, 700] }, output: [{}] });
const conversationRespond = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'Respond to conversation browser', parameters: { respondWith: 'json', responseBody: expr('{{ $json.body || $json }}') }, position: [780, 700] }, output: [{}] });

// Notes remains a projection route: n8n authenticates and bounds its envelope, while the private
// runtime owns all Markdown parsing, filtering, ranking, link resolution, and provider decisions.
const notesRequest = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey Notes request', parameters: { httpMethod: 'POST', path: 'notes', responseMode: 'responseNode' }, position: [0, 1000] }, output: [{ body: { operation: 'query', mode: 'feed' } }] });
const notesValidate = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'Validate Notes request', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const body = $input.first().json.body || {}; const operation = typeof body.operation === 'string' ? body.operation : ''; const shapes = { capabilities: new Set(['operation']), query: new Set(['operation', 'query', 'filters', 'snapshot_ids', 'page_size', 'cursor', 'sort', 'mode']), intelligent: new Set(['operation', 'query', 'filters', 'page_size', 'cursor', 'sort']), detail: new Set(['operation', 'note_id']), backlinks: new Set(['operation', 'note_id', 'page_size', 'cursor']) }; const allowed = shapes[operation]; const query = typeof body.query === 'string' ? body.query : ''; const page_size = Number.isInteger(body.page_size) ? body.page_size : undefined; const cursor = typeof body.cursor === 'string' ? body.cursor : undefined; const note_id = typeof body.note_id === 'string' ? body.note_id : undefined; const filters = Array.isArray(body.filters) ? body.filters : []; const snapshot_ids = Array.isArray(body.snapshot_ids) ? body.snapshot_ids : []; const sort = typeof body.sort === 'string' ? body.sort : undefined; const mode = typeof body.mode === 'string' ? body.mode : undefined; const valid = Boolean(allowed) && Object.keys(body).every(key => allowed.has(key)) && query.length <= 4096 && filters.length <= 16 && snapshot_ids.length <= 64 && snapshot_ids.every(id => typeof id === 'string' && id.length <= 128) && (page_size === undefined || (page_size >= 1 && page_size <= 40)) && (cursor === undefined || cursor.length <= 4096) && (operation !== 'detail' || (note_id && note_id.length <= 128)) && (operation !== 'backlinks' || (note_id && note_id.length <= 128)); if (!valid) return [{ json: { invalid: true, error: 'invalid notes request' } }]; const forwarded = { operation }; if (operation === 'query') { Object.assign(forwarded, { query, filters, snapshot_ids }); if (page_size !== undefined) forwarded.page_size = page_size; if (cursor !== undefined) forwarded.cursor = cursor; if (sort !== undefined) forwarded.sort = sort; if (mode !== undefined) forwarded.mode = mode; } if (operation === 'intelligent') { Object.assign(forwarded, { query, filters }); if (page_size !== undefined) forwarded.page_size = page_size; if (cursor !== undefined) forwarded.cursor = cursor; if (sort !== undefined) forwarded.sort = sort; } if (operation === 'detail') forwarded.note_id = note_id; if (operation === 'backlinks') { forwarded.note_id = note_id; if (page_size !== undefined) forwarded.page_size = page_size; if (cursor !== undefined) forwarded.cursor = cursor; } ${conversationIdentity} return [{ json: { ...forwarded${deploymentEnvironment === 'DEV' ? ', authenticated_actor' : ', external_principal'} } }];` }, position: [240, 1000] }, output: [{ operation: 'query', mode: 'feed' }] });
const notesValid = node({ type: 'n8n-nodes-base.switch', version: 3.2, config: { name: 'Notes request valid?', parameters: { mode: 'expression', numberOutputs: 2, output: expr('{{ $json.invalid ? 1 : 0 }}') }, position: [390, 1000] }, output: [{ operation: 'query', mode: 'feed' }, { invalid: true, error: 'invalid notes request' }] });
const notesCall = node({ type: 'n8n-nodes-base.httpRequest', version: 4.5, config: { name: 'Execute Notes operation', parameters: { method: 'POST', url: `${runtimeBaseUrl}/notes`, sendBody: true, contentType: 'json', specifyBody: 'json', jsonBody: expr('{{ $json }}'), options: { timeout: 30000 }, response: { response: { neverError: true, responseFormat: 'json' } } }, onError: 'continueErrorOutput', position: [520, 1000] }, output: [{ kind: 'page', items: [] }] });
const notesRespond = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'Respond to Notes browser', parameters: { respondWith: 'json', responseBody: expr('{{ $json }}') }, position: [780, 1000] }, output: [{}] });
const notesInvalidRespond = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'Reject invalid Notes request', parameters: { respondWith: 'json', responseBody: expr("{{ { error: 'invalid notes request' } }}") }, position: [520, 1100] }, output: [{}] });

export default workflow('odyssey-online', workflowName).add(request).to(validate).to(valid).add(valid.output(0).to(runtime).to(route).to(select)).add(runtime.onError(route)).add(select.output(0).to(answer).to(finish).to(respond)).add(select.output(1).to(direct).to(respond)).add(valid.output(1).to(direct).to(respond)).add(conversationRequest).to(conversationValidate).to(conversationCall).to(conversationRespond).add(notesRequest).to(notesValidate).to(notesValid).add(notesValid.output(0).to(notesCall).to(notesRespond)).add(notesValid.output(1).to(notesInvalidRespond));
