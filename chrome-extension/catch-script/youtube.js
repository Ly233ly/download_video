(function () {
    "use strict";
    const current = document.currentScript;
    const channel = new URL(current?.src || location.href).searchParams.get("channel") || "";
    if (!channel || !/(^|\.)youtube\.com$/i.test(location.hostname)) return;

    const SOURCE = "liudi-downloader-youtube";
    let lastFingerprint = "";

    function parseValue(value) {
        if (!value) return null;
        if (typeof value === "string") {
            try { return JSON.parse(value); } catch (_error) { return null; }
        }
        return typeof value === "object" ? value : null;
    }

    function safeUrl(value) {
        if (typeof value !== "string" || !value.trim()) return "";
        try {
            const url = new URL(value, location.href);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "";
        } catch (_error) {
            return "";
        }
    }

    function mimeParts(value) {
        const source = String(value || "");
        const mimeType = source.split(";", 1)[0].trim().toLowerCase();
        const codec = source.match(/codecs\s*=\s*["']([^"']+)["']/i)?.[1] || "";
        const extension = mimeType === "video/webm" ? "webm"
            : mimeType === "audio/webm" ? "weba"
                : mimeType === "audio/mp4" ? "m4a"
                    : mimeType === "video/mp4" ? "mp4" : "";
        return { mimeType, codec, extension };
    }

    function largestThumbnail(details) {
        return [...(details?.thumbnail?.thumbnails || [])]
            .filter(item => safeUrl(item?.url))
            .sort((left, right) => Number(right?.width || 0) * Number(right?.height || 0)
                - Number(left?.width || 0) * Number(left?.height || 0))[0]?.url || "";
    }

    function directFormatUrl(format) {
        const direct = safeUrl(format?.url);
        if (direct) return direct;
        const cipher = new URLSearchParams(String(format?.signatureCipher || format?.cipher || ""));
        // An `s` value needs YouTube's current player signature transform.
        // Do not submit an undeciphered URL that the desktop cannot reproduce.
        if (cipher.get("s")) return "";
        const base = safeUrl(cipher.get("url"));
        if (!base) return "";
        const signature = cipher.get("sig") || cipher.get("signature");
        if (!signature) return base;
        const url = new URL(base);
        url.searchParams.set(cipher.get("sp") || "signature", signature);
        return url.href;
    }

    function collect(value) {
        const response = parseValue(value);
        const details = response?.videoDetails || {};
        const streaming = response?.streamingData || {};
        const videoId = String(details.videoId || new URL(location.href).searchParams.get("v") || "")
            .replace(/[^a-z0-9_-]/gi, "").slice(0, 32);
        if (!videoId) return [];
        const title = String(details.title || document.title || "YouTube").slice(0, 220);
        const duration = Math.max(0, Number(details.lengthSeconds || 0));
        const thumbnailUrl = safeUrl(largestThumbnail(details));
        const adaptive = Array.isArray(streaming.adaptiveFormats) ? streaming.adaptiveFormats : [];
        const progressive = Array.isArray(streaming.formats) ? streaming.formats : [];
        const directAdaptive = adaptive.filter(format => directFormatUrl(format));
        const catalogQualities = [...new Set(adaptive
            .filter(format => String(format?.mimeType || "").toLowerCase().startsWith("video/"))
            .map(format => Math.max(0, Number(format?.height || String(format?.qualityLabel || "").match(/(\d{2,5})p/i)?.[1] || 0)))
            .filter(height => height >= 100 && height <= 10000))]
            .sort((left, right) => right - left)
            .map(height => `${height}p`);
        // Current YouTube SABR responses expose a complete adaptive-format
        // catalog but intentionally omit reusable URLs. Keep the catalog as
        // one desktop-resolved choice instead of degrading the UI to the lone
        // progressive 360p fallback.
        if (!directAdaptive.length && catalogQualities.length > 1 && streaming.serverAbrStreamingUrl) {
            const canonical = new URL(location.href);
            canonical.search = videoId ? `?v=${encodeURIComponent(videoId)}` : "";
            canonical.hash = "";
            return [{
                url: canonical.href,
                role: "video",
                id: `resolver-${videoId}`,
                streamId: `resolver-${videoId}`,
                label: catalogQualities[0],
                mimeType: "video/mp4",
                extension: "mp4",
                codec: "",
                width: 0,
                height: Number(catalogQualities[0].replace(/p$/i, "")) || 0,
                frameRate: "",
                bitrate: 0,
                duration,
                estimatedSize: 0,
                thumbnailUrl,
                groupKey: `youtube:${videoId}`,
                title,
                availableQualities: catalogQualities,
                qualitySource: "youtube_player_catalog",
                resolver: "youtube",
                separateAv: true,
                drm: false
            }];
        }
        const formats = directAdaptive.length ? directAdaptive : progressive.filter(format => directFormatUrl(format));
        const streams = [];
        for (const format of formats.slice(0, 160)) {
            const url = directFormatUrl(format);
            const media = mimeParts(format.mimeType);
            const role = media.mimeType.startsWith("video/") ? "video"
                : media.mimeType.startsWith("audio/") ? "audio" : "";
            if (!url || !role || !media.extension) continue;
            const bitrate = Math.max(0, Number(format.bitrate || format.averageBitrate || 0));
            const contentLength = Math.max(0, Number(format.contentLength || 0));
            const height = Math.max(0, Number(format.height || 0));
            const audioLabel = bitrate ? `${Math.round(bitrate / 1000)}K` : "音频";
            streams.push({
                url,
                role,
                id: String(format.itag || `${role}-${height || bitrate}`),
                streamId: String(format.itag || `${role}-${height || bitrate}`),
                label: role === "video" ? String(format.qualityLabel || (height ? `${height}p` : "视频")) : audioLabel,
                mimeType: media.mimeType,
                extension: media.extension,
                codec: media.codec,
                width: Math.max(0, Number(format.width || 0)),
                height,
                frameRate: format.fps ? String(format.fps) : "",
                bitrate,
                duration,
                estimatedSize: contentLength || (duration && bitrate ? Math.round(duration * bitrate / 8) : 0),
                thumbnailUrl,
                groupKey: `youtube:${videoId}`,
                title,
                qualitySource: "player_catalog",
                separateAv: directAdaptive.length > 0,
                drm: false
            });
        }
        return streams;
    }

    function publish(value) {
        const streams = collect(value);
        if (!streams.length) return false;
        const fingerprint = streams.map(item => `${item.streamId}:${item.url}`).join("|");
        if (fingerprint === lastFingerprint) return true;
        lastFingerprint = fingerprint;
        window.postMessage({ source: SOURCE, channel, streams }, location.origin);
        return true;
    }

    function inspectPlayerResponse(response) {
        if (!response?.clone || !String(response.url || "").includes("/youtubei/v1/player")) return;
        response.clone().json().then(publish).catch(() => {});
    }

    const nativeFetch = window.fetch;
    if (typeof nativeFetch === "function") {
        window.fetch = function (...args) {
            const request = nativeFetch.apply(this, args);
            request.then(inspectPlayerResponse).catch(() => {});
            return request;
        };
    }

    if (typeof XMLHttpRequest === "undefined") {
        // Unit tests and restricted pages may not expose XHR.
    } else {
        const nativeOpen = XMLHttpRequest.prototype.open;
        const nativeSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function (method, url, ...args) {
            this.__downloadTransferYouTubePlayer = String(url || "").includes("/youtubei/v1/player");
            return nativeOpen.call(this, method, url, ...args);
        };
        XMLHttpRequest.prototype.send = function (...args) {
            if (this.__downloadTransferYouTubePlayer) {
                this.addEventListener("load", () => {
                    try {
                        publish(this.responseType === "json" ? this.response : this.responseText);
                    } catch (_error) {
                        // 非文本 XHR 响应不属于播放器 JSON，忽略即可。
                    }
                }, { once: true });
            }
            return nativeSend.apply(this, args);
        };
    }

    function scan() {
        return publish(window.ytInitialPlayerResponse)
            || publish(window.ytplayer?.config?.args?.player_response);
    }

    scan();
    window.addEventListener("yt-navigate-finish", scan, true);
    window.addEventListener("yt-page-data-updated", scan, true);
    document.addEventListener("readystatechange", scan, true);
    setInterval(scan, 1500);
})();
