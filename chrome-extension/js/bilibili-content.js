(function () {
    "use strict";
    if (window.top !== window) return;
    const channel = `liudi-downloader-${crypto.randomUUID()}`;
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL(`catch-script/bilibili.js?channel=${encodeURIComponent(channel)}`);
    script.async = false;
    (document.documentElement || document.head).appendChild(script);
    script.addEventListener("load", () => script.remove(), { once: true });

    window.addEventListener("message", event => {
        if (event.source !== window || event.origin !== location.origin) return;
        const message = event.data;
        if (!message || message.channel !== channel || message.source !== "liudi-downloader-bilibili") return;
        if (!Array.isArray(message.streams) || message.streams.length > 200) return;
        for (const stream of message.streams) {
            if (!stream || typeof stream.url !== "string" || !stream.url.startsWith("http")) continue;
            chrome.runtime.sendMessage({
                Message: "addMedia",
                url: stream.url,
                href: location.href,
                extraExt: stream.extension || "m4s",
                mime: stream.mimeType,
                requestId: `bilibili-${stream.groupKey}-${stream.role}-${stream.id}-${stream.bitrate}`,
                requestHeaders: {
                    referer: location.href,
                    origin: "https://www.bilibili.com",
                    "user-agent": navigator.userAgent
                },
                mediaMeta: stream
            });
        }
    });
})();
