"use strict";

(() => {
  const now = Date.now() / 1000;
  const fixtureParams = new URLSearchParams(location.search);
  const eagleAvailable = fixtureParams.get("eagle") !== "0";
  const desktopAvailable = fixtureParams.get("desktop") !== "0";
  const candidates = [
    {
      requestId: "video-1080",
      tabId: 77,
      url: "https://media.example/video-1080.m4s?token=visual-fixture",
      webUrl: "https://www.bilibili.com/video/BV1visual",
      title: "东京夜景延时摄影 - 哔哩哔哩",
      ext: "m4s",
      type: "video/mp4",
      role: "video",
      label: "1080P",
      codec: "avc1.640028",
      width: 1920,
      height: 1080,
      duration: 184,
      groupKey: "BV1visual:main",
      estimatedSize: 734003200
    },
    {
      requestId: "video-720",
      tabId: 77,
      url: "https://media.example/video-720.m4s?token=visual-fixture",
      webUrl: "https://www.bilibili.com/video/BV1visual",
      title: "东京夜景延时摄影 - 哔哩哔哩",
      ext: "m4s",
      type: "video/mp4",
      role: "video",
      label: "720P",
      codec: "avc1.64001f",
      width: 1280,
      height: 720,
      duration: 184,
      groupKey: "BV1visual:main",
      estimatedSize: 419430400
    },
    {
      requestId: "audio-192",
      tabId: 77,
      url: "https://media.example/audio-192.m4a?token=visual-fixture",
      webUrl: "https://www.bilibili.com/video/BV1visual",
      title: "东京夜景延时摄影 - 哔哩哔哩",
      ext: "m4a",
      type: "audio/mp4",
      role: "audio",
      label: "192K",
      codec: "mp4a.40.2",
      bitrate: 192000,
      duration: 184,
      groupKey: "BV1visual:main",
      estimatedSize: 12582912
    },
    {
      requestId: "second-video",
      tabId: 77,
      url: "https://cdn.example.net/city-walk.mp4",
      webUrl: "https://www.bilibili.com/video/BV1visual",
      title: "城市漫游纪录片",
      ext: "mp4",
      type: "video/mp4",
      role: "video",
      label: "720P",
      codec: "avc1.4d401f",
      width: 1280,
      height: 720,
      duration: 96,
      groupKey: "city-walk:main",
      estimatedSize: 188743680
    }
  ];

  if (fixtureParams.get("many") === "1") {
    for (let index = 3; index <= 18; index += 1) {
      candidates.push({
        requestId: `visual-video-${index}`,
        tabId: 77,
        url: `https://cdn.example.net/visual-video-${index}.mp4`,
        webUrl: "https://www.bilibili.com/video/BV1visual",
        title: `候选视频 ${String(index).padStart(2, "0")}`,
        ext: "mp4",
        type: "video/mp4",
        role: "video",
        label: "720P",
        codec: "avc1.4d401f",
        width: 1280,
        height: 720,
        duration: 90 + index,
        groupKey: `visual-video-${index}`,
        estimatedSize: 100 * 1024 * 1024 + index
      });
    }
  }

  const plans = [
    {
      id: "plan-active",
      title: "东京夜景延时摄影",
      output_name: "东京夜景延时摄影.mkv",
      status: "downloading",
      progress: 68,
      downloaded_bytes: 734003200,
      total_bytes: 1073741824,
      phase_detail: "正在下载视频流 2/3",
      page_url: "https://www.bilibili.com/video/BV1visual",
      updated_at: now
    },
    {
      id: "plan-complete",
      title: "产品发布会完整回放",
      output_name: "产品发布会完整回放.mp4",
      status: "completed_local",
      progress: 100,
      downloaded_bytes: 823132160,
      total_bytes: 823132160,
      phase_detail: "已下载到本机",
      page_url: "https://example.com/product-launch",
      final_path: "C:\\Downloads\\产品发布会完整回放.mp4",
      updated_at: now - 420
    },
    {
      id: "plan-failed",
      title: "城市漫游纪录片",
      output_name: "城市漫游纪录片.mp4",
      status: "retry",
      progress: 41,
      downloaded_bytes: 283115520,
      total_bytes: 692060160,
      phase_detail: "来源临时不可用，可稍后重试",
      page_url: "https://video.example.net/watch/urban-walk",
      updated_at: now - 900
    }
  ];

  function responseFor(payload) {
    if (payload?.Message === "getAllData") return { "77": candidates };
    if (payload?.Message === "getMediaPreviews") return {};
    if (payload?.Message === "getButtonState") return {};
    if (payload?.eagleBridge === "authState") {
      return { ok: true, data: { paired: true } };
    }
    if (payload?.eagleBridge === "autoPair") {
      return { ok: true, data: { paired: true, serviceReachable: desktopAvailable } };
    }
    if (payload?.eagleBridge === "health") return desktopAvailable
      ? { ok: true, data: { eagleAvailable } }
      : { ok: false, error: "fixture desktop offline" };
    if (payload?.eagleBridge === "plans") return desktopAvailable
      ? { ok: true, data: plans }
      : { ok: false, error: "fixture desktop offline" };
    if (payload?.eagleBridge === "siteStatus") return { ok: true, data: { enabled: true } };
    if (payload?.eagleBridge === "ensureDiscovery") return { ok: true };
    if (payload?.eagleBridge === "planPreview") return { ok: true, data: { dataUrl: "" } };
    return { ok: true, data: {} };
  }

  window.chrome = {
    i18n: { getUILanguage: () => "zh-CN" },
    runtime: {
      lastError: null,
      getURL: path => new URL(`/chrome-extension/${path}`, location.origin).href,
      sendMessage(payload, callback) {
        queueMicrotask(() => callback(responseFor(payload)));
      },
      onMessage: { addListener() {} }
    },
    storage: { onChanged: { addListener() {} } },
    tabs: {
      async query() {
        return [{
          id: 77,
          title: "东京夜景延时摄影 - 哔哩哔哩",
          url: "https://www.bilibili.com/video/BV1visual"
        }];
      },
      async get() {
        return (await this.query())[0];
      },
      async create() {}
    },
    windows: { async create() {} }
  };
})();
