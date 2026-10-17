/* Validate the ACTUAL n8n workflow's safeFlow and flowMatchesStages code.
 * Usage: node tests/p4_dependent_n8n_flow_contract.mjs < JSON-result
 * No n8n network, browser, or provider. Uses the installed workflow source.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const content = readFileSync(path.join(root,'workflows/odyssey-online.ts'),'utf8');
const begin = content.indexOf('const safeFlow = ');
const after = content.indexOf('\nif (!id || !r',begin);
assert(begin > 0 && after > begin, 'Route code must expose bounded workflow checks');
const program = content.slice(begin,after);
const sandbox = vm.createContext({});
const {safeFlow, flowMatchesStages} = vm.runInContext(program + '\n({safeFlow,flowMatchesStages})',sandbox,{timeout:500});
assert(typeof safeFlow==='function' && typeof flowMatchesStages==='function');
const sanitizerBegin=content.indexOf('function safeUsage(');
const sanitizerEnd=content.indexOf('\n`;\n',sanitizerBegin);
assert(sanitizerBegin>0 && sanitizerEnd>sanitizerBegin,
  'Actual n8n helpers must be present');
const helpers=vm.runInNewContext(content.slice(sanitizerBegin,sanitizerEnd)
  +'\n({safeOperational,safeDetailStage})',{}, {timeout:500});
const data = JSON.parse(readFileSync(0,'utf8'));
const flow = data.execution_flow;
const stages = data.operational?.stages;
assert(Array.isArray(stages) && stages.length>=1, 'No observed operational stages');
const sanitized=helpers.safeOperational(data.operational);
assert(Array.isArray(sanitized.stages) && sanitized.stages.length===stages.length,
  'Actual n8n sanitizer suppressed stages unexpectedly');
assert.equal(sanitized.stages.filter(st=>st.route_index===0).length,
  stages.filter(st=>st.route_index===0).length);
assert.equal(sanitized.stages.filter(st=>st.route_index===1).length,
  stages.filter(st=>st.route_index===1).length);
assert(sanitized.stages.some(st=>st.route_index===0)
  && sanitized.stages.some(st=>st.route_index===1));
const spoofedStage={...stages.find(s=>s.route_index===0),route_index:99};
assert.equal(helpers.safeDetailStage(spoofedStage),undefined,
  'Unbounded fake route ownership passed n8n sanitizer');
assert.equal(safeFlow(flow)===undefined, false, 'Real n8n safeFlow rejected dependent execution');
assert.equal(flowMatchesStages(flow,stages),true,'Actual n8n graph cannot correlate stages');
assert.deepEqual(Array.from(flow.routes, r=>r.capability),['core','tasks']);
assert.equal(flow.routes[0].depends_on,null);
assert.equal(flow.routes[1].depends_on,0);
assert(stages.some(s=>s.name==='application.router'), 'The observed router boundary is absent');
assert(stages.some(s=>s.route_index===0) && stages.some(s=>s.route_index===1));
const fakeOwner = JSON.parse(JSON.stringify(stages));
const firstOwned = fakeOwner.find(s => s.route_index === 0);
assert(firstOwned, 'Core-owned stage was lost in the public result');
firstOwned.route_index = 1;
assert.equal(flowMatchesStages(flow,fakeOwner),false,
  'A stage falsely attributed to Tasks was accepted as Core');
// Verify the real HTTP diagnostics sanitizer has a bounded route owner path.
assert(content.includes('const owner = value.route_index;'),
  'n8n sanitization silently drops Core/Tasks stage ownership');
const mutated = JSON.parse(JSON.stringify(flow));
mutated.routes[1].stage_count+=1;
assert.equal(safeFlow(mutated)===undefined || flowMatchesStages(mutated,stages)===false,true,
  'Mutated stage ownership was accepted');
const forged = JSON.parse(JSON.stringify(flow));
forged.routes[1].steps[0].name='fictional.model.success';
assert.equal(flowMatchesStages(forged,stages),false,'Forged stage accepted');
const fakeDependency = JSON.parse(JSON.stringify(flow));
fakeDependency.routes[0].depends_on=1;
assert.equal(safeFlow(fakeDependency),undefined,
  'Cyclic/backwards dependency was accepted by real n8n safeFlow');
const injected = JSON.parse(JSON.stringify(flow));
injected.routes[1].steps[0].extra='another permission';
assert.equal(safeFlow(injected),undefined,'Malformed graph injected extra fields');
console.log(JSON.stringify({checked:true,route_count:flow.routes.length,stages:stages.length,
  dependency:'core->tasks',n8n_flow_accepted:true,adversarial_rejected:5}));
