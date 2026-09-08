"use strict";
const COMPOSER_SELECTOR = '#prompt-textarea, [contenteditable="true"][role="textbox"]';
function findComposer(doc) {
    const candidate = doc.querySelector(COMPOSER_SELECTOR);
    if (!candidate)
        return null;
    if (classifyComposer(candidate) !== 'unsupported')
        return candidate;
    const nested = candidate.querySelector?.('textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]') ?? null;
    if (nested && classifyComposer(nested) !== 'unsupported')
        return nested;
    return candidate;
}
function classifyComposer(element) {
    if ((element.tagName ?? '').toUpperCase() === 'TEXTAREA')
        return 'textarea';
    const contentEditable = element.getAttribute?.('contenteditable');
    if ((contentEditable !== null && contentEditable.toLowerCase() !== 'false') || element.isContentEditable === true) {
        return 'contenteditable';
    }
    return 'unsupported';
}
function describeUnsupportedComposer(element) {
    const nested = element.querySelector?.('textarea, [contenteditable], [role="textbox"]') ?? null;
    return {
        tagName: (element.tagName ?? '').toUpperCase(),
        contentEditable: element.getAttribute?.('contenteditable') ?? null,
        role: element.getAttribute?.('role') ?? null,
        isContentEditable: element.isContentEditable === true,
        nestedTagName: nested ? (nested.tagName ?? '').toUpperCase() : null,
        nestedContentEditable: nested?.getAttribute?.('contenteditable') ?? null,
        nestedRole: nested?.getAttribute?.('role') ?? null,
    };
}
function readText(element, kind) {
    if (kind === 'textarea')
        return element.value ?? '';
    return element.textContent ?? '';
}
function dispatchInput(doc, element, text) {
    const view = doc.defaultView;
    const InputCtor = view?.InputEvent ?? globalThis.InputEvent;
    const EventCtor = view?.Event ?? globalThis.Event;
    const event = typeof InputCtor === 'function'
        ? new InputCtor('input', { bubbles: true, inputType: 'insertText', data: text })
        : new EventCtor('input', { bubbles: true });
    element.dispatchEvent(event);
}
function inspectComposer(doc) {
    const element = findComposer(doc);
    if (!element)
        return { status: 'composer_missing', charCount: 0, empty: true };
    const kind = classifyComposer(element);
    if (kind === 'unsupported') {
        return { status: 'unsupported', charCount: 0, empty: true, diagnostic: describeUnsupportedComposer(element) };
    }
    const text = readText(element, kind);
    return {
        status: 'available',
        charCount: text.length,
        empty: text.length === 0,
        kind,
    };
}
function placeText(doc, text, options = {}) {
    const element = findComposer(doc);
    if (!element)
        return { status: 'composer_missing', charCount: 0 };
    const kind = classifyComposer(element);
    if (kind === 'unsupported')
        return { status: 'unsupported', charCount: 0 };
    const existing = readText(element, kind);
    if (existing.length > 0 && options.replaceExisting !== true) {
        return { status: 'blocked_nonempty', charCount: existing.length };
    }
    if (kind === 'textarea') {
        element.value = text;
    }
    else {
        element.textContent = text;
    }
    dispatchInput(doc, element, text);
    return { status: 'placed', charCount: text.length };
}
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
const ERROR_PHRASE = 'error in message stream';
const INITIAL_CANDIDATE_SELECTOR = '[role="alert"], [data-testid*="error" i], [class*="error" i]';
function normalizeText(value) {
    return (value ?? '').replace(/\s+/g, ' ').trim().toLowerCase();
}
function isVisible(candidate) {
    if (candidate.hidden === true)
        return false;
    if (candidate.getAttribute?.('aria-hidden') === 'true')
        return false;
    return true;
}
function isStreamErrorCandidate(candidate) {
    if (!candidate || !isVisible(candidate))
        return false;
    return normalizeText(candidate.textContent).includes(ERROR_PHRASE);
}
function collectCandidateTree(root) {
    const candidates = [root];
    const descendants = root.querySelectorAll?.(INITIAL_CAANDIDATE_SELECTOR);
    if (descendants) {
        for (const descendant of Array.from(descendants))
            candidates.push(descendant);
    }
    return candidates;
}
function countDomNodes(doc) {
    try {
        return doc.getElementsByTagName('*').length;
    }
    catch {
        return 0;
    }
}
function readDraftLength(doc) {
    try {
        const composer = doc.querySelector('#prompt-textarea, [contenteditable="true"][role="textbox"]');
        return composer?.textContent?.length ?? 0;
    }
    catch {
        return 0;
    }
}
function createLongTaskCollector(doc) {
    const view = doc.defaultView;
    const ObserverCtor = view?.PerformanceObserver;
    const supported = ObserverCtor?.supportedEntryTypes;
    if (!ObserverCtor || (supported && !supported.includes('longtask'))) {
        return {
            snapshot: () => ({
                count: 0,
                totalDurationMs: 0,
                maxDurationMs: 0,
                available: false,
            }),
            stop: () => undefined,
        };
    }
    let count = 0;
    let totalDurationMs = 0;
    let maxDurationMs = 0;
    let observer = null;
    try {
        observer = new ObserverCtor((list) => {
            for (const entry of Array.from(list.getEntries())) {
                const duration = Number(entry.duration ?? 0);
                count += 1;
                totalDurationMs += duration;
                maxDurationMs = Math.max(maxDurationMs, duration);
            }
        });
        observer.observe({ entryTypes: ['longtask'] });
    }
    catch {
        observer = null;
    }
    if (!observer) {
        return {
            snapshot: () => ({
                count: 0,
                totalDurationMs: 0,
                maxDurationMs: 0,
                available: false,
            }),
            stop: () => undefined,
        };
    }
    return {
        snapshot: () => ({ count, totalDurationMs, maxDurationMs, available: true }),
        stop: () => observer?.disconnect(),
    };
}
function resolveMutationObserver(doc) {
    const view = doc.defaultView;
    const ObserverCtor = view?.MutationObserver ??
        globalThis.MutationObserver;
    if (!ObserverCtor)
        throw new Error('MutationObserver is unavailable');
    return ObserverCtor;
}
function observeStreamFailures(doc, emit) {
    if (!doc.body)
        return () => undefined;
    const activeCandidates = new WeakSet();
    const candidateIds = new WeakMap();
    let nextCandidateId = 1;
    let occurrence = 1;
    const longTasks = createLongTaskCollector(doc);
    const candidateId = (candidate) => {
        const existing = candidateIds.get(candidate);
        if (existing !== undefined)
            return existing;
        const assigned = nextCandidateId++;
        candidateIds.set(candidate, assigned);
        return assigned;
    };
    const handleCandidate = (candidate) => {
        if (!isStreamErrorCandidate(candidate)) {
            activeCandidates.delete(candidate);
            return;
        }
        if (activeCandidates.has(candidate))
            return;
        activeCandidates.add(candidate);
        emit(buildSentinelEvent({
            fingerprint: `stream-error:${candidateId(candidate)}:${occurrence++}`,
            source: 'dom',
            domNodeCount: countDomNodes(doc),
            draftLength: readDraftLength(doc),
            online: doc.defaultView?.navigator.onLine ?? true,
            visibilityState: doc.visibilityState ?? 'unknown',
            longTasks: longTasks.snapshot(),
        }));
    };
    const inspect = (candidate) => {
        if (!candidate)
            return;
        const normalized = candidate.nodeType === 3 && candidate.parentElement
            ? candidate.parentElement
            : candidate;
        for (const node of collectCandidateTree(normalized))
            handleCandidate(node);
    };
    for (const candidate of Array.from(doc.querySelectorAll(INITIAL_CANDIDATE_SELECTOR))) {
        inspect(candidate);
    }
    const ObserverCtor = resolveMutationObserver(doc);
    const observer = new ObserverCtor((records) => {
        for (const record of records) {
            if (record.type === 'childList') {
                for (const node of Array.from(record.addedNodes ?? []))
                    inspect(node);
                continue;
            }
            inspect(record.target);
        }
    });
    observer.observe(doc.body, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['hidden', 'aria-hidden', 'class'],
    });
    return () => {
        observer.disconnect();
        longTasks.stop();
    };
}
const VERSION = '0.7.0';
const BUILD_ID = 'sha256:0b96946680bd6c00438b27a33df0eded4af9c16d900d5ef56e44ec9128323a8d';
const EXPECTED_EXTENSION_ID = 'dkjgeplcldbicjciacambbemephQlbfc';
function isPlacementMessage(message) {
    if (!message || typeof message !== 'object')
        return false;
    const c = message;
    return c.type === 'place-text' && typeof c.text === 'string';
}
function isInspectMessage(message) {
    return !!message && typeof message === 'object' && message.type === 'inspect-composer';
}
function isIdentityMessage(message) {
    return !!message && typeof message === 'object' && message.type === 'runtime-identity';
}
let adapterState = 'READY';
let sentinelState = 'STARTING';
let sentinelError = null;
try {
    observeStreamFailures(document, (event) => {
        chrome.runtime.sendMessage({ type: 'stream-failure', event }, () => { void chrome.runtime.lastError; });
    });
    sentinelState = 'READY';
}
catch (error) {
    sentinelState = 'FAILED';
    sentinelError = error instanceof Error ? error.name : 'sentinel_init_failed';
}
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (isIdentityMessage(message)) {
        sendResponse({
            ok: true,
            context: 'content',
            version: VERSION,
            buildId: BUILD_ID,
            expectedExtensionId: EXPECTED_EXTENSION_ID,
            extensionId: chrome.runtime.id,
            adapter: adapterState,
            sentinel: sentinelState,
            sentinelError,
        });
        return false;
    }
    if (isInspectMessage(message)) {
        try {
            const result = inspectComposer(document);
            const status = result.status === 'unsupported' ? 'composer_shape_unsupported' : result.status;
            sendResponse({ ...result, status });
        }
        catch (error) {
            adapterState = 'FAILED';
            sendResponse({ status: 'adapter_init_failed', charCount: 0, error: error instanceof Error ? error.name : 'unknown' });
        }
        return false;
    }
    if (isPlacementMessage(message)) {
        try {
            const result = placeText(document, message.text, { replaceExisting: message.replaceExisting === true });
            const status = result.status === 'unsupported' ? 'composer_shape_unsupported' : result.status === 'blocked_nonempty' ? 'composer_nonempty' : result.status;
            sendResponse({ ...result, status });
        }
        catch (error) {
            adapterState = 'FAILED';
            sendResponse({ status: 'placement_failed', charCount: 0, error: error instanceof Error ? error.name : 'unknown' });
        }
        return false;
    }
    return false;
});
