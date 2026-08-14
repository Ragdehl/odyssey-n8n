const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workflowSource = fs.readFileSync(path.join(__dirname, '..', 'workflows', 'storage-list.ts'), 'utf8');

/**
 * Loads one embedded Code-node program from the version-controlled workflow.
 * @param {string} constantName Workflow constant containing a serialized JavaScript program.
 * @returns {string} Code-node source text.
 * @throws {Error} When the requested program is absent or malformed.
 */
function loadCode(constantName) {
  const match = new RegExp('const ' + constantName + ' = ("(?:\\\\.|[^"\\\\])*");').exec(workflowSource);
  if (!match) throw new Error('Missing workflow code: ' + constantName);
  return JSON.parse(match[1]);
}

/**
 * Executes one all-items Code-node program with controlled n8n-like inputs.
 * @param {string} source Code-node program to execute.
 * @param {Array<object>} items Input items.
 * @returns {object} Code-node output item.
 */
function runAllItemsCode(source, items) {
  return vm.runInNewContext('(function () {\n' + source + '\n})()', { $input: { all: () => items } });
}

/**
 * Executes one per-item Code-node program with controlled n8n-like input.
 * @param {string} source Code-node program to execute.
 * @param {object} json Input item JSON.
 * @returns {object} Code-node output item.
 */
function runItemCode(source, json) {
  return vm.runInNewContext('(function () {\n' + source + '\n})()', { $json: json });
}

/**
 * Builds the binary identity emitted by n8n's native file-read node.
 * @param {string} directory Absolute POSIX directory.
 * @param {string} fileName File basename.
 * @returns {object} Minimal native item shape.
 */
function fileItem(directory, fileName) {
  return { binary: { data: { directory, fileName, data: 'content-must-not-escape' } } };
}

const shapeListCode = loadCode('SHAPE_LIST_CODE');
const shapeListErrorCode = loadCode('SHAPE_LIST_ERROR_CODE');

test('returns root and nested Markdown paths in deterministic lexical order', () => {
  const result = runAllItemsCode(shapeListCode, [
    fileItem('/odyssey/vault/zeta', 'last.md'),
    fileItem('/odyssey/vault', 'root.md'),
    fileItem('/odyssey/vault/alpha/deep', 'first.md'),
  ]).json;
  assert.deepEqual(Array.from(result.paths), ['alpha/deep/first.md', 'root.md', 'zeta/last.md']);
});

test('returns relative paths only and does not expose native metadata or content', () => {
  const result = runAllItemsCode(shapeListCode, [fileItem('/odyssey/vault/people', 'carlos.md')]).json;
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { ok: true, paths: ['people/carlos.md'] });
  assert.equal(JSON.stringify(result).includes('/odyssey/vault'), false);
  assert.equal(JSON.stringify(result).includes('content-must-not-escape'), false);
});

test('fails closed for missing, outside-vault, and traversal-like native identities', () => {
  for (const item of [
    {},
    fileItem('/odyssey/config', 'schema.md'),
    fileItem('/odyssey/vault/../config', 'schema.md'),
    fileItem('/odyssey/vault', 'not-markdown.txt'),
  ]) {
    const result = runAllItemsCode(shapeListCode, [item]).json;
    assert.deepEqual(JSON.parse(JSON.stringify(result)), {
      ok: false,
      error: { code: 'LIST_ERROR', message: 'Unable to list notes' },
    });
  }
});

test('maps an empty native glob result to an empty successful list', () => {
  const result = runItemCode(shapeListErrorCode, { error: 'No file(s) found' }).json;
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { ok: true, paths: [] });
});

test('sanitizes unexpected native failures as LIST_ERROR', () => {
  for (const error of ['Access to the file is not allowed.', 'EACCES: permission denied', 'Unexpected I/O timeout']) {
    const result = runItemCode(shapeListErrorCode, { error }).json;
    assert.deepEqual(JSON.parse(JSON.stringify(result)), {
      ok: false,
      error: { code: 'LIST_ERROR', message: 'Unable to list notes' },
    });
  }
});

test('uses a fixed recursive Markdown selector with no caller-supplied pattern', () => {
  assert.match(workflowSource, /fileSelector: '\/odyssey\/vault\/\*\*\/\*\.md'/);
  assert.match(workflowSource, /inputSource: 'passthrough'/);
  assert.doesNotMatch(workflowSource, /workflowInputs:\s*\{/);
});
