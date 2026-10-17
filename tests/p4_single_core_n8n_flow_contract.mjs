/* Authoritative single Core P4 result passes source n8n sanitizer + browser flow validation.
 * Input is the real offline Core Writer/Markdown result serialized by the runtime.
 * This does not claim actual browser launch or live webhook execution.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {validateExecutionFlow, ProductRequestError} from '../odyssey_web/client.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const code=readFileSync(path.join(root,'workflows/odyssey-online.ts'),'utf8');
const begin=code.indexOf('const safeFlow = ');
const end=code.indexOf('\nif (!id || !r',begin);
assert(begin>0 && end>begin);
const {safeFlow,flowMatchesStages}=vm.runInNewContext(
  code.slice(begin,end)+'\n({safeFlow,flowMatchesStages})',{}, {timeout:500});
const result=JSON.parse(readFileSync(0,'utf8'));
assert.equal(result.status,'completed');
const {execution_flow:flow,operational}=result;
assert.equal(flow.routes.length,1);
assert.equal(flow.routes[0].capability,'core');
assert.equal(flow.routes[0].text,flow.input);
assert.equal(flow.routes[0].depends_on,undefined);
assert(flow.routes[0].stage_count>0);
assert(operational.stages.some(s=>s.name==='application.source_processing'));
const source=operational.stages.find(s=>s.name==='application.source_processing');
assert(source.substeps.length>=3);
assert(source.substeps.filter(s=>s.name.startsWith('provider.')).length>=3);
assert(source.substeps.every(s=>!s.name.includes(flow.input)));
assert(safeFlow(flow), 'n8n source sanitizer discarded legitimate Core flow');
assert.equal(flowMatchesStages(flow,operational.stages),true);
const validated=validateExecutionFlow(flow,operational.stages);
assert.equal(validated.routes[0].stage_count,flow.routes[0].stage_count);
const tampered=structuredClone(flow);
tampered.routes[0].depends_on=0;
tampered.routes[0].reason=null;
assert.equal(safeFlow(tampered),undefined);
assert.throws(()=>validateExecutionFlow(tampered,operational.stages),ProductRequestError);
console.log(JSON.stringify({passed:true,provider_calls:source.substeps.length,core_stages:flow.routes[0].stage_count}));
