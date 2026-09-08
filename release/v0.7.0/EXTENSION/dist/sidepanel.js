"use strict";
const VERSION = '0.7.0';
const BUILD_ID = 'sha256:0b96946680bd6c00438b27a33df0eded4af9c16d900d5ef56e44ec9128323a8d';
const EXPECTED_EXTENSION_ID = 'dkjgeplcldbicjciacambbemephklbfc';
const CONVERSATION_KEY = /^[0-9a-f]{64}$/;
const CANARY_TEXT = 'MetaChat v0.7.0 canary line 1\nCanary line 2 — español 日本語 🙂';
let lastHandshake = { ok: false, status: 'content_script_no_receiver' };
let composerReady = false;
function sendRuntimeMessage(message) {
    return new Promise((resolve, reject) => chrome.runtime.sendMessage(message, (response) => {
        const e = chrome.runtime.lastError;
        if (e) {
            reject(new Error(e.message || 'runtime_message_failed'));
            return;
        }
        if (response === undefined) {
            reject(new Error('runtime_empty_response'));
            return;
        }
        resolve(response);
    }));
}
function queryActiveTab() {
    return new Promise((resolve) => chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs[0] ?? null)));
}
function sendTabMessage(tabId, message) {
    return new Promise((resolve, reject) => chrome.tabs.sendMessage(tabId, message, (response) => {
        const e = chrome.runtime.lastError;
        if (e) {
            reject(new Error(e.message || 'content_script_no_receiver'));
            return;
        }
        if (response === undefined) {
            reject(new Error('content_script_no_receiver'));
            return;
        }
        resolve(response);
    }));
}
function getStored(keys) {
    return new Promise((resolve) => chrome.storage.local.get(keys, (values) => resolve(values ?? {})));
}
async function checkRuntimeHandshake() {
    const manifestVersion = chrome.runtime.getManifest?.().version ?? VERSION;
    const worker = await sendRuntimeMessage({ type: 'runtime-identity' }).catch(() => undefined);
    const tab = await queryActiveTab();
    if (!worker || typeof tab?.id !== 'number')
        return { ok: false, status: 'content_script_no_receiver', worker };
    const content = await sendTabMessage(tab.id, { type: 'runtime-identity' }).catch(() => undefined);
    if (!content)
        return { ok: false, status: 'content_script_no_receiver', worker, tabId: tab.id };
    const ids = [worker.extensionId, content.extensionId, chrome.runtime.id];
    const versions = [manifestVersion, VERSION, worker.version, content.version];
    const builds = [BUILD_ID, worker.buildId, content.buildId];
    if (ids.some((v) => v !== EXPECTED_EXTENSION_ID) || versions.some((v) => v !== VERSION) || builds.some((v) => v !== BUILD_ID)) {
        return { ok: false, status: 'build_mismatch', worker, content, tabId: tab.id };
    }
    if (content.adapter !== 'READY')
        return { ok: false, status: 'adapter_init_failed', worker, content, tabId: tab.id };
    if (content.sentinel !== 'READY')
        return { ok: false, status: 'sentinel_init_failed', worker, content, tabId: tab.id };
    return { ok: true, status: 'ready', worker, content, tabId: tab.id };
}
async function inspectActiveComposer() {
    lastHandshake = await checkRuntimeHandshake();
    if (!lastHandshake.ok || typeof lastHandshake.tabId !== 'number')
        return { status: lastHandshake.status === 'ready' ? 'build_mismatch' : lastHandshake.status };
    return sendTabMessage(lastHandshake.tabId, { type: 'inspect-composer' }).catch(() => ({ status: 'content_script_no_receiver' }));
}
async function placeCanaryText() {
    const inspected = await inspectActiveComposer();
    if (inspected.status !== 'available' || inspected.empty !== true || typeof lastHandshake.tabId !== 'number') {
        return inspected.status === 'available' ? { status: 'composer_nonempty', charCount: inspected.charCount } : inspected;
    }
    return sendTabMessage(lastHandshake.tabId, { type: 'place-text', text: CANARY_TEXT, replaceExisting: false }).catch(() => ({ status: 'content_script_no_receiver' }));
}
async function listNativeDrafts() {
    const response = await sendRuntimeMessage({ type: 'native-command', command: 'list_drafts', args: {} });
    if (!response.ok || !Array.isArray(response.result))
        return [];
    return response.result.filter((row) => {
        if (!row || typeof row !== 'object')
            return false;
        const c = row;
        return typeof c.conversationKey === 'string' && CONVERSATION_KEY.test(c.conversationKey) && typeof c.updatedAtUtc === 'string' && typeof c.charCount === 'number';
    });
}
async function placeDraftIntoActiveTab(conversationKey, replaceExisting) {
    if (!CONVERSATION_KEY.test(conversationKey))
        return { status: 'invalid_conversation_key' };
    lastHandshake = await checkRuntimeHandshake();
    if (!lastHandshake.ok || typeof lastHandshake.tabId !== 'number')
        return { status: lastHandshake.status === 'ready' ? 'build_mismatch' : lastHandshake.status };
    const native = await sendRuntimeMessage({ type: 'native-command', command: 'load_draft', args: { conversationKey } });
    const loaded = native.result;
    if (!native.ok || !loaded?.found || typeof loaded.text !== 'string')
        return { status: 'native_draft_missing' };
    return sendTabMessage(lastHandshake.tabId, { type: 'place-text', text: loaded.text, replaceExisting }).catch(() => ({ status: 'content_script_no_receiver' }));
}
function setText(id, value) { const el = document.getElementById(id); if (el)
    el.textContent = value; }
function setDisabled(id, disabled) { const el = document.getElementById(id); if (el)
    el.disabled = disabled; }
function short(value) { return value.length > 20 ? `${value.slice(0, 20)}…` : value; }
function describe(result) {
    const map = {
        placed: `Placed ${result.charCount ?? 0} characters. Nothing was sent.`, composer_nonempty: 'Composer already contains unsent text.', composer_missing: 'composer_missing',
        composer_shape_unsupported: 'composer_shape_unsupported', adapter_init_failed: 'adapter_init_failed', sentinel_init_failed: 'sentinel_init_failed', placement_failed: 'placement_failed',
        native_draft_missing: 'native_draft_missing', active_chatgpt_tab_missing: 'active_chatgpt_tab_missing', invalid_conversation_key: 'invalid_conversation_key', content_script_no_receiver: 'content_script_no_receiver', build_mismatch: 'build_mismatch', available: 'Composer available.'
    };
    return map[result.status] ?? result.status;
}
async function renderIdentity() {
    lastHandshake = await checkRuntimeHandshake();
    const c = lastHandshake.content;
    const w = lastHandshake.worker;
    setText('identity-version', w?.version ?? VERSION);
    setText('identity-build', short(w?.buildId ?? BUILD_ID));
    setText('identity-extension', short(chrome.runtime.id ?? EXPECTED_EXTENSION_ID));
    setText('identity-content', lastHandshake.ok ? 'READY' : lastHandshake.status);
    setText('identity-adapter', c?.adapter ?? 'UNKNOWN');
    setText('identity-sentinel', c?.sentinel ?? 'UNKNOWN');
    setText('identity-status', lastHandshake.ok ? 'Identity verified. Composer inspection is enabled.' : lastHandshake.status);
    setDisabled('check-composer', !lastHandshake.ok);
    setDisabled('place-canary', true);
    setDisabled('place-draft', !lastHandshake.ok);
    setDisabled('replace-draft', !lastHandshake.ok);
    composerReady = false;
    return lastHandshake;
}
async function refreshDraftSelect(select, status) {
    status.textContent = 'Reading native drafts…';
    const drafts = await listNativeDrafts();
    select.replaceChildren();
    for (const draft of drafts) {
        const o = document.createElement('option');
        o.value = draft.conversationKey;
        o.textContent = `${draft.charCount} chars · ${draft.conversationKey.slice(0, 10)}…`;
        select.append(o);
    }
    status.textContent = drafts.length ? `${drafts.length} native draft${drafts.length === 1 ? '' : 's'} available.` : 'No native drafts found.';
}
async function renderHealth() {
    const tab = await queryActiveTab();
    const stored = await getStored(['tabHealthById', 'nativeHostState']);
    const h = (stored.tabHealthById ?? {});
    const row = typeof tab?.id === 'number' ? h[String(tab.id)] : undefined;
    setText('health-evidence', row?.evidence === 'high' ? 'High observations' : 'Normal');
    setText('health-failures', String(row?.streamFailureCount ?? 0));
    setText('native-host-state', (stored.nativeHostState?.status) ?? 'Unknown');
}
function bindPanel() {
    const select = document.getElementById('draft-select');
    const action = document.getElementById('action-status');
    const canary = document.getElementById('canary-status');
    if (!select || !action || !canary)
        return;
    document.getElementById('refresh-identity')?.addEventListener('click', () => void renderIdentity());
    document.getElementById('check-composer')?.addEventListener('click', () => void inspectActiveComposer().then((r) => { composerReady = r.status === 'available' && r.empty === true; setDisabled('place-canary', !composerReady); canary.textContent = describe(composerReady ? r : { ...r, status: r.status === 'available' ? 'composer_nonempty' : r.status }); }));
    document.getElementById('place-canary')?.addEventListener('click', () => void placeCanaryText().then((r) => { canary.textContent = describe(r); setDisabled('place-canary', true); }));
    document.getElementById('refresh-drafts')?.addEventListener('click', () => void refreshDraftSelect(select, action));
    document.getElementById('place-draft')?.addEventListener('click', () => { const k = select.value; if (k)
        void placeDraftIntoActiveTab(k, false).then((r) => action.textContent = describe(r)); });
    document.getElementById('replace-draft')?.addEventListener('click', () => { const k = select.value; if (k && window.confirm('Replace the existing unsent ChatGPT composer text?'))
        void placeDraftIntoActiveTab(k, true).then((r) => action.textContent = describe(r)); });
    document.getElementById('launch-composer')?.addEventListener('click', () => void sendRuntimeMessage({ type: 'native-command', command: 'launch_composer', args: {} }).then((r) => action.textContent = r.ok ? 'Native composer opened.' : 'Native composer unavailable.'));
    void renderIdentity();
    void renderHealth();
    void refreshDraftSelect(select, action).catch(() => { action.textContent = 'Native drafts unavailable.'; });
}
if (typeof document !== 'undefined') {
    if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', bindPanel, { once: true });
    else
        bindPanel();
}
