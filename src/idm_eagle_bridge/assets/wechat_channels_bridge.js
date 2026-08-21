(function () {
  "use strict";

  const SESSION = "__DOWNLOAD_STATION_SESSION__";
  const ENDPOINT = `/__download_station_wechat__/candidate?token=${SESSION}`;
  const MAX_SEEN = 500;
  const seen = new Map();
  const downloadsInFlight = new Set();
  const ACTIVE_DETAIL_METHODS = new Set([
    "finderGetCommentDetail",
  ]);
  const videoBindings = new WeakMap();
  let activeObjectId = "";
  let activeVersion = 0;
  let publishedActiveObjectId = "";
  let uiRefreshTimer = 0;
  let activeRefreshTimer = 0;
  let menuCloseTimer = 0;

  function text(value, maxLength) {
    return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
  }

  function firstText(values, maxLength) {
    for (const value of values) {
      const result = text(value, maxLength);
      if (result) return result;
    }
    return "";
  }

  function decodeKey(value) {
    if (typeof value === "bigint") return value > 0n ? value.toString() : "";
    if (typeof value === "number") {
      return Number.isSafeInteger(value) && value > 0 ? String(value) : "";
    }
    const result = text(value, 32);
    return /^(?:0[xX][0-9a-fA-F]+|[0-9]+)$/.test(result) && !/^0+$/.test(result)
      ? result
      : "";
  }

  function feedId(value) {
    const result = text(value, 128);
    return /^[A-Za-z0-9_-]{4,128}$/.test(result) ? result : "";
  }

  function mediaItem(value) {
    if (!value || typeof value !== "object") return null;
    const url = text(value.url || value.mediaUrl || value.playUrl, 8192);
    if (!/^https:\/\//i.test(url)) return null;
    const specs = Array.isArray(value.spec) ? value.spec.slice(0, 32).map((spec) => ({
      width: number(spec && spec.width),
      height: number(spec && spec.height),
      durationMs: number(spec && spec.durationMs),
      fileFormat: text(spec && spec.fileFormat, 64),
      bitrate: number(spec && (spec.videoBitrate || spec.bitRate)),
    })).filter((spec) => spec.fileFormat) : [];
    return {
      url,
      urlToken: text(value.urlToken, 8192),
      decodeKey: decodeKey(value.decodeKey),
      mediaType: number(value.mediaType),
      width: number(value.width),
      height: number(value.height),
      durationMs: number(value.durationMs) || number(value.videoPlayLen) * 1000,
      fileSize: number(value.fileSize),
      coverUrl: text(value.coverUrl || value.coverURL, 8192),
      specs,
    };
  }

  function normalizeFeed(value) {
    if (!value || typeof value !== "object") return null;
    const description = value.objectDesc || value.object_desc;
    const rawMedia = description && Array.isArray(description.media) ? description.media : value.media;
    if (!description || !Array.isArray(rawMedia)) return null;
    const objectId = feedId(value.id || value.objectId || value.objectid);
    if (!objectId) return null;
    const media = rawMedia.map(mediaItem).filter(Boolean);
    if (!media.length) return null;
    const contact = value.contact && typeof value.contact === "object" ? value.contact : {};
    const reportedSource = text(value.source_url || value.sourceUrl, 8192);
    const pageSource = location.href.includes(objectId) ? location.href : "";
    return {
      action: "candidate",
      objectId,
      nonceId: text(value.objectNonceId || value.nonceId, 256),
      title: firstText([
        description.description,
        description.flowCardDesc && description.flowCardDesc.description,
        description.finderNewlifeDesc && description.finderNewlifeDesc.richTextTitle,
        value.description,
      ], 500),
      author: text(contact.nickname || value.nickname, 160),
      authorId: text(contact.username || value.username, 160),
      authorAvatar: text(contact.headUrl || contact.avatarUrl, 8192),
      sourceUrl: reportedSource || pageSource,
      createdAt: number(value.createtime || value.createTime),
      media,
    };
  }

  function request(payload) {
    var body = JSON.stringify(payload);
    if (body.length > 500000) return Promise.reject(new Error("请求内容过大"));
    return fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body,
      credentials: "same-origin",
      cache: "no-store",
    }).then(function (response) {
      if (!response || response.ok === false) {
        throw new Error("HTTP " + (response && response.status || 500));
      }
      if (typeof response.json !== "function") return {};
      return response.json().catch(function () { return {}; });
    });
  }

  function postDiagnostic(payload) {
    request(payload).catch(function () {});
  }

  function objectIdFromLocation() {
    const href = String(location && location.href || "");
    const matches = knownObjectIdsInValue(href);
    return matches.size === 1 ? matches.values().next().value : "";
  }

  function knownObjectIdsInValue(value) {
    let haystack = text(value, 8192);
    if (!haystack) return new Set();
    try { haystack = decodeURIComponent(haystack); } catch (_error) {}
    const matches = new Set();
    for (const objectId of seen.keys()) {
      const escaped = objectId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = new RegExp("(?:^|[^A-Za-z0-9_-])" + escaped + "(?:$|[^A-Za-z0-9_-])");
      if (pattern.test(haystack)) matches.add(objectId);
    }
    return matches;
  }

  function markActive(objectId) {
    let changed = false;
    if (objectId && seen.has(objectId)) {
      if (activeObjectId !== objectId) {
        activeObjectId = objectId;
        activeVersion = Math.max(activeVersion + 1, Date.now() * 1000);
        changed = true;
      }
      syncCandidate(seen.get(objectId));
    }
    if (changed) scheduleUiRefresh();
  }

  function publishActive(entry) {
    if (!entry || activeObjectId !== entry.feed.objectId) return;
    if (publishedActiveObjectId === entry.feed.objectId || entry.activating) return;
    const version = activeVersion;
    entry.activating = true;
    request({
      action: "active",
      objectId: entry.feed.objectId,
      version,
    }).then(function (result) {
      if (
        activeObjectId === entry.feed.objectId
        && version === activeVersion
        && result
        && result.action === "active"
        && result.accepted !== false
      ) {
        publishedActiveObjectId = entry.feed.objectId;
        scheduleUiRefresh();
      }
    }).catch(function () {
      // 当前视频可能仍在提交媒体信息；下一次播放/识别事件会自动重试。
    }).finally(function () {
      entry.activating = false;
    });
  }

  function syncCandidate(entry) {
    if (!entry) return;
    if (entry.candidate && !entry.dirty) {
      publishActive(entry);
      return;
    }
    if (entry.pending) return;
    entry.pending = true;
    request(Object.assign({}, entry.feed, { current: false })).then(function (result) {
      const current = seen.get(entry.feed.objectId);
      if (current && result && result.candidate) {
        current.candidate = result.candidate;
        current.dirty = false;
        publishActive(current);
        scheduleUiRefresh();
      }
    }).catch(function (err) {
      console.warn("[留底桌面端] 提交候选失败:", String(err).slice(0, 200));
    }).finally(function () {
      const current = seen.get(entry.feed.objectId);
      if (current) current.pending = false;
    });
  }

  function accept(feed) {
    if (!feed) return;
    const signature = JSON.stringify({
      title: feed.title,
      author: feed.author,
      media: feed.media.map((item) => [
        item.url,
        item.urlToken,
        item.width,
        item.height,
        item.fileSize,
        item.specs,
      ]),
    });
    const previous = seen.get(feed.objectId);
    if (previous && previous.signature === signature) {
      if (objectIdFromLocation() === feed.objectId) markActive(feed.objectId);
      else syncCandidate(previous);
      return;
    }
    seen.delete(feed.objectId);
    const entry = {
      signature,
      feed,
      candidate: previous && previous.candidate || null,
      pending: false,
      activating: false,
      dirty: true,
    };
    seen.set(feed.objectId, entry);
    while (seen.size > MAX_SEEN) {
      const oldest = seen.keys().next().value;
      if (oldest === activeObjectId) {
        const active = seen.get(oldest);
        seen.delete(oldest);
        seen.set(oldest, active);
        continue;
      }
      seen.delete(oldest);
    }
    if (objectIdFromLocation() === feed.objectId) markActive(feed.objectId);
    else syncCandidate(entry);
    scheduleUiRefresh();
  }

  function authoritativeDetailIds(value, sourceMethod) {
    if (!ACTIVE_DETAIL_METHODS.has(text(sourceMethod, 64))) return [];
    const data = value && typeof value === "object" ? value.data : null;
    const direct = data && typeof data === "object" ? data.object : null;
    const objects = Array.isArray(direct) ? direct : direct && typeof direct === "object" ? [direct] : [];
    const ids = [];
    for (const item of objects) {
      const normalized = normalizeFeed(item);
      if (normalized && !ids.includes(normalized.objectId)) ids.push(normalized.objectId);
    }
    return ids;
  }

  function scan(value, sourceMethod) {
    const authoritative = authoritativeDetailIds(value, sourceMethod);
    const queue = [value];
    const visited = new Set();
    const matched = [];
    let count = 0;
    let unmatched = 0;
    let cursor = 0;
    while (cursor < queue.length && count < 2000) {
      const item = queue[cursor];
      cursor += 1;
      if (!item || typeof item !== "object" || visited.has(item)) continue;
      visited.add(item);
      count += 1;
      const normalized = normalizeFeed(item);
      accept(normalized);
      if (normalized) matched.push(normalized.objectId);
      if (!normalized && !feedId(item.id || item.objectId || item.objectid)) {
        const description = item.objectDesc || item.object_desc;
        const media = description && Array.isArray(description.media) ? description.media : item.media;
        if (Array.isArray(media) && media.some(mediaItem)) unmatched += 1;
      }
      if (Array.isArray(item)) {
        for (const child of item.slice(0, 200)) queue.push(child);
      } else {
        for (const [key, child] of Object.entries(item)) {
          if (/cookie|authorization|token|trace|buffer/i.test(key)) continue;
          if (child && typeof child === "object") queue.push(child);
        }
      }
    }
    const unique = Array.from(new Set(matched));
    if (authoritative.length === 1) {
      bindCurrentPlayingVideo(authoritative[0], "detail");
      markActive(authoritative[0]);
    } else {
      const located = objectIdFromLocation();
      if (located) markActive(located);
    }
    markActivePlayingVideo();
    if (unmatched) {
      postDiagnostic({
        action: "diagnostic",
        reason: "missing_object_id",
        count: Math.min(unmatched, 1000),
      });
    }
    return unique;
  }

  let internalApiObservations = 0;
  function observeInternalApi(value, sourceMethod) {
    internalApiObservations += 1;
    if (internalApiObservations === 1 || internalApiObservations % 25 === 0) {
      postDiagnostic({
        action: "diagnostic",
        reason: "internal_api_observed",
        count: internalApiObservations === 1 ? 1 : 25,
      });
    }
    scan(value, sourceMethod);
  }

  Object.defineProperty(globalThis, "__DOWNLOAD_STATION_WECHAT_OBSERVE__", {
    value: observeInternalApi,
    configurable: true,
  });

  function parseJson(value) {
    if (typeof value !== "string" || value.length > 16 * 1024 * 1024) return;
    try { scan(JSON.parse(value)); } catch (_error) {}
  }

  if (globalThis.__DOWNLOAD_STATION_TEST__) {
    globalThis.__DOWNLOAD_STATION_WECHAT_TEST__ = {
      mediaItem,
      normalizeFeed,
      scan,
      accept,
      entryFromTrigger,
      requestDownload,
      selectDefaultVariant,
      downloadStartedMessage,
      activeObjectId: function () { return activeObjectId; },
      seenCount: function () { return seen.size; },
      setCandidate: function (objectId, candidate) {
        const entry = seen.get(objectId);
        if (!entry) return false;
        entry.candidate = candidate;
        entry.dirty = false;
        return true;
      },
    };
  }

  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const request = originalFetch.apply(this, args);
    request.then((response) => {
      const type = response.headers && response.headers.get("content-type") || "";
      if (/json|javascript|text/i.test(type)) {
        response.clone().text().then(parseJson).catch(() => {});
      }
    }).catch(() => {});
    return request;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (...args) {
    this.addEventListener("load", function () {
      if (this.responseType === "" || this.responseType === "text") parseJson(this.responseText);
      else if (this.responseType === "json") scan(this.response);
    }, { once: true });
    return originalOpen.apply(this, args);
  };

  (function () {
    if (typeof Response === "undefined" || !Response.prototype) return;
    var originalJson = Response.prototype.json;
    if (typeof originalJson !== "function") return;
    try {
      Response.prototype.json = function () {
        var result = originalJson.apply(this, arguments);
        if (result && typeof result.then === "function") {
          result.then(scan).catch(function () {});
        }
        return result;
      };
    } catch (_patchError) {
      // 原型可能被冻结或在不同隔离世界中，fetch/XHR 拦截器仍作为后备
    }
  })();

  function comparableMediaPath(value) {
    try {
      const parsed = new URL(value, location.href);
      if (!/^https?:$/i.test(parsed.protocol)) return "";
      return parsed.hostname.toLowerCase() + parsed.pathname;
    } catch (_error) {
      return "";
    }
  }

  function mediaIdentity(value) {
    try {
      const parsed = new URL(value, location.href);
      if (!/^https?:$/i.test(parsed.protocol)) return null;
      let encfilekey = "";
      for (const [name, argument] of parsed.searchParams.entries()) {
        if (name.toLowerCase() === "encfilekey") {
          encfilekey = text(argument, 2048);
          break;
        }
      }
      return {
        path: parsed.hostname.toLowerCase() + parsed.pathname,
        encfilekey,
        sharedPath: /\/stodownload$/i.test(parsed.pathname),
      };
    } catch (_error) {
      return null;
    }
  }

  function feedMediaIdentity(media) {
    return mediaIdentity(text(media && media.url, 8192) + text(media && media.urlToken, 8192));
  }

  function isVisiblePlayingVideo(video) {
    if (!video || video.paused === true || video.ended === true) return false;
    if (video.hidden === true) return false;
    if (typeof window.getComputedStyle === "function") {
      const style = window.getComputedStyle(video);
      if (style && (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")) {
        return false;
      }
    }
    if (typeof video.getClientRects === "function") {
      const rects = Array.from(video.getClientRects());
      if (!rects.length) return false;
      const viewportWidth = number(window.innerWidth)
        || number(document && document.documentElement && document.documentElement.clientWidth);
      const viewportHeight = number(window.innerHeight)
        || number(document && document.documentElement && document.documentElement.clientHeight);
      if (viewportWidth && viewportHeight && !rects.some(function (rect) {
        return number(rect.width) > 0
          && number(rect.height) > 0
          && Number(rect.right) > 0
          && Number(rect.bottom) > 0
          && Number(rect.left) < viewportWidth
          && Number(rect.top) < viewportHeight;
      })) return false;
    }
    return true;
  }

  function playingVideos(scope) {
    if (!scope || typeof scope.querySelectorAll !== "function") return [];
    return Array.from(scope.querySelectorAll("video")).filter(isVisiblePlayingVideo);
  }

  function videoSource(video) {
    return firstText([video && video.currentSrc, video && video.src], 8192);
  }

  function bindVideo(video, objectId, reason) {
    if (!isVisiblePlayingVideo(video) || !objectId || !seen.has(objectId)) return false;
    videoBindings.set(video, {
      objectId,
      reason: text(reason, 32),
      source: videoSource(video),
      duration: Number(video.duration),
    });
    return true;
  }

  function bindCurrentPlayingVideo(objectId, reason) {
    if (!document || typeof document.querySelectorAll !== "function") return false;
    const videos = playingVideos(document);
    return videos.length === 1 ? bindVideo(videos[0], objectId, reason) : false;
  }

  function boundEntryForVideo(video) {
    if (!isVisiblePlayingVideo(video)) return null;
    const binding = videoBindings.get(video);
    if (!binding || !seen.has(binding.objectId)) return null;
    const source = videoSource(video);
    if (binding.source && source && binding.source !== source) {
      videoBindings.delete(video);
      return null;
    }
    const duration = Number(video.duration);
    if (
      Number.isFinite(binding.duration)
      && binding.duration > 0
      && Number.isFinite(duration)
      && duration > 0
      && Math.abs(binding.duration - duration) > 0.5
    ) {
      videoBindings.delete(video);
      return null;
    }
    return seen.get(binding.objectId) || null;
  }

  function videoSources(scope) {
    if (!scope || typeof scope.querySelectorAll !== "function") return [];
    const result = [];
    const allVideos = Array.from(scope.querySelectorAll("video"));
    const currentVideos = allVideos.filter(isVisiblePlayingVideo);
    const videos = currentVideos.length === 1 ? currentVideos : allVideos;
    for (const video of videos) {
      const values = [video.currentSrc, video.src];
      if (typeof video.querySelectorAll === "function") {
        for (const source of video.querySelectorAll("source")) values.push(source.src);
      }
      for (const value of values) {
        const source = text(value, 8192);
        if (source && !result.includes(source)) result.push(source);
      }
    }
    return result;
  }

  function entryMatchingSources(sources) {
    const identities = sources.map(mediaIdentity).filter(Boolean);
    if (!identities.length) return null;
    const matches = Array.from(seen.values()).filter(function (entry) {
      return entry.feed.media.some(function (media) {
        const candidate = feedMediaIdentity(media);
        if (!candidate) return false;
        return identities.some(function (source) {
          if (source.path !== candidate.path) return false;
          // 微信大量视频共享 stodownload 路径。只要播放地址带有稳定的
          // encfilekey，就必须同时匹配它；其余 token/sign 可正常轮换。
          if (source.encfilekey) return source.encfilekey === candidate.encfilekey;
          if (source.sharedPath || candidate.sharedPath) return false;
          return true;
        });
      });
    });
    return matches.length === 1 ? matches[0] : null;
  }

  function markActiveFromVideo(video) {
    if (!video) return;
    const sources = [video.currentSrc, video.src];
    if (typeof video.querySelectorAll === "function") {
      for (const source of video.querySelectorAll("source")) sources.push(source.src);
    }
    const entry = entryMatchingSources(
      sources.map(function (value) { return text(value, 8192); }).filter(Boolean),
    );
    if (entry) {
      bindVideo(video, entry.feed.objectId, "media");
      markActive(entry.feed.objectId);
    }
  }

  function markActivePlayingVideo() {
    if (!document || typeof document.querySelectorAll !== "function") return;
    for (const video of document.querySelectorAll("video")) {
      if (!video.paused && !video.ended) {
        markActiveFromVideo(video);
        return;
      }
    }
  }

  function objectIdFromScope(scope) {
    if (!scope || scope === document) return "";
    const nodes = [scope];
    const found = new Set();
    if (typeof scope.querySelectorAll === "function") {
      const selector = [
        "a[href]", "[data-id]", "[data-object-id]", "[data-objectid]", "[data-feed-id]", "[data-feedid]",
      ].join(",");
      for (const node of scope.querySelectorAll(selector)) nodes.push(node);
    }
    for (const node of nodes) {
      const values = [node && node.href];
      if (node && typeof node.getAttribute === "function") {
        for (const name of [
          "href", "data-id", "data-object-id", "data-objectid", "data-feed-id", "data-feedid",
        ]) values.push(node.getAttribute(name));
      }
      for (const value of values) {
        const haystack = text(value, 8192);
        if (!haystack) continue;
        for (const objectId of knownObjectIdsInValue(haystack)) found.add(objectId);
      }
    }
    return found.size === 1 ? found.values().next().value : "";
  }

  function coverSources(scope) {
    if (!scope || typeof scope.querySelectorAll !== "function") return [];
    const result = [];
    const currentVideos = playingVideos(scope);
    if (currentVideos.length !== 1) return result;
    const poster = text(currentVideos[0] && currentVideos[0].poster, 8192);
    if (poster) result.push(poster);
    return result;
  }

  function entryMatchingCover(sources) {
    const paths = new Set(sources.map(comparableMediaPath).filter(Boolean));
    if (!paths.size) return null;
    const matches = Array.from(seen.values()).filter(function (entry) {
      return entry.feed.media.some(function (media) {
        return paths.has(comparableMediaPath(media.coverUrl));
      });
    });
    return matches.length === 1 ? matches[0] : null;
  }

  function normalizedVisibleText(value) {
    return text(value, 20000).replace(/[\s\u200b-\u200d\ufeff]+/g, "").toLowerCase();
  }

  function triggerScope(trigger) {
    const slide = trigger && typeof trigger.closest === "function"
      ? trigger.closest(".slides-item")
      : null;
    if (slide) return slide;
    let current = trigger && trigger.parentElement;
    for (let depth = 0; current && depth < 10; depth += 1) {
      if (playingVideos(current).length === 1) return current;
      current = current.parentElement;
    }
    return document;
  }

  function entryFromTrigger(trigger) {
    const located = objectIdFromLocation();
    const slide = trigger && typeof trigger.closest === "function"
      ? trigger.closest(".slides-item")
      : null;
    const scope = triggerScope(trigger);
    const scopedObjectId = objectIdFromScope(scope);
    const evidence = new Set();
    const corroboratingEvidence = new Set();
    if (located && seen.has(located)) evidence.add(located);
    if (scopedObjectId && seen.has(scopedObjectId)) {
      evidence.add(scopedObjectId);
      corroboratingEvidence.add(scopedObjectId);
    }

    const currentVideos = playingVideos(scope);
    if (currentVideos.length === 1) {
      const bound = boundEntryForVideo(currentVideos[0]);
      if (bound) {
        evidence.add(bound.feed.objectId);
        corroboratingEvidence.add(bound.feed.objectId);
      }
    }
    const sources = videoSources(scope);
    const sourceMatch = entryMatchingSources(sources);
    if (sourceMatch) {
      evidence.add(sourceMatch.feed.objectId);
      corroboratingEvidence.add(sourceMatch.feed.objectId);
    }

    const coverMatch = entryMatchingCover(coverSources(scope));
    if (coverMatch) {
      evidence.add(coverMatch.feed.objectId);
      corroboratingEvidence.add(coverMatch.feed.objectId);
    }

    const scopeText = normalizedVisibleText(scope && scope.textContent);
    if (scopeText) {
      const matches = Array.from(seen.values()).filter(function (entry) {
        const title = normalizedVisibleText(entry.feed.title);
        return title.length >= 4 && scopeText.includes(title);
      });
      if (matches.length === 1) {
        evidence.add(matches[0].feed.objectId);
        corroboratingEvidence.add(matches[0].feed.objectId);
      }
    }

    if (evidence.size === 1) {
      const objectId = evidence.values().next().value;
      // WeChat SPA may leave the previous objectId in the address bar while a
      // new blob video is already playing.  Location alone cannot authorize a
      // click whenever a current player exists.
      if (located === objectId && currentVideos.length && !corroboratingEvidence.has(objectId)) {
        return null;
      }
      return seen.get(objectId) || null;
    }
    if (evidence.size > 1) return null;

    // An inline control belongs to one concrete slide.  If that slide cannot
    // be tied to a candidate by URL, object id, or title, falling back to the
    // globally active/newest feed can submit a late preloaded neighbour.
    // Refuse the click instead: a visible retry is safer than downloading a
    // different person's video under the selected title.
    if (slide) return null;
    return null;
  }

  function selectDefaultVariant(candidate, currentSource) {
    const variants = candidate && Array.isArray(candidate.variants)
      ? candidate.variants
      : [];
    if (!variants.length) return null;
    let deliverySpec = "";
    try {
      const parsed = new URL(currentSource || "", location.href);
      deliverySpec = text(
        parsed.searchParams.get("X-snsvideoflag")
          || parsed.searchParams.get("x-snsvideoflag"),
        64,
      );
    } catch (_error) {}
    if (deliverySpec) {
      const exact = variants.find(function (variant) {
        return variant.deliverySpec === deliverySpec;
      });
      if (exact) return exact;
    }
    const explicitQuality = variants.find(function (variant) {
      return Boolean(variant.deliverySpec);
    });
    if (explicitQuality) return explicitQuality;
    return variants.find(function (variant) {
      return !variant.deliverySpec;
    }) || variants[0];
  }

  function currentSourceForTrigger(trigger) {
    const scope = triggerScope(trigger);
    return videoSources(scope)[0] || "";
  }

  function toast(message, isError) {
    if (!document || typeof document.createElement !== "function") return;
    let node = document.getElementById("download-station-wechat-toast");
    if (!node) {
      node = document.createElement("div");
      node.id = "download-station-wechat-toast";
      node.style.cssText = "position:fixed;left:50%;top:24px;z-index:2147483647;max-width:min(520px,calc(100vw - 32px));transform:translateX(-50%);padding:10px 14px;border-radius:8px;background:rgba(22,22,22,.94);box-shadow:0 8px 28px rgba(0,0,0,.28);color:#fff;font:14px/1.45 system-ui;text-align:center;pointer-events:none";
      document.documentElement.appendChild(node);
    }
    node.textContent = text(message, 300);
    node.style.background = isError ? "rgba(214,48,49,.96)" : "rgba(22,22,22,.94)";
    node.style.display = "block";
    clearTimeout(node.__downloadStationTimer);
    node.__downloadStationTimer = setTimeout(function () {
      node.style.display = "none";
    }, 2600);
  }

  function setButtonState(trigger, label, busy) {
    if (!trigger) return;
    const textNode = trigger.querySelector('[data-role="download-label"]');
    if (textNode) textNode.textContent = label;
    trigger.setAttribute("aria-busy", busy ? "true" : "false");
    trigger.style.pointerEvents = busy ? "none" : "";
    trigger.style.opacity = busy ? "0.65" : "";
  }

  function downloadStartedMessage(plan, title) {
    const name = text(title, 512) || "当前视频";
    const delivery = text(plan && plan.delivery, 16);
    if (delivery === "local") {
      return "Eagle 未连接，已改为下载到电脑并保留文件：" + name;
    }
    if (delivery === "eagle") {
      return "已开始下载并导入 Eagle：" + name;
    }
    return "已开始下载：" + name;
  }

  function requestDownload(trigger, requestedVariantId) {
    const entry = entryFromTrigger(trigger);
    if (!entry) {
      postDiagnostic({
        action: "diagnostic",
        reason: "current_video_ambiguous",
        count: 1,
      });
      toast("未能确认当前视频，请先播放当前视频后重试", true);
      return;
    }
    if (!entry.candidate) {
      toast("正在识别当前视频质量，请稍后再点一次", true);
      return;
    }
    const defaultVariant = selectDefaultVariant(
      entry.candidate,
      currentSourceForTrigger(trigger),
    );
    const variantId = text(requestedVariantId, 128)
      || text(defaultVariant && defaultVariant.id, 128);
    if (!variantId) {
      toast("当前视频没有可用的下载质量", true);
      return;
    }
    if (downloadsInFlight.has(entry.feed.objectId)) return;
    downloadsInFlight.add(entry.feed.objectId);
    setButtonState(trigger, "创建中…", true);
    closeQualityMenu();
    request({
      action: "download",
      objectId: entry.feed.objectId,
      variantId: variantId,
    }).then(function (result) {
      if (!result || result.action !== "download" || !result.plan || !result.plan.id) {
        throw new Error("任务响应无效");
      }
      toast(downloadStartedMessage(result.plan, entry.feed.title), false);
    }).catch(function (error) {
      console.warn("[留底桌面端] 创建视频号任务失败:", String(error).slice(0, 200));
      toast("创建下载任务失败，请确认留底桌面端仍在运行", true);
    }).finally(function () {
      downloadsInFlight.delete(entry.feed.objectId);
      setButtonState(trigger, "下载", false);
    });
  }

  function closeQualityMenu() {
    clearTimeout(menuCloseTimer);
    const menu = document && document.getElementById
      ? document.getElementById("download-station-wechat-quality-menu")
      : null;
    if (menu) menu.remove();
  }

  function scheduleMenuClose() {
    clearTimeout(menuCloseTimer);
    menuCloseTimer = setTimeout(closeQualityMenu, 160);
  }

  function showQualityMenu(trigger) {
    clearTimeout(menuCloseTimer);
    closeQualityMenu();
    const entry = entryFromTrigger(trigger);
    if (!entry || !entry.candidate || !Array.isArray(entry.candidate.variants)) return;
    const variants = entry.candidate.variants;
    if (!variants.length) return;
    const menu = document.createElement("div");
    menu.id = "download-station-wechat-quality-menu";
    menu.setAttribute("role", "menu");
    menu.style.cssText = "position:fixed;z-index:2147483647;min-width:190px;max-width:280px;padding:6px;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:rgba(31,31,31,.98);box-shadow:0 10px 32px rgba(0,0,0,.36);color:#fff;font:13px/1.4 system-ui";
    const current = selectDefaultVariant(
      entry.candidate,
      currentSourceForTrigger(trigger),
    );
    for (const variant of variants) {
      const item = document.createElement("button");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      item.style.cssText = "display:block;width:100%;padding:9px 10px;border:0;border-radius:5px;background:transparent;color:inherit;font:inherit;text-align:left;white-space:nowrap;cursor:pointer";
      item.textContent = (variant.id === (current && current.id) ? "当前播放 · " : "")
        + (variant.quality || "自动质量");
      item.addEventListener("mouseenter", function () {
        item.style.background = "rgba(255,255,255,.1)";
      });
      item.addEventListener("mouseleave", function () {
        item.style.background = "transparent";
      });
      item.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        requestDownload(trigger, variant.id);
      });
      menu.appendChild(item);
    }
    menu.addEventListener("mouseenter", function () { clearTimeout(menuCloseTimer); });
    menu.addEventListener("mouseleave", scheduleMenuClose);
    document.documentElement.appendChild(menu);
    const rect = trigger.getBoundingClientRect();
    const width = menu.getBoundingClientRect().width || 220;
    const height = menu.getBoundingClientRect().height || 44 * variants.length;
    menu.style.left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width)) + "px";
    menu.style.top = Math.max(8, rect.top - height - 8) + "px";
  }

  const DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"></path><path d="m7.5 10.5 4.5 4.5 4.5-4.5"></path><path d="M5 20h14"></path></svg>';

  function createDownloadControl(floating) {
    const wrapper = document.createElement("div");
    wrapper.dataset.downloadStationWechatDownload = "true";
    const trigger = document.createElement("div");
    trigger.className = "click-box op-item";
    trigger.setAttribute("role", "button");
    trigger.setAttribute("tabindex", "0");
    trigger.setAttribute(
      "aria-label",
      "下载视频；Eagle 可用时导入，否则保留在电脑中"
    );
    trigger.setAttribute(
      "title",
      "Eagle 为可选功能；未连接时仍可正常下载并保留文件"
    );
    trigger.style.cssText = floating
      ? "display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;width:58px;height:58px;border-radius:10px;background:rgba(31,31,31,.96);box-shadow:0 8px 28px rgba(0,0,0,.32);color:#fff;cursor:pointer;user-select:none"
      : "padding:4px;cursor:pointer;user-select:none";
    const icon = document.createElement("div");
    icon.className = "op-icon download-station-download-icon";
    icon.style.cssText = "height:28px;display:flex;align-items:center;justify-content:center";
    icon.innerHTML = DOWNLOAD_ICON;
    const label = document.createElement("div");
    label.className = "op-text";
    label.dataset.role = "download-label";
    label.textContent = "下载";
    trigger.append(icon, label);
    wrapper.appendChild(trigger);
    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      requestDownload(trigger, "");
    });
    trigger.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        requestDownload(trigger, "");
      }
    });
    trigger.addEventListener("mouseenter", function () { showQualityMenu(trigger); });
    trigger.addEventListener("mouseleave", scheduleMenuClose);
    return wrapper;
  }

  function operationParents() {
    const result = [];
    const items = document.querySelectorAll(
      ".slides-item .click-box.op-item, .full-opr-wrp.layout-col .click-box.op-item",
    );
    for (const item of items) {
      if (item.closest("[data-download-station-wechat-download]")) continue;
      const parent = item.parentElement;
      if (parent && !result.includes(parent)) result.push(parent);
    }
    return result;
  }

  function renderControls() {
    if (!document || typeof document.querySelectorAll !== "function") return;
    const parents = operationParents();
    for (const parent of parents) {
      const exists = Array.from(parent.children || []).some(function (child) {
        return child.dataset && child.dataset.downloadStationWechatDownload === "true";
      });
      if (!exists) parent.appendChild(createDownloadControl(false));
    }
    let fallback = document.getElementById("download-station-wechat-control");
    if (parents.length) {
      if (fallback) fallback.remove();
      return;
    }
    if (!fallback) {
      fallback = createDownloadControl(true);
      fallback.id = "download-station-wechat-control";
      fallback.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483646";
      document.documentElement.appendChild(fallback);
    }
  }

  function scheduleUiRefresh() {
    if (uiRefreshTimer) return;
    uiRefreshTimer = setTimeout(function () {
      uiRefreshTimer = 0;
      renderControls();
    }, 80);
  }

  function scheduleActiveRefresh() {
    if (activeRefreshTimer) return;
    activeRefreshTimer = setTimeout(function () {
      activeRefreshTimer = 0;
      markActivePlayingVideo();
    }, 120);
  }

  function startPageControls() {
    renderControls();
    markActivePlayingVideo();
    if (typeof document.addEventListener === "function") {
      document.addEventListener("play", function (event) {
        if (event && event.target && String(event.target.tagName).toLowerCase() === "video") {
          markActiveFromVideo(event.target);
        }
      }, true);
      document.addEventListener("playing", function (event) {
        if (event && event.target && String(event.target.tagName).toLowerCase() === "video") {
          markActiveFromVideo(event.target);
        }
      }, true);
      const clearVideoBinding = function (event) {
        if (event && event.target && String(event.target.tagName).toLowerCase() === "video") {
          videoBindings.delete(event.target);
        }
      };
      document.addEventListener("loadstart", clearVideoBinding, true);
      document.addEventListener("emptied", clearVideoBinding, true);
      document.addEventListener("durationchange", function (event) {
        const video = event && event.target;
        const binding = video && videoBindings.get(video);
        const duration = Number(video && video.duration);
        if (
          binding
          && Number.isFinite(binding.duration)
          && binding.duration > 0
          && Number.isFinite(duration)
          && duration > 0
          && Math.abs(binding.duration - duration) > 0.5
        ) videoBindings.delete(video);
      }, true);
    }
    if (typeof MutationObserver !== "undefined" && document.documentElement) {
      const observer = new MutationObserver(function () {
        scheduleUiRefresh();
        scheduleActiveRefresh();
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document && document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", startPageControls, { once: true });
  } else {
    startPageControls();
  }

})();
