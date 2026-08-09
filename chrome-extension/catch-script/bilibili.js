(function () {
    "use strict";
    const current = document.currentScript;
    const channel = new URL(current?.src || location.href).searchParams.get("channel") || "";
    if (!channel) return;

    const quality = {
        6: "240P", 16: "360P", 32: "480P", 64: "720P", 74: "720P60",
        80: "1080P", 112: "1080P+", 116: "1080P60", 120: "4K",
        125: "HDR", 126: "杜比视界", 127: "8K"
    };
    const audioQuality = {
        30216: "64K", 30232: "132K", 30280: "192K", 30250: "杜比全景声", 30251: "Hi-Res"
    };
    let lastFingerprint = "";

    function parseValue(value) {
        if (!value) return null;
        if (typeof value === "string") {
            try { return JSON.parse(value); } catch (_error) { return null; }
        }
        return typeof value === "object" ? value : null;
    }

    function absoluteUrl(value) {
        if (!value) return "";
        try { return new URL(String(value), location.href).href; } catch (_error) { return ""; }
    }

    function metaContent(selectors) {
        for (const selector of selectors) {
            const value = document.querySelector?.(selector)?.content;
            if (value) return String(value);
        }
        return "";
    }

    function assignedJson(text, marker) {
        const start = String(text || "").indexOf(marker);
        if (start < 0) return "";
        const source = String(text).slice(start + marker.length);
        let offset = 0;
        while (/\s/.test(source[offset] || "")) offset += 1;
        if (!["{", "["].includes(source[offset])) return "";
        const opening = source[offset];
        const closing = opening === "{" ? "}" : "]";
        let depth = 0;
        let quote = "";
        let escaped = false;
        for (let index = offset; index < source.length; index += 1) {
            const character = source[index];
            if (quote) {
                if (escaped) escaped = false;
                else if (character === "\\") escaped = true;
                else if (character === quote) quote = "";
                continue;
            }
            if (character === '"' || character === "'") {
                quote = character;
                continue;
            }
            if (character === opening) depth += 1;
            else if (character === closing && --depth === 0) return source.slice(offset, index + 1);
        }
        return "";
    }

    function pageMeta(playInfo) {
        const initial = parseValue(window.__INITIAL_STATE__) || {};
        const video = initial.videoData || initial.videoInfo || {};
        const data = playInfo?.data || playInfo?.result || playInfo || {};
        const pathBvid = new URL(location.href).pathname.match(/\/video\/([^/?#]+)/i)?.[1] || "";
        const bvid = video.bvid || initial.bvid || pathBvid || "video";
        const cid = video.cid || initial.cid || data.cid || "0";
        const title = video.title || metaContent(['meta[property="og:title"]', 'meta[name="title"]'])
            || document.title.replace(/_哔哩哔哩.*$/, "");
        const thumbnailUrl = absoluteUrl(video.pic || initial.pic || metaContent([
            'meta[property="og:image"]', 'meta[itemprop="image"]', 'meta[name="thumbnail"]'
        ]));
        return {
            title,
            thumbnailUrl,
            duration: Number(data.timelength || Number(video.duration || 0) * 1000 || 0) / 1000,
            groupKey: `${bvid}:${cid}`
        };
    }

    function collect(playInfo) {
        const parsed = parseValue(playInfo);
        const data = parsed?.data || parsed?.result || parsed;
        const dash = data?.dash;
        if (!dash || !Array.isArray(dash.video)) return [];
        const page = pageMeta(parsed);
        const streams = [];
        for (const item of dash.video || []) {
            const url = item.baseUrl || item.base_url || item.backupUrl?.[0] || item.backup_url?.[0];
            if (!url) continue;
            const bitrate = Number(item.bandwidth || 0);
            streams.push({
                url,
                role: "video",
                id: Number(item.id || 0),
                label: quality[item.id] || `${item.height || "?"}P`,
                mimeType: item.mimeType || item.mime_type || "video/mp4",
                extension: "m4s",
                codec: item.codecs || "",
                width: Number(item.width || 0),
                height: Number(item.height || 0),
                frameRate: String(item.frameRate || item.frame_rate || ""),
                bitrate,
                duration: page.duration,
                estimatedSize: page.duration && bitrate ? Math.round(page.duration * bitrate / 8) : 0,
                thumbnailUrl: page.thumbnailUrl,
                groupKey: page.groupKey,
                drm: Boolean(item.pssh || item.contentProtection)
            });
        }
        const audioEntries = [...(dash.audio || [])];
        if (dash.dolby?.audio) audioEntries.push(...(Array.isArray(dash.dolby.audio) ? dash.dolby.audio : [dash.dolby.audio]));
        if (dash.flac?.audio) audioEntries.push(dash.flac.audio);
        for (const item of audioEntries) {
            const url = item.baseUrl || item.base_url || item.backupUrl?.[0] || item.backup_url?.[0];
            if (!url) continue;
            const bitrate = Number(item.bandwidth || 0);
            streams.push({
                url,
                role: "audio",
                id: Number(item.id || 0),
                label: audioQuality[item.id] || `${Math.round(bitrate / 1000) || "?"}K`,
                mimeType: item.mimeType || item.mime_type || "audio/mp4",
                extension: "m4s",
                codec: item.codecs || "",
                bitrate,
                duration: page.duration,
                estimatedSize: page.duration && bitrate ? Math.round(page.duration * bitrate / 8) : 0,
                thumbnailUrl: page.thumbnailUrl,
                groupKey: page.groupKey,
                drm: Boolean(item.pssh || item.contentProtection)
            });
        }
        return streams;
    }

    function publish(value) {
        const streams = collect(value);
        if (!streams.length) return;
        const fingerprint = streams.map(item => `${item.role}:${item.id}:${item.url}`).join("|");
        if (fingerprint === lastFingerprint) return;
        lastFingerprint = fingerprint;
        window.postMessage({ source: "liudi-downloader-bilibili", channel, streams }, location.origin);
    }

    function scan() {
        publish(window.__playinfo__);
        publish(window.__PLAYINFO__);
        const scripts = document.querySelectorAll("script:not([data-download-transfer-scanned])");
        for (const script of scripts) {
            script.dataset.downloadTransferScanned = "1";
            const text = script.textContent || "";
            const marker = "window.__playinfo__=";
            const index = text.indexOf(marker);
            if (index < 0) continue;
            const candidate = assignedJson(text, marker);
            publish(candidate);
        }
    }

    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setInterval(scan, 1500);
})();
