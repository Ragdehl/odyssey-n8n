import { expr, ifElse, node, trigger, workflow } from '@n8n/workflow-sdk';

const NORMALIZE_PATH_CODE = "\n/**\n * Normalizes one caller-supplied note path within the Odyssey vault contract.\n * @param {unknown} candidate Vault-relative path supplied by the workflow caller.\n * @returns {{valid: true, path: string, filePath: string} | {valid: false, result: object}} A safe native-read target or a public INVALID_PATH result.\n */\nfunction normalizeNotePath(candidate) {\n  const invalid = () => ({\n    valid: false,\n    result: { ok: false, error: { code: 'INVALID_PATH', message: 'Invalid note path' } },\n  });\n\n  if (typeof candidate !== 'string' || candidate.trim() === '') return invalid();\n  if (candidate !== candidate.trim() || candidate.includes('\\\\') || candidate.includes('\\0')) return invalid();\n  if (candidate.startsWith('/') || /^[A-Za-z]:/.test(candidate)) return invalid();\n\n  const segments = [];\n  for (const segment of candidate.split('/')) {\n    if (segment === '' || segment === '.') continue;\n    if (segment === '..') {\n      if (segments.length === 0) return invalid();\n      segments.pop();\n      continue;\n    }\n    segments.push(segment);\n  }\n\n  const path = segments.join('/');\n  if (!path || !path.endsWith('.md')) return invalid();\n  return { valid: true, path, filePath: '/odyssey/vault/' + path };\n}\n\nreturn { json: normalizeNotePath($json.path) };\n";

const PARSE_NOTE_CODE = "\n/**\n * Produces a stable public error without leaking runtime or filesystem details.\n * @param {'INVALID_NOTE_FORMAT'} code Public storage_read error code.\n * @param {string} message Stable caller-facing description.\n * @returns {{json: object}} An n8n item containing the public error result.\n */\nfunction publicError(code, message) {\n  return { json: { ok: false, error: { code, message } } };\n}\n\n/**\n * Splits a comma-separated inline scalar array while respecting supported quotes.\n * @param {string} source Text between the inline array brackets.\n * @returns {string[]} Serialized scalar tokens.\n * @throws {Error} When quoting is malformed or nested structures are present.\n */\nfunction splitInlineArray(source) {\n  const tokens = [];\n  let token = '';\n  let quote = null;\n  for (let index = 0; index < source.length; index += 1) {\n    const char = source[index];\n    if (quote) {\n      token += char;\n      if (char === quote) {\n        if (quote === \"'\" && source[index + 1] === \"'\") token += source[++index];\n        else if (source[index - 1] !== '\\\\') quote = null;\n      }\n    } else if (char === \"'\" || char === '\"') {\n      quote = char;\n      token += char;\n    } else if (char === ',') {\n      tokens.push(token.trim());\n      token = '';\n    } else {\n      if (char === '[' || char === ']' || char === '{' || char === '}') throw new Error('Nested YAML is unsupported');\n      token += char;\n    }\n  }\n  if (quote) throw new Error('Unclosed quote');\n  if (token.trim() !== '' || source.trim() !== '') tokens.push(token.trim());\n  if (tokens.some((value) => value === '')) throw new Error('Empty array item');\n  return tokens;\n}\n\n/**\n * Parses one scalar from the supported deterministic frontmatter subset.\n * @param {string} source Serialized scalar value.\n * @returns {string | number | boolean | null | Array<unknown>} Parsed metadata value.\n * @throws {Error} When the value uses unsupported or malformed YAML syntax.\n */\nfunction parseScalar(source) {\n  const value = source.trim();\n  if (value === '') throw new Error('Missing scalar');\n  if (value.startsWith('[')) {\n    if (!value.endsWith(']')) throw new Error('Unclosed inline array');\n    return splitInlineArray(value.slice(1, -1)).map(parseScalar);\n  }\n  if (/^[!&*|>]/.test(value) || /^[{[]/.test(value)) throw new Error('Unsupported YAML structure');\n  if (value.startsWith('\"')) {\n    if (!value.endsWith('\"')) throw new Error('Unclosed quote');\n    try { return JSON.parse(value); } catch { throw new Error('Invalid quoted string'); }\n  }\n  if (value.startsWith(\"'\")) {\n    if (!value.endsWith(\"'\")) throw new Error('Unclosed quote');\n    return value.slice(1, -1).replace(/''/g, \"'\");\n  }\n  if (value.includes(' #')) throw new Error('Inline comments are unsupported');\n  if (/^(true|false)$/i.test(value)) return value.toLowerCase() === 'true';\n  if (/^(null|~)$/i.test(value)) return null;\n  if (/^[+-]?(?:0|[1-9]\\d*)(?:\\.\\d+)?(?:[eE][+-]?\\d+)?$/.test(value)) return Number(value);\n  return value;\n}\n\n/**\n * Parses flat Odyssey frontmatter with scalar values and flat scalar arrays.\n * @param {string} source Frontmatter text without delimiter lines.\n * @returns {Record<string, unknown>} Parsed metadata object.\n * @throws {Error} When syntax is malformed, duplicated, nested, or outside the supported subset.\n */\nfunction parseFrontmatter(source) {\n  const metadata = {};\n  const lines = source.split(/\\r?\\n/);\n  for (let index = 0; index < lines.length; index += 1) {\n    const line = lines[index];\n    if (line.trim() === '' || line.trimStart().startsWith('#')) continue;\n    if (/^\\s/.test(line)) throw new Error('Unexpected indentation');\n    const match = /^([A-Za-z_][A-Za-z0-9_-]*):(?:\\s*(.*))$/.exec(line);\n    if (!match) throw new Error('Invalid property');\n    const [, key, serialized] = match;\n    if (Object.prototype.hasOwnProperty.call(metadata, key)) throw new Error('Duplicate property');\n    if (serialized !== '') {\n      metadata[key] = parseScalar(serialized);\n      continue;\n    }\n\n    const values = [];\n    while (index + 1 < lines.length && /^\\s+-\\s+/.test(lines[index + 1])) {\n      const arrayLine = lines[++index];\n      if (!/^  +-\\s+\\S/.test(arrayLine)) throw new Error('Invalid array indentation');\n      values.push(parseScalar(arrayLine.replace(/^\\s+-\\s+/, '')));\n    }\n    if (values.length === 0) throw new Error('Nested or empty mapping is unsupported');\n    metadata[key] = values;\n  }\n  return metadata;\n}\n\n/**\n * Separates supported frontmatter serialization from the Markdown body.\n * @param {string} markdown UTF-8 note text returned by the native extraction node.\n * @returns {{metadata: Record<string, unknown>, content: string}} Parsed note serialization.\n * @throws {Error} When delimiters, encoding, or supported frontmatter syntax are invalid.\n */\nfunction parseNote(markdown) {\n  if (typeof markdown !== 'string' || markdown.includes('\\uFFFD')) throw new Error('Invalid UTF-8 note');\n  if (!markdown.startsWith('---\\n') && !markdown.startsWith('---\\r\\n')) throw new Error('Missing frontmatter');\n  const delimiter = /\\r?\\n---(?:\\r?\\n|$)/g;\n  delimiter.lastIndex = markdown.indexOf('\\n') + 1;\n  const closing = delimiter.exec(markdown);\n  if (!closing) throw new Error('Unclosed frontmatter');\n  const metadataSource = markdown.slice(markdown.indexOf('\\n') + 1, closing.index);\n  let content = markdown.slice(closing.index + closing[0].length);\n  if (content.startsWith('\\r\\n')) content = content.slice(2);\n  else if (content.startsWith('\\n')) content = content.slice(1);\n  return { metadata: parseFrontmatter(metadataSource), content };\n}\n\ntry {\n  const parsed = parseNote($json.markdown);\n  return { json: { ok: true, path: $('Normalize Note Path').item.json.path, metadata: parsed.metadata, content: parsed.content } };\n} catch {\n  return publicError('INVALID_NOTE_FORMAT', 'Invalid note format');\n}\n";

const SHAPE_READ_ERROR_CODE = "\n/**\n * Maps a native read failure to Odyssey's stable public storage_read vocabulary.\n * @param {unknown} errorValue Native n8n error payload.\n * @returns {{json: object}} An n8n item containing a sanitized public error.\n */\nfunction shapeReadError(errorValue) {\n  const message = String(errorValue?.message ?? errorValue ?? '');\n  if (/no file|not found|enoent|directory|eisdir|access to the file is not allowed/i.test(message)) {\n    return { json: { ok: false, error: { code: 'NOT_FOUND', message: 'Note not found' } } };\n  }\n  return { json: { ok: false, error: { code: 'READ_ERROR', message: 'Unable to read note' } } };\n}\n\nreturn shapeReadError($json.error ?? $json);\n";

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.2,
  config: {
    name: 'storage_read Input',
    parameters: {
      inputSource: 'workflowInputs',
      workflowInputs: { values: [{ name: 'path', type: 'string' }] },
    },
    position: [0, 0],
  },
  output: [{ path: 'people/carlos.md' }],
});

const normalizePath = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Normalize Note Path',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: NORMALIZE_PATH_CODE },
    position: [260, 0],
  },
  output: [{ valid: true, path: 'people/carlos.md', filePath: '/odyssey/vault/people/carlos.md' }],
});

const validPath = ifElse({
  version: 2.3,
  config: {
    name: 'Valid Note Path?',
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

const readFile = node({
  type: 'n8n-nodes-base.readWriteFile',
  version: 1.1,
  config: {
    name: 'Read Note from Vault',
    parameters: {
      operation: 'read',
      fileSelector: expr('{{ $json.filePath }}'),
      options: { dataPropertyName: 'data', fileExtension: 'md', mimeType: 'text/markdown' },
    },
    onError: 'continueErrorOutput',
    position: [780, -100],
  },
  output: [{ binary: { data: { fileName: 'carlos.md', mimeType: 'text/markdown' } } }],
});

const extractText = node({
  type: 'n8n-nodes-base.extractFromFile',
  version: 1.1,
  config: {
    name: 'Decode UTF-8 Markdown',
    parameters: { operation: 'text', destinationKey: 'markdown' },
    position: [1040, -160],
  },
  output: [{ markdown: '---\nid: abc\ntype: person\n---\n\n# Carlos' }],
});

const parseNote = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Parse Note Serialization',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: PARSE_NOTE_CODE },
    position: [1300, -160],
  },
  output: [{ ok: true, path: 'people/carlos.md', metadata: { id: 'abc', type: 'person' }, content: '# Carlos' }],
});

const shapeReadError = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Read Error',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: SHAPE_READ_ERROR_CODE },
    position: [1040, 40],
  },
  output: [{ ok: false, error: { code: 'NOT_FOUND', message: 'Note not found' } }],
});

const shapeInvalidPath = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape Invalid Path',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: 'return { json: $json.result };' },
    position: [780, 120],
  },
  output: [{ ok: false, error: { code: 'INVALID_PATH', message: 'Invalid note path' } }],
});

export default workflow('storage-read', 'Odyssey — storage_read')
  .add(input)
  .to(normalizePath)
  .to(validPath
    .onTrue(readFile.to(extractText).to(parseNote))
    .onFalse(shapeInvalidPath))
  .add(readFile.onError(shapeReadError));
