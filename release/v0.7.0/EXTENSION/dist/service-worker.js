"use strict";
const EMPTY_LONG_TASKS = Object.freeze({
    count: 0,
    totalDurationMs: 0,
    maxDurationMs: 0,
    available: false,
});
function buildSentinelEvent(raw) {
    return Object.freeze({
        schema: 'metachat.stream_failure.v1',
        kind: 'stream-failure',
        timestampUtc: raw.timestampUtc ?? new Date().toISOString(),
        fingerprint: raw.fingerprint,
        source: raw.source ?? 'dom',
        domNodeCount: raw.domNodeCount ?? 0,
        draftLength: raw.draftLength ?? 0,
        online: raw.online ?? true,
        visibilityState: raw.visibilityState ?? 'unknown',
        longTasks: raw.longTasks ?? EMPTY_LONG_TASKS,
    });
}
// ---- native-client.ts ----
const NATIVE_HOST_NAME = 'com.metablooms.metachat_sidecar';
const ALLOWED_NATIVE_COMMANDS = [
    'ping',
    'list_drafts',
    'load_draft',
    'launch_composer',
    'capture_process_snapshot',
];
function isAllowedNativeCommand(command) {
    return typeof command === 'string' &&
        ALLOWED_NATIVE_COMMANDS.includes(command);
}
function sendNativeCommand(command, args = {}) {
    if (!isAllowedNativeCommand(command)) {
        return Promise.reject(new Error(`Native command is not allowlisted: ${command}`));
    }
    return new Promise((resolve, reject) => {
        chrome.runtime.sendNativeMessage(NATIVE_HOST_NAME, { command, args }, (response) => {
            const lastError = chrome.runtime.lastError;
            if (lastError) {
                reject(new Error(lastError.message || 'Native messaging failed.'));
                return;
            }
            if (!response || typeof response.ok !== 'boolean') {
                reject(new Error('Native host returned an invalid response.'));
                return;
            }
            resolve(response);
        });
    });
}
// ---- state-store.ts ----
const EVENTS_KEY = 'streamFailureEvents';
const TAB_HEALTH_KEY = 'tabHealthById';
const NATIVE_HOST_KEY = 'nativeHostState';
const MAX_EVENTS = 100;
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
async function initializeStorageAccess() {
    const setter = chrome.storage?.local?.setAccessLevel;
    if (typeof setter === 'function') {
        await setter.call(chrome.storage.local, { accessLevel: 'TRUSTED_CONTEXTS' });
    }
}
async function recordStreamFailure(tabId, event, nowMs = Date.now()) {
    const stored = await chrome.storage.local.get([EVENTS_KEY, TAB_HEALTH_KEY]);
    const previousEvents = Array.isArray(stored[EVENTS_KEY])
        ? stored[EVENTS_KEY]
        : [];
    const cutoff = nowMs - MAX_AGE_MS;
    const retained = previousEvents.filter((candidate) => {
        const timestamp = Date.parse(candidate.timestampUtc);
        return Number.isFinite(timestamp) && timestamp >= cutoff;
    });
    retained.push({ ...event, tabId });
    const events = retained.slice(-MAX_EVENTS);
    const healthById = typeof stored[TAB_HEALTH_KEY] === 'object' && stored[TAB_HEALTH_KEY] !== null
        ? { ...stored[TAB_HEALTH_KEY] }
        : {};
    const prior = healthById[String(tabId)];
    healthById[String(tabId)] = {
        tabId,
        evidence: 'high',
        streamFailureCount: (prior?.streamFailureCount ?? 0) + 1,
        lastStreamFailureUtc: event.timestampUtc,
    };
    await chrome.storage.local.set({
        [EVENTS_KEY]: events,
        [TAB_HEALTH_KEY]: healthById,
    });
}
async function setNativeHostState(status) {
    await chrome.storage.local.set({
        [NATIVE_HOST_KEY]: {
            status,
            updatedAtUtc: new Date().toISOString(),
        },
    });
}
const VERSION = '0.7.0';
const BUILD_ID = 'sha256:0b96946680bd6c00438b27a33df0eded4af9c16d900d5ef56e44ec9128323a8d';
const EXPECTED_EXTENSION_ID = 'dkjgeplcldbicjciacambbemephklbfc';
function isStreamFailureMessage(message) {
    return !!message && typeof message === 'object' && message.type === 'stream-failure' && !!message.event;
}
function isNativeCommandMessage(message) {
    return !!message && typeof message === 'object' && message.type === 'native-command' && typeof message.command === 'string';
}
function isIdentityMessage(message) {
    return !!message && typeof message === 'object' && message.type === 'runtime-identity';
}
void initializeStorageAccess();
chrome.runtime.onInstalled?.addListener(() => { void initializeStorageAccess(); });
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (isIdentityMessage(message)) {
        sendResponse({ ok: true, context: 'worker', version: VERSION, buildId: BUILD_ID, expectedExtensionId: EXPECTED_EXTENSION_ID, extensionId: chrome.runtime.id });
        return false;
    }
    if (isStreamFailureMessage(message)) {
        const tabId = sender.tab?.id;
        if (typeof tabId !== 'number') {
            sendResponse({ ok: false, error: 'sender_tab_unavailable' });
            return false;
        }
        void recordStreamFailure(tabId, message.event).then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false, error: 'storage_unavailable' }));
        return true;
    }
    if (isNativeCommandMessage(message)) {
        void sendNativeCommand(message.command, message.args ?? {}).then(async (response) => {
            await setNativeHostState('connected');
            sendResponse(response);
        }).catch(async () => {
            await setNativeHostState('unavailable');
            sendResponse({ ok: false, command: message.command, result: null, error: { code: 'native_unavailable', message: 'Native helper is unavailable.' } });
        });
        return true;
    }
    return false;
});
