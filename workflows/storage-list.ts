import { node, trigger, workflow } from '@n8n/workflow-sdk';

const SHAPE_LIST_CODE = "\n/**\n * Converts native file-node output into the minimal storage_list result.\n * @param {Array<{binary?: {data?: {directory?: string, fileName?: string}}}>} items Native n8n items for matched Markdown files.\n * @returns {{json: {ok: true, paths: string[]} | {ok: false, error: {code: 'LIST_ERROR', message: string}}}} Sorted relative paths or a sanitized failure.\n */\nfunction shapeList(items) {\n  try {\n    const vaultRoot = '/odyssey/vault';\n    const paths = items.map((item) => {\n      const directory = item.binary?.data?.directory;\n      const fileName = item.binary?.data?.fileName;\n      if (typeof directory !== 'string' || typeof fileName !== 'string') throw new Error('Missing native file identity');\n      const absolutePath = directory.replace(/\\\\/g, '/') + '/' + fileName;\n      if (!absolutePath.startsWith(vaultRoot + '/') || !absolutePath.endsWith('.md')) throw new Error('Invalid native file identity');\n      const relativePath = absolutePath.slice(vaultRoot.length + 1);\n      if (!relativePath || relativePath.split('/').includes('..')) throw new Error('Invalid native file identity');\n      return relativePath;\n    });\n    paths.sort();\n    return { json: { ok: true, paths } };\n  } catch {\n    return { json: { ok: false, error: { code: 'LIST_ERROR', message: 'Unable to list notes' } } };\n  }\n}\n\nreturn shapeList($input.all());\n";

const SHAPE_LIST_ERROR_CODE = "\n/**\n * Maps native listing failures to the stable storage_list public contract.\n * @param {unknown} errorValue Native n8n error payload.\n * @returns {{json: {ok: true, paths: []} | {ok: false, error: {code: 'LIST_ERROR', message: string}}}} Empty-list success or sanitized listing failure.\n */\nfunction shapeListError(errorValue) {\n  const message = String(errorValue?.message ?? errorValue ?? '');\n  if (/no file\\(s\\) found/i.test(message)) return { json: { ok: true, paths: [] } };\n  return { json: { ok: false, error: { code: 'LIST_ERROR', message: 'Unable to list notes' } } };\n}\n\nreturn shapeListError($json.error ?? $json);\n";

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.2,
  config: {
    name: 'storage_list Input',
    parameters: { inputSource: 'passthrough' },
    position: [0, 0],
  },
  output: [{}],
});

const readMarkdownFiles = node({
  type: 'n8n-nodes-base.readWriteFile',
  version: 1.1,
  config: {
    name: 'Enumerate Vault Markdown',
    parameters: {
      operation: 'read',
      fileSelector: '/odyssey/vault/**/*.md',
      options: { dataPropertyName: 'data', fileExtension: 'md', mimeType: 'text/markdown' },
    },
    onError: 'continueErrorOutput',
    position: [280, 0],
  },
  output: [{ binary: { data: { directory: '/odyssey/vault/people', fileName: 'carlos.md' } } }],
});

const shapeList = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return Relative Paths',
    parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: SHAPE_LIST_CODE },
    position: [560, -100],
  },
  output: [{ ok: true, paths: ['people/carlos.md'] }],
});

const shapeListError = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shape List Error',
    parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: SHAPE_LIST_ERROR_CODE },
    position: [560, 100],
  },
  output: [{ ok: true, paths: [] }],
});

export default workflow('storage-list', 'Odyssey — storage_list')
  .add(input)
  .to(readMarkdownFiles.to(shapeList))
  .add(readMarkdownFiles.onError(shapeListError));
