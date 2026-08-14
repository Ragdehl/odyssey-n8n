const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workflowSource = fs.readFileSync(path.join(__dirname, '..', 'workflows', 'storage-read.ts'), 'utf8');

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

const normalizeCode = loadCode('NORMALIZE_PATH_CODE');
const parseCode = loadCode('PARSE_NOTE_CODE');
const readErrorCode = loadCode('SHAPE_READ_ERROR_CODE');

test('normalizes harmless POSIX segments and rejects unsafe or active pattern targets', () => {
  assert.equal(runCode(normalizeCode, { path: 'people/./archive/../carlos.md' }).json.path, 'people/carlos.md');
  assert.equal(runCode(normalizeCode, { path: 'people/Carlos (work).md' }).json.path, 'people/Carlos (work).md');
  assert.equal(runCode(normalizeCode, { path: 'people/[Draft] Carlos.md' }).json.path, 'people/[Draft] Carlos.md');
  for (const candidate of [undefined, '', '/odyssey/vault/a.md', '/data/odyssey/a.md', '../a.md', 'a/../../b.md', 'a.txt', 'a\\b.md', 'people/*.md', 'people/carl?s.md', 'people/{carlos,carla}.md', 'people/(carlos|carla).md', 'people/@(carlos|carla).md']) {
    assert.equal(runCode(normalizeCode, { path: candidate }).json.result.error.code, 'INVALID_PATH');
  }
});

test('parses the supported scalar and flat-array frontmatter subset', () => {
  const markdown = '---\nid: abc\ntype: definitely_unregistered\nactive: true\nrevision: 2\nrating: 4.5\noptional: null\naliases: [Carlos, "C. Example"]\n---\n\n# Carlos\n\nText';
  const result = runCode(parseCode, { markdown }, { 'Normalize Note Path': { path: 'people/carlos.md' } }).json;
  assert.deepEqual(JSON.parse(JSON.stringify(result)), {
    ok: true,
    path: 'people/carlos.md',
    metadata: { id: 'abc', type: 'definitely_unregistered', active: true, revision: 2, rating: 4.5, optional: null, aliases: ['Carlos', 'C. Example'] },
    content: '# Carlos\n\nText',
  });
});

test('parses block arrays and preserves Markdown body text', () => {
  const markdown = "---\nid: abc\naliases:\n  - Carlos\n  - 'C. Example'\n---\n\n# Carlos\n\nLine 1\n\nLine 2\n";
  const result = runCode(parseCode, { markdown }, { 'Normalize Note Path': { path: 'people/carlos.md' } }).json;
  assert.deepEqual(Array.from(result.metadata.aliases), ['Carlos', 'C. Example']);
  assert.equal(result.content, '# Carlos\n\nLine 1\n\nLine 2\n');
});

test('rejects plain Markdown without frontmatter and unsupported structures', () => {
  const plain = runCode(parseCode, { markdown: '# Plain\n' }, { 'Normalize Note Path': { path: 'plain.md' } }).json;
  assert.deepEqual(JSON.parse(JSON.stringify(plain)), {
    ok: false,
    error: { code: 'INVALID_NOTE_FORMAT', message: 'Invalid note format' },
  });
  const malformed = runCode(parseCode, { markdown: '---\nid: abc\nnested:\n  child: value\n---\nBody' }, { 'Normalize Note Path': { path: 'bad.md' } }).json;
  assert.equal(malformed.error.code, 'INVALID_NOTE_FORMAT');
});

test('maps every native no-accessible-file outcome to NOT_FOUND', () => {
  for (const scenario of ['missing Markdown file', 'Markdown path is a directory', 'denied symlink target']) {
    const result = runCode(readErrorCode, { error: 'No file(s) found', scenario }).json;
    assert.equal(result.error.code, 'NOT_FOUND');
    assert.equal(result.error.message, 'Note not found');
  }
  assert.equal(runCode(readErrorCode, { error: 'Access to the file is not allowed.' }).json.error.code, 'NOT_FOUND');
  assert.equal(runCode(readErrorCode, { error: 'EISDIR: illegal operation on a directory' }).json.error.code, 'NOT_FOUND');
});

test('maps unexpected native failures to READ_ERROR', () => {
  assert.equal(runCode(readErrorCode, { error: 'Invalid path after validated input' }).json.error.code, 'READ_ERROR');
  assert.equal(runCode(readErrorCode, { error: 'Unexpected I/O timeout' }).json.error.code, 'READ_ERROR');
});
