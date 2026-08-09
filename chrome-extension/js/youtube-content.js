(function () {
    "use strict";
    if (window.top !== window) return;
    const channel = `liudi-downloader-${crypto.randomUUID()}`;
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL(`catch-script/youtube.js?channel=${encodeURIComponent(channel)}`);
    script.async = false;
    (document.documentElement || document.head).appendChild(script);
    script.addEventListener("load", () => script.remove(), { once: true });

    window.addEventListener("message", event => {
        if (event.source !== window || event.origin !== location.origin) return;
        const message = event.data;
        if (!message || message.channel !== channel || message.source !== "liudi-downloader-youtube") return;
        if (!Array.isArray(message.streams) || message.streams.length > 200) return;
        for (const stream of message.streams) {
            if (!stream || typeof stream.url !== "string" || !/^https?:\/\//i.test(stream.url)) continue;
            if (!['video', 'audio'].includes(stream.role)) continue;
            chrome.runtime.sendMessage({
                Message: "addMedia",
                url: stream.url,
                href: location.href,
                extraExt: stream.extension,
                mime: stream.mimeType,
                requestId: `youtube-${stream.groupKey}-${stream.role}-${stream.streamId}-${stream.bitrate}`,
                requestHeaders: {
                    referer: location.href,
                    origin: "https://www.youtube.com",
                    "user-agent": navigator.userAgent
                },
                mediaMeta: stream
            }, () => { void chrome.runtime.lastError; });
        }
    });
})();
