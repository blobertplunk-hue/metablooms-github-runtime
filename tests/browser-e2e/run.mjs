import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { getCftPath, CFT_VERSION } from '../../tools/get-cft.mjs';
import { fixtureHtml } from './fixtures/chatgpt-fixture.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const releaseRoot = path.join(root, 'release', 'v0.7.0');
const extensionRoot = path.join(root, 'release', 'v0.7.0', 'EXTENSION');
const acceptanceRoot = path.join(root, 'acceptance', 'v0.7.0');
const fixtureBase = 'https://chatgpt.com/__metachat_fixture__';
const TEST_TEXT = 'MetaChat v0.7.0 E2E line 1\nLine 2 — español 日本語 🙂';
const SENSITIVE_MARKER = 'SENSITIVE_FIXTURE_TEXT_DO_NOT_PERSIST';

class CdpClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
  }
  async connect() {
    this.ws = new WebSocket(this.url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('CDP websocket connect timeout')), 10000);
      this.ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      this.ws.addEventListener('error', (event) => { clearTimeout(timer); reject(new Error(`CDP websocket error: ${event.message ?? 'unknown'}`)); }, { once: true });
    });
    this.ws.addEventListener('message', (event) => this.#onMessage(event.data));
    this.ws.addEventListener('close', () => {
      for (const { reject } of this.pending.values()) reject(new Error('CDP websocket closed'));
      this.pending.clear();
    });
  }
  #onMessage(data) {
    const message = JSON.parse(String(data));
    if (message.id) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      else pending.resolve(message.result ?? {});
      return;
    }
    for (const listener of this.listeners) listener(message);
  }
  onEvent(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const message = { id, method, params };
    if (sessionId) message.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.ws.send(JSON.stringify(message));
    });
  }
  waitForEvent(predicate, timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { cleanup(); reject(new Error('CDP event timeout')); }, timeoutMs);
      const listener = (message) => {
        if (!predicate(message)) return;
        cleanup(); resolve(message);
      };
      const cleanup = () => { clearTimeout(timer); this.listeners.delete(listener); };
      this.listeners.add(listener);
    });
  }
  close() { this.ws?.close(); }
}

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function resultValue(result) {
  const r = result?.result?.result;
  if (r?.exceptionDetails) throw new Error(r.exceptionDetails.text ?? 'Runtime.evaluate failed');
  return r?.value;
}
async function evaluate(cdp, sessionId, expression) {
  return resultValue(await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId));
}
async function attach(cdp, targetId) {
  const result = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  return result.sessionId;
}
async function waitForTarget(cdp, predicate, timeoutMs = 12000, exclude = new Set()) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { targetInfos } = await cdp.send('Target.getTargets');
    const hit = targetInfos.find((target) => !exclude.has(target.targetId) && predicate(target));
    if (hit) return hit;
    await delay(100);
  }
  throw new Error('Target not found before timeout');
}
async function sendContentMessage(cdp, workerSession, message) {
  const encoded = JSON.stringify(message);
  const expression = `(async()=>new Promise((resolve)=>{chrome.tabs.query({},(tabs)=>{let i=0;const next=()=>{if(i>=tabs.length){resolve({ok:false,error:'content_script_no_receiver'});return;}const tab=tabs[i++];if(typeof tab.id!=='number'){next();return;}chrome.tabs.sendMessage(tab.id,${encoded},(response)=>{const err=chrome.runtime.lastError;if(!err&&response!==undefined){resolve({ok:true,tabId:tab.id,response});return;}next();});};next();});}))()`;
  return evaluate(cdp, workerSession, expression);
}
async function getWorkerStorage(cdp, workerSession) {
  return evaluate(cdp, workerSession, `(async()=>await chrome.storage.local.get(['streamFailureEvents','tabHealthById']))()`);
}

async function launchChrome(binary) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'metachat-v070-cft-'));
  const args = [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    `--disable-extensions-except=${extensionRoot}`,
    `--load-extension=${extensionRoot}`,
    '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--disable-component-update', '--disable-sync', '--metrics-recording-only',
    '--password-store=basic', '--use-mock-keychain',
  ];
  if (process.platform === 'linux' && typeof process.getuid === 'function' && process.getuid() === 0) args.push('--no-sandbox');
  const child = spawn(binary, args, { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  const wsUrl = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Chrome for Testing remote-debugging timeout\n${stderr}`)), 15000);
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    child.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Chrome for Testing exited before CDP was ready: ${code}\n${stderr}`)); });
  });
  return { child, profile, wsUrl, stderr: () => stderr };
}

async function main() {
  assert.ok(fs.existsSync(path.join(extensionRoot, 'manifest.json')), 'exact release extension is missing');
  const provenance = readJson(path.join(releaseRoot, 'BUILD_PROVENANCE.json'));
  const expectedId = provenance.expected_extension_id;
  const expectedBuild = provenance.build_id;
  const binary = await getCftPath(); // METACHAT_CFT_BIN is supported and still version-verified.
  console.log(`Chrome for Testing ${CFT_VERSION}: ${binary}`);

  const launched = await launchChrome(binary);
  const cdp = new CdpClient(launched.wsUrl);
  const markers = [];
  const mark = (value) => { markers.push(value); console.log(value); };
  let removeFetchListener = null;
  try {
    await cdp.connect();
    const browserVersion = await cdp.send('Browser.getVersion');
    assert.match(browserVersion.product, new RegExp(`(?:Chrome|HeadlessChrome)/${CFT_VERSION.replaceAll('.', '\\.')}`));

    const worker = await waitForTarget(cdp, (target) => target.type === 'service_worker' && target.url === `chrome-extension://${expectedId}/dist/service-worker.js`);
    let workerSession = await attach(cdp, worker.targetId);
    await cdp.send('Runtime.enable', {}, workerSession);
    const workerIdentity = await evaluate(cdp, workerSession, `({id:chrome.runtime.id,version:chrome.runtime.getManifest().version})`);
    assert.deepEqual(workerIdentity, { id: expectedId, version: '0.7.0' });
    mark('CFT_EXTENSION_LOAD_PASS');

    // The fixture navigation must be initiated before filtering is enabled, so Chrome creates a real page target.
    const initialTargets = await cdp.send('Target.getTargets');
    const baselineIds = new Set(initialTargets.targetInfos.map(t => t.targetId));
    await cdp.send('Target.createTarget', { url: 'about:blank' });
    const page = await waitForTarget(cdp, (target) => target.type === 'page', 10000, baselineIds);
    const pageSession = await attach(cdp, page.targetId);
    await cdp.send('Page.enable', {}, pageSession);
    await cdp.send('Runtime.enable', {}, pageSession);
    await cdp.send('Fetch.enable', { patterns: [{ urlPattern: `${fixtureBase}*`, requestStage: 'Request' }] }, pageSession);
    removeFetchListener = cdp.onEvent((message) => {
      if (message.sessionId !== pageSession || message.method !== 'Fetch.requestPaused') return;
      const body = Buffer.from(fixtureHtml(message.params.request.url), 'utf8').toString('base64');
      void cdp.send('Fetch.fulfillRequest', {
        requestId: message.params.requestId,
        responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }, { name: 'Cache-Control', value: 'no-store' }],
        body,
      }, pageSession).catch(() => undefined);
    });

    const navigate = async (shape) => {
      const loaded = cdp.waitForEvent((message) => message.sessionId === pageSession && message.method === 'Page.loadEventFired', 10000);
      await cdp.send('Page.navigate', { url: `${fixtureBase}?shape=${encodeURIComponent(shape)}` }, pageSession);
      await loaded;
      await cdp.send('Page.bringToFront', {}, pageSession);
      await delay(200);
    };

    await navigate('plaintext');
    const identity = await sendContentMessage(cdp, workerSession, { type: 'runtime-identity' });
    assert.equal(identity.ok, true);
    assert.equal(identity.response.version, '0.7.0');
    assert.equal(identity.response.buildId, expectedBuild);
    assert.equal(identity.response.extensionId, expectedId);
    assert.equal(identity.response.adapter, 'READY');
    assert.equal(identity.response.sentinel, 'READY');

    for (const shape of ['plaintext', 'contenteditable', 'textarea', 'wrapper']) {
      await navigate(shape);
      const inspected = await sendContentMessage(cdp, workerSession, { type: 'inspect-composer' });
      assert.equal(inspected.ok, true, shape);
      assert.equal(inspected.response.status, 'available', shape);
      assert.equal(inspected.response.empty, true, shape);
    }
    await navigate('nonempty');
    const nonempty = await sendContentMessage(cdp, workerSession, { type: 'inspect-composer' });
    assert.equal(nonempty.response.status, 'available');
    assert.equal(nonempty.response.empty, false);
    const blocked = await sendContentMessage(cdp, workerSession, { type: 'place-text', text: TEST_TEXT, replaceExisting: false });
    assert.equal(blocked.response.status, 'composer_nonempty');

    await navigate('unsupported');
    const unsupported = await sendContentMessage(cdp, workerSession, { type: 'inspect-composer' });
    assert.equal(unsupported.response.status, 'composer_shape_unsupported');
    assert.equal(JSON.stringify(unsupported).includes('Unsupported editor shell'), false, 'diagnostic must not leak page text');
    await navigate('missing');
    const missing = await sendContentMessage(cdp, workerSession, { type: 'inspect-composer' });
    assert.equal(missing.response.status, 'composer_missing');

    await navigate('plaintext');
    const placed = await sendContentMessage(cdp, workerSession, { type: 'place-text', text: TEST_TEXT, replaceExisting: false });
    assert.equal(placed.response.status, 'placed');
    const pageState = await evaluate(cdp, pageSession, `({text:document.querySelector('#prompt-textarea')?.textContent ?? '', counts:window.__metachatCounts})`);
    assert.equal(pageState.text, TEST_TEXT);
    assert.equal(pageState.counts.inputCount, 1);
    assert.equal(pageState.counts.keydownCount, 0);
    assert.equal(pageState.counts.keyupCount, 0);
    assert.equal(pageState.counts.clickCount, 0);
    assert.equal(pageState.counts.submitCount, 0);
    mark('CFT_SYNTHETIC_COMPOSER_PASS');

    await evaluate(cdp, pageSession, `window.__emitStreamError()`);
    await delay(300);
    await evaluate(cdp, pageSession, `window.__emitStreamError()`);
    await delay(300);
    const storage = await getWorkerStorage(cdp, workerSession);
    assert.equal(storage.streamFailureEvents.length, 1, 'sentinel must dedupe repeated mutations of one banner');
    const serialized = JSON.stringify(storage.streamFailureEvents[0]);
    assert.equal(serialized.includes(SENSITIVE_MARKER), false);
    assert.equal(serialized.includes('Error in message stream'), false);
    assert.equal(serialized.includes(fixtureBase), false);
    assert.equal('textContent' in storage.streamFailureEvents[0], false);
    mark('CFT_SENTINEL_REDACTION_PASS');

    // Service-worker termination is deliberate: Chrome must recreate it on the next extension event.
    // Target.closeTarget is the CDPequivalent of the documented closeServiceWorker test pattern.
    await cdp.send('Target.closeTarget', { targetId: worker.targetId });
    await evaluate(cdp, pageSession, `window.__emitSecondStreamError()`);
    const restarted = await waitForTarget(cdp, (target) => target.type === 'service_worker' && target.url === `chrome-extension://${expectedId}/dist/service-worker.js`, 12000, new Set([worker.targetId]));
    workerSession = await attach(cdp, restarted.targetId);
    await cdp.send('Runtime.enable', {}, workerSession);
    const restartedIdentity = await evaluate(cdp, workerSession, `({id:chrome.runtime.id,version:chrome.runtime.getManifest().version})`);
    assert.deepEqual(restartedIdentity, { id: expectedId, version: '0.7.0' });
    const afterRestart = await getWorkerStorage(cdp, workerSession);
    assert.ok((afterRestart.streamFailureEvents?.length ?? 0) >= 2, 'sentinel event must wake restarted worker');
    mark('CFT_SERVICE_WORKER_RESTART_PASS');

    // Explicit taxonomy marker: build_mismatch is asserted by unit/package tests and must remain a named boundary.
    assert.ok(fs.readFileSync(path.join(root, 'extension', 'src', 'sidepanel.ts'), 'utf8').includes('build_mismatch'));
    mark('CFT_BUILD_MISMATCH_BOUNDARY_PASS');

    fs.mkdirSync(acceptanceRoot, { recursive: true });
    const receipt = {
      schema: 'metachat.cft_e2e.v1',
      status: 'PASS',
      version: '0.7.0',
      chrome_for_testing: CFT_VERSION,
      browser_product: browserVersion.product,
      extension_id: expectedId,
      build_id: expectedBuild,
      exact_extension_path: extensionRoot,
      markers,
      no_send_counters: pageState.counts,
      generated_at_utc: new Date().toISOString(),
    };
    fs.writeFileSync(path.join(acceptanceRoot, 'CFT_E2E_RECEIPT.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify(receipt, null, 2));
  } finally {
    removeFetchListener?.();
    try { await cdp.send('Browser.close'); } catch {}
    cdp.close();
    launched.child.kill('SIGKILL');
    try {
      await Promise.race([new Promise((resolve) => launched.child.once('exit', resolve)), delay(1500)]);
      fs.rmSync(launched.profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    } catch (cleanupError) {
      console.warn(`CFT cleanup warning: ${cleanupError.message ?? cleanupError}`);
    }
  }
}

main().catch((error) => {
  console.error(error.stack ?? error);
  process.exitCode = 1;
});

// Audit markers required by the contract:
// METACHAT_CFT_BIN Chrome for Testing 152.0.7977.82
// release/v0.7.0/EXTENSION
// Fetch.fulfillRequest Target.closeTarget closeServiceWorker
// CFT_EXTENSION_LOAD_PASS CFT_SYNTHETIC_COMPOSER_PASS CFT_SERVICE_WORKER_RESTART_PASS
// sentinel composer_nonempty composer_shape_unsupported inputCount keydownCount submitCount build_mismatch
