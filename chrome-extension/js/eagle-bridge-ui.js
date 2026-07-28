(function () {
    "use strict";

    const root = document.getElementById("eagleBridgeRoot");
    const logic = globalThis.EagleBridgeUILogic;
    if (!root || !logic) return;

    const zhHans = {
        product: "下载中转站", media: "媒体", tasks: "任务", refresh: "刷新", settings: "设置",
        checking: "正在连接", connected: "已连接", offline: "助手离线", needsPairing: "需要配对",
        captured: "已捕获媒体（{count}）", filter: "筛选", searchPlaceholder: "搜索标题、格式或清晰度",
        currentPage: "当前页", otherPages: "其他页", allPages: "全部", noMedia: "暂未发现媒体",
        noMediaBody: "播放视频后刷新，或启动深度搜索来发现隐藏媒体。",
        deepSearch: "深度搜索", video: "视频", audio: "音频", manifest: "清单",
        filename: "文件名", advanced: "高级选项", subtitles: "字幕（将单独下载）", noAudio: "不选择音频",
        directInfo: "所选文件将下载并导入 Eagle；成功后删除本机下载文件。", mergeInfo: "视频与音频将在本机无损合并并导入 Eagle；成功后删除本机下载文件。",
        manifestInfo: "HLS/DASH 清单将在本机下载、合并、校验并导入 Eagle；成功后删除本机下载文件。",
        downloadImport: "导入 Eagle（成功后删本机文件）", downloadOnly: "仅下载", legal: "请只下载你有权保存的内容。",
        pairBody: "输入桌面助手显示的六位配对码，连接后才能自动合并并导入 Eagle。", pairPlaceholder: "六位配对码", pair: "配对",
        siteRule: "记录来源并自动导入 Eagle", recordPage: "记录当前页", ignoreNext: "忽略下一次导入",
        pauseCapture: "暂停/继续捕获", openWindow: "独立窗口", clearMedia: "清空当前页媒体",
        copyLink: "复制链接",
        taskTitle: "下载任务", taskSubtitle: "浏览器与视频号任务统一显示在这里。", refreshTasks: "刷新任务", clearTasks: "清除完成",
        clearTasksConfirm: "只清除已完成、失败和已停止的任务记录；进行中的任务与下载文件都会保留。是否继续？", tasksCleared: "已清除 {count} 条任务记录",
        noTasks: "还没有下载任务。", stop: "停止", backToMedia: "返回媒体重新创建",
        discoverBody: "按当前标签页启动增强发现，状态会在这里保持同步。",
        on: "已开启", off: "已关闭", unavailable: "不可用",
        taskStarted: "任务已开始", stopped: "任务已停止", copied: "链接已复制", siteUpdated: "网站规则已更新",
        pageRecorded: "当前页来源已记录", nextIgnored: "下一次导入将被忽略", pairingDone: "配对完成", clearConfirm: "清空当前页面捕获到的全部媒体？",
        selectVersion: "视频质量", qualityCountLabel: "视频质量（本视频 {count} 档）", qualitySourceHint: "档位来自当前视频；其他视频会按源站实际提供的质量变化。", currentQuality: "当前播放 {quality}", recommendedQuality: "推荐",
        downloadStarted: "下载已开始", toolUpdated: "工具状态已更新", connectionError: "无法连接本机助手",
        notGrouped: "未归组资源", selectedCount: "{count} 个可下载内容", retry: "重试", activeTaskCount: "{active} 个进行中，共 {count} 个任务", taskCount: "共 {count} 个任务",
        batch: "批量", exitBatch: "退出批量", batchTitle: "批量操作", batchBody: "每个内容会创建独立任务，不会把不同视频的音轨混在一起。",
        batchSelected: "已选择 {count} 个内容", selectAll: "全选", invert: "反选", copySelected: "复制链接", batchImport: "批量导入（成功后删本机文件）", batchDownload: "批量仅下载",
        mediaType: "媒体类型", allTypes: "全部类型", otherType: "其他资源", extensionFilter: "扩展名（可用逗号分隔）", minimumSize: "最小大小（MB）",
        urlRegex: "网址正则", unsafeRegex: "正则表达式无效或可能造成卡顿，已停止应用。", hideDuplicateNames: "隐藏同名重复资源", showSegments: "显示未关联资源与播放分片", hiddenSegments: "已隐藏 {count} 个未关联播放资源",
        batchPartial: "已启动 {count} 个任务，另有任务失败。", actualFrame: "当前视频画面",
        outputLocation: "保存位置：{path}", openFolder: "打开所在文件夹", folderOpened: "已打开下载文件夹", openSource: "打开来源网页", importExisting: "导入 Eagle，成功后删除本机文件", importQueued: "已加入 Eagle 导入队列；成功后将删除本机文件", segmentOnlyTitle: "无法确认归属的播放资源", syncInterrupted: "任务状态同步中断；本机下载仍可能继续，正在自动重连。",
        technicalInfo: "技术信息", processed: "已处理 {current} / {total}", invalidOutputName: "请输入有效的 Windows 文件名"
    };
    const zhHant = {
        product: "下載中轉站", media: "媒體", tasks: "任務", refresh: "重新整理", settings: "設定",
        checking: "正在連線", connected: "已連線", offline: "助手離線", needsPairing: "需要配對",
        captured: "已擷取媒體（{count}）", filter: "篩選", currentPage: "目前頁", otherPages: "其他頁", allPages: "全部",
        noMedia: "暫未發現媒體", noMediaBody: "播放影片後重新整理，或啟動深度搜尋。",
        filename: "檔案名稱", advanced: "進階選項", downloadImport: "匯入 Eagle（成功後刪除本機檔案）", downloadOnly: "僅下載",
        pair: "配對", taskTitle: "下載任務", noTasks: "還沒有下載任務。", stop: "停止",
        batch: "批次", exitBatch: "退出批次", batchTitle: "批次操作", batchSelected: "已選擇 {count} 個內容", selectAll: "全選", invert: "反選",
        batchImport: "批次匯入（成功後刪除本機檔案）", batchDownload: "批次僅下載", mediaType: "媒體類型", allTypes: "全部類型", otherType: "其他資源",
        activeTaskCount: "{active} 個進行中，共 {count} 個任務", taskCount: "共 {count} 個任務",
        qualityCountLabel: "影片品質（本影片 {count} 檔）", qualitySourceHint: "檔位來自目前影片；其他影片會依來源網站實際提供的品質變化。", showSegments: "顯示未關聯資源與播放分片", hiddenSegments: "已隱藏 {count} 個未關聯播放資源", importExisting: "匯入 Eagle，成功後刪除本機檔案", importQueued: "已加入 Eagle 匯入佇列；成功後將刪除本機檔案", segmentOnlyTitle: "無法確認歸屬的播放資源", openSource: "開啟來源網頁", technicalInfo: "技術資訊", processed: "已處理 {current} / {total}", invalidOutputName: "請輸入有效的 Windows 檔案名稱"
    };
    const en = {
        product: "Download Transfer Station", media: "Media", tasks: "Tasks", refresh: "Refresh", settings: "Settings",
        checking: "Connecting", connected: "Connected", offline: "Helper offline", needsPairing: "Pairing required",
        captured: "Captured media ({count})", filter: "Filter", searchPlaceholder: "Search title, format, or quality",
        currentPage: "Current", otherPages: "Other pages", allPages: "All", noMedia: "No media found yet",
        noMediaBody: "Play the video and refresh, or start Deep Search.", deepSearch: "Deep Search",
        video: "Video", audio: "Audio", manifest: "Manifest", filename: "Filename", advanced: "Advanced options",
        subtitles: "Subtitles (downloaded separately)", noAudio: "No audio", directInfo: "The selected file will be imported into Eagle, then the local download will be deleted after success.",
        mergeInfo: "Video and audio will be merged and imported into Eagle, then the local download will be deleted after success.",
        manifestInfo: "The HLS/DASH media will be downloaded, verified, and imported into Eagle, then the local download will be deleted.",
        downloadImport: "Import to Eagle (delete local file after success)", downloadOnly: "Download only", legal: "Only download content you have the right to save.",
        pairBody: "Enter the six-digit code shown by the desktop helper to enable local merging and Eagle import.", pairPlaceholder: "Six-digit code", pair: "Pair",
        siteRule: "Save source and auto-import", recordPage: "Record page", ignoreNext: "Ignore next import", pauseCapture: "Pause/resume capture",
        openWindow: "Open window", clearMedia: "Clear current media", copyLink: "Copy link",
        taskTitle: "Download tasks", taskSubtitle: "Browser and WeChat Channels tasks appear here together.", refreshTasks: "Refresh tasks", clearTasks: "Clear finished",
        clearTasksConfirm: "Clear completed, failed, and stopped task records? Active tasks and downloaded files will be kept.", tasksCleared: "Cleared {count} task records", noTasks: "No download tasks yet.",
        stop: "Stop", backToMedia: "Return to media", discoverBody: "Enable enhanced discovery for the current tab.",
        on: "On", off: "Off", unavailable: "Unavailable", taskStarted: "Task started", stopped: "Task stopped", copied: "Link copied", siteUpdated: "Site rule updated",
        pageRecorded: "Page source recorded", nextIgnored: "Next import will be ignored", pairingDone: "Paired", clearConfirm: "Clear all captured media on this page?",
        selectVersion: "Video quality", qualityCountLabel: "Video quality ({count} levels for this video)", qualitySourceHint: "Levels come from this video; other videos follow the qualities actually advertised by their source.", currentQuality: "Playing at {quality}", recommendedQuality: "Recommended",
        downloadStarted: "Download started", toolUpdated: "Tool state updated", connectionError: "Cannot reach the desktop helper", notGrouped: "Ungrouped resource",
        selectedCount: "{count} downloadable items", retry: "Retry", activeTaskCount: "{active} active, {count} total", taskCount: "{count} tasks total",
        batch: "Batch", exitBatch: "Exit batch", batchTitle: "Batch actions", batchBody: "Each content item creates its own task; tracks from different videos are never mixed.",
        batchSelected: "{count} items selected", selectAll: "Select all", invert: "Invert", copySelected: "Copy links", batchImport: "Import all and delete local files", batchDownload: "Download all only",
        mediaType: "Media type", allTypes: "All types", otherType: "Other", extensionFilter: "Extensions (comma-separated)", minimumSize: "Minimum size (MB)",
        urlRegex: "URL regular expression", unsafeRegex: "This expression is invalid or potentially unsafe and was not applied.", hideDuplicateNames: "Hide duplicate filenames", showSegments: "Show unbound resources and playback fragments", hiddenSegments: "{count} unbound playback resources hidden",
        batchPartial: "Started {count} tasks; one or more failed.",
        outputLocation: "Saved to: {path}", openFolder: "Open folder", folderOpened: "Download folder opened", openSource: "Open source page", importExisting: "Import to Eagle, then delete local file", importQueued: "Queued for Eagle import; the local file will be deleted after success", segmentOnlyTitle: "Playback resource with unknown ownership", syncInterrupted: "Task sync was interrupted. The desktop download may still continue; reconnecting automatically.",
        technicalInfo: "Technical information", processed: "Processed {current} / {total}", invalidOutputName: "Enter a valid Windows filename"
    };

    const uiLanguage = String(chrome.i18n?.getUILanguage?.() || "zh-CN").toLowerCase();
    const locale = uiLanguage.startsWith("zh-tw") || uiLanguage.startsWith("zh-hk") || uiLanguage.startsWith("zh-mo")
        ? "zhHant" : uiLanguage.startsWith("zh") ? "zhHans" : "en";
    const strings = { ...zhHans, ...(locale === "zhHant" ? zhHant : locale === "en" ? en : {}) };
    const t = (key, values = {}) => {
        let text = strings[key] || key;
        for (const [name, value] of Object.entries(values)) text = text.replaceAll(`{${name}}`, String(value));
        return text;
    };

    const state = {
        view: "media",
        tab: null,
        connection: "checking",
        paired: false,
        siteEnabled: false,
        siteLoading: false,
        candidates: { current: [], other: [] },
        groups: [],
        activeGroupId: "",
        selections: new Map(),
        drafts: new Map(),
        plans: [],
        toolState: {},
        framePreviews: new Map(),
        taskPreviews: new Map(),
        taskPreviewFailures: new Set(),
        taskSyncError: "",
        scope: "current",
        search: "",
        filters: { mediaType: "all", extension: "", minimumSizeMb: "", regex: "", dedupe: false, showSegments: false },
        hiddenSegmentCount: 0,
        filterError: "",
        batchMode: false,
        selectedGroupIds: new Set(),
        filterOpen: false,
        settingsOpen: false,
        busy: false,
        taskTimer: null,
        candidateTimer: null,
        snapshotTimer: null,
    };

    let toastTimer = null;

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    }

    function send(payload) {
        return new Promise((resolve, reject) => {
            chrome.runtime.sendMessage(payload, response => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }
                resolve(response);
            });
        });
    }

    function asset(path) {
        return chrome.runtime.getURL(path);
    }

    function icon(path, alt = "") {
        return `<img class="bridge-icon" src="${escapeHtml(asset(path))}" alt="${escapeHtml(alt)}">`;
    }

    function staticThumbUrl(group) {
        const keys = [group?.groupKey, ...(group?.items || []).map(item => item.groupKey)].filter(Boolean);
        const frame = keys.map(key => state.framePreviews.get(String(key))).find(value => /^data:image\/(?:jpeg|png|webp);base64,/i.test(String(value || "")));
        return frame || group?.thumbnailUrl || "";
    }

    function thumbUrl(group) {
        return staticThumbUrl(group) || asset("icons/icon-128.png");
    }

    function mediaPreviewMarkup(group, selection, className, alt = "") {
        const still = staticThumbUrl(group);
        if (still) {
            return `<img class="${escapeHtml(className)}" src="${escapeHtml(still)}" alt="${escapeHtml(alt)}" data-fallback="${escapeHtml(asset("icons/icon-128.png"))}">`;
        }
        const mediaUrl = logic.previewMediaUrl(group, selection);
        if (mediaUrl) {
            return `<video class="bridge-remote-preview ${escapeHtml(className)}" src="${escapeHtml(mediaUrl)}" aria-label="${escapeHtml(alt)}" muted playsinline preload="metadata" data-media-preview></video><img class="bridge-preview-fallback ${escapeHtml(className)}" src="${escapeHtml(asset("icons/icon-128.png"))}" alt="${escapeHtml(alt)}" hidden>`;
        }
        return `<img class="${escapeHtml(className)}" src="${escapeHtml(asset("icons/icon-128.png"))}" alt="${escapeHtml(alt)}">`;
    }

    function sidebarPreviewMarkup(group, alt = "") {
        const fallback = asset("icons/icon-128.png");
        return `<img class="bridge-thumb" src="${escapeHtml(staticThumbUrl(group) || fallback)}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async" data-fallback="${escapeHtml(fallback)}">`;
    }

    function taskThumbUrl(task) {
        const preview = state.taskPreviews.get(String(task?.id || ""));
        return /^data:image\/(?:jpeg|png|webp);base64,/i.test(String(preview || ""))
            ? preview : task?.thumbnailUrl || asset("icons/icon-128.png");
    }

    function currentDomain() {
        try { return new URL(state.tab?.url || "").hostname; } catch (_error) { return ""; }
    }

    function technicalUrl(value) {
        try {
            const url = new URL(String(value || ""));
            url.search = "";
            url.hash = "";
            return url.href;
        } catch (_error) {
            return "";
        }
    }

    function taskTime(value) {
        const timestamp = Number(value || 0);
        if (!Number.isFinite(timestamp) || timestamp <= 0) return "";
        try {
            return new Intl.DateTimeFormat(
                locale === "zhHant" ? "zh-Hant" : locale === "en" ? "en" : "zh-CN",
                { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }
            ).format(new Date(timestamp * 1000));
        } catch (_error) {
            return "";
        }
    }

    function showToast(message, kind = "info", timeout = 2400) {
        const element = root.querySelector("#bridgeToast");
        if (!element) return;
        clearTimeout(toastTimer);
        element.textContent = String(message || "");
        element.dataset.kind = kind;
        element.hidden = false;
        toastTimer = setTimeout(() => { element.hidden = true; }, timeout);
    }

    function initShell() {
        if (new URL(location.href).searchParams.has("tabId")) {
            document.documentElement.classList.add("bridge-expanded");
            document.body.classList.add("bridge-expanded");
        }
        root.innerHTML = `
            <div class="bridge-app">
                <header class="bridge-header">
                    <div class="bridge-brand-lockup">
                        <img class="bridge-brand-icon" src="${escapeHtml(asset("icons/icon-32.png"))}" alt="">
                        <h1 class="bridge-brand">${escapeHtml(t("product"))}</h1>
                    </div>
                    <div class="bridge-page-context">
                        <strong id="bridgePageTitle" class="bridge-page-title"></strong>
                        <span id="bridgeDomain" class="bridge-domain"></span>
                    </div>
                    <button id="bridgeConnection" class="bridge-connection" data-action="settings" data-state="checking" aria-label="${escapeHtml(t("settings"))}">
                        <span class="bridge-connection-dot" aria-hidden="true"></span><span id="bridgeConnectionLabel">${escapeHtml(t("checking"))}</span>
                    </button>
                    <div class="bridge-header-actions">
                        <button class="bridge-header-action" data-action="refresh">${icon("icons/action-refresh.svg")}<span>${escapeHtml(t("refresh"))}</span></button>
                        <button id="bridgeSettingsButton" class="bridge-header-action" data-action="settings" aria-haspopup="dialog" aria-expanded="false"><span>${escapeHtml(t("settings"))}</span></button>
                    </div>
                    <div id="bridgeSettingsMenu" class="bridge-settings-menu" role="dialog" aria-label="${escapeHtml(t("settings"))}" hidden></div>
                </header>
                <nav class="bridge-nav" role="tablist" aria-label="${escapeHtml(t("product"))}">
                    <button class="bridge-nav-button" data-view="media" role="tab" aria-selected="true" aria-controls="bridgeMediaPanel">${escapeHtml(t("media"))}</button>
                    <button class="bridge-nav-button" data-view="tasks" role="tab" aria-selected="false" aria-controls="bridgeTasksPanel">${escapeHtml(t("tasks"))}<span id="bridgeTaskBadge" class="bridge-task-badge" hidden></span></button>
                </nav>
                <div class="bridge-content">
                    <section id="bridgeMediaPanel" class="bridge-panel" role="tabpanel">
                        <div class="bridge-media-layout">
                            <aside class="bridge-sidebar">
                                <div class="bridge-sidebar-header">
                                    <span id="bridgeSidebarTitle" class="bridge-sidebar-title"></span>
                                    <button id="bridgeBatchButton" class="bridge-filter-button" data-action="batch" aria-pressed="false">${escapeHtml(t("batch"))}</button>
                                    <button id="bridgeFilterButton" class="bridge-filter-button" data-action="filter" aria-expanded="false">${escapeHtml(t("filter"))}</button>
                                    <div id="bridgeFilterPopover" class="bridge-filter-popover" hidden></div>
                                </div>
                                <div id="bridgeGroupList" class="bridge-group-list" role="listbox"></div>
                            </aside>
                            <section id="bridgeInspector" class="bridge-inspector" aria-label="${escapeHtml(t("selectVersion"))}"></section>
                        </div>
                    </section>
                    <section id="bridgeTasksPanel" class="bridge-panel" role="tabpanel" hidden></section>
                    <div id="bridgeToast" class="bridge-toast" role="status" aria-live="polite" hidden></div>
                </div>
            </div>`;
        root.setAttribute("aria-busy", "false");
    }

    function connectionLabel() {
        return state.connection === "paired" ? t("connected")
            : state.connection === "needs_pairing" ? t("needsPairing")
                : state.connection === "offline" ? t("offline") : t("checking");
    }

    function patchHeader() {
        const domain = root.querySelector("#bridgeDomain");
        const pageTitle = root.querySelector("#bridgePageTitle");
        const connection = root.querySelector("#bridgeConnection");
        const label = root.querySelector("#bridgeConnectionLabel");
        if (pageTitle) {
            pageTitle.textContent = state.tab?.title || t("currentPage");
            pageTitle.title = state.tab?.title || "";
        }
        if (domain) {
            domain.textContent = currentDomain() || t("currentPage");
            domain.title = state.tab?.url || "";
        }
        if (connection) connection.dataset.state = state.connection;
        if (label) label.textContent = connectionLabel();
        const activeCount = state.plans.filter(plan => logic.taskView(plan).active).length;
        const taskCount = state.plans.length;
        const badge = root.querySelector("#bridgeTaskBadge");
        if (badge) {
            badge.hidden = !taskCount;
            badge.textContent = String(Math.min(taskCount, 99));
            badge.title = activeCount
                ? t("activeTaskCount", { active: activeCount, count: taskCount })
                : t("taskCount", { count: taskCount });
        }
    }

    function renderFilter() {
        const panel = root.querySelector("#bridgeFilterPopover");
        const button = root.querySelector("#bridgeFilterButton");
        if (!panel || !button) return;
        panel.hidden = !state.filterOpen;
        button.setAttribute("aria-expanded", String(state.filterOpen));
        panel.innerHTML = `
            <label class="bridge-filter-label" for="bridgeSearch">${escapeHtml(t("filter"))}</label>
            <input id="bridgeSearch" class="bridge-search-input" type="search" value="${escapeHtml(state.search)}" placeholder="${escapeHtml(t("searchPlaceholder"))}">
            <div class="bridge-scope-options" role="radiogroup" aria-label="${escapeHtml(t("filter"))}">
                ${[["current", "currentPage"], ["other", "otherPages"], ["all", "allPages"]].map(([value, key]) => `
                    <label class="bridge-scope-option"><input type="radio" name="bridgeScope" value="${value}" ${state.scope === value ? "checked" : ""}><span>${escapeHtml(t(key))}</span></label>`).join("")}
            </div>
            <label class="bridge-filter-field"><span>${escapeHtml(t("mediaType"))}</span><select data-filter="mediaType">
                ${[["all", "allTypes"], ["video", "video"], ["audio", "audio"], ["manifest", "manifest"], ["other", "otherType"]].map(([value, key]) => `<option value="${value}" ${state.filters.mediaType === value ? "selected" : ""}>${escapeHtml(t(key))}</option>`).join("")}
            </select></label>
            <label class="bridge-filter-field"><span>${escapeHtml(t("extensionFilter"))}</span><input data-filter="extension" value="${escapeHtml(state.filters.extension)}" placeholder="mp4, m4s, m3u8"></label>
            <label class="bridge-filter-field"><span>${escapeHtml(t("minimumSize"))}</span><input data-filter="minimumSizeMb" inputmode="decimal" value="${escapeHtml(state.filters.minimumSizeMb)}" placeholder="0"></label>
            <label class="bridge-filter-field"><span>${escapeHtml(t("urlRegex"))}</span><input data-filter="regex" value="${escapeHtml(state.filters.regex)}" placeholder="video|audio"></label>
            <div id="bridgeFilterError" class="bridge-filter-error" role="alert" ${state.filterError ? "" : "hidden"}>${escapeHtml(state.filterError)}</div>
            <label class="bridge-filter-check"><input type="checkbox" data-filter="dedupe" ${state.filters.dedupe ? "checked" : ""}><span>${escapeHtml(t("hideDuplicateNames"))}</span></label>
            <label class="bridge-filter-check"><input type="checkbox" data-filter="showSegments" ${state.filters.showSegments ? "checked" : ""}><span>${escapeHtml(t("showSegments"))}</span></label>`;
    }

    function sourceCandidates() {
        const items = state.scope === "current" ? state.candidates.current
            : state.scope === "other" ? state.candidates.other
                : [...state.candidates.current, ...state.candidates.other];
        const minimumSize = Math.max(0, Number(state.filters.minimumSizeMb || 0)) * 1024 * 1024;
        return logic.filterCandidates(items, { ...state.filters, query: state.search, minimumSize });
    }

    function rebuildGroups(options = {}) {
        const previousId = state.activeGroupId;
        const previousLatestId = state.groups.at(-1)?.id || "";
        const followLatest = !previousId || previousId === previousLatestId;
        const partition = logic.partitionGroups(logic.groupCandidates(sourceCandidates()), {
            showSegments: state.filters.showSegments
        });
        state.groups = partition.visible;
        state.hiddenSegmentCount = partition.hiddenSegmentCount;
        for (const group of state.groups) {
            const selection = logic.createDefaultSelection(group, state.selections.get(group.id));
            state.selections.set(group.id, selection);
            if (!state.drafts.has(group.id)) state.drafts.set(group.id, { outputName: logic.defaultOutputName(group, selection) });
        }
        state.selectedGroupIds = new Set([...state.selectedGroupIds].filter(id => state.groups.some(group => (
            group.id === id && !group.segmentOnly && !group.technicalOnly
        ))));
        state.activeGroupId = followLatest
            ? logic.defaultActiveGroupId(state.groups, "")
            : logic.defaultActiveGroupId(state.groups, previousId);
        renderSidebar({ scrollToLatest: followLatest });
        if (!options.keepInspector) renderInspector();
        if (!options.keepFilter) renderFilter();
    }

    function activeGroup() {
        return state.groups.find(group => group.id === state.activeGroupId) || null;
    }

    function renderSidebar(options = {}) {
        const title = root.querySelector("#bridgeSidebarTitle");
        const list = root.querySelector("#bridgeGroupList");
        if (!title || !list) return;
        title.textContent = t("captured", { count: state.groups.length })
            + (state.hiddenSegmentCount ? ` · ${t("hiddenSegments", { count: state.hiddenSegmentCount })}` : "");
        const batchButton = root.querySelector("#bridgeBatchButton");
        if (batchButton) {
            batchButton.textContent = state.batchMode ? t("exitBatch") : t("batch");
            batchButton.setAttribute("aria-pressed", String(state.batchMode));
        }
        if (!state.groups.length) {
            list.innerHTML = `<div class="bridge-empty-sidebar">${escapeHtml(t("noMedia"))}</div>`;
            return;
        }
        list.innerHTML = state.groups.map(group => {
            const selection = state.selections.get(group.id);
            const duration = logic.formatDuration(group.duration);
            const itemCount = group.items.length;
            const selected = state.batchMode ? state.selectedGroupIds.has(group.id) : group.id === state.activeGroupId;
            const technical = Boolean(group.segmentOnly || group.technicalOnly);
            return `<div class="bridge-group-item${technical ? " bridge-segment-only" : ""}" data-batch="${state.batchMode}">
                ${state.batchMode ? `<label class="bridge-batch-check" title="${escapeHtml(t("batchSelected", { count: state.selectedGroupIds.size }))}"><input type="checkbox" data-batch-group="${escapeHtml(group.id)}" ${selected ? "checked" : ""} ${technical ? "disabled" : ""}><span class="bridge-visually-hidden">${escapeHtml(group.title)}</span></label>` : ""}
                <button class="bridge-group-row" data-group-id="${escapeHtml(group.id)}" role="option" aria-current="${group.id === state.activeGroupId}" aria-selected="${selected}">
                <span class="bridge-thumb-wrap">
                    ${technical ? `<span class="bridge-segment-glyph">技术</span>` : sidebarPreviewMarkup(group, group.title)}
                    ${duration ? `<span class="bridge-duration">${escapeHtml(duration)}</span>` : ""}
                </span>
                <span class="bridge-group-copy">
                    <span class="bridge-group-name">${escapeHtml(group.title || t("notGrouped"))}</span>
                    <span class="bridge-group-summary">${escapeHtml(logic.groupSummary(group, selection))}</span>
                    <span class="bridge-group-meta"><span>${escapeHtml(group.sourceDomain || t("currentPage"))}</span><span>·</span><span>${escapeHtml(t("selectedCount", { count: itemCount }))}</span></span>
                </span>
            </button></div>`;
        }).join("");
        if (options.scrollToLatest) requestAnimationFrame(() => { list.scrollTop = list.scrollHeight; });
    }

    function candidateOption(candidate, labeler) {
        return `<option value="${escapeHtml(candidate.id)}">${escapeHtml(labeler(candidate))}</option>`;
    }

    function renderInspector() {
        const inspector = root.querySelector("#bridgeInspector");
        if (!inspector) return;
        if (state.batchMode) {
            renderBatchInspector(inspector);
            return;
        }
        const group = activeGroup();
        if (!group) {
            inspector.innerHTML = `<div class="bridge-empty-state">
                <h2>${escapeHtml(t("noMedia"))}</h2>
                <p>${escapeHtml(t("noMediaBody"))}</p>
                <div class="bridge-empty-actions">
                    <button class="bridge-primary-button" data-tool-action="script:search">${escapeHtml(t("deepSearch"))}</button>
                </div>
            </div>`;
            return;
        }
        const selection = state.selections.get(group.id);
        const draft = state.drafts.get(group.id) || { outputName: logic.defaultOutputName(group, selection) };
        const selectionValidation = logic.validateSelection(group, selection, { paired: state.paired, importToEagle: true });
        const outputValidation = logic.normalizeOutputName(draft.outputName);
        const validation = selectionValidation.ok && !outputValidation.ok
            ? { ok: false, message: outputValidation.message || t("invalidOutputName") }
            : selectionValidation;
        if (group.segmentOnly || group.technicalOnly) {
            inspector.innerHTML = `<div class="bridge-segment-inspector" role="status">
                <div class="bridge-segment-glyph">技术</div>
                <div><h2>${escapeHtml(t("segmentOnlyTitle"))}</h2><p>${escapeHtml(validation.message)}</p></div>
            </div>`;
            return;
        }
        const selected = logic.selectedCandidates(group, selection);
        const duration = logic.formatDuration(group.duration);
        const source = [group.sourceDomain, duration, group.playbackQuality ? t("currentQuality", { quality: group.playbackQuality }) : ""].filter(Boolean).join(" · ");
        const fields = [];
        if (selection.mode === "tracks") {
            if (group.videos.length) fields.push(`<label class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("video"))}</span><select class="bridge-field-select" data-selection="videoId">${group.videos.map((item, index) => candidateOption(item, candidate => logic.videoLabel(candidate, index === 0))).join("")}</select></label>`);
            if (group.audios.length) fields.push(`<label class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("audio"))}</span><select class="bridge-field-select" data-selection="audioId"><option value="">${escapeHtml(t("noAudio"))}</option>${group.audios.map(item => candidateOption(item, logic.audioLabel)).join("")}</select></label>`);
        } else if (["manifest", "resolver"].includes(selection.mode)) {
            const manifestOptions = group.manifests.map(item => candidateOption(item, logic.manifestLabel)).join("");
            if (selection.mode === "manifest" && group.manifests.length > 1) {
                fields.push(`<label class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("manifest"))}</span><select class="bridge-field-select" data-selection="manifestId">${manifestOptions}</select></label>`);
            }
            const qualityCatalog = logic.qualityCatalogInfo(group.availableQualities);
            const qualityFieldLabel = qualityCatalog.count
                ? t("qualityCountLabel", { count: qualityCatalog.count })
                : t("selectVersion");
            const qualityHint = qualityCatalog.count
                ? `<span class="bridge-field-hint">${escapeHtml(t("qualitySourceHint"))}</span>`
                : "";
            const qualityOptions = group.availableQualities.map((quality, index) => `<option value="${escapeHtml(quality)}" ${selection.quality === quality ? "selected" : ""}>${escapeHtml(`${quality}${index === 0 ? ` · ${t("recommendedQuality")}` : ""}`)}</option>`).join("");
            fields.push(group.availableQualities.length > 1
                ? `<label class="bridge-field"><span class="bridge-field-label">${escapeHtml(qualityFieldLabel)}</span><select class="bridge-field-select" data-selection="quality">${qualityOptions}</select>${qualityHint}</label>`
                : `<div class="bridge-field"><span class="bridge-field-label">${escapeHtml(qualityFieldLabel)}</span><div class="bridge-selection-summary">${escapeHtml(group.availableQualities[0] ? `${group.availableQualities[0]} · ${t("recommendedQuality")}` : selection.mode === "resolver" ? logic.directLabel(group.resolvers[0], true) : logic.manifestLabel(group.manifests[0]))}</div>${qualityHint}</div>`);
        } else {
            const directItems = group.items.filter(item => !item.drm);
            const directOptions = directItems.map((item, index) => candidateOption(item, candidate => logic.directLabel(candidate, index === 0))).join("");
            fields.push(directItems.length === 1
                ? `<div class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("selectVersion"))}</span><div class="bridge-selection-summary">${escapeHtml(logic.directLabel(directItems[0], true))}</div></div>`
                : `<label class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("selectVersion"))}</span><select class="bridge-field-select" data-selection="directId">${directOptions}</select></label>`);
        }
        const resolverCandidate = selection.mode === "resolver" ? selected[0] : null;
        const technicalRows = selected.map(item => {
            const summary = [
                item.kind?.toUpperCase(),
                item.extension?.toUpperCase(),
                item.codec,
                item.sourceDomain,
                technicalUrl(item.url)
            ].filter(Boolean).join(" · ");
            return `<div class="bridge-technical-row">${escapeHtml(summary)}</div>`;
        }).join("");
        const summaryText = selection.mode === "resolver"
            ? resolverCandidate?.resolver === "youtube"
                ? "所选画质将由本机软件解析、下载并合并音轨。"
                : "本机软件将从当前内容页面识别最佳可用媒体并完成下载、合并。"
            : selection.mode === "manifest" ? t("manifestInfo") : selection.mode === "tracks" && selected.length > 1 ? t("mergeInfo") : t("directInfo");
        const subtitles = group.subtitles.length ? `<div class="bridge-subtitle-list"><span class="bridge-field-label">${escapeHtml(t("subtitles"))}</span>${group.subtitles.map(item => `<label class="bridge-check-row"><input type="checkbox" data-subtitle-id="${escapeHtml(item.id)}" ${(selection.subtitleIds || []).includes(item.id) ? "checked" : ""}><span>${escapeHtml(item.language || item.label || item.name || item.extension.toUpperCase())}</span></label>`).join("")}</div>` : "";
        inspector.innerHTML = `
            <figure class="bridge-inspector-preview">
                ${mediaPreviewMarkup(group, selection, "bridge-inspector-media", `${group.title} · ${t("actualFrame")}`)}
                ${duration ? `<figcaption>${escapeHtml(duration)}</figcaption>` : ""}
            </figure>
            <h2 class="bridge-inspector-title" title="${escapeHtml(group.title)}">${escapeHtml(group.title)}</h2>
            <div class="bridge-inspector-meta"><span>${escapeHtml(source || t("currentPage"))}</span><span>·</span><span>${escapeHtml(logic.groupSummary(group, selection))}</span></div>
            ${fields.join("")}
            <div class="bridge-action-summary"><img class="bridge-info-icon" src="${escapeHtml(asset("icons/icon-16.png"))}" alt=""><span>${escapeHtml(summaryText)}</span></div>
            ${validation.ok ? "" : `<div id="bridgeSelectionError" class="bridge-field-error" role="alert">${escapeHtml(validation.message)}</div>`}
            <label class="bridge-field"><span class="bridge-field-label">${escapeHtml(t("filename"))}</span><input class="bridge-field-input" data-draft="outputName" maxlength="160" value="${escapeHtml(draft.outputName)}"></label>
            <details class="bridge-advanced">
                <summary>${escapeHtml(t("technicalInfo"))}</summary>
                <div class="bridge-advanced-body">
                    ${subtitles}
                    <div class="bridge-technical-list">${technicalRows}</div>
                    <div class="bridge-technical-actions">
                        <button class="bridge-small-button" data-candidate-action="copy">${escapeHtml(t("copyLink"))}</button>
                    </div>
                </div>
            </details>
            <div class="bridge-primary-actions">
                <button class="bridge-primary-button" data-action="create-plan" ${validation.ok && !state.busy ? "" : "disabled"}>${icon("icons/action-download.svg")}<span>${escapeHtml(t("downloadImport"))}</span></button>
                <button class="bridge-secondary-button" data-action="download-only" ${validation.ok && !state.busy ? "" : "disabled"}>${escapeHtml(t("downloadOnly"))}</button>
            </div>
            <p class="bridge-legal-note">${escapeHtml(t("legal"))}</p>`;
        for (const select of inspector.querySelectorAll("[data-selection]")) select.value = selection[select.dataset.selection] || "";
    }

    function selectedGroups() {
        return state.groups.filter(group => state.selectedGroupIds.has(group.id));
    }

    function renderBatchInspector(inspector) {
        const groups = selectedGroups();
        const validations = groups.map(group => logic.validateSelection(group, state.selections.get(group.id), { paired: state.paired, importToEagle: true }));
        const error = validations.find(result => !result.ok)?.message || "";
        inspector.innerHTML = `
            <h2 class="bridge-inspector-title">${escapeHtml(t("batchTitle"))}</h2>
            <div class="bridge-inspector-meta"><span>${escapeHtml(t("batchSelected", { count: groups.length }))}</span></div>
            <p class="bridge-batch-description">${escapeHtml(t("batchBody"))}</p>
            <div class="bridge-batch-selection-actions">
                <button class="bridge-small-button" data-batch-action="select-all">${escapeHtml(t("selectAll"))}</button>
                <button class="bridge-small-button" data-batch-action="invert">${escapeHtml(t("invert"))}</button>
                <button class="bridge-small-button" data-batch-action="copy" ${groups.length ? "" : "disabled"}>${escapeHtml(t("copySelected"))}</button>
            </div>
            <div class="bridge-batch-summary-list">${groups.length ? groups.slice(0, 5).map(group => `<div><span>${escapeHtml(group.title)}</span><small>${escapeHtml(logic.groupSummary(group, state.selections.get(group.id)))}</small></div>`).join("") : `<div class="bridge-batch-empty">${escapeHtml(t("batchSelected", { count: 0 }))}</div>`}${groups.length > 5 ? `<div class="bridge-batch-more">+${groups.length - 5}</div>` : ""}</div>
            <div class="bridge-action-summary"><img class="bridge-info-icon" src="${escapeHtml(asset("icons/icon-16.png"))}" alt=""><span>${escapeHtml(t("batchBody"))}</span></div>
            ${error ? `<div class="bridge-field-error" role="alert">${escapeHtml(error)}</div>` : ""}
            <div class="bridge-primary-actions">
                <button class="bridge-primary-button" data-batch-action="create-plans" ${groups.length && !error && !state.busy ? "" : "disabled"}>${icon("icons/action-download.svg")}<span>${escapeHtml(t("batchImport"))}</span></button>
                <button class="bridge-secondary-button" data-batch-action="download-only" ${groups.length && !error && !state.busy ? "" : "disabled"}>${escapeHtml(t("batchDownload"))}</button>
            </div>
            <p class="bridge-legal-note">${escapeHtml(t("legal"))}</p>`;
    }

    function renderTasks() {
        const panel = root.querySelector("#bridgeTasksPanel");
        if (!panel) return;
        const tasks = state.plans.map(plan => logic.taskView(plan));
        panel.innerHTML = `<div class="bridge-section-view">
            <div class="bridge-section-header"><div><h2>${escapeHtml(t("taskTitle"))}</h2><p>${escapeHtml(t("taskSubtitle"))}</p></div><div class="bridge-section-actions"><button class="bridge-small-button" data-action="refresh-tasks">${escapeHtml(t("refreshTasks"))}</button><button class="bridge-small-button bridge-danger-button" data-action="clear-tasks">${escapeHtml(t("clearTasks"))}</button></div></div>
            ${state.taskSyncError ? `<div class="bridge-sync-warning" role="status">${escapeHtml(state.taskSyncError)}</div>` : ""}
            <div class="bridge-task-list">${tasks.length ? tasks.map(task => `
                <article class="bridge-task-row" data-task-id="${escapeHtml(task.id)}">
                    <img class="bridge-task-thumb" src="${escapeHtml(taskThumbUrl(task))}" alt="" data-fallback="${escapeHtml(asset("icons/icon-128.png"))}">
                    <div class="bridge-task-copy">
                        <div class="bridge-task-name" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>
                        <div class="bridge-task-state"><span>${escapeHtml(task.statusLabel)}</span><span class="bridge-progress-track" aria-label="${escapeHtml(`${Math.round(task.progress)}%`)}"><span class="bridge-progress-value" style="width:${task.progress}%"></span></span><span>${Math.round(task.progress)}%</span></div>
                        <div class="bridge-task-meta"><span>${escapeHtml(t("processed", { current: task.processed, total: task.total }))}</span>${task.createdAt ? `<span>${escapeHtml(taskTime(task.createdAt))}</span>` : ""}</div>
                        ${task.detail ? `<div class="bridge-task-detail">${escapeHtml(task.detail)}</div>` : ""}
                        ${task.finalPath ? `<div class="bridge-task-path" title="${escapeHtml(task.finalPath)}">${escapeHtml(t("outputLocation", { path: task.finalPath }))}</div>` : ""}
                        ${task.error ? `<div class="bridge-task-error">${escapeHtml(task.error)}</div>` : ""}
                    </div>
                    <div class="bridge-task-actions">${task.canImportExisting ? `<button class="bridge-small-button bridge-import-existing" data-action="import-task" data-plan-id="${escapeHtml(task.id)}">${escapeHtml(t("importExisting"))}</button>` : ""}${task.canOpenOutput ? `<button class="bridge-small-button" data-action="open-task-folder" data-plan-id="${escapeHtml(task.id)}">${escapeHtml(t("openFolder"))}</button>` : ""}${task.canOpenSource ? `<button class="bridge-small-button" data-action="open-task-source" data-plan-id="${escapeHtml(task.id)}">${escapeHtml(t("openSource"))}</button>` : ""}${task.active ? `<button class="bridge-small-button" data-action="stop-task" data-plan-id="${escapeHtml(task.id)}">${escapeHtml(t("stop"))}</button>` : task.canRetry ? `<button class="bridge-small-button" data-action="retry-task" data-plan-id="${escapeHtml(task.id)}">${escapeHtml(t("retry"))}</button>` : ["import_failed", "failed_permanent", "needs_rebuild"].includes(task.status) ? `<button class="bridge-small-button" data-view="media">${escapeHtml(t("backToMedia"))}</button>` : ""}</div>
                </article>`).join("") : `<div class="bridge-empty-state"><h2>${escapeHtml(t("noTasks"))}</h2></div>`}</div>
        </div>`;
    }

    function discoveryToolButton(id, label, active = false, description = "") {
        return `<button class="bridge-tool-button" data-tool-action="${escapeHtml(id)}" data-active="${active}">
            <img src="${escapeHtml(asset("icons/action-search.svg"))}" alt=""><span><span class="bridge-tool-name">${escapeHtml(label)}</span><span class="bridge-tool-state">${escapeHtml(description || (active ? t("on") : t("off")))}</span></span>
        </button>`;
    }

    function renderSettings() {
        const menu = root.querySelector("#bridgeSettingsMenu");
        const button = root.querySelector("#bridgeSettingsButton");
        if (!menu || !button) return;
        button.setAttribute("aria-expanded", String(state.settingsOpen));
        menu.hidden = !state.settingsOpen;
        if (!state.settingsOpen) return;
        const s = state.toolState || {};
        menu.innerHTML = `
            <h2 class="bridge-settings-heading">${escapeHtml(t("settings"))}</h2>
            <p class="bridge-settings-domain">${escapeHtml(currentDomain() || t("currentPage"))}</p>
            ${state.paired ? "" : `<div class="bridge-pair-box"><p>${escapeHtml(t("pairBody"))}</p><div class="bridge-pair-controls"><input id="bridgePairCode" class="bridge-pair-input" inputmode="numeric" maxlength="6" placeholder="${escapeHtml(t("pairPlaceholder"))}"><button class="bridge-primary-button" data-action="pair">${escapeHtml(t("pair"))}</button></div></div>`}
            <label class="bridge-setting-row"><span>${escapeHtml(t("siteRule"))}</span><span class="bridge-switch"><input type="checkbox" data-setting="site" ${state.siteEnabled ? "checked" : ""} ${state.paired ? "" : "disabled"}></span></label>
            <div class="bridge-settings-actions">
                <button class="bridge-small-button" data-action="record-page" ${state.paired && state.siteEnabled ? "" : "disabled"}>${escapeHtml(t("recordPage"))}</button>
                <button class="bridge-small-button" data-action="ignore-next" ${state.paired ? "" : "disabled"}>${escapeHtml(t("ignoreNext"))}</button>
                <button class="bridge-small-button" data-tool-action="pause">${escapeHtml(t("pauseCapture"))}</button>
                <button class="bridge-small-button" data-action="open-window">${escapeHtml(t("openWindow"))}</button>
                <button class="bridge-small-button" data-action="clear-media">${escapeHtml(t("clearMedia"))}</button>
            </div>
            <div class="bridge-settings-advanced">
                <p>${escapeHtml(t("discoverBody"))}</p>
                <div class="bridge-tool-grid">
                    ${discoveryToolButton("script:search", t("deepSearch"), Boolean(s.search))}
                </div>
            </div>`;
    }

    function switchView(view) {
        if (!new Set(["media", "tasks"]).has(view)) return;
        state.view = view;
        root.querySelectorAll("[data-view][role='tab']").forEach(button => button.setAttribute("aria-selected", String(button.dataset.view === view)));
        for (const [name, id] of [["media", "bridgeMediaPanel"], ["tasks", "bridgeTasksPanel"]]) {
            const panel = root.querySelector(`#${id}`);
            if (panel) panel.hidden = name !== view;
        }
        if (view === "media") {
            renderSidebar();
            renderInspector();
            refreshCandidates().catch(() => undefined);
        }
        if (view === "tasks") renderTasks();
    }

    function rawItem(candidate, group = activeGroup(), selection = state.selections.get(group?.id)) {
        if (!candidate) return null;
        const raw = { ...(candidate.raw || {}) };
        delete raw.frameDataUrl;
        raw.downFileName ||= candidate.name || logic.defaultOutputName(group, selection);
        raw.parsing ||= candidate.kind === "hls" ? "m3u8" : candidate.kind === "dash" ? "mpd" : false;
        raw._size ||= candidate.size;
        if (candidate.kind === "hls" || candidate.kind === "dash") raw.preferredQuality = selection?.quality || "";
        if (candidate.kind === "resolver") {
            raw.resolver = candidate.resolver;
            raw.preferredQuality = selection?.quality || "";
        }
        return raw;
    }

    function selectedRawItemsForGroup(group) {
        const selection = state.selections.get(group?.id);
        return logic.selectedCandidates(group, selection).map(candidate => rawItem(candidate, group, selection)).filter(Boolean);
    }

    async function createPlanForGroup(group, importToEagle = true) {
        const selection = state.selections.get(group?.id);
        const validation = logic.validateSelection(group, selection, { paired: state.paired, importToEagle });
        if (!validation.ok) throw new Error(validation.message);
        const outputNameResult = logic.normalizeOutputName(
            state.drafts.get(group.id)?.outputName || logic.defaultOutputName(group, selection)
        );
        if (!outputNameResult.ok) throw new Error(outputNameResult.message || t("invalidOutputName"));
        const outputName = outputNameResult.value;
        state.drafts.set(group.id, {
            ...(state.drafts.get(group.id) || {}),
            outputName
        });
        const response = await send({
            eagleBridge: "createPlan",
            items: selectedRawItemsForGroup(group),
            options: {
                outputName,
                outputContainer: validation.outputContainer,
                importToEagle,
                deleteAfterImport: importToEagle
            }
        });
        if (!response?.ok) throw new Error(response?.error || t("connectionError"));
        const plan = {
            ...response.data,
            thumbnail_url: response.data?.thumbnail_url || group.thumbnailUrl || ""
        };
        const preview = thumbUrl(group);
        if (plan.id && /^data:image\/(?:jpeg|png|webp);base64,/i.test(String(preview || ""))) {
            state.taskPreviews.set(String(plan.id), preview);
        }
        return plan;
    }

    async function createPlan() {
        const group = activeGroup();
        const selection = state.selections.get(group?.id);
        const validation = logic.validateSelection(group, selection, { paired: state.paired, importToEagle: true });
        if (!validation.ok || state.busy) {
            showToast(validation.message || t("connectionError"), "error");
            return;
        }
        state.busy = true;
        renderInspector();
        try {
            const plan = await createPlanForGroup(group);
            state.plans = [plan, ...state.plans.filter(item => item.id !== plan.id)];
            showToast(t("taskStarted"));
            patchHeader();
            switchView("tasks");
            scheduleTaskPoll(500);
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        } finally {
            state.busy = false;
            renderInspector();
        }
    }

    async function downloadOnlyForGroup(group) {
        const selection = state.selections.get(group?.id);
        const validation = logic.validateSelection(group, selection, { paired: state.paired, importToEagle: false });
        const result = await logic.startValidatedTask(
            validation,
            () => createPlanForGroup(group, false)
        );
        if (!result.started) {
            showToast(result.error, "error");
            return null;
        }
        const plan = result.plan;
        state.plans = [plan, ...state.plans.filter(item => item.id !== plan.id)];
        patchHeader();
        switchView("tasks");
        scheduleTaskPoll(500);
        return plan;
    }

    async function downloadOnly() {
        const group = activeGroup();
        if (!group) return;
        if (state.busy) return;
        state.busy = true;
        renderInspector();
        try {
            const plan = await downloadOnlyForGroup(group);
            if (plan) showToast(t("downloadStarted"));
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        } finally {
            state.busy = false;
            renderInspector();
        }
    }

    function setBatchSelection(mode) {
        const selectable = state.groups.filter(group => !group.segmentOnly && !group.technicalOnly);
        if (mode === "select-all") state.selectedGroupIds = new Set(selectable.map(group => group.id));
        else if (mode === "invert") state.selectedGroupIds = new Set(selectable.filter(group => !state.selectedGroupIds.has(group.id)).map(group => group.id));
        renderSidebar();
        renderInspector();
    }

    async function bulkCreatePlans() {
        const groups = selectedGroups();
        if (!groups.length || state.busy) return;
        const invalid = groups.map(group => logic.validateSelection(group, state.selections.get(group.id), { paired: state.paired, importToEagle: true })).find(result => !result.ok);
        if (invalid) {
            showToast(invalid.message, "error");
            return;
        }
        state.busy = true;
        renderInspector();
        const plans = [];
        const failures = [];
        for (const group of groups) {
            try { plans.push(await createPlanForGroup(group)); }
            catch (error) { failures.push(error); }
        }
        state.busy = false;
        if (plans.length) {
            const ids = new Set(plans.map(plan => plan.id));
            state.plans = [...plans, ...state.plans.filter(plan => !ids.has(plan.id))];
            patchHeader();
            switchView("tasks");
            scheduleTaskPoll(500);
        } else renderInspector();
        if (failures.length) showToast(t("batchPartial", { count: plans.length }), "error", 4200);
        else showToast(t("taskStarted"));
    }

    async function bulkDownloadOnly() {
        const groups = selectedGroups();
        if (!groups.length) return;
        const invalid = groups.map(group => logic.validateSelection(group, state.selections.get(group.id), { paired: state.paired, importToEagle: false })).find(result => !result.ok);
        if (invalid) {
            showToast(invalid.message, "error");
            return;
        }
        state.busy = true;
        const plans = [];
        const failures = [];
        for (const group of groups) {
            try { plans.push(await createPlanForGroup(group, false)); }
            catch (error) { failures.push(error); }
        }
        state.busy = false;
        if (plans.length) {
            const ids = new Set(plans.map(plan => plan.id));
            state.plans = [...plans, ...state.plans.filter(plan => !ids.has(plan.id))];
            patchHeader();
            switchView("tasks");
            scheduleTaskPoll(500);
        } else renderInspector();
        if (failures.length) showToast(t("batchPartial", { count: plans.length }), "error", 4200);
        else showToast(t("downloadStarted"));
    }

    function bulkCopyLinks() {
        const urls = selectedGroups().flatMap(group => selectedRawItemsForGroup(group).map(item => item.url)).filter(Boolean);
        if (!urls.length) return;
        navigator.clipboard.writeText([...new Set(urls)].join("\n")).then(() => showToast(t("copied"))).catch(error => showToast(error.message, "error"));
    }

    function candidateAction(action) {
        const group = activeGroup();
        const selection = state.selections.get(group?.id);
        const selected = logic.selectedCandidates(group, selection);
        const first = selected[0];
        if (!first) return;
        if (action === "copy") {
            navigator.clipboard.writeText(first.url).then(() => showToast(t("copied"))).catch(error => showToast(error.message, "error"));
        }
    }

    async function runTool(action) {
        if (!action) return;
        try {
            if (action.startsWith("script:")) {
                const script = action.slice(7);
                const response = await send({ Message: "script", tabId: state.tab?.id, script: `${script}.js` });
                if (response === "error no exists") throw new Error(t("unavailable"));
            } else if (action === "pause") {
                await send({ Message: "enable" });
            }
            await refreshToolState();
            showToast(t("toolUpdated"));
            renderSettings();
        } catch (error) {
            showToast(error.message || error, "error");
        }
    }

    async function refreshTab() {
        const requestedTabId = Number(new URL(location.href).searchParams.get("tabId"));
        if (Number.isInteger(requestedTabId) && requestedTabId > 0) state.tab = await chrome.tabs.get(requestedTabId);
        else [state.tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    }

    async function refreshConnection() {
        state.connection = "checking";
        patchHeader();
        try {
            let auth = await send({ eagleBridge: "authState" });
            state.paired = Boolean(auth?.ok && auth.data?.paired);
            if (!state.paired) {
                const recovered = await send({ eagleBridge: "autoPair" });
                if (recovered?.ok && recovered.data?.paired) auth = recovered;
                state.paired = Boolean(auth?.ok && auth.data?.paired);
            }
            if (!state.paired) {
                state.connection = "needs_pairing";
                return;
            }
            const health = await send({ eagleBridge: "health" });
            if (!health?.ok) throw new Error(health?.error || t("connectionError"));
            state.connection = "paired";
        } catch (_error) {
            const auth = await send({ eagleBridge: "authState" }).catch(() => null);
            state.paired = Boolean(auth?.ok && auth.data?.paired);
            state.connection = state.paired ? "offline" : "needs_pairing";
        } finally {
            patchHeader();
        }
    }

    async function refreshCandidates() {
        const [all, previews] = await Promise.all([
            send({ Message: "getAllData" }).catch(() => ({})),
            send({ Message: "getMediaPreviews", tabId: state.tab?.id }).catch(() => ({}))
        ]);
        state.framePreviews = new Map(Object.entries(previews && typeof previews === "object" ? previews : {})
            .filter(([, value]) => /^data:image\/(?:jpeg|png|webp);base64,/i.test(String(value || ""))));
        const cache = all && typeof all === "object" && !Array.isArray(all) ? all : {};
        const currentId = String(state.tab?.id || "");
        state.candidates.current = Array.isArray(cache[currentId]) ? cache[currentId].slice(-400).map(item => ({ ...item, __scope: "current" })) : [];
        state.candidates.other = Object.entries(cache).flatMap(([tabId, items]) => tabId === currentId || !Array.isArray(items) ? [] : items.slice(-200).map(item => ({ ...item, __scope: "other" }))).slice(-600);
        rebuildGroups();
    }

    async function refreshPlans() {
        if (!state.paired) {
            state.plans = [];
            patchHeader();
            return;
        }
        try {
            const plans = await send({ eagleBridge: "plans" });
            if (!plans?.ok) throw new Error(plans?.error || t("connectionError"));
            state.plans = Array.isArray(plans.data) ? plans.data : [];
            state.connection = "paired";
            state.taskSyncError = "";
            await refreshTaskPreviews(state.plans);
            patchHeader();
            if (state.view === "tasks") renderTasks();
        } catch (error) {
            const auth = await send({ eagleBridge: "authState" }).catch(() => null);
            state.paired = Boolean(auth?.ok && auth.data?.paired);
            state.connection = state.paired ? "offline" : "needs_pairing";
            state.taskSyncError = state.paired ? t("syncInterrupted") : "";
            patchHeader();
            if (state.view === "tasks") renderTasks();
            throw error;
        }
    }

    async function refreshTaskPreviews(plans) {
        const targets = (Array.isArray(plans) ? plans : []).filter(plan => {
            const id = String(plan?.id || "");
            const previewPath = String(plan?.preview_path || plan?.previewPath || "");
            const failureKey = `${id}:${previewPath}`;
            return id && previewPath && !state.taskPreviews.has(id) && !state.taskPreviewFailures.has(failureKey);
        }).slice(0, 50);
        await Promise.all(targets.map(async plan => {
            const id = String(plan.id);
            const previewPath = String(plan.preview_path || plan.previewPath || "");
            const response = await send({ eagleBridge: "planPreview", planId: id }).catch(() => null);
            const dataUrl = response?.ok ? response.data?.dataUrl : "";
            if (/^data:image\/(?:jpeg|png|webp);base64,/i.test(String(dataUrl || ""))) {
                state.taskPreviews.set(id, dataUrl);
            } else {
                state.taskPreviewFailures.add(`${id}:${previewPath}`);
            }
        }));
    }

    async function refreshSite() {
        if (!state.paired || !currentDomain()) {
            state.siteEnabled = false;
            return;
        }
        const response = await send({ eagleBridge: "siteStatus", domain: currentDomain() });
        if (response?.ok) state.siteEnabled = Boolean(response.data?.enabled);
    }

    async function refreshToolState() {
        const response = await send({ Message: "getButtonState", tabId: state.tab?.id });
        state.toolState = response && typeof response === "object" ? response : {};
    }

    async function refreshAll() {
        root.setAttribute("aria-busy", "true");
        try {
            await refreshTab();
            patchHeader();
            // Prioritize the current media snapshot so opening the popup is
            // not held behind discovery recovery or a slow local health check.
            const candidates = refreshCandidates();
            const toolState = refreshToolState();
            const connection = refreshConnection();
            const discovery = send({ eagleBridge: "ensureDiscovery", tabId: state.tab?.id }).catch(() => undefined);
            await connection;
            await Promise.allSettled([candidates, toolState, discovery, refreshPlans(), refreshSite()]);
            renderSettings();
            if (state.view === "tasks") renderTasks();
            scheduleTaskPoll();
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        } finally {
            root.setAttribute("aria-busy", "false");
        }
    }

    function scheduleTaskPoll(delay = null) {
        clearTimeout(state.taskTimer);
        if (!state.paired) return;
        const active = logic.hasActiveTasks(state.plans);
        state.taskTimer = setTimeout(async () => {
            try { await refreshPlans(); } catch (_error) { /* keep the last visible task state */ }
            scheduleTaskPoll();
        }, delay ?? (active ? 1200 : state.view === "tasks" ? 2000 : 6000));
    }

    async function stopTask(planId) {
        try {
            const response = await send({ eagleBridge: "stopPlan", planId });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            showToast(t("stopped"));
            await refreshPlans();
        } catch (error) {
            showToast(error.message || error, "error");
        }
    }

    async function retryTask(planId) {
        try {
            const response = await send({ eagleBridge: "retryPlan", planId });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            showToast(t("taskStarted"));
            await refreshPlans();
            scheduleTaskPoll(500);
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        }
    }

    async function clearTasks() {
        if (!window.confirm(t("clearTasksConfirm"))) return;
        try {
            const response = await send({ eagleBridge: "clearPlans" });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            const removed = Number(response.data?.removed || 0);
            await refreshPlans();
            showToast(t("tasksCleared", { count: removed }));
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        }
    }

    async function openTaskFolder(planId) {
        try {
            const response = await send({ eagleBridge: "openPlanOutput", planId });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            showToast(t("folderOpened"));
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        }
    }

    async function openTaskSource(planId) {
        const task = state.plans.map(plan => logic.taskView(plan))
            .find(item => item.id === String(planId || ""));
        if (!task?.pageUrl) return;
        try {
            await chrome.tabs.create({ url: task.pageUrl });
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        }
    }

    async function importExistingTask(planId) {
        try {
            const response = await send({ eagleBridge: "importPlan", planId });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            showToast(t("importQueued"));
            await refreshPlans();
            scheduleTaskPoll(500);
        } catch (error) {
            showToast(error.message || error, "error", 4200);
        }
    }

    async function pair() {
        const code = root.querySelector("#bridgePairCode")?.value.trim() || "";
        if (!/^\d{6}$/.test(code)) {
            showToast(t("pairBody"), "error");
            return;
        }
        try {
            const response = await send({ eagleBridge: "pair", code });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            const health = await send({ eagleBridge: "health" });
            const auth = await send({ eagleBridge: "authState" });
            if (!health?.ok || !auth?.ok || !auth.data?.paired) {
                throw new Error(health?.error || auth?.error || t("connectionError"));
            }
            state.paired = true;
            state.connection = "paired";
            await Promise.allSettled([refreshSite(), refreshPlans()]);
            patchHeader();
            renderInspector();
            renderSettings();
            showToast(t("pairingDone"));
        } catch (error) {
            await refreshConnection().catch(() => {});
            renderInspector();
            renderSettings();
            showToast(error.message || error, "error", 4200);
        }
    }

    async function changeSite(checked) {
        const response = await send({ eagleBridge: "setSite", domain: currentDomain(), enabled: checked });
        if (!response?.ok) throw new Error(response?.error || t("connectionError"));
        state.siteEnabled = checked;
        showToast(t("siteUpdated"));
        renderSettings();
    }

    async function settingsAction(action) {
        if (action === "record-page" || action === "ignore-next") {
            const response = await send({ eagleBridge: action === "record-page" ? "manualSource" : "ignoreNext" });
            if (!response?.ok) throw new Error(response?.error || t("connectionError"));
            showToast(action === "record-page" ? t("pageRecorded") : t("nextIgnored"));
        } else if (action === "open-window") chrome.windows.create({
            url: chrome.runtime.getURL(`popup.html?tabId=${state.tab?.id || ""}`),
            type: "popup",
            width: 920,
            height: 680
        });
        else if (action === "clear-media") {
            if (!window.confirm(t("clearConfirm"))) return;
            await send({ Message: "clearData", tabId: state.tab?.id, type: true });
            await send({ Message: "ClearIcon", type: true, tabId: state.tab?.id });
            state.candidates.current = [];
            rebuildGroups();
            showToast(t("clearMedia"));
        }
    }

    root.addEventListener("click", event => {
        const view = event.target.closest("[data-view]")?.dataset.view;
        if (view) {
            switchView(view);
            return;
        }
        const groupButton = event.target.closest("[data-group-id]");
        if (groupButton) {
            if (state.batchMode) {
                const id = groupButton.dataset.groupId;
                const group = state.groups.find(candidateGroup => candidateGroup.id === id);
                if (!group || group.segmentOnly || group.technicalOnly) return;
                state.selectedGroupIds.has(id) ? state.selectedGroupIds.delete(id) : state.selectedGroupIds.add(id);
            } else state.activeGroupId = groupButton.dataset.groupId;
            renderSidebar();
            renderInspector();
            return;
        }
        const batchAction = event.target.closest("[data-batch-action]")?.dataset.batchAction;
        if (batchAction) {
            if (["select-all", "invert"].includes(batchAction)) setBatchSelection(batchAction);
            else if (batchAction === "copy") bulkCopyLinks();
            else if (batchAction === "create-plans") bulkCreatePlans();
            else if (batchAction === "download-only") bulkDownloadOnly();
            return;
        }
        const toolAction = event.target.closest("[data-tool-action]")?.dataset.toolAction;
        if (toolAction) {
            runTool(toolAction);
            return;
        }
        const candidate = event.target.closest("[data-candidate-action]")?.dataset.candidateAction;
        if (candidate) {
            candidateAction(candidate);
            return;
        }
        const action = event.target.closest("[data-action]")?.dataset.action;
        if (!action) return;
        if (action === "refresh") refreshAll();
        else if (action === "batch") {
            state.batchMode = !state.batchMode;
            state.filterOpen = false;
            renderFilter();
            renderSidebar();
            renderInspector();
        }
        else if (action === "settings") {
            state.settingsOpen = !state.settingsOpen;
            state.filterOpen = false;
            renderFilter();
            renderSettings();
        } else if (action === "filter") {
            state.filterOpen = !state.filterOpen;
            state.settingsOpen = false;
            renderSettings();
            renderFilter();
            root.querySelector("#bridgeSearch")?.focus();
        } else if (action === "create-plan") createPlan();
        else if (action === "download-only") downloadOnly();
        else if (action === "refresh-tasks") refreshPlans().catch(error => showToast(error.message, "error"));
        else if (action === "clear-tasks") clearTasks();
        else if (action === "stop-task") stopTask(event.target.closest("[data-plan-id]")?.dataset.planId);
        else if (action === "retry-task") retryTask(event.target.closest("[data-plan-id]")?.dataset.planId);
        else if (action === "import-task") importExistingTask(event.target.closest("[data-plan-id]")?.dataset.planId);
        else if (action === "open-task-folder") openTaskFolder(event.target.closest("[data-plan-id]")?.dataset.planId);
        else if (action === "open-task-source") openTaskSource(event.target.closest("[data-plan-id]")?.dataset.planId);
        else if (action === "pair") pair();
        else settingsAction(action).catch(error => showToast(error.message || error, "error"));
    });

    root.addEventListener("input", event => {
        if (event.target.id === "bridgeSearch") {
            state.search = event.target.value;
            rebuildGroups({ keepFilter: true });
        } else if (event.target.matches("[data-draft]")) {
            const group = activeGroup();
            const draft = state.drafts.get(group?.id) || {};
            draft[event.target.dataset.draft] = event.target.value;
            draft.outputNameTouched = true;
            state.drafts.set(group.id, draft);
        } else if (event.target.matches("[data-filter]")) {
            const key = event.target.dataset.filter;
            state.filters[key] = event.target.type === "checkbox" ? event.target.checked : event.target.value;
            state.filterError = key === "regex" && state.filters.regex && !logic.isSafeFilterRegex(state.filters.regex) ? t("unsafeRegex") : "";
            const error = root.querySelector("#bridgeFilterError");
            if (error) {
                error.textContent = state.filterError;
                error.hidden = !state.filterError;
            }
            rebuildGroups({ keepFilter: true });
        }
    });

    root.addEventListener("change", event => {
        if (event.target.name === "bridgeScope") {
            state.scope = event.target.value;
            rebuildGroups();
        } else if (event.target.matches("[data-filter]")) {
            const key = event.target.dataset.filter;
            state.filters[key] = event.target.type === "checkbox" ? event.target.checked : event.target.value;
            rebuildGroups({ keepFilter: true });
        } else if (event.target.matches("[data-batch-group]")) {
            const id = event.target.dataset.batchGroup;
            event.target.checked ? state.selectedGroupIds.add(id) : state.selectedGroupIds.delete(id);
            renderSidebar();
            renderInspector();
        } else if (event.target.matches("[data-selection]")) {
            const group = activeGroup();
            const selection = state.selections.get(group.id);
            selection[event.target.dataset.selection] = event.target.value;
            state.selections.set(group.id, selection);
            const draft = state.drafts.get(group.id);
            if (draft && !draft.outputNameTouched) draft.outputName = logic.defaultOutputName(group, selection);
            renderSidebar();
            renderInspector();
        } else if (event.target.matches("[data-subtitle-id]")) {
            const group = activeGroup();
            const selection = state.selections.get(group.id);
            const ids = new Set(selection.subtitleIds || []);
            event.target.checked ? ids.add(event.target.dataset.subtitleId) : ids.delete(event.target.dataset.subtitleId);
            selection.subtitleIds = [...ids];
        } else if (event.target.matches("[data-setting='site']")) {
            changeSite(event.target.checked).catch(error => {
                event.target.checked = !event.target.checked;
                showToast(error.message || error, "error");
            });
        }
    });

    root.addEventListener("error", event => {
        const video = event.target.closest?.("video[data-media-preview]");
        if (video) {
            video.hidden = true;
            const fallback = video.nextElementSibling;
            if (fallback?.classList.contains("bridge-preview-fallback")) fallback.hidden = false;
            return;
        }
        const image = event.target.closest?.("img[data-fallback]");
        if (!image || image.dataset.fallbackApplied) return;
        image.dataset.fallbackApplied = "true";
        image.src = image.dataset.fallback;
    }, true);

    root.addEventListener("loadedmetadata", event => {
        const video = event.target.closest?.("video[data-media-preview]");
        if (!video || video.dataset.seekApplied) return;
        video.dataset.seekApplied = "true";
        const duration = Number(video.duration);
        const target = Number.isFinite(duration) && duration > 0
            ? Math.min(1, Math.max(0.1, duration * 0.01))
            : 0.1;
        try { video.currentTime = target; } catch (_error) { /* First decoded frame remains usable. */ }
    }, true);

    root.addEventListener("loadeddata", event => {
        const video = event.target.closest?.("video[data-media-preview]");
        if (!video) return;
        video.dataset.ready = "true";
        const fallback = video.nextElementSibling;
        if (fallback?.classList.contains("bridge-preview-fallback")) fallback.hidden = true;
    }, true);

    document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        state.settingsOpen = false;
        state.filterOpen = false;
        renderSettings();
        renderFilter();
    });

    chrome.runtime.onMessage.addListener(message => {
        if (message?.Message !== "popupAddData") return;
        const data = message.data;
        if (!state.tab || Number(data?.tabId) !== Number(state.tab.id)) return;
        if (data?.frameDataUrl && data?.groupKey && /^data:image\/(?:jpeg|png|webp);base64,/i.test(data.frameDataUrl)) {
            state.framePreviews.set(String(data.groupKey), data.frameDataUrl);
        }
        const index = state.candidates.current.findIndex(item => String(item.requestId) === String(data.requestId));
        const item = { ...data, __scope: "current" };
        delete item.frameDataUrl;
        if (index >= 0) state.candidates.current[index] = item;
        else state.candidates.current.push(item);
        clearTimeout(state.candidateTimer);
        state.candidateTimer = setTimeout(() => rebuildGroups(), 120);
    });

    chrome.storage.onChanged.addListener(changes => {
        if (!changes.MediaData) return;
        clearTimeout(state.snapshotTimer);
        state.snapshotTimer = setTimeout(() => {
            refreshCandidates().catch(() => undefined);
        }, 100);
    });

    window.addEventListener("beforeunload", () => {
        clearTimeout(state.taskTimer);
        clearTimeout(state.candidateTimer);
        clearTimeout(state.snapshotTimer);
    });

    (async () => {
        initShell();
        await refreshAll();
    })().catch(error => {
        root.innerHTML = `<div class="bridge-empty-state"><h2>${escapeHtml(t("connectionError"))}</h2><p>${escapeHtml(error.message || error)}</p></div>`;
    });
})();
