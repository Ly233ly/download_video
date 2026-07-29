(function () {
    var _framePreviewCache = new Map();

    function absoluteImageUrl(value) {
        try {
            const url = new URL(String(value || ""), location.href);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "";
        } catch (_error) {
            return "";
        }
    }

    function elementScore(element) {
        const rect = element.getBoundingClientRect();
        const width = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0));
        const height = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
        const visibleArea = width * height;
        const style = getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return 0;
        return visibleArea || Math.max(0, rect.width * rect.height * 0.05);
    }

    function videoSources(video) {
        return [video.currentSrc, video.src, ...Array.from(video.querySelectorAll("source"), source => source.src)]
            .map(value => {
                try { return new URL(value, location.href).href; } catch (_error) { return ""; }
            })
            .filter(Boolean);
    }

    function videoArtwork(video) {
        return absoluteImageUrl(video.poster || video.getAttribute("poster"));
    }

    function backgroundArtwork(element) {
        for (let current = element; current && current !== document.documentElement; current = current.parentElement) {
            const value = getComputedStyle(current).backgroundImage || "";
            const match = value.match(/url\((?:["']?)(https?:[^"')]+)(?:["']?)\)/i);
            if (match) return absoluteImageUrl(match[1]);
        }
        return "";
    }

    function metadataArtwork() {
        const values = Array.from(document.querySelectorAll(
            'meta[property="og:image"], meta[property="og:image:secure_url"], meta[name="twitter:image"], meta[itemprop="thumbnailUrl"], link[rel="image_src"]'
        ), element => element.content || element.href || "");
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
            try {
                const parsed = JSON.parse(script.textContent || "null");
                const records = Array.isArray(parsed) ? parsed : [parsed];
                for (const record of records) {
                    const thumbnail = record?.thumbnailUrl || record?.thumbnail?.contentUrl;
                    if (Array.isArray(thumbnail)) values.push(...thumbnail);
                    else if (thumbnail) values.push(thumbnail);
                }
            } catch (_error) { /* Ignore unrelated or malformed JSON-LD. */ }
        }
        return values.map(absoluteImageUrl).filter(Boolean);
    }

    function metadataContent(selector) {
        const element = document.querySelector(selector);
        return String(element?.getAttribute?.("content") || element?.getAttribute?.("href") || "").trim();
    }

    function discoverStructuredPageResolver(logic) {
        const pageUrl = logic?.chooseStructuredVideoPageUrl?.(location.href, {
            ogType: metadataContent('meta[property="og:type"]'),
            twitterCard: metadataContent('meta[name="twitter:card"]'),
            canonicalUrl: metadataContent('meta[property="og:url"], link[rel="canonical"]'),
            playerUrl: metadataContent('meta[name="twitter:player"]'),
            videoUrl: metadataContent('meta[property="og:video"], meta[property="og:video:url"], meta[property="og:video:secure_url"]')
        }) || "";
        if (!pageUrl || _pageResolverSent.has(pageUrl)) return false;
        const duration = Number(metadataContent('meta[property="video:duration"], meta[property="og:video:duration"]')) || 0;
        const width = Number(metadataContent('meta[property="og:video:width"]')) || 0;
        const height = Number(metadataContent('meta[property="og:video:height"]')) || 0;
        const groupKey = `page:${logic.stableVisualKey(pageUrl, 0, duration)}`;
        const title = metadataContent('meta[property="og:title"], meta[name="twitter:title"]')
            || String(document.title || "网页视频").slice(0, 220);
        const thumbnailUrl = absoluteImageUrl(metadataContent(
            'meta[property="og:image"], meta[property="og:image:secure_url"], meta[name="twitter:image"]'
        ));
        _pageResolverSent.add(pageUrl);
        chrome.runtime.sendMessage({
            Message: "addMedia",
            url: pageUrl,
            href: location.href,
            extraExt: "mp4",
            mime: "video/mp4",
            requestId: `page-resolver-metadata-${groupKey}`,
            requestHeaders: {
                referer: location.href,
                origin: location.origin,
                "user-agent": navigator.userAgent
            },
            mediaMeta: {
                resolver: "page",
                role: "video",
                streamId: groupKey,
                title: title.slice(0, 220),
                label: "页面视频 · 最佳可用",
                width,
                height,
                duration,
                thumbnailUrl,
                groupKey,
                qualitySource: "structured_page_metadata",
                separateAv: true,
                drm: false
            }
        }, () => { void chrome.runtime.lastError; });
        return true;
    }

    function captureVideoFrame(video) {
        const logic = globalThis.EagleBridgeCandidateLogic;
        if (!logic || !video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return "";
        try {
            const scale = Math.min(1, 360 / video.videoWidth, 202 / video.videoHeight);
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
            canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
            const context = canvas.getContext("2d", { alpha: false });
            if (!context) return "";
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            return logic.safeFrameDataUrl(canvas.toDataURL("image/jpeg", 0.72));
        } catch (_error) {
            // Cross-origin players can taint a canvas. Poster/metadata remains
            // available, but a generic website icon must never pretend to be
            // a frame from the video.
            return "";
        }
    }

    function cachedVideoFrame(video, groupKey) {
        if (!video || !groupKey) return "";
        const cached = _framePreviewCache.get(groupKey);
        if (cached && Date.now() - cached.capturedAt < 1500) return cached.dataUrl;
        const dataUrl = captureVideoFrame(video);
        if (dataUrl) {
            _framePreviewCache.set(groupKey, { dataUrl, capturedAt: Date.now() });
            if (_framePreviewCache.size > 8) {
                const oldest = [..._framePreviewCache.entries()].sort((left, right) => left[1].capturedAt - right[1].capturedAt)[0];
                if (oldest) _framePreviewCache.delete(oldest[0]);
            }
        }
        return dataUrl;
    }

    function collectMediaVisualContext(mediaUrl) {
        const logic = globalThis.EagleBridgeCandidateLogic;
        if (!logic) return { thumbnailUrl: "" };
        let target = "";
        try { target = new URL(String(mediaUrl || ""), location.href).href; } catch (_error) { /* keep empty */ }
        const videos = Array.from(document.querySelectorAll("video"))
            .map((video, ordinal) => ({
                video,
                ordinal,
                sources: videoSources(video),
                artwork: videoArtwork(video),
                score: elementScore(video),
                playing: !video.paused && !video.ended && video.readyState >= 2
            }))
            .sort((left, right) => (Number(right.playing) - Number(left.playing)) || right.score - left.score);
        const visualMatch = logic.resolveVisualMatch(videos, target);
        const exactVideos = visualMatch.matches;
        const selected = visualMatch.selected;
        const exact = exactVideos.map(item => item.artwork).filter(Boolean);
        const nearby = [];
        for (const item of exactVideos.slice(0, 3)) {
            const container = item.video.closest("figure, article, [role='dialog'], [class*='player'], [class*='video']") || item.video.parentElement;
            if (!container) continue;
            const images = Array.from(container.querySelectorAll("img"))
                .filter(image => Math.max(image.naturalWidth, image.width) >= 160 && Math.max(image.naturalHeight, image.height) >= 90)
                .sort((left, right) => elementScore(right) - elementScore(left));
            nearby.push(...images.map(image => absoluteImageUrl(image.currentSrc || image.src)).filter(Boolean));
        }
        const duration = Number(selected?.video?.duration);
        const selectedSource = selected?.sources?.[0] || selected?.video?.currentSrc || location.href;
        const selectedDouyinItem = selected?.video?.closest?.('[data-e2e="feed-item"]');
        const selectedDouyinRoot = selected?.video?.closest?.('[data-e2e="feed-active-video"], [data-e2e="feed-video"], [class*="video_"]');
        const selectedDouyinVideoId = logic.douyinVideoIdFromSignals?.([
            selectedDouyinRoot?.getAttribute?.("data-aweme-id"),
            selectedDouyinRoot?.getAttribute?.("data-video-id"),
            selectedDouyinRoot?.className,
            selectedDouyinItem?.getAttribute?.("data-aweme-id"),
            selectedDouyinItem?.getAttribute?.("data-video-id"),
            selectedDouyinRoot?.matches?.('[data-e2e="feed-active-video"]') ? location.href : ""
        ]) || "";
        const groupKey = selected
            ? (selectedDouyinVideoId ? `douyin:${selectedDouyinVideoId}` : logic.stableVisualKey(selectedSource, selected.ordinal, duration))
            : "";
        const rect = selected?.video?.getBoundingClientRect?.();
        const selectedContainer = selected?.video?.closest?.("article, [role='article'], [role='dialog'], figure")
            || selected?.video?.parentElement;
        const captureRect = rect && rect.width >= 48 && rect.height >= 27
            && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
            ? {
                x: Math.max(0, rect.left),
                y: Math.max(0, rect.top),
                width: Math.min(innerWidth, rect.right) - Math.max(0, rect.left),
                height: Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top),
                viewportWidth: innerWidth,
                viewportHeight: innerHeight
            }
            : null;
        return {
            thumbnailUrl: selected ? logic.selectThumbnail({ exact, nearby, metadata: metadataArtwork() }) : "",
            frameDataUrl: cachedVideoFrame(selected?.video, groupKey),
            groupKey,
            duration: Number.isFinite(duration) && duration > 0 ? duration : 0,
            width: Number(selected?.video?.videoWidth) || 0,
            height: Number(selected?.video?.videoHeight) || 0,
            title: selected ? pageResolverTitle(selected.video, selectedContainer) : "",
            captureRect,
            visualMatch: visualMatch.kind
        };
    }

    function embeddingFrameRect(frameUrl) {
        let target = "";
        try { target = new URL(String(frameUrl || ""), location.href).href; } catch (_error) { return null; }
        const frames = Array.from(document.querySelectorAll("iframe"));
        const exact = frames.find(frame => {
            try { return new URL(frame.src, location.href).href === target; } catch (_error) { return false; }
        });
        const sameDocument = exact || frames.find(frame => {
            try {
                const left = new URL(frame.src, location.href);
                const right = new URL(target);
                return left.origin === right.origin && left.pathname === right.pathname;
            } catch (_error) { return false; }
        });
        const rect = sameDocument?.getBoundingClientRect?.();
        if (!rect || rect.width < 48 || rect.height < 27) return null;
        return {
            x: Math.max(0, rect.left),
            y: Math.max(0, rect.top),
            width: Math.min(innerWidth, rect.right) - Math.max(0, rect.left),
            height: Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top),
            viewportWidth: innerWidth,
            viewportHeight: innerHeight
        };
    }

    var _structuredCatalogSent = new Set();
    var _structuredCatalogObserver = null;
    var _pageResolverSent = new Set();
    var _pageResolverSchedule = null;
    var _pageLocationTimer = null;
    var _pageLocationTracker = null;

    function discoverStructuredPlayerMedia() {
        if (location.hostname !== "player.vimeo.com") return false;
        const logic = globalThis.EagleBridgeCandidateLogic;
        if (!logic?.parseVimeoPlayerConfig) return false;
        const configScript = Array.from(document.scripts || [])
            .find(script => (script.textContent || "").includes("window.playerConfig"));
        const media = logic.parseVimeoPlayerConfig(configScript?.textContent || "");
        if (!media?.url || _structuredCatalogSent.has(media.url)) return Boolean(media?.url);
        const visual = collectMediaVisualContext(media.url);
        _structuredCatalogSent.add(media.url);
        chrome.runtime.sendMessage({
            Message: "addMedia",
            url: media.url,
            href: location.href,
            extraExt: media.extension,
            mime: media.mimeType,
            requestId: `vimeo-${media.groupKey}-hls`,
            requestHeaders: {
                referer: location.href,
                origin: location.origin,
                "user-agent": navigator.userAgent
            },
            mediaMeta: {
                label: media.label,
                width: media.width,
                height: media.height,
                duration: media.duration,
                thumbnailUrl: media.thumbnailUrl || visual.thumbnailUrl,
                groupKey: visual.groupKey || media.groupKey,
                availableQualities: media.availableQualities,
                qualitySource: "player_catalog",
                separateAv: media.separateAv
            }
        }, () => { void chrome.runtime.lastError; });
        return true;
    }

    function startStructuredPlayerDiscovery() {
        if (location.hostname !== "player.vimeo.com") return;
        if (discoverStructuredPlayerMedia()) return;
        if (_structuredCatalogObserver) return;
        const target = document.documentElement || document;
        _structuredCatalogObserver = new MutationObserver(() => {
            if (!discoverStructuredPlayerMedia()) return;
            _structuredCatalogObserver?.disconnect();
            _structuredCatalogObserver = null;
        });
        _structuredCatalogObserver.observe(target, { childList: true, subtree: true });
        setTimeout(() => {
            _structuredCatalogObserver?.disconnect();
            _structuredCatalogObserver = null;
            discoverStructuredPlayerMedia();
        }, 15000);
    }

    function pageResolverTitle(video, container) {
        if (/(^|\.)douyin\.com$/i.test(location.hostname)) {
            const item = video.closest('[data-e2e="feed-item"]');
            const root = video.closest('[data-e2e="feed-active-video"], [data-e2e="feed-video"], [class*="video_"]');
            const videoId = globalThis.EagleBridgeCandidateLogic.douyinVideoIdFromSignals?.([
                root?.getAttribute?.("data-aweme-id"), root?.getAttribute?.("data-video-id"), root?.className,
                item?.getAttribute?.("data-aweme-id"), item?.getAttribute?.("data-video-id"),
                root?.matches?.('[data-e2e="feed-active-video"]') ? location.href : ""
            ]) || "";
            const nickname = item?.querySelector?.('[data-e2e="feed-video-nickname"]')?.textContent || "";
            const description = item?.querySelector?.('[data-e2e="video-desc"]')?.textContent || "";
            return globalThis.EagleBridgeCandidateLogic.douyinCandidateTitle?.(nickname, description, videoId)
                || (videoId ? `抖音视频 ${videoId}` : "抖音视频");
        }
        const textValues = selector => Array.from(container?.querySelectorAll?.(selector) || [], element =>
            element.getAttribute?.("content") || element.getAttribute?.("aria-label") || element.textContent || ""
        ).slice(0, 24);
        const captions = textValues([
            "figcaption", "[itemprop='caption']", "[itemprop='description']",
            "[itemprop='headline']", "[aria-description]"
        ].join(","));
        const headings = textValues("h1, h2, h3, [role='heading'], [itemprop='name']");
        const lines = String(container?.innerText || container?.textContent || "")
            .split(/[\r\n]+/).map(value => value.trim()).filter(Boolean).slice(0, 60);
        const imageAlts = Array.from(container?.querySelectorAll?.("img[alt]") || [], image => image.getAttribute("alt") || "").slice(0, 12);
        return globalThis.EagleBridgeCandidateLogic.selectContentTitle?.({
            captions,
            headings,
            lines,
            imageAlts,
            fallback: document.title || "网页视频"
        }) || String(document.title || "网页视频").slice(0, 220);
    }

    function nearbyVideoContent(video, logic) {
        const currentPageUrl = logic.chooseContentPageUrl(location.href, []);
        let element = video;
        for (let depth = 0; element && depth < 16; depth += 1, element = element.parentElement) {
            const links = [];
            if (element.matches?.("a[href]") && element.href) links.push(element.href);
            links.push(...Array.from(element.querySelectorAll?.("a[href]") || [], link => link.href).slice(0, 64));
            const linkedPageUrl = logic.chooseNearbyContentPageUrl?.(location.href, [links]) || "";
            if (linkedPageUrl && linkedPageUrl !== currentPageUrl) {
                return {
                    container: element.matches?.("a[href]") ? element.parentElement || element : element,
                    pageUrl: linkedPageUrl
                };
            }
        }
        const container = video.closest("article, [role='article'], [role='dialog'], figure") || video.parentElement;
        return { container, pageUrl: currentPageUrl };
    }

    function discoverPageResolvers() {
        if (window.top !== window) return;
        const logic = globalThis.EagleBridgeCandidateLogic;
        if (!logic?.chooseContentPageUrl) return;
        const structuredHost = /(^|\.)(?:youtube\.com|bilibili\.com|player\.vimeo\.com)$/i.test(location.hostname);
        if (structuredHost) return;
        discoverStructuredPageResolver(logic);
        const videos = Array.from(document.querySelectorAll("video")).slice(0, 32);
        const douyinHost = /(^|\.)douyin\.com$/i.test(location.hostname);
        const douyinPrimaryIndex = douyinHost && logic.selectPrimaryPageVideo
            ? logic.selectPrimaryPageVideo(videos.map(video => {
                const rect = video.getBoundingClientRect();
                return {
                    duration: Number(video.duration) || 0,
                    currentTime: Number(video.currentTime) || 0,
                    paused: video.paused,
                    ended: video.ended,
                    readyState: video.readyState,
                    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                };
            }), { width: innerWidth, height: innerHeight })
            : -1;
        for (const [videoIndex, video] of videos.entries()) {
            const sources = videoSources(video);
            const hasDirectSource = sources.some(source => /^https?:\/\//i.test(source));
            const hasBlobSource = sources.some(source => source.startsWith("blob:"));
            if (!douyinHost && hasDirectSource) continue;
            if ((!hasBlobSource && !(douyinHost && hasDirectSource)) || video.readyState < 2) continue;
            const douyinItem = douyinHost ? video.closest('[data-e2e="feed-item"]') : null;
            const douyinRoot = douyinHost
                ? video.closest('[data-e2e="feed-active-video"], [data-e2e="feed-video"], [class*="video_"]')
                : null;
            const explicitDouyinVideoId = douyinHost && logic.douyinVideoIdFromSignals
                ? logic.douyinVideoIdFromSignals([
                    douyinRoot?.getAttribute?.("data-aweme-id"), douyinRoot?.getAttribute?.("data-video-id"), douyinRoot?.className,
                    douyinItem?.getAttribute?.("data-aweme-id"), douyinItem?.getAttribute?.("data-video-id"),
                    videoIndex === douyinPrimaryIndex ? location.href : ""
                ])
                : "";
            if (douyinHost && !explicitDouyinVideoId) continue;
            const content = douyinItem
                ? { container: douyinItem, pageUrl: "" }
                : nearbyVideoContent(video, logic);
            const container = content.container;
            const pageUrl = explicitDouyinVideoId
                ? `https://www.douyin.com/video/${explicitDouyinVideoId}`
                : content.pageUrl;
            if (!pageUrl || _pageResolverSent.has(pageUrl)) continue;
            const duration = Number(video.duration);
            const douyinVideoId = explicitDouyinVideoId || pageUrl.match(/\/video\/(\d+)$/)?.[1] || "";
            const groupKey = douyinVideoId
                ? `douyin:${douyinVideoId}`
                : `page:${logic.stableVisualKey(pageUrl, 0, duration)}`;
            const frameDataUrl = captureVideoFrame(video);
            const thumbnailUrl = videoArtwork(video) || backgroundArtwork(video);
            const directSource = hasDirectSource
                ? sources.find(source => /^https?:\/\//i.test(source)) || ""
                : "";
            const usesDirectDouyinStream = douyinHost && Boolean(directSource);
            const isCurrentDouyinVideo = douyinHost && videoIndex === douyinPrimaryIndex;
            _pageResolverSent.add(pageUrl);
            chrome.runtime.sendMessage({
                Message: "addMedia",
                url: usesDirectDouyinStream ? directSource : pageUrl,
                href: location.href,
                extraExt: "mp4",
                mime: "video/mp4",
                requestId: `${usesDirectDouyinStream ? "douyin-direct" : "page-resolver"}-${groupKey}`,
                requestHeaders: {
                    referer: location.href,
                    origin: location.origin,
                    "user-agent": navigator.userAgent
                },
                mediaMeta: {
                    resolver: usesDirectDouyinStream ? "" : "page",
                    role: "video",
                    streamId: groupKey,
                    title: pageResolverTitle(video, container),
                    label: usesDirectDouyinStream
                        ? `${Number(video.videoHeight) > 0 ? `${Number(video.videoHeight)}p · ` : ""}${isCurrentDouyinVideo ? "当前播放" : "页面已加载"}`
                        : `${isCurrentDouyinVideo ? "当前播放" : "页面已加载"} · 最佳可用`,
                    width: Number(video.videoWidth) || 0,
                    height: Number(video.videoHeight) || 0,
                    duration: Number.isFinite(duration) && duration > 0 ? duration : 0,
                    thumbnailUrl,
                    frameDataUrl,
                    groupKey,
                    qualitySource: usesDirectDouyinStream
                        ? (isCurrentDouyinVideo ? "douyin_current_player" : "douyin_feed_player")
                        : "desktop_page_resolver",
                    separateAv: !usesDirectDouyinStream,
                    drm: false
                }
            }, () => { void chrome.runtime.lastError; });
        }
    }

    function schedulePageResolverDiscovery() {
        const logic = globalThis.EagleBridgeCandidateLogic;
        if (!_pageResolverSchedule) {
            _pageResolverSchedule = logic?.createBoundedScheduler
                ? logic.createBoundedScheduler(discoverPageResolvers, 250)
                : (() => {
                    let pending = false;
                    return () => {
                        if (pending) return;
                        pending = true;
                        setTimeout(() => {
                            pending = false;
                            discoverPageResolvers();
                        }, 250);
                    };
                })();
        }
        _pageResolverSchedule();
    }

    function startPageResolverDiscovery() {
        if (window.top !== window) return;
        discoverPageResolvers();
        document.addEventListener("play", schedulePageResolverDiscovery, true);
        document.addEventListener("loadedmetadata", schedulePageResolverDiscovery, true);
        const observer = new MutationObserver(schedulePageResolverDiscovery);
        observer.observe(document.documentElement || document, { childList: true, subtree: true });
    }

    function resetPageDiscovery(nextUrl, _previousUrl, context = {}) {
        _framePreviewCache.clear();
        _structuredCatalogSent.clear();
        _pageResolverSent.clear();
        _structuredCatalogObserver?.disconnect();
        _structuredCatalogObserver = null;

        startStructuredPlayerDiscovery();
        if (window.top !== window) return;
        discoverPageResolvers();
        [250, 900, 1800].forEach(delay => {
            setTimeout(schedulePageResolverDiscovery, delay);
        });
        if (context.notifyBackground) {
            chrome.runtime.sendMessage({
                Message: "notifyPageLocationChanged",
                url: nextUrl
            }, () => { void chrome.runtime.lastError; });
        }
    }

    function initializePageLocationTracking() {
        if (window.top !== window || _pageLocationTracker) return;
        const logic = globalThis.EagleBridgeCandidateLogic;
        _pageLocationTracker = logic?.createLocationChangeTracker
            ? logic.createLocationChangeTracker(location.href, resetPageDiscovery)
            : (() => {
                let currentUrl = String(location.href || "");
                return (nextUrl, context) => {
                    const normalizedUrl = String(nextUrl || "");
                    if (!normalizedUrl || normalizedUrl === currentUrl) return false;
                    const previousUrl = currentUrl;
                    currentUrl = normalizedUrl;
                    resetPageDiscovery(normalizedUrl, previousUrl, context);
                    return true;
                };
            })();
        _pageLocationTimer = setInterval(() => {
            _pageLocationTracker(location.href, { notifyBackground: true });
        }, 750);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            startStructuredPlayerDiscovery();
            startPageResolverDiscovery();
            initializePageLocationTracking();
        }, { once: true });
    } else {
        startStructuredPlayerDiscovery();
        startPageResolverDiscovery();
        initializePageLocationTracking();
    }

    chrome.runtime.onMessage.addListener(function (Message, sender, sendResponse) {
        if (chrome.runtime.lastError) { return; }
        if (Message.Message == "getMediaVisualContext") {
            sendResponse({ ...collectMediaVisualContext(Message.url), frameUrl: location.href });
            return true;
        }
        if (Message.Message == "getEmbeddingFrameRect") {
            sendResponse(embeddingFrameRect(Message.frameUrl));
            return true;
        }
        if (Message.Message == "discoverPageResolvers") {
            discoverPageResolvers();
            sendResponse({ ok: true });
            return true;
        }
        if (Message.Message == "pageLocationChanged") {
            if (_pageLocationTracker) {
                _pageLocationTracker(Message.url || location.href, { notifyBackground: false });
            } else {
                resetPageDiscovery(Message.url || location.href, "", { notifyBackground: false });
            }
            sendResponse({ ok: true });
            return true;
        }
    });

    // Heart Beat
    var Port;
    function connect() {
        Port = chrome.runtime.connect(chrome.runtime.id, { name: "HeartBeat" });
        Port.postMessage("HeartBeat");
        Port.onMessage.addListener(function (message, Port) { return true; });
        Port.onDisconnect.addListener(connect);
    }
    connect();

    const sendAddMedia = (data) => {
        chrome.runtime.sendMessage({
            Message: "addMedia",
            url: data.url,
            href: data.href ?? location.href,
            extraExt: data.ext,
            mime: data.mime,
            requestHeaders: { referer: data.referer },
            requestId: data.requestId
        });
    };
    window.addEventListener("message", (event) => {
        const action = ["downloadTransferAddMedia"];
        if (!event.data || !event.data.action || event.origin !== window.location.origin || !action.includes(event.data.action)) { return; }
        event.stopPropagation();
        event.stopImmediatePropagation();

        if (event.data.action == "downloadTransferAddMedia") {
            if (!event.data.url) { return; }

            sendAddMedia(event.data);
        }

    }, { capture: true });
})();
