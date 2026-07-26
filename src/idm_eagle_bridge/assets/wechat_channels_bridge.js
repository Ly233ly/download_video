(function () {
  "use strict";

  const SESSION = "__DOWNLOAD_STATION_SESSION__";
  const ENDPOINT = `/__download_station_wechat__/candidate?token=${SESSION}`;
  const seen = new Map();
  const downloadsInFlight = new Set();
  const ACTIVE_DETAIL_METHODS = new Set([
    "finderGetCommentDetail",
    "goToNextFlowFeed",
    "goToPrevFlowFeed",
    "loadLocalPlaylist",
  ]);
  let activeObjectId = "";
  let uiRefreshTimer = 0;
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
    for (const item of seen.keys()) {
      if (href.includes(item)) return item;
    }
    return "";
  }

  function markActive(objectId) {
    if (objectId && seen.has(objectId)) activeObjectId = objectId;
    scheduleUiRefresh();
  }

  function syncCandidate(entry) {
    if (!entry || entry.pending || entry.candidate) return;
    entry.pending = true;
    request(entry.feed).then(function (result) {
      const current = seen.get(entry.feed.objectId);
      if (current && result && result.candidate) {
        current.candidate = result.candidate;
        scheduleUiRefresh();
      }
    }).catch(function (err) {
      console.warn("[下载中转站] 提交候选失败:", String(err).slice(0, 200));
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
      syncCandidate(previous);
      return;
    }
    seen.delete(feed.objectId);
    const entry = {
      signature,
      feed,
      candidate: previous && previous.candidate || null,
      pending: false,
    };
    seen.set(feed.objectId, entry);
    while (seen.size > 500) seen.delete(seen.keys().next().value);
    if (objectIdFromLocation() === feed.objectId) activeObjectId = feed.objectId;
    syncCandidate(entry);
    scheduleUiRefresh();
  }

  function scan(value, sourceMethod) {
    const queue = [value];
    const visited = new Set();
    const matched = [];
    let count = 0;
    let unmatched = 0;
    while (queue.length && count < 6000) {
      const item = queue.shift();
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
        for (const child of item.slice(0, 500)) queue.push(child);
      } else {
        for (const [key, child] of Object.entries(item)) {
          if (/cookie|authorization|token|trace|buffer/i.test(key)) continue;
          if (child && typeof child === "object") queue.push(child);
        }
      }
    }
    const unique = Array.from(new Set(matched));
    if (unique.length === 1 && ACTIVE_DETAIL_METHODS.has(text(sourceMethod, 64))) {
      markActive(unique[0]);
    } else {
      const located = objectIdFromLocation();
      if (located) markActive(located);
    }
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
    if (internalApiObservations <= 1000) {
      postDiagnostic({ action: "diagnostic", reason: "internal_api_observed", count: 1 });
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
      selectDefaultVariant,
      activeObjectId: function () { return activeObjectId; },
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

  function videoSources(scope) {
    if (!scope || typeof scope.querySelectorAll !== "function") return [];
    const result = [];
    for (const video of scope.querySelectorAll("video")) {
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

  function entryFromTrigger(trigger) {
    const located = objectIdFromLocation();
    if (located) return seen.get(located) || null;

    const scope = trigger && typeof trigger.closest === "function"
      ? trigger.closest(".slides-item") || document
      : document;
    const sources = videoSources(scope);
    const paths = new Set(sources.map(comparableMediaPath).filter(Boolean));
    if (paths.size) {
      const matches = Array.from(seen.values()).filter(function (entry) {
        return entry.feed.media.some(function (media) {
          return paths.has(comparableMediaPath(media.url));
        });
      });
      if (matches.length === 1) return matches[0];
    }

    const scopeText = text(scope && scope.textContent, 20000);
    if (scopeText) {
      const matches = Array.from(seen.values()).filter(function (entry) {
        const title = text(entry.feed.title, 500);
        return title.length >= 4 && scopeText.includes(title);
      });
      if (matches.length === 1) return matches[0];
    }

    if (activeObjectId && seen.has(activeObjectId)) return seen.get(activeObjectId);
    if (seen.size === 1) return seen.values().next().value;
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
    return variants.find(function (variant) {
      return !variant.deliverySpec;
    }) || variants[0];
  }

  function currentSourceForTrigger(trigger) {
    const scope = trigger && typeof trigger.closest === "function"
      ? trigger.closest(".slides-item") || document
      : document;
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

  function requestDownload(trigger, requestedVariantId) {
    const entry = entryFromTrigger(trigger);
    if (!entry) {
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
      toast("已开始下载：" + (entry.feed.title || "当前视频"), false);
    }).catch(function (error) {
      console.warn("[下载中转站] 创建视频号任务失败:", String(error).slice(0, 200));
      toast("创建下载任务失败，请确认下载中转站仍在运行", true);
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
      "下载并导入 Eagle，成功后删除本机下载文件"
    );
    trigger.setAttribute(
      "title",
      "导入 Eagle 成功后会自动删除本机下载文件"
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

  function startPageControls() {
    renderControls();
    if (typeof MutationObserver !== "undefined" && document.documentElement) {
      const observer = new MutationObserver(scheduleUiRefresh);
      observer.observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document && document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", startPageControls, { once: true });
  } else {
    startPageControls();
  }

  if (!globalThis.__DOWNLOAD_STATION_TEST__) {
    (function poll() {
      fetch("/__download_station_wechat__/poll?token=" + SESSION, {
        credentials: "same-origin",
        cache: "no-store",
      }).then(function (r) {
        if (!r.ok) return;
        return r.json();
      }).then(function (cmd) {
        if (cmd && cmd.method) {
          try {
            var fn = eval(cmd.method);
            if (typeof fn === "function") {
              var result = fn(cmd.params ? JSON.parse(cmd.params) : undefined);
              if (result && typeof result.then === "function") {
                result.then(scan).catch(function () {});
              } else {
                scan(result);
              }
            }
          } catch (_e) {}
        }
      }).catch(function () {}).finally(function () {
        setTimeout(poll, 100);
      });
    })();
  }
})();
