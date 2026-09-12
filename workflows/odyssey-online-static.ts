import { node, trigger, workflow } from '@n8n/workflow-sdk';

const deploymentEnvironment = process.env.ODYSSEY_WORKFLOW_ENVIRONMENT;
if (deploymentEnvironment !== 'DEV' && deploymentEnvironment !== 'PROD') {
  throw new Error('ODYSSEY_WORKFLOW_ENVIRONMENT must be DEV or PROD');
}
const workflowName = deploymentEnvironment === 'DEV'
  ? 'Odyssey — DEV Online static assets'
  : 'Odyssey — Online static assets';

const page = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey page', parameters: { httpMethod: 'GET', path: 'odyssey', responseMode: 'responseNode' }, position: [0, 0] }, output: [{}] });
const css = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey styles', parameters: { httpMethod: 'GET', path: 'styles.css', responseMode: 'responseNode' }, position: [0, 180] }, output: [{}] });
const app = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey app', parameters: { httpMethod: 'GET', path: 'app.js', responseMode: 'responseNode' }, position: [0, 360] }, output: [{}] });
const client = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey client', parameters: { httpMethod: 'GET', path: 'client.js', responseMode: 'responseNode' }, position: [0, 540] }, output: [{}] });
const environment = trigger({ type: 'n8n-nodes-base.webhook', version: 2.1, config: { name: 'Odyssey deployment environment', parameters: { httpMethod: 'GET', path: 'environment.js', responseMode: 'responseNode' }, position: [0, 720] }, output: [{}] });
const pageFile = node({ type: 'n8n-nodes-base.readWriteFile', version: 1.1, config: { name: 'Read Odyssey page', parameters: { operation: 'read', fileSelector: '/odyssey-web/index.html', options: { mimeType: 'text/html; charset=utf-8' } }, position: [240, 0] }, output: [{}] });
const cssFile = node({ type: 'n8n-nodes-base.readWriteFile', version: 1.1, config: { name: 'Read Odyssey styles', parameters: { operation: 'read', fileSelector: '/odyssey-web/styles.css', options: { mimeType: 'text/css; charset=utf-8' } }, position: [240, 180] }, output: [{}] });
const appFile = node({ type: 'n8n-nodes-base.readWriteFile', version: 1.1, config: { name: 'Read Odyssey app', parameters: { operation: 'read', fileSelector: '/odyssey-web/app.js', options: { mimeType: 'text/javascript; charset=utf-8' } }, position: [240, 360] }, output: [{}] });
const clientFile = node({ type: 'n8n-nodes-base.readWriteFile', version: 1.1, config: { name: 'Read Odyssey client', parameters: { operation: 'read', fileSelector: '/odyssey-web/client.js', options: { mimeType: 'text/javascript; charset=utf-8' } }, position: [240, 540] }, output: [{}] });
const environmentFile = node({ type: 'n8n-nodes-base.readWriteFile', version: 1.1, config: { name: 'Read Odyssey deployment environment', parameters: { operation: 'read', fileSelector: '/odyssey-web/environment.js', options: { mimeType: 'text/javascript; charset=utf-8' } }, position: [240, 720] }, output: [{}] });
const response = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'Serve Odyssey asset', parameters: { respondWith: 'binary', responseDataSource: 'set', inputFieldName: 'data' }, position: [520, 260] }, output: [{}] });

export default workflow('odyssey-online-static', workflowName).add(page).to(pageFile).to(response).add(css).to(cssFile).to(response).add(app).to(appFile).to(response).add(client).to(clientFile).to(response).add(environment).to(environmentFile).to(response);
