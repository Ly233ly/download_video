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
  document: {},
  fetch: (_url, options) => {
    posted.push(JSON.parse(options.body));
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
  },
  globalThis: null,
  location: { href: "https://channels.weixin.qq.com/web/pages/feed?objectId=feed-1234" },
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

console.log("wechat channels bridge tests passed");
