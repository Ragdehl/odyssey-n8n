import { expr, ifElse, node, trigger, workflow } from '@n8n/workflow-sdk';

const PREPARE_NOTE_CODE = "\n/**\n * Produces one stable public storage_write error.\n * @param {'INVALID_PATH' | 'INVALID_INPUT'} code Public error code.\n * @param {string} message Stable caller-facing message.\n * @returns {{valid: false, result: object}} Invalid preparation result.\n */\nfunction invalidResult(code, message) {\n  return { valid: false, result: { ok: false, error: { code, message } } };\n}\n\n/**\n * Normalizes one caller-supplied note path within the Odyssey vault contract.\n * @param {unknown} candidate Vault-relative path supplied by the workflow caller.\n * @returns {{valid: true, path: string, filePath: string} | {valid: false, result: object}} Safe native-write target or public INVALID_PATH result.\n */\nfunction normalizeNotePath(candidate) {\n  if (typeof candidate !== 'string' || candidate.trim() === '') return invalidResult('INVALID_PATH', 'Invalid note path');\n  if (candidate !== candidate.trim() || candidate.includes('\\\\') || candidate.includes('\\0')) return invalidResult('INVALID_PATH', 'Invalid note path');\n  if (/[?*{}|]/.test(candidate)) return invalidResult('INVALID_PATH', 'Invalid note path');\n  if (candidate.startsWith('/') || /^[A-Za-z]:/.test(candidate)) return invalidResult('INVALID_PATH', 'Invalid note path');\n\n  const segments = [];\n  for (const segment of candidate.split('/')) {\n    if (segment === '' || segment === '.') continue;\n    if (segment === '..') {\n      if (segments.length === 0) return invalidResult('INVALID_PATH', 'Invalid note path');\n      segments.pop();\n      continue;\n    }\n    segments.push(segment);\n  }\n\n  const path = segments.join('/');\n  if (!path || !path.endsWith('.md')) return invalidResult('INVALID_PATH', 'Invalid note path');\n  return { valid: true, path, filePath: '/odyssey/vault/' + path };\n}\n\n/**\n * Serializes one supported flat metadata scalar without YAML type ambiguity.\n * @param {unknown} value Structured metadata value.\n * @returns {string} Deterministic YAML scalar representation.\n * @throws {Error} When the value is not a supported scalar.\n */\nfunction serializeScalar(value) {\n  if (typeof value === 'string') return JSON.stringify(value);\n  if (typeof value === 'boolean') return value ? 'true' : 'false';\n  if (typeof value === 'number' && Number.isFinite(value)) return String(Object.is(value, -0) ? 0 : value);\n  if (value === null) return 'null';\n  throw new Error('Unsupported metadata scalar');\n}\n\n/**\n * Serializes a flat metadata object with lexicographically ordered keys.\n * @param {unknown} metadata Structured caller metadata.\n * @returns {string} Deterministic supported Odyssey frontmatter without delimiters.\n * @throws {Error} When metadata is empty, nested, malformed, or contains unsupported values.\n */\nfunction serializeMetadata(metadata) {\n  if (metadata === null || typeof metadata !== 'object' || Array.isArray(metadata)) throw new Error('Metadata must be an object');\n  const keys = Object.keys(metadata).sort();\n  if (keys.length === 0) throw new Error('Metadata must not be empty');\n\n  return keys.map((key) => {\n    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(key)) throw new Error('Invalid metadata key');\n    const value = metadata[key];\n    if (Array.isArray(value)) {\n      if (value.length === 0) throw new Error('Metadata arrays must not be empty');\n      return key + ': [' + value.map(serializeScalar).join(', ') + ']';\n    }\n    return key + ': ' + serializeScalar(value);\n  }).join('\\n');\n}\n\n/**\n * Validates the public input and builds the exact Markdown serialization to write.\n * @param {unknown} input Workflow input object.\n * @returns {object} Prepared safe target and Markdown, or a stable public validation result.\n */\nfunction prepareNote(input) {\n  const target = normalizeNotePath(input?.path);\n  if (!target.valid) return target;\n  if (typeof input?.content !== 'string') return invalidResult('INVALID_INPUT', 'Invalid note input');\n  try {\n    const frontmatter = serializeMetadata(input.metadata);\n    return { ...target, markdown: '---\\n' + frontmatter + '\\n---\\n\\n' + input.content };\n  } catch {\n    return invalidResult('INVALID_INPUT', 'Invalid note input');\n  }\n}\n\nreturn { json: prepareNote($json) };\n";

const CLASSIFY_PREFLIGHT_ERROR_CODE = "\n/**\n * Classifies a failed native existence check without exposing filesystem details.\n * @param {unknown} errorValue Native n8n error payload.\n * @returns {{json: object}} Prepared write input for an absent target or a public WRITE_ERROR result.\n */\nfunction classifyPreflightError(errorValue) {\n  const message = String(errorValue?.message ?? errorValue ?? '');\n  if (/no file|not found|enoent/i.test(message)) {\n    return { json: { ...$('Prepare Note').item.json, canWrite: true } };\n  }\n  return { json: { canWrite: false, result: { ok: false, error: { code: 'WRITE_ERROR', message: 'Unable to write note' } } } };\n}\n\nreturn classifyPreflightError($json.error ?? $json);\n";

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.2,
  config: {
    name: 'storage_write Input',
    parameters: {
      inputSource: 'workflowInputs',
      workflowInputs: {
        values: [
          { name: 'path', type: 'string' },
          { name: 'metadata', type: 'object' },
          { name: 'content', type: 'string' },
        ],
      },
    },
    position: [0, 0],
  },
  output: [{ path: 'people/carlos.md', metadata: { id: 'abc', type: 'person' }, content: '# Carlos' }],
});

const prepareNote = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Note',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: PREPARE_NOTE_CODE },
    position: [260, 0],
  },
  output: [{ valid: true, path: 'people/carlos.md', filePath: '/odyssey/vault/people/carlos.md', markdown: '---\nid: "abc"\ntype: "person"\n---\n\n# Carlos' }],
});

const validInput = ifElse({
  version: 2.3,
  config: {
    name: 'Valid Write Input?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
        conditions: [{ leftValue: expr('{{ $json.valid }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } }],
        combinator: 'and',
      },
    },
    position: [520, 0],
  },
  output: [{ valid: true, path: 'people/carlos.md', filePath: '/odyssey/vault/people/carlos.md' }],
});

const checkTarget = node({
  type: 'n8n-nodes-base.readWriteFile',
  version: 1.1,
  config: {
    name: 'Check Target Does Not Exist',
    parameters: {
      operation: 'read',
      fileSelector: expr('{{ $json.filePath }}'),
      options: { dataPropertyName: 'data', fileExtension: 'md', mimeType: 'text/markdown' },
    },
    onError: 'continueErrorOutput',
    position: [780, -120],
  },
  output: [{ binary: { data: { fileName: 'carlos.md', mimeType: 'text/markdown' } } }],
});

const alreadyExists = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Already Exists',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: "return { json: { ok: false, error: { code: 'ALREADY_EXISTS', message: 'Note already exists' } } };" },
    position: [1040, -220],
  },
  output: [{ ok: false, error: { code: 'ALREADY_EXISTS', message: 'Note already exists' } }],
});

const classifyPreflightError = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Classify Missing Target',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: CLASSIFY_PREFLIGHT_ERROR_CODE },
    position: [1040, 0],
  },
  output: [{ valid: true, canWrite: true, path: 'people/carlos.md', filePath: '/odyssey/vault/people/carlos.md', markdown: '---\nid: "abc"\n---\n\n# Carlos' }],
});

const canWrite = ifElse({
  version: 2.3,
  config: {
    name: 'Target Absent?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
        conditions: [{ leftValue: expr('{{ $json.canWrite }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } }],
        combinator: 'and',
      },
    },
    position: [1300, 0],
  },
  output: [{ canWrite: true, path: 'people/carlos.md', markdown: '---\nid: "abc"\n---\n\n# Carlos' }],
});

const convertMarkdown = node({
  type: 'n8n-nodes-base.convertToFile',
  version: 1.1,
  config: {
    name: 'Encode UTF-8 Markdown',
    parameters: {
      operation: 'toText',
      sourceProperty: 'markdown',
      options: { encoding: 'utf8', fileName: 'note.md', mimeType: 'text/markdown' },
    },
    position: [1560, -80],
  },
  output: [{ binary: { data: { fileName: 'note.md', mimeType: 'text/markdown' } } }],
});

const writeNote = node({
  type: 'n8n-nodes-base.readWriteFile',
  version: 1.1,
  config: {
    name: 'Write Note to Vault',
    parameters: {
      operation: 'write',
      fileName: expr("{{ $('Prepare Note').item.json.filePath }}"),
      dataPropertyName: 'data',
    },
    onError: 'continueErrorOutput',
    position: [1820, -80],
  },
  output: [{ fileName: '/odyssey/vault/people/carlos.md' }],
});

const shapeSuccess = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Write Success',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: "return { json: { ok: true, path: $('Prepare Note').item.json.path } };" },
    position: [2080, -140],
  },
  output: [{ ok: true, path: 'people/carlos.md' }],
});

const shapeWriteError = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Write Error',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: "return { json: { ok: false, error: { code: 'WRITE_ERROR', message: 'Unable to write note' } } };" },
    position: [2080, 20],
  },
  output: [{ ok: false, error: { code: 'WRITE_ERROR', message: 'Unable to write note' } }],
});

const shapeResult = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Public Error',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: 'return { json: $json.result };' },
    position: [1560, 120],
  },
  output: [{ ok: false, error: { code: 'INVALID_INPUT', message: 'Invalid note input' } }],
});

export default workflow('storage-write', 'Odyssey — storage_write')
  .add(input)
  .to(prepareNote)
  .to(validInput
    .onTrue(checkTarget.to(alreadyExists))
    .onFalse(shapeResult))
  .add(checkTarget.onError(classifyPreflightError.to(canWrite
    .onTrue(convertMarkdown.to(writeNote.to(shapeSuccess)))
    .onFalse(shapeResult))))
  .add(writeNote.onError(shapeWriteError));
