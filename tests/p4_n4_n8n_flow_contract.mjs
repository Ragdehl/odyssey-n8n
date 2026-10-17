/* Validate the real n8n workflow and browser for Python's N:M Session result.
 * Invoked with JSON result from a temporary vault: no n8n deployment.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {validateExecutionFlow, ProductRequestError} from '../odyssey_web/client.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const code = readFileSync(path.join(root, 'workflows/odyssey-online.ts'), 'utf8');
const begin = code.indexOf('const safeFlow = ');
const end = code.indexOf('\nif (!id || !r', begin);
assert(begin > 0 && end > begin);
const {safeFlow, flowMatchesStages} = vm.runInNewContext(
  code.slice(begin, end) + '\n({safeFlow,flowMatchesStages})', {}, {timeout: 500});
const result = JSON.parse(readFileSync(0, 'utf8'));
const flow = result.execution_flow;
const stages = result.operational?.stages;
assert.equal(result.status, 'completed');
assert.deepEqual(Array.from(flow.routes, r => r.capability), ['core', 'core', 'tasks', 'tasks']);
assert.equal(flow.routes[0].depends_on, undefined);
assert.equal(flow.routes[1].depends_on, undefined);
assert.deepEqual(Array.from(flow.routes[3].dependency_indices), [0, 2]);
assert.equal(flow.routes[3].depends_on, 2);
assert.notEqual(safeFlow(flow), undefined, 'Real n8n dropped multi-parent flow');
assert.equal(flowMatchesStages(flow, stages), true);
const validated = validateExecutionFlow(flow, stages);
assert.deepEqual(validated.routes[3].dependency_indices, [0, 2]);
const original = structuredClone(flow);
for (const indices of [[0, 0, 2], [0, 4], [-1, 2], [0, 1], [true, 2]]) {
  const altered = structuredClone(original);
  altered.routes[3].dependency_indices = indices;
  assert.equal(safeFlow(altered), undefined, 'Unsafe multi-parent references passed n8n');
  assert.throws(() => validateExecutionFlow(altered, stages), ProductRequestError);
}
const external = structuredClone(original);
external.routes[3].depends_on = 3;
assert.equal(safeFlow(external), undefined);
assert.throws(() => validateExecutionFlow(external, stages), ProductRequestError);
console.log(JSON.stringify({passed: true, routes: 4, verified_dependencies: 2}));
