/*
 * Download Transfer Station bridge.
 *
 * This file is original project code layered on top of the GPL-3.0
 * cat-catch extension. The extension discovers media and submits an
 * authenticated plan; the desktop helper owns every download, merge and
 * Eagle import. Sensitive request context is never stored by the extension.
 */

const EAGLE_BRIDGE_API_BASE = "http://127.0.0.1:47652";
const EAGLE_BRIDGE_STATE_KEY = "downloadTransferStation";
const EAGLE_BRIDGE_RETRY_ALARM = "downloadTransferStationRetry";
const EAGLE_BRIDGE_VERSION_ALARM = "eagleBridgeVersionCheck";
const EAGLE_BRIDGE_MAX_PENDING_EVENTS = 200;
const EAGLE_BRIDGE_SITE_CACHE_TTL = 30 * 1000;

let eagleBridgeFlushPromise = null;
let eagleBridgeAutoPairPromise = null;
let eagleBridgeStateWriter = null;
const eagleBridgeSiteCache = new Map();

function eagleBridgeDefaultState() {
    return {
        token: "",
        pendingEvents: [],
        lastPlanId: "",
        lastPlanStatus: ""
    };
}

async function eagleBridgeGetState() {
    const stored = await chrome.storage.local.get([EAGLE_BRIDGE_STATE_KEY, "token", "pendingEvents"]);
    if (!stored[EAGLE_BRIDGE_STATE_KEY] && (stored.token || Array.isArray(stored.pendingEvents))) {
        const migrated = {
            ...eagleBridgeDefaultState(),
            token: String(stored.token || ""),
            pendingEvents: Array.isArray(stored.pendingEvents)
                ? stored.pendingEvents.map(eagleBridgeSanitizeEvent).slice(-EAGLE_BRIDGE_MAX_PENDING_EVENTS)
                : []
        };
        await chrome.storage.local.set({ [EAGLE_BRIDGE_STATE_KEY]: migrated });
        return migrated;
    }
    const current = { ...eagleBridgeDefaultState(), ...(stored[EAGLE_BRIDGE_STATE_KEY] || {}) };
    delete current.downloads;
    return current;
}

async function eagleBridgeUpdateState(changes) {
    if (!eagleBridgeStateWriter) {
        eagleBridgeStateWriter = EagleBridgeAuthLogic.createStateUpdateQueue(
            eagleBridgeGetState,
            next => chrome.storage.local.set({ [EAGLE_BRIDGE_STATE_KEY]: next })
        );
    }
    return eagleBridgeStateWriter(changes);
}

async function eagleBridgeApi(path, options = {}, allowAuthRecovery = true) {
    let state = await eagleBridgeGetState();
    if (!state.token && path !== "/api/pair" && path !== "/api/pair/auto") {
        await eagleBridgeTryAutoPair();
        state = await eagleBridgeGetState();
    }
    const requestToken = state.token;
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let body = options.body;
    if (state.token && body && String(options.method || "GET").toUpperCase() === "POST") {
        const parsed = typeof body === "string" ? JSON.parse(body) : body;
        body = JSON.stringify({ ...parsed, authToken: state.token });
    }
    const response = await fetch(`${EAGLE_BRIDGE_API_BASE}${path}`, { ...options, headers, body });
    const result = await response.json().catch(() => ({ ok: false, error: "本机助手返回格式错误" }));
    if (response.status === 401 && allowAuthRecovery && path !== "/api/pair" && path !== "/api/pair/auto") {
        const latestState = await eagleBridgeGetState();
        const action = EagleBridgeAuthLogic.unauthorizedAction(requestToken, latestState.token);
        if (action === "retry-latest") {
            return eagleBridgeApi(path, options, false);
        }
        if (action === "clear-rejected") {
            await eagleBridgeUpdateState(current => current.token === requestToken ? { token: "" } : {});
        }
        if (await eagleBridgeTryAutoPair()) {
            return eagleBridgeApi(path, options, false);
        }
    }
    if (!response.ok || !result.ok) throw new Error(result.error || "本机助手连接失败");
    return result.data;
}

function eagleBridgeRead(path, payload = {}) {
    return eagleBridgeApi(path, {
        method: "POST",
        body: JSON.stringify(payload)
    });
}

async function eagleBridgeTryAutoPair() {
    const state = await eagleBridgeGetState();
    if (state.token) return true;
    const secret = String(globalThis.IDM_EAGLE_BOOTSTRAP_SECRET || "");
    if (!secret) return false;
    if (eagleBridgeAutoPairPromise) return eagleBridgeAutoPairPromise;
    eagleBridgeAutoPairPromise = (async () => {
        try {
            const response = await fetch(`${EAGLE_BRIDGE_API_BASE}/api/pair/auto`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ secret })
            });
            const result = await response.json().catch(() => ({ ok: false }));
            if (!response.ok || !result.ok || !result.data?.token) return false;
            await eagleBridgeUpdateState({ token: result.data.token });
            eagleBridgeScheduleRetry();
            return true;
        } catch (_error) {
            return false;
        } finally {
            eagleBridgeAutoPairPromise = null;
        }
    })();
    return eagleBridgeAutoPairPromise;
}

async function eagleBridgePair(code) {
    const data = await eagleBridgeApi("/api/pair", {
        method: "POST",
        body: JSON.stringify({ code })
    });
    if (!data?.token) throw new Error("本机助手未返回有效配对信息");
    await eagleBridgeUpdateState({ token: data.token });
    eagleBridgeScheduleRetry();
    return data;
}

function eagleBridgeSanitizeEvent(event) {
    const clean = {
        pageUrl: String(event.pageUrl || ""),
        pageTitle: String(event.pageTitle || "").slice(0, 500),
        mediaUrl: String(event.mediaUrl || ""),
        eventType: String(event.eventType || "media"),
        tabId: Number.isInteger(event.tabId) ? event.tabId : undefined,
        capturedAt: Number(event.capturedAt || Date.now())
    };
    if (event.deferSiteCheck) clean.deferSiteCheck = true;
    return clean;
}

async function eagleBridgeCurrentTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url?.startsWith("http")) throw new Error("当前页面不是普通网页");
    return tab;
}

async function eagleBridgeEnsureDiscovery(tabId) {
    const normalizedTabId = Number(tabId);
    if (!Number.isInteger(normalizedTabId) || normalizedTabId < 0) {
        return { ready: false, injected: false, reason: "invalid_tab" };
    }
    const tab = await chrome.tabs.get(normalizedTabId);
    return EagleBridgeCandidateLogic.ensureContentDiscovery(chrome, tab);
}

async function eagleBridgeExplicitSource(eventType) {
    const tab = await eagleBridgeCurrentTab();
    return eagleBridgeQueueSourceEvent({
        pageUrl: tab.url,
        pageTitle: tab.title || "",
        mediaUrl: "",
        eventType,
        tabId: tab.id,
        capturedAt: Date.now()
    });
}

async function eagleBridgeSourceClick(event, senderTab) {
    const clean = eagleBridgeSanitizeEvent({
        ...(event || {}),
        pageUrl: event?.pageUrl || senderTab?.url || "",
        pageTitle: event?.pageTitle || senderTab?.title || "",
        tabId: senderTab?.id,
        capturedAt: event?.capturedAt || Date.now()
    });
    let domain = "";
    try {
        domain = new URL(clean.pageUrl).hostname;
    } catch (_error) {
        throw new Error("页面来源地址无效");
    }
    try {
        const site = await eagleBridgeSiteStatus(domain);
        if (!site?.enabled) clean.eventType = "site_disabled";
    } catch (_error) {
        clean.deferSiteCheck = true;
    }
    return eagleBridgeQueueSourceEvent(clean);
}

async function eagleBridgeQueueSourceEvent(event) {
    const clean = eagleBridgeSanitizeEvent(event);
    await eagleBridgeUpdateState(current => ({
        pendingEvents: [...(Array.isArray(current.pendingEvents) ? current.pendingEvents : []), clean]
            .slice(-EAGLE_BRIDGE_MAX_PENDING_EVENTS)
    }));
    eagleBridgeScheduleRetry();
    return eagleBridgeFlushEvents();
}

async function eagleBridgeFlushEvents() {
    if (eagleBridgeFlushPromise) return eagleBridgeFlushPromise;
    eagleBridgeFlushPromise = (async () => {
        let state = await eagleBridgeGetState();
        if (!state.token && !(await eagleBridgeTryAutoPair())) return false;
        state = await eagleBridgeGetState();
        const pending = Array.isArray(state.pendingEvents) ? [...state.pendingEvents] : [];
        let consumed = 0;
        for (const queuedEvent of pending) {
            const event = { ...queuedEvent };
            try {
                if (event.deferSiteCheck) {
                    const domain = new URL(event.pageUrl).hostname;
                    const site = await eagleBridgeSiteStatus(domain);
                    delete event.deferSiteCheck;
                    if (!site?.enabled) event.eventType = "site_disabled";
                }
                await eagleBridgeApi("/api/source", {
                    method: "POST",
                    body: JSON.stringify(event)
                });
                consumed += 1;
            } catch (error) {
                if (/未开启自动导入/.test(String(error?.message || ""))) {
                    consumed += 1;
                    continue;
                }
                break;
            }
        }
        if (consumed) {
            await eagleBridgeUpdateState(current => ({
                pendingEvents: (Array.isArray(current.pendingEvents) ? current.pendingEvents : []).slice(consumed)
            }));
        }
        return consumed === pending.length;
    })().finally(() => {
        eagleBridgeFlushPromise = null;
    });
    return eagleBridgeFlushPromise;
}

function eagleBridgeScheduleRetry() {
    chrome.alarms.create(EAGLE_BRIDGE_RETRY_ALARM, { delayInMinutes: 0.5 });
    setTimeout(() => eagleBridgeFlushEvents(), 1000);
    setTimeout(() => eagleBridgeFlushEvents(), 5000);
}

function eagleBridgeIsNewerVersion(candidate, current) {
    const left = String(candidate || "").split(".").map(value => Number.parseInt(value, 10) || 0);
    const right = String(current || "").split(".").map(value => Number.parseInt(value, 10) || 0);
    for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
        if ((left[index] || 0) !== (right[index] || 0)) return (left[index] || 0) > (right[index] || 0);
    }
    return false;
}

async function eagleBridgeCheckDesktopVersion() {
    try {
        const response = await fetch(`${EAGLE_BRIDGE_API_BASE}/health`);
        const health = await response.json();
        if (response.ok && eagleBridgeIsNewerVersion(health.version, chrome.runtime.getManifest().version)) {
            chrome.runtime.reload();
        }
    } catch (_error) {
        // 桌面助手离线时保持当前扩展，下一次唤醒再检查。
    }
}

function eagleBridgeScheduleVersionCheck() {
    chrome.alarms.create(EAGLE_BRIDGE_VERSION_ALARM, { periodInMinutes: 30 });
}

async function eagleBridgeSiteStatus(domain) {
    const normalized = String(domain || "").toLowerCase();
    const cached = eagleBridgeSiteCache.get(normalized);
    if (cached && Date.now() - cached.time < EAGLE_BRIDGE_SITE_CACHE_TTL) return cached.value;
    const value = await eagleBridgeApi("/api/site/status", {
        method: "POST",
        body: JSON.stringify({ domain: normalized })
    });
    eagleBridgeSiteCache.set(normalized, { time: Date.now(), value });
    return value;
}

async function eagleBridgeCandidate(info) {
    if (!info?.webUrl || !String(info.webUrl).startsWith("http")) return;
    let domain = "";
    try {
        domain = new URL(info.webUrl).hostname;
    } catch (_error) {
        return;
    }
    try {
        const state = await eagleBridgeSiteStatus(domain);
        if (!state?.enabled) return;
        await eagleBridgeQueueSourceEvent({
            pageUrl: info.webUrl,
            pageTitle: info.title || "",
            mediaUrl: info.url || "",
            eventType: "media",
            tabId: info.tabId,
            capturedAt: info.getTime || Date.now()
        });
    } catch (_error) {
        return;
    }
}

function eagleBridgeSafeExtension(value, fallback = "bin") {
    const cleaned = String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    return cleaned.slice(0, 10) || fallback;
}

function eagleBridgePublicStream(data, index) {
    const type = String(data.type || "").toLowerCase();
    const role = ["video", "audio", "subtitle"].includes(data.role)
        ? data.role
        : type.startsWith("audio/") ? "audio" : type.startsWith("video/") ? "video" : `media${index + 1}`;
    const fallbackExtension = role === "audio" ? "m4a" : role === "subtitle" ? "vtt" : "mp4";
    return {
        clientIndex: index,
        url: String(data.url || ""),
        role,
        name: String(data.downFileName || data.name || `${role}.${eagleBridgeSafeExtension(data.ext)}`),
        extension: eagleBridgeSafeExtension(data.ext, fallbackExtension),
        mimeType: type,
        size: Number.isFinite(Number(data._size ?? data.size)) ? Number(data._size ?? data.size) : null,
        width: Number.isFinite(Number(data.videoWidth)) ? Number(data.videoWidth) : null,
        height: Number.isFinite(Number(data.videoHeight)) ? Number(data.videoHeight) : null,
        duration: Number.isFinite(Number(data.duration)) ? Number(data.duration) : null,
        codec: String(data.codec || ""),
        language: String(data.language || ""),
        label: String(data.label || ""),
        resolver: ["youtube", "page"].includes(data.resolver) ? data.resolver : "",
        preferredQuality: /^\d{2,5}p$/i.test(String(data.preferredQuality || "")) ? String(data.preferredQuality).toLowerCase() : "",
        drm: Boolean(data.drm || data.pssh || data.keySystem)
    };
}

function eagleBridgePrivateHeaders(data) {
    const source = { ...(data.requestHeaders || {}) };
    if (data.cookie) source.cookie = data.cookie;
    const allowed = {};
    for (const [key, value] of Object.entries(source)) {
        const lower = key.toLowerCase();
        if (["referer", "origin", "authorization", "cookie", "user-agent"].includes(lower) && typeof value === "string") {
            allowed[lower] = value;
        }
    }
    return allowed;
}

async function eagleBridgeCreatePlan(items, options = {}) {
    if (!Array.isArray(items) || !items.length) throw new Error("请先选择要下载的媒体");
    if (items.some(item => item.drm || item.pssh || item.keySystem)) {
        throw new Error("检测到 DRM 保护，本程序不会下载或尝试绕过");
    }
    const first = items[0];
    const payload = {
        pageUrl: String(first.resolver === "page" ? first.url : (first.webUrl || first.initiator || "")),
        pageTitle: String(first._title || first.title || ""),
        thumbnailUrl: String(first.thumbnailUrl || ""),
        outputName: String(options.outputName || first.downFileName || first.name || first.title || "media"),
        outputContainer: String(options.outputContainer || (items.length > 1 ? "mkv" : eagleBridgeSafeExtension(first.ext, "mp4"))),
        mergeMode: items.length > 1 ? "local_streamcopy" : "direct",
        route: "desktop",
        importToEagle: options.importToEagle !== false,
        deleteAfterImport: options.deleteAfterImport === true,
        tabId: Number.isInteger(first.tabId) ? first.tabId : null,
        streams: items.map(eagleBridgePublicStream),
        runtimeHeaders: items.map(item => {
            const headers = eagleBridgePrivateHeaders(item);
            return {
                referer: headers.referer,
                origin: headers.origin,
                "user-agent": headers["user-agent"],
                authorization: headers.authorization,
                cookie: headers.cookie
            };
        })
    };
    const plan = await eagleBridgeApi("/api/media/plan", {
        method: "POST",
        body: JSON.stringify(payload)
    });
    await eagleBridgeUpdateState({ lastPlanId: plan.id, lastPlanStatus: plan.status });

    return plan;
}

chrome.alarms.onAlarm.addListener(alarm => {
    if (alarm.name === EAGLE_BRIDGE_RETRY_ALARM) eagleBridgeFlushEvents();
    if (alarm.name === EAGLE_BRIDGE_VERSION_ALARM) eagleBridgeCheckDesktopVersion();
});

chrome.runtime.onStartup.addListener(() => {
    eagleBridgeTryAutoPair();
    eagleBridgeScheduleVersionCheck();
    eagleBridgeCheckDesktopVersion();
});

chrome.runtime.onInstalled.addListener(() => {
    eagleBridgeTryAutoPair();
    eagleBridgeScheduleVersionCheck();
    eagleBridgeCheckDesktopVersion();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message?.eagleBridge) return undefined;
    (async () => {
        switch (message.eagleBridge) {
            case "authState": {
                const state = await eagleBridgeGetState();
                return { paired: Boolean(state.token), pendingEvents: state.pendingEvents.length, lastPlanId: state.lastPlanId };
            }
            case "autoPair": {
                await eagleBridgeTryAutoPair();
                const state = await eagleBridgeGetState();
                return { paired: Boolean(state.token), pendingEvents: state.pendingEvents.length, lastPlanId: state.lastPlanId };
            }
            case "health":
                return eagleBridgeRead("/api/media/health");
            case "pair":
                return eagleBridgePair(String(message.code || ""));
            case "resetAuth":
                await eagleBridgeUpdateState({ token: "" });
                return { paired: false };
            case "siteStatus":
                return eagleBridgeSiteStatus(String(message.domain || ""));
            case "setSite": {
                const data = await eagleBridgeApi("/api/site", {
                    method: "POST",
                    body: JSON.stringify({ domain: message.domain, enabled: Boolean(message.enabled), includeSubdomains: true })
                });
                eagleBridgeSiteCache.delete(String(message.domain || "").toLowerCase());
                return data;
            }
            case "currentTab":
                return eagleBridgeCurrentTab();
            case "ensureDiscovery":
                return eagleBridgeEnsureDiscovery(message.tabId);
            case "sourceClick":
                return eagleBridgeSourceClick(message.event || {}, sender.tab);
            case "manualSource":
                return eagleBridgeExplicitSource("manual");
            case "ignoreNext":
                return eagleBridgeExplicitSource("ignore");
            case "source":
                return eagleBridgeQueueSourceEvent(message.event || {});
            case "createPlan":
                return eagleBridgeCreatePlan(message.items || [], message.options || {});
            case "plan":
                return eagleBridgeRead("/api/media/plan/get", { planId: String(message.planId || "") });
            case "plans":
                return eagleBridgeRead("/api/media/plans");
            case "planPreview":
                return eagleBridgeRead("/api/media/preview", { planId: String(message.planId || "") });
            case "openPlanOutput":
                return eagleBridgeApi("/api/media/open", {
                    method: "POST",
                    body: JSON.stringify({ planId: message.planId })
                });
            case "importPlan":
                return eagleBridgeApi("/api/media/import", {
                    method: "POST",
                    body: JSON.stringify({ planId: message.planId })
                });
            case "stopPlan":
                return eagleBridgeApi("/api/media/stop", {
                    method: "POST",
                    body: JSON.stringify({ planId: message.planId })
                });
            case "retryPlan":
                return eagleBridgeApi("/api/media/retry", {
                    method: "POST",
                    body: JSON.stringify({ planId: message.planId })
                });
            default:
                throw new Error("未知的下载中转站扩展操作");
        }
    })().then(
        data => sendResponse({ ok: true, data }),
        error => sendResponse({ ok: false, error: String(error?.message || error) })
    );
    return true;
});

eagleBridgeTryAutoPair();
eagleBridgeScheduleVersionCheck();
eagleBridgeCheckDesktopVersion();
