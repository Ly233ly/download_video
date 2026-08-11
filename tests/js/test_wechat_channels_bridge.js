const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "..", "src", "idm_eagle_bridge", "assets", "wechat_channels_bridge.js"),
  "utf8",
);

function XMLHttpRequest() {}
XMLHttpRequest.prototype.open = function () {};
XMLHttpRequest.prototype.addEventListener = function () {};

const posted = [];
const context = {
  __DOWNLOAD_STATION_TEST__: true,
  console,
  document: { createElement() { return {}; } },
  fetch: (_url, options) => {
    const payload = JSON.parse(options.body);
    posted.push(payload);
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payload.action === "download"
        ? { action: "download", plan: { id: "plan-test", delivery: "local" } }
        : {}),
    });
  },
  globalThis: null,
  location: { href: "https://channels.weixin.qq.com/web/pages/feed?objectId=feed-1234" },
  clearTimeout,
  setTimeout,
  URL,
  window: { addEventListener() {} },
  XMLHttpRequest,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);

const api = context.__DOWNLOAD_STATION_WECHAT_TEST__;
assert(api, "test API should be exposed only in test mode");
assert(source.includes(".slides-item .click-box.op-item"));
assert(source.includes('action: "download"'));
assert(source.includes("variantId"));
assert(source.includes("download-station-wechat-control"));

const normalized = api.normalizeFeed({
  id: "feed-1234",
  objectDesc: {
    description: "每条内容自己的标题",
    media: [{
      url: "https://finder.video.qq.com/video.mp4?token=one",
      urlToken: "&extra=two",
      decodeKey: "123456789",
      width: 1920,
      height: 1080,
      videoPlayLen: 91,
      fileSize: 5000000,
      coverUrl: "https://finder.video.qq.com/cover.jpg",
      spec: [{
        fileFormat: "hd",
        width: 1920,
        height: 1080,
        durationMs: 91000,
        videoBitrate: 4000000,
      }],
    }],
  },
  contact: { nickname: "视频号作者", username: "author-id" },
});

assert.strictEqual(normalized.objectId, "feed-1234");
assert.strictEqual(normalized.title, "每条内容自己的标题");
assert.strictEqual(normalized.author, "视频号作者");
assert.strictEqual(normalized.media[0].height, 1080);
assert.strictEqual(normalized.media[0].decodeKey, "123456789");
assert.strictEqual(normalized.media[0].durationMs, 91000);
assert.strictEqual(normalized.media[0].specs[0].fileFormat, "hd");
assert(normalized.sourceUrl.includes("feed-1234"));
assert.strictEqual(api.normalizeFeed({ id: "no-media", objectDesc: { media: [] } }), null);

const flowTitle = api.normalizeFeed({
  id: "feed-flow",
  objectDesc: {
    flowCardDesc: { description: "卡片内容标题" },
    media: [{ url: "https://finder.video.qq.com/flow.mp4" }],
  },
});
assert.strictEqual(flowTitle.title, "卡片内容标题");

const richTitle = api.normalizeFeed({
  id: "feed-rich",
  objectDesc: {
    finderNewlifeDesc: { richTextTitle: "富文本内容标题" },
    media: [{ url: "https://finder.video.qq.com/rich.mp4" }],
  },
});
assert.strictEqual(richTitle.title, "富文本内容标题");

const clearMedia = api.mediaItem({ url: "https://finder.video.qq.com/clear.mp4", decodeKey: 0, videoPlayLen: 41 });
assert.strictEqual(clearMedia.decodeKey, "");
assert.strictEqual(clearMedia.durationMs, 41000);

assert.strictEqual(typeof context.__DOWNLOAD_STATION_WECHAT_OBSERVE__, "function");
context.__DOWNLOAD_STATION_WECHAT_OBSERVE__({ data: { object: [{
  id: "feed-internal-api",
  objectDesc: {
    description: "内部 API 返回的视频",
    media: [{ url: "https://finder.video.qq.com/internal.mp4", videoPlayLen: 15 }],
  },
}] } }, "finderGetCommentDetail");
assert(posted.some((item) => item.objectId === "feed-internal-api"));
assert.strictEqual(api.activeObjectId(), "feed-internal-api");

const currentVariant = api.selectDefaultVariant({
  variants: [
    { id: "hd", deliverySpec: "hd", quality: "1080p · hd" },
    { id: "current", deliverySpec: "", quality: "720p · 原始/最高" },
  ],
}, "https://finder.video.qq.com/video.mp4");
assert.strictEqual(currentVariant.id, "current");

const selectedVariant = api.selectDefaultVariant({
  variants: [
    { id: "hd", deliverySpec: "hd", quality: "1080p · hd" },
    { id: "current", deliverySpec: "", quality: "720p · 原始/最高" },
  ],
}, "https://finder.video.qq.com/video.mp4?X-snsvideoflag=hd");
assert.strictEqual(selectedVariant.id, "hd");

assert.strictEqual(
  api.downloadStartedMessage({ delivery: "local" }, "本机视频"),
  "Eagle 未连接，已改为下载到电脑并保留文件：本机视频",
);
assert.strictEqual(
  api.downloadStartedMessage({ delivery: "eagle" }, "归档视频"),
  "已开始下载并导入 Eagle：归档视频",
);
assert.strictEqual(
  api.downloadStartedMessage({}, "兼容旧版"),
  "已开始下载：兼容旧版",
);

// A late response for a preloaded next feed must never make the download
// control inside an ambiguous current slide submit that other feed.  This is
// the intermittent production shape: WeChat may expose a blob currentSrc and
// the visible overlay text may not contain the feed description.
context.location.href = "https://channels.weixin.qq.com/web/pages/feed";
const visibleFeed = api.normalizeFeed({
  id: "visible-feed",
  objectDesc: {
    description: "用户当前看见的视频",
    media: [{ url: "https://finder.video.qq.com/visible.mp4" }],
  },
});
const preloadedRaw = {
  id: "preloaded-feed",
  objectDesc: {
    description: "下一条预加载视频",
    media: [{ url: "https://finder.video.qq.com/preloaded.mp4" }],
  },
};
api.accept(visibleFeed);
api.scan({ data: { object: [preloadedRaw] } }, "goToNextFlowFeed");
assert.notStrictEqual(
  api.activeObjectId(),
  "preloaded-feed",
  "a next-feed response may be a preload and must not activate before playback",
);
api.setCandidate("visible-feed", {
  objectId: "visible-feed",
  variants: [{ id: "visible-original", deliverySpec: "", quality: "原始视频" }],
});
api.setCandidate("preloaded-feed", {
  objectId: "preloaded-feed",
  variants: [{ id: "preloaded-original", deliverySpec: "", quality: "原始视频" }],
});
const ambiguousSlide = {
  textContent: "当前播放画面没有接口返回的描述文本",
  querySelectorAll(selector) {
    return selector === "video"
      ? [{ currentSrc: "blob:https://channels.weixin.qq.com/current", src: "", querySelectorAll() { return []; } }]
      : [];
  },
};
const label = { textContent: "下载" };
const ambiguousTrigger = {
  style: {},
  closest(selector) { return selector === ".slides-item" ? ambiguousSlide : null; },
  querySelector(selector) { return selector === '[data-role="download-label"]' ? label : null; },
  setAttribute() {},
};
const toastNode = { style: {}, textContent: "", __downloadStationTimer: 0 };
context.document.getElementById = (id) => id === "download-station-wechat-toast" ? toastNode : null;
posted.length = 0;
api.requestDownload(ambiguousTrigger, "");
assert.strictEqual(
  posted.some((item) => item.action === "download"),
  false,
  "an ambiguous slide must not fall back to a different active/preloaded feed",
);
assert.strictEqual(toastNode.textContent, "未能确认当前视频，请先播放当前视频后重试");
clearTimeout(toastNode.__downloadStationTimer);

// The safety guard must not disable a strongly matched current slide.  Even
// with the neighbour already preloaded, the visible media URL owns the click.
ambiguousSlide.querySelectorAll = function (selector) {
  return selector === "video"
    ? [{ currentSrc: "https://finder.video.qq.com/visible.mp4?token=fresh", src: "", querySelectorAll() { return []; } }]
    : [];
};
posted.length = 0;
api.requestDownload(ambiguousTrigger, "");
const matchedDownload = posted.find((item) => item.action === "download");
assert(matchedDownload, "a strongly matched visible slide should still download");
assert.strictEqual(matchedDownload.objectId, "visible-feed");
assert.strictEqual(matchedDownload.variantId, "visible-original");

console.log("wechat channels bridge tests passed");
