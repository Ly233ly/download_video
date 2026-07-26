const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const presentation = require(path.join(root, "chrome-extension", "js", "eagle-bridge-candidate-logic.js"));
const ui = require(path.join(root, "chrome-extension", "js", "eagle-bridge-ui-logic.js"));

const douyinFrame = presentation.selectThumbnail({
    playing: ["https://p3-sign.douyinpic.com/egg-video-frame.webp"],
    metadata: ["https://lf1-cdn-tos.bytegoofy.com/obj/icon/favicon.ico"]
});
if (douyinFrame !== "https://p3-sign.douyinpic.com/egg-video-frame.webp") {
    throw new Error("Playing-video artwork must win over site metadata");
}

const embeddedPlayer = presentation.selectThumbnail({
    exact: ["javascript:alert(1)"],
    visible: ["https://i.vimeocdn.com/video/project-frame.jpg"],
    metadata: ["https://a5.behance.net/favicon.ico"]
});
if (embeddedPlayer !== "https://i.vimeocdn.com/video/project-frame.jpg") {
    throw new Error("Embedded-player artwork must be accepted without a site adapter");
}

const frame = "data:image/jpeg;base64," + "A".repeat(128);
if (presentation.safeFrameDataUrl(frame) !== frame) {
    throw new Error("A bounded JPEG captured from the playing video must be accepted as an in-memory preview");
}
if (presentation.safeFrameDataUrl("data:text/html;base64,PHNjcmlwdD4=") !== "") {
    throw new Error("Only image data URLs may be used as in-memory video frames");
}
if (presentation.stableVisualKey("https://player.vimeo.com/video/123?token=one", 2, 91.2)
    !== presentation.stableVisualKey("https://player.vimeo.com/video/123?token=two", 2, 91.4)) {
    throw new Error("Signed-query changes must not create a new player identity");
}

const instagramEfg = Buffer.from(JSON.stringify({
    vencode_tag: "ig-xpvds.clips.c2-C3.dash_r2evevp9-r1gen2vp9_q80",
    xpv_asset_id: "18421119973183903",
    duration_s: 10,
    bitrate: 296985
})).toString("base64");
const instagramFragmentUrl = `https://scontent-dfw5-2.cdninstagram.com/o1/v/t2/f2/m367/clip.mp4?efg=${encodeURIComponent(instagramEfg)}&token=signed&bytestart=886&byteend=173864`;
const reconstructedInstagram = presentation.reconstructByteRangeUrl(instagramFragmentUrl);
if (!reconstructedInstagram || reconstructedInstagram.start !== 886 || reconstructedInstagram.end !== 173864) {
    throw new Error("Paired bytestart/byteend values must be recognized as one fixed playback fragment");
}
if (/bytestart|byteend/i.test(reconstructedInstagram.url) || !reconstructedInstagram.url.includes("token=signed")) {
    throw new Error("Range reconstruction must remove only transport offsets and preserve signed media parameters");
}
const instagramMetadata = presentation.parseInstagramCdnMetadata(instagramFragmentUrl);
if (instagramMetadata?.groupKey !== "instagram:18421119973183903"
    || instagramMetadata?.role !== "video"
    || instagramMetadata?.duration !== 10
    || instagramMetadata?.bitrate !== 296985
    || instagramMetadata?.estimatedSize !== 371232) {
    throw new Error("Instagram CDN metadata must group qualities and estimate the complete track instead of reporting one fragment size");
}

const instagramPermalink = presentation.chooseContentPageUrl("https://www.instagram.com/", [
    "https://www.instagram.com/reels/audio/27606406132373961/",
    "https://www.instagram.com/p/Da9rBuVjAGK/liked_by/",
    "https://www.instagram.com/p/Da9rBuVjAGK/",
    "https://www.instagram.com/reels/Da9rBuVjAGK/"
]);
if (instagramPermalink !== "https://www.instagram.com/p/Da9rBuVjAGK") {
    throw new Error("A feed video must resolve to its stable content permalink, not the home feed or audio/liked-by pages");
}
if (presentation.chooseContentPageUrl("https://example.com/", []) !== "") {
    throw new Error("A generic feed without a stable content permalink must not be guessed");
}
const nearbyGridVideo = presentation.chooseNearbyContentPageUrl("https://example.com/videos/current", [
    [],
    ["https://example.com/videos/related?tracking=1"],
    ["https://example.com/videos/far-away"]
]);
if (nearbyGridVideo !== "https://example.com/videos/related") {
    throw new Error("The closest distinct content link must identify a related video card");
}
if (presentation.chooseNearbyContentPageUrl("https://example.com/videos/current", [[], []]) !== "https://example.com/videos/current") {
    throw new Error("A primary player without a nearer content link must keep the current work page");
}
if (presentation.chooseContentPageUrl("https://x.com/user/status/123?tracking=1", []) !== "https://x.com/user/status/123") {
    throw new Error("A single-content page may safely use its own canonical URL for desktop resolution");
}
const genericFeedTitle = presentation.selectContentTitle({
    headings: [],
    captions: [],
    lines: [
        "alan酱",
        "@alanshen144905",
        "·",
        "15小时",
        "我单方面宣布，Joy-Con 才是 Voice Coding 的最佳神器，没有之一。",
        "0:41 / 0:48",
        "18",
        "50",
        "351",
        "5.6万"
    ],
    imageAlts: ["alan酱的头像"],
    fallback: "主页 / X"
});
if (genericFeedTitle !== "我单方面宣布，Joy-Con 才是 Voice Coding 的最佳神器，没有之一。") {
    throw new Error(`A generic feed item must use its own meaningful caption instead of the tab title; got ${genericFeedTitle}`);
}
if (presentation.selectContentTitle({ lines: ["18", "0:41 / 0:48"], fallback: "主页 / X" }) !== "主页 / X") {
    throw new Error("Pure counters and player timestamps must not replace the page-title fallback");
}

const scheduledCallbacks = [];
let boundedScanCount = 0;
const boundedSchedule = presentation.createBoundedScheduler(
    () => { boundedScanCount += 1; },
    250,
    { setTimeout: callback => { scheduledCallbacks.push(callback); return scheduledCallbacks.length; } }
);
for (let index = 0; index < 100; index += 1) boundedSchedule();
if (scheduledCallbacks.length !== 1) {
    throw new Error("Continuous feed mutations must not postpone media discovery forever");
}
scheduledCallbacks.shift()();
if (boundedScanCount !== 1) throw new Error("The bounded discovery scheduler must run the queued scan");
boundedSchedule();
if (scheduledCallbacks.length !== 1) throw new Error("A new scan must be schedulable after the previous scan completes");

const keyedCallbacks = [];
const keyedRuns = [];
const scheduleByTab = presentation.createKeyedBoundedScheduler(
    tabId => { keyedRuns.push(tabId); },
    250,
    { setTimeout: callback => { keyedCallbacks.push(callback); return keyedCallbacks.length; } }
);
for (let index = 0; index < 400; index += 1) scheduleByTab(9);
scheduleByTab(10);
if (keyedCallbacks.length !== 2) {
    throw new Error("A media burst must schedule at most one expensive badge regroup per tab");
}
keyedCallbacks.splice(0).forEach(callback => callback());
if (keyedRuns.join(",") !== "9,10") {
    throw new Error(`Each tab must eventually refresh its badge once; got ${keyedRuns.join(",")}`);
}
scheduleByTab(9);
if (keyedCallbacks.length !== 1) {
    throw new Error("A tab badge must be schedulable again after its previous refresh completes");
}

const injectionCalls = [];
let discoveryMessageCount = 0;
const recoveredDiscoveryPromise = presentation.ensureContentDiscovery({
    tabs: {
        sendMessage: async (_tabId, message) => {
            discoveryMessageCount += 1;
            if (discoveryMessageCount === 1) throw new Error("Receiving end does not exist");
            return { ok: message.Message === "discoverPageResolvers" };
        }
    },
    scripting: {
        executeScript: async details => { injectionCalls.push(details); }
    }
}, { id: 42, url: "https://example.com/feed" }).then(recoveredDiscovery => {
    if (!recoveredDiscovery?.ready || !recoveredDiscovery?.injected || injectionCalls.length !== 1) {
        throw new Error("Opening the popup must recover discovery on a page left open across an extension reload");
    }
    if (injectionCalls[0]?.target?.tabId !== 42
        || injectionCalls[0]?.files?.join(",") !== "js/eagle-bridge-candidate-logic.js,js/content-script.js") {
        throw new Error("Recovery must inject only the active discovery scripts into the requested web tab");
    }
});
const alreadyReadyInjectionCalls = [];
const alreadyReadyDiscoveryPromise = presentation.ensureContentDiscovery({
    tabs: { sendMessage: async () => ({ ok: true }) },
    scripting: { executeScript: async details => { alreadyReadyInjectionCalls.push(details); } }
}, { id: 43, url: "https://example.com/feed/two" }).then(result => {
    if (!result?.ready || result?.injected || alreadyReadyInjectionCalls.length) {
        throw new Error("A responsive content script must be scanned without duplicate injection");
    }
});
const restrictedDiscoveryPromise = presentation.ensureContentDiscovery({
    tabs: { sendMessage: async () => { throw new Error("must not be called"); } },
    scripting: { executeScript: async () => { throw new Error("must not be called"); } }
}, { id: 44, url: "chrome://extensions" }).then(result => {
    if (result?.ready || result?.injected || result?.reason !== "unsupported_tab") {
        throw new Error("Restricted browser pages must never receive discovery injection");
    }
});
const genericPermalinkMatrix = [
    ["https://www.tiktok.com/@creator/video/7523401234567890123?lang=en", "https://www.tiktok.com/@creator/video/7523401234567890123"],
    ["https://www.reddit.com/r/videos/comments/abc123/a_title/?utm_source=share", "https://www.reddit.com/r/videos/comments/abc123/a_title"],
    ["https://www.facebook.com/watch/?v=123456789012345", "https://www.facebook.com/watch?v=123456789012345"],
    ["https://www.douyin.com/jingxuan?modal_id=7523401234567890123&from_page=feed", "https://www.douyin.com/video/7523401234567890123"],
    ["https://www.pinterest.com/pin/123456789012345678/", "https://www.pinterest.com/pin/123456789012345678"],
    ["https://www.instagram.com/stories/creator/12345678901234567/?utm_source=ig_story_item_share", "https://www.instagram.com/stories/creator/12345678901234567"]
];
for (const [input, expected] of genericPermalinkMatrix) {
    const actual = presentation.chooseContentPageUrl(input, []);
    if (actual !== expected) throw new Error(`Generic permalink matrix failed: ${input} -> ${actual}`);
}

const vimeoStructuredPage = presentation.chooseStructuredVideoPageUrl(
    "https://vimeo.com/746646949?fl=pl&fe=vl",
    {
        ogType: "video.other",
        twitterCard: "player",
        canonicalUrl: "https://vimeo.com/746646949",
        playerUrl: "https://player.vimeo.com/video/746646949?h=727f6a2632"
    }
);
if (vimeoStructuredPage !== "https://vimeo.com/746646949") {
    throw new Error(`Structured video metadata must expose the canonical Vimeo content page; got ${vimeoStructuredPage}`);
}
if (presentation.chooseStructuredVideoPageUrl("https://example.com/", {
    ogType: "website",
    twitterCard: "summary"
}) !== "") {
    throw new Error("A generic home page without explicit video metadata must not become a resolver candidate");
}

const liveDouyinPrimaryIndex = presentation.selectPrimaryPageVideo([
    {
        duration: 223.237007,
        currentTime: 114.837846,
        paused: true,
        readyState: 4,
        rect: { x: 0, y: 0, width: 1920, height: 808 }
    },
    {
        duration: 49.041,
        currentTime: 0,
        paused: true,
        readyState: 4,
        rect: { x: 0, y: 856, width: 1920, height: 808 }
    }
], { width: 1920, height: 808 });
if (liveDouyinPrimaryIndex !== 0) {
    throw new Error(`Douyin must select the visible 3:43 player instead of the offscreen 0:49 preload; got ${liveDouyinPrimaryIndex}`);
}

const douyinFeedItems = [
    {
        className: "NhEiLku8 video_7662692425235828009 sliderVideo",
        nickname: " @热话动漫 ",
        description: "这一集的瑞克，终于不像个疯子，像个外公 #动漫解说 展开"
    },
    {
        className: "NhEiLku8 video_7653805516250025262 sliderVideo",
        nickname: "@木板解说",
        description: "第7集：深度拆解瑞克和莫蒂 S6E4《夜晚家庭》 展开"
    }
].map(item => ({
    id: presentation.douyinVideoIdFromSignals([item.className]),
    title: presentation.douyinCandidateTitle(item.nickname, item.description)
}));
if (douyinFeedItems[0].id !== "7662692425235828009"
    || douyinFeedItems[1].id !== "7653805516250025262") {
    throw new Error("Each Douyin feed item must keep its own explicit video identity");
}
if (douyinFeedItems[0].title !== "@热话动漫 · 这一集的瑞克，终于不像个疯子，像个外公 #动漫解说"
    || douyinFeedItems[1].title !== "@木板解说 · 第7集：深度拆解瑞克和莫蒂 S6E4《夜晚家庭》") {
    throw new Error("Each Douyin feed item must use its own author and lower-left caption instead of the tab title");
}
if (new Set(douyinFeedItems.map(item => item.title)).size !== 2) {
    throw new Error("Different Douyin videos must never collapse to one tab title");
}

const douyinPlayers = [
    {
        id: "visible-45m",
        sources: ["https://v95-web-sz.douyinvod.com/current/video.mp4?token=one"],
        playing: true,
        score: 900,
        duration: 2713.034
    },
    {
        id: "preloaded-11m",
        sources: ["blob:https://www.douyin.com/preloaded"],
        playing: false,
        score: 0,
        duration: 708.18
    }
];
const signedDirectMatch = presentation.resolveVisualMatch(
    douyinPlayers,
    "https://v95-web-sz.douyinvod.com/current/video.mp4?token=two"
);
if (signedDirectMatch?.selected?.id !== "visible-45m" || signedDirectMatch.kind !== "exact") {
    throw new Error("A direct media request must match its player after signed-query normalization");
}
const preloadedRequest = presentation.resolveVisualMatch(
    douyinPlayers,
    "https://v95-web-sz.douyinvod.com/preloaded/other-video.mp4?token=hidden"
);
if (preloadedRequest?.selected || preloadedRequest?.kind !== "none") {
    throw new Error("An unmatched preload request must not inherit the visible player's frame, duration or identity");
}

const vimeoConfig = presentation.parseVimeoPlayerConfig(`window.playerConfig = ${JSON.stringify({
    video: {
        id: 1143783367,
        title: "Song of the Stars",
        width: 1920,
        height: 1080,
        duration: 103,
        thumbnail_url: "https://i.vimeocdn.com/video/frame.webp"
    },
    request: {
        files: {
            hls: {
                default_cdn: "fastly",
                separate_av: true,
                cdns: { fastly: { avc_url: "https://skyfire.vimeocdn.com/video/playlist.m3u8" } }
            },
            dash: {
                streams: [
                    { id: "v720", quality: "720p", fps: 24 },
                    { id: "v1080", quality: "1080p", fps: 24 },
                    { id: "v360", quality: "360p", fps: 24 }
                ]
            }
        }
    }
})}`);
if (vimeoConfig?.url !== "https://skyfire.vimeocdn.com/video/playlist.m3u8") {
    throw new Error("Vimeo player config must expose its complete HLS master instead of MP4 fragments");
}
if (vimeoConfig?.groupKey !== "vimeo:1143783367"
    || vimeoConfig?.availableQualities?.join(",") !== "1080p,720p,360p") {
    throw new Error("Vimeo quality catalog must be explicit, sorted and tied to one video identity");
}

const manyQualityConfig = presentation.parseVimeoPlayerConfig(`window.playerConfig = ${JSON.stringify({
    video: { id: 9988, title: "Eight qualities", width: 3840, height: 2160, duration: 60 },
    request: { files: {
        hls: { default_cdn: "one", cdns: { one: { avc_url: "https://vod.example/eight/master.m3u8" } } },
        dash: { streams: ["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"].map(quality => ({ quality })) }
    } }
})}`);
if (manyQualityConfig?.availableQualities?.join(",") !== "2160p,1440p,1080p,720p,480p,360p,240p,144p") {
    throw new Error("Quality catalogs must use every level advertised by the current video, not a fixed five-level list");
}

const hlsCatalog = presentation.parseManifestQualities(`#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=180000,RESOLUTION=256x144
144/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=480000,RESOLUTION=426x240
240/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360
360/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1300000,RESOLUTION=854x480
480/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1280x720
720/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4800000,RESOLUTION=1920x1080
1080/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=9000000,RESOLUTION=2560x1440
1440/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=18000000,RESOLUTION=3840x2160
2160/index.m3u8`, "m3u8");
if (hlsCatalog.join(",") !== "2160p,1440p,1080p,720p,480p,360p,240p,144p") {
    throw new Error("A generic HLS master must expose every resolution it actually advertises");
}

const dashCatalog = presentation.parseManifestQualities(`<MPD><Period><AdaptationSet mimeType="video/mp4">
<Representation id="one" width="7680" height="4320" />
<Representation id="two" width="3840" height="2160" />
<Representation id="three" width="1920" height="1080" />
</AdaptationSet></Period></MPD>`, "mpd");
if (dashCatalog.join(",") !== "4320p,2160p,1080p") {
    throw new Error("A generic DASH manifest must expose its own resolution count without a preset list");
}

const grouped = ui.groupCandidates([
    { tabId: 9, requestId: "v", url: "https://cdn.example/video.m4s", webUrl: "https://example.com/watch", role: "video", groupKey: "same-content", duration: 10 },
    { tabId: 9, requestId: "a", url: "https://cdn.example/audio.m4s", webUrl: "https://example.com/watch", role: "audio", groupKey: "same-content", duration: 10 }
]);
if (grouped.length !== 1) throw new Error("Toolbar count must use the same grouped-content model as the popup");

(async () => {
    await Promise.all([recoveredDiscoveryPromise, alreadyReadyDiscoveryPromise, restrictedDiscoveryPromise]);
    let ready = false;
    let snapshot = { init: true };
    setTimeout(() => {
        snapshot = { 9: [{ requestId: "ready" }] };
        ready = true;
    }, 25);
    const result = await presentation.waitForSnapshot(() => ready, () => snapshot, 500, 5);
    if (result[9]?.[0]?.requestId !== "ready") {
        throw new Error("Initial popup read returned before the restored media cache was ready");
    }
    console.log("Cross-site candidate presentation and startup snapshot OK");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
