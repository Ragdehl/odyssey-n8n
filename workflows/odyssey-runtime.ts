import { expr, node, trigger, workflow } from '@n8n/workflow-sdk';

/** Development/test workflow: delegate one request to the host-side Odyssey runtime. */
const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.2,
  config: {
    name: 'odyssey_runtime Input',
    parameters: {
      inputSource: 'workflowInputs',
      workflowInputs: { values: [{ name: 'request', type: 'string' }] },
    },
    position: [0, 0],
  },
  output: [{ request: 'A disposable runtime smoke request' }],
});

const execute = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Execute Odyssey Request',
    parameters: {
      method: 'POST',
      url: expr("{{ $env.ODYSSEY_RUNTIME_URL || 'http://172.18.0.1:8765/execute' }}"),
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr("={{ JSON.stringify({ request: $json.request }) }}"),
      options: { timeout: 120000 },
    },
    position: [420, 0],
  },
  output: [{ request_id: 'disposable-smoke', status: 'completed', actions: [] }],
});

export default workflow('odyssey-runtime', 'Odyssey — runtime bridge (development)')
  .add(input)
  .to(execute);
