const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workflowSource = fs.readFileSync(path.join(__dirname, '..', 'workflows', 'storage-write.ts'), 'utf8');

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
 * Executes one per-item Code-node program with controlled n8n-like inputs.
 * @param {string} source Code-node program to execute.
 * @param {object} json Input item JSON.
 * @param {Record<string, object>} nodeItems Named upstream node JSON used by n8n expressions.
 * @returns {object} Code-node output item.
 */
function runCode(source, json, nodeItems = {}) {
  const context = {
    $json: json,
    $: (name) => ({ item: { json: nodeItems[name] } }),
  };
  return vm.runInNewContext('(function () {\n' + source + '\n})()', context);
}

const prepareCode = loadCode('PREPARE_NOTE_CODE');
const preflightCode = loadCode('CLASSIFY_PREFLIGHT_ERROR_CODE');

test('normalizes literal vault-relative Markdown paths and rejects unsafe targets', () => {
  const input = { metadata: { id: 'abc' }, content: '# Note' };
  assert.equal(runCode(prepareCode, { ...input, path: 'people/./archive/../carlos.md' }).json.path, 'people/carlos.md');
  assert.equal(runCode(prepareCode, { ...input, path: 'people/[Draft] Carlos.md' }).json.path, 'people/[Draft] Carlos.md');
  for (const candidate of [undefined, '', '/odyssey/vault/a.md', '/data/odyssey/a.md', '../a.md', 'a/../../b.md', 'a.txt', 'a\\b.md', 'people/*.md', 'people/carl?s.md', 'people/{a,b}.md', 'people/(a|b).md']) {
    assert.equal(runCode(prepareCode, { ...input, path: candidate }).json.result.error.code, 'INVALID_PATH');
  }
});

test('serializes metadata deterministically and preserves Markdown content', () => {
  const result = runCode(prepareCode, {
    path: 'people/carlos.md',
    metadata: { type: 'person', aliases: ['Carlos', 'C. Example'], active: true, optional: null, rating: 4.5, revision: 2, id: 'abc: 123' },
    content: '# Carlos\n\nText\n',
  }).json;
  assert.equal(result.markdown, '---\nactive: true\naliases: ["Carlos", "C. Example"]\nid: "abc: 123"\noptional: null\nrating: 4.5\nrevision: 2\ntype: "person"\n---\n\n# Carlos\n\nText\n');
});

test('rejects malformed structured input and unsupported metadata values', () => {
  const valid = { path: 'note.md', metadata: { id: 'abc' }, content: '# Note' };
  for (const input of [
    { ...valid, metadata: null },
    { ...valid, metadata: {} },
    { ...valid, metadata: { 'bad key': 'value' } },
    { ...valid, metadata: { nested: { child: 'value' } } },
    { ...valid, metadata: { empty: [] } },
    { ...valid, metadata: { nestedArray: [['value']] } },
    { ...valid, content: 42 },
  ]) {
    assert.equal(runCode(prepareCode, input).json.result.error.code, 'INVALID_INPUT');
  }
});

test('allows only definite absence to proceed after the native preflight', () => {
  const prepared = { valid: true, path: 'note.md', filePath: '/odyssey/vault/note.md', markdown: '---\nid: "abc"\n---\n\n# Note' };
  for (const error of ['No file(s) found', 'ENOENT: missing target', 'File not found']) {
    const result = runCode(preflightCode, { error }, { 'Prepare Note': prepared }).json;
    assert.equal(result.canWrite, true);
    assert.equal(result.markdown, prepared.markdown);
  }
});

test('sanitizes ambiguous or restricted preflight failures as WRITE_ERROR', () => {
  for (const error of ['Access to the file is not allowed', 'EISDIR: target is a directory', 'Unexpected I/O timeout']) {
    const result = runCode(preflightCode, { error }, { 'Prepare Note': {} }).json;
    assert.deepEqual(JSON.parse(JSON.stringify(result)), {
      canWrite: false,
      result: { ok: false, error: { code: 'WRITE_ERROR', message: 'Unable to write note' } },
    });
  }
});
