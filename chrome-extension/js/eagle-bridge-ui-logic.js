(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.EagleBridgeUILogic = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const MANIFEST_EXTENSIONS = new Set(["m3u8", "m3u", "mpd"]);
    const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "webp", "avif", "bmp", "svg", "ico"]);
    const SUBTITLE_EXTENSIONS = new Set(["vtt", "srt", "ass", "ssa", "ttml"]);
    const TRANSPORT_SEGMENT_EXTENSIONS = new Set(["m4s", "ts"]);
    const ACTIVE_TASK_STATUSES = new Set([
        "selected", "creating", "queued", "downloading", "merging",
        "validating", "ready_to_import", "waiting_eagle", "importing"
    ]);
    const TERMINAL_TASK_STATUSES = new Set(["imported", "completed_local", "retry", "import_failed", "failed_permanent", "canceled", "blocked_drm", "needs_rebuild"]);

    function number(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function cleanText(value, maximum = 500) {
        return String(value ?? "").replace(/\s+/g, " ").trim().slice(0, maximum);
    }

    function qualityHeight(value) {
        const match = cleanText(value, 80).match(/(?:^|\D)(\d{2,5})\s*p(?:\D|$)/i);
        return match ? number(match[1]) : 0;
    }

    function normalizeQualities(values) {
        const heights = new Set();
        for (const value of Array.isArray(values) ? values : []) {
            const height = qualityHeight(value);
            if (height >= 100 && height <= 10000) heights.add(height);
        }
        return [...heights].sort((left, right) => right - left).map(height => `${height}p`);
    }

    function qualityCatalogInfo(values) {
        const qualities = normalizeQualities(values);
        return {
            count: qualities.length,
            highest: qualities[0] || "",
            lowest: qualities[qualities.length - 1] || ""
        };
    }

    function extensionOf(item) {
        const explicit = cleanText(item?.ext || item?.extension, 20).toLowerCase().replace(/[^a-z0-9]/g, "");
        if (explicit) return explicit;
        try {
            const name = new URL(String(item?.url || "")).pathname.split("/").pop() || "";
            return cleanText(name.split(".").pop(), 20).toLowerCase().replace(/[^a-z0-9]/g, "");
        } catch (_error) {
            return "";
        }
    }

    function kindCode(item) {
        const resolver = cleanText(item?.resolver, 40).toLowerCase();
        if (["youtube", "page"].includes(resolver)) return "resolver";
        const ext = extensionOf(item);
        const type = cleanText(item?.type || item?.mimeType, 120).toLowerCase();
        const explicitRole = cleanText(item?.role, 20).toLowerCase();
        if (MANIFEST_EXTENSIONS.has(ext) || type.includes("mpegurl")) return ext === "mpd" ? "dash" : "hls";
        if (ext === "mpd" || type.includes("dash+xml")) return "dash";
        if (explicitRole === "subtitle" || SUBTITLE_EXTENSIONS.has(ext) || type.includes("text/vtt")) return "subtitle";
        if (explicitRole === "video" || type.startsWith("video/")) return "video";
        if (explicitRole === "audio" || type.startsWith("audio/")) return "audio";
        if (IMAGE_EXTENSIONS.has(ext) || type.startsWith("image/")) return "image";
        return "file";
    }

    function isManifest(item) {
        return ["hls", "dash"].includes(kindCode(item));
    }

    function safeUrl(value) {
        try {
            const url = new URL(String(value || ""));
            if (!["http:", "https:", "blob:"].includes(url.protocol)) return "";
            return url.href;
        } catch (_error) {
            return "";
        }
    }

    function domainOf(value) {
        try { return new URL(String(value || "")).hostname; } catch (_error) { return ""; }
    }

    function titleCore(value) {
        let title = cleanText(value || "媒体", 220);
        title = title.replace(/\s*[-_|｜]\s*(哔哩哔哩|bilibili|YouTube|抖音|Douyin|腾讯视频|优酷|爱奇艺).*$/i, "");
        title = title.replace(/\s*[-_|｜]\s*(新标签页|New Tab)$/i, "");
        return title || "媒体";
    }

    function stableId(item, index = 0) {
        const requestId = cleanText(item?.requestId, 220);
        if (requestId) return `${number(item?.tabId) || 0}:${requestId}`;
        const url = safeUrl(item?.url);
        return `${number(item?.tabId) || 0}:fallback:${url || index}:${kindCode(item)}`;
    }

    function sizeOf(item) {
        const direct = Number(item?._size ?? item?.size ?? item?.estimatedSize);
        return Number.isFinite(direct) && direct > 0 ? direct : 0;
    }

    function normalizeCandidate(item, index = 0) {
        const kind = kindCode(item);
        const title = titleCore(item?._title || item?.title || item?.pageTitle || item?.name);
        const url = safeUrl(item?.url);
        const pageUrl = safeUrl(item?.webUrl || item?.pageUrl || item?.initiator);
        const label = cleanText(item?.label, 120);
        const explicitRole = ["video", "audio", "subtitle"].includes(cleanText(item?.role, 20).toLowerCase());
        return {
            id: stableId(item, index),
            raw: item,
            tabId: Number.isInteger(Number(item?.tabId)) ? Number(item.tabId) : null,
            requestId: cleanText(item?.requestId, 220),
            url,
            pageUrl,
            title,
            name: cleanText(item?.downFileName || item?.name, 260),
            extension: extensionOf(item),
            type: cleanText(item?.type || item?.mimeType, 120),
            kind,
            role: explicitRole ? cleanText(item.role, 20).toLowerCase() : kind,
            explicitRole,
            streamId: cleanText(item?.streamId ?? item?.itag, 100),
            label,
            codec: cleanText(item?.codec, 100),
            language: cleanText(item?.language, 80),
            width: number(item?.videoWidth ?? item?.width),
            height: number(item?.videoHeight ?? item?.height),
            playerWidth: number(item?.playerWidth),
            playerHeight: number(item?.playerHeight),
            frameRate: cleanText(item?.frameRate, 40),
            bitrate: number(item?.bitrate),
            duration: number(item?.duration),
            size: sizeOf(item),
            availableQualities: normalizeQualities(item?.availableQualities),
            qualitySource: cleanText(item?.qualitySource, 40),
            resolver: cleanText(item?.resolver, 40).toLowerCase(),
            reconstructedRange: Boolean(item?.reconstructedRange),
            unboundDouyinMedia: Boolean(item?.unboundDouyinMedia),
            // A site favicon identifies the website, not the video. Keep it
            // separate so presentation code can fall back to a page frame
            // instead of showing the same logo for every captured item.
            thumbnailUrl: safeUrl(item?.thumbnailUrl),
            favIconUrl: safeUrl(item?.favIconUrl),
            groupKey: cleanText(item?.groupKey, 220),
            contentIdentity: cleanText(item?.contentIdentity || item?.contentFingerprint, 320),
            capturedAt: number(item?.getTime || item?.capturedAt),
            drm: Boolean(item?.drm || item?.pssh || item?.keySystem),
            sourceDomain: domainOf(pageUrl || item?.initiator || url),
            scope: cleanText(item?.__scope, 20) || "current"
        };
    }

    function isSupportedPageResolverCandidate(candidate) {
        if (candidate?.resolver !== "page") return true;
        let url;
        try { url = new URL(candidate.url); } catch (_error) { return false; }
        if (!/(^|\.)douyin\.com$/i.test(url.hostname)) return true;
        return /^\/video\/\d{10,30}\/?$/i.test(url.pathname);
    }

    function manifestIdentity(candidate) {
        try {
            const url = new URL(candidate.url);
            return `${url.hostname}${url.pathname}`.slice(0, 420);
        } catch (_error) {
            return candidate.id;
        }
    }

    function streamIdentity(candidate) {
        if (candidate.groupKey && candidate.streamId) {
            return `${candidate.role || candidate.kind}:stream:${candidate.groupKey}:${candidate.streamId}`.slice(0, 900);
        }
        const alias = mediaAliasIdentity(candidate);
        if (alias) return alias.replace(/:size:\d+:/, ":path:");
        try {
            const url = new URL(candidate.url);
            return `${candidate.role || candidate.kind}:${url.origin}${url.pathname}`.slice(0, 900);
        } catch (_error) {
            return candidate.id;
        }
    }

    function candidateRichness(candidate) {
        return Number(Boolean(candidate.thumbnailUrl)) * 1e22
            + Number(Boolean(candidate.groupKey)) * 1e21
            + Number(Boolean(candidate.duration)) * 1e20
            + Number(Boolean(candidate.label)) * 1e18
            + Number(Boolean(candidate.codec)) * 1e17
            + Number(Boolean(candidate.width || candidate.height)) * 1e16
            + candidate.availableQualities.length * 1e15
            + candidate.size * 1e3
            + candidate.capturedAt;
    }

    function collapseRotatingStreams(candidates) {
        const streams = new Map();
        for (const candidate of candidates) {
            const key = streamIdentity(candidate);
            const existing = streams.get(key);
            if (!existing || candidateRichness(candidate) >= candidateRichness(existing)) streams.set(key, candidate);
        }
        return [...streams.values()];
    }

    function fixedByteRange(candidate) {
        let url;
        try { url = new URL(candidate.url); } catch (_error) { return false; }
        const matchesSize = (start, end) => {
            const first = Number(start);
            const last = Number(end);
            if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 0 || last < first) return false;
            const span = last - first + 1;
            return span > 0 && (!candidate.size || candidate.size === span);
        };
        const parseNamedRange = value => {
            const match = cleanText(value, 300).match(/^(?:range|bytes)=(\d+)-(\d+)$/i);
            return Boolean(match && matchesSize(match[1], match[2]));
        };
        const explicitBareRange = value => {
            const match = cleanText(value, 100).match(/^(\d+)-(\d+)$/);
            if (!match) return false;
            const first = Number(match[1]);
            const last = Number(match[2]);
            return Number.isSafeInteger(first) && Number.isSafeInteger(last) && first >= 0 && last >= first;
        };
        for (const [name, value] of url.searchParams) {
            if (["range", "bytes"].includes(name.toLowerCase()) && explicitBareRange(value)) return true;
        }
        const start = url.searchParams.get("start");
        const end = url.searchParams.get("end");
        if (start !== null && end !== null && explicitBareRange(`${start}-${end}`)) return true;
        const byteStart = url.searchParams.get("bytestart");
        const byteEnd = url.searchParams.get("byteend");
        if (byteStart !== null && byteEnd !== null && explicitBareRange(`${byteStart}-${byteEnd}`)) return true;
        for (const rawSegment of url.pathname.split("/").filter(Boolean)) {
            let segment;
            try { segment = decodeURIComponent(rawSegment); } catch (_error) { segment = rawSegment; }
            if (parseNamedRange(segment)) return true;
            if (!/^[a-z0-9_-]{12,300}$/i.test(segment)) continue;
            try {
                const padded = segment.replace(/-/g, "+").replace(/_/g, "/")
                    + "=".repeat((4 - segment.length % 4) % 4);
                if (parseNamedRange(atob(padded))) return true;
            } catch (_error) {
                // Not a base64url-encoded range token.
            }
        }
        return false;
    }

    function isTransportSegment(candidate) {
        return candidate.unboundDouyinMedia
            || (!candidate.explicitRole
            && (TRANSPORT_SEGMENT_EXTENSIONS.has(candidate.extension)
                || fixedByteRange(candidate)
                || (!candidate.groupKey
                    && ["video", "audio"].includes(candidate.kind)
                    && candidate.size > 0
                    && candidate.size < 128 * 1024
                    && candidate.duration <= 0)));
    }

    function stableMediaPath(candidate) {
        try {
            const path = new URL(candidate.url).pathname.replace(/\/{2,}/g, "/");
            // Short generic paths such as /video.mp4 are not enough to prove
            // that two unrelated CDN hosts serve the same bytes.
            return path.length >= 24 && path.split("/").filter(Boolean).length >= 3 ? path : "";
        } catch (_error) {
            return "";
        }
    }

    function mediaAliasIdentity(candidate) {
        const role = candidate.role || candidate.kind;
        if (candidate.contentIdentity.length >= 8) {
            return `${role}:header:${candidate.contentIdentity}`.slice(0, 900);
        }
        const path = stableMediaPath(candidate);
        if (!path || candidate.size < 256 * 1024) return "";
        return `${role}:size:${candidate.size}:${path}`.slice(0, 900);
    }

    function scopedAliasIdentity(candidate) {
        const alias = mediaAliasIdentity(candidate);
        if (!alias) return "";
        const pageDomain = domainOf(candidate.pageUrl) || candidate.sourceDomain || "page";
        return `${candidate.tabId ?? 0}:${pageDomain}:${alias}`;
    }

    function candidateGroupId(candidate) {
        const pageDomain = domainOf(candidate.pageUrl) || candidate.sourceDomain || "page";
        if (candidate.groupKey) return `explicit:${candidate.tabId ?? 0}:${pageDomain}:${candidate.groupKey}`;
        if (candidate.explicitRole && candidate.duration > 0) {
            const durationBucket = Math.round(candidate.duration / 2) * 2;
            return `timed:${candidate.tabId ?? 0}:${pageDomain}:${titleCore(candidate.title)}:${durationBucket}`;
        }
        if (isManifest(candidate)) return `manifest:${candidate.tabId ?? 0}:${manifestIdentity(candidate)}`;
        return `single:${candidate.id}`;
    }

    function qualityScore(candidate) {
        const labelMatch = candidate.label.match(/(\d{3,4})\s*[pP]/);
        const labelHeight = labelMatch ? number(labelMatch[1]) : 0;
        const height = candidate.height || labelHeight;
        const frameRate = number(candidate.frameRate.split("/")[0]);
        return height * 1e12 + candidate.width * 1e9 + candidate.bitrate * 1e2 + frameRate * 1e4 + candidate.size;
    }

    function audioScore(candidate) {
        const labelBitrate = number(candidate.label.match(/(\d{2,4})\s*[kK]/)?.[1]) * 1000;
        return Math.max(candidate.bitrate, labelBitrate) * 1e3 + candidate.size;
    }

    function sortVideo(candidates) {
        return [...candidates].sort((a, b) => qualityScore(b) - qualityScore(a) || a.id.localeCompare(b.id));
    }

    function sortAudio(candidates) {
        return [...candidates].sort((a, b) => audioScore(b) - audioScore(a) || a.id.localeCompare(b.id));
    }

    function createGroup(id, candidates) {
        const collapsed = collapseRotatingStreams(candidates);
        const hasManifest = collapsed.some(isManifest);
        const hiddenByManifest = new Set(hasManifest
            ? collapsed.filter(item => !item.explicitRole && !isManifest(item) && ["video", "audio"].includes(item.kind)).map(item => item.id)
            : []);
        const transportSegments = collapsed.filter(item => isTransportSegment(item) || hiddenByManifest.has(item.id));
        let items = collapsed.filter(item => !isTransportSegment(item) && !hiddenByManifest.has(item.id));
        const segmentOnly = !items.length && transportSegments.length > 0;
        if (segmentOnly) {
            items = [transportSegments.sort((left, right) => right.capturedAt - left.capturedAt || right.size - left.size)[0]];
        }
        const videos = sortVideo(items.filter(item => item.kind === "video"));
        const audios = sortAudio(items.filter(item => item.kind === "audio"));
        const subtitles = items.filter(item => item.kind === "subtitle");
        const manifests = items.filter(isManifest);
        const resolvers = items.filter(item => item.kind === "resolver");
        const attachments = items.filter(item => ["image", "file"].includes(item.kind));
        const first = items[0] || collapsed[0];
        const thumbnail = collapsed.find(item => item.thumbnailUrl)?.thumbnailUrl || "";
        const newest = Math.max(0, ...collapsed.map(item => item.capturedAt));
        const playerHeight = Math.max(0, ...collapsed.map(item => item.playerHeight));
        const playerWidth = Math.max(0, ...collapsed.filter(item => item.playerHeight === playerHeight).map(item => item.playerWidth));
        const availableQualities = normalizeQualities(collapsed.flatMap(item => item.availableQualities));
        return {
            id,
            tabId: first?.tabId ?? null,
            title: first?.title || "媒体",
            pageUrl: first?.pageUrl || "",
            sourceDomain: first?.sourceDomain || "",
            thumbnailUrl: thumbnail,
            favIconUrl: collapsed.find(item => item.favIconUrl)?.favIconUrl || "",
            duration: Math.max(0, ...collapsed.map(item => item.duration)),
            playerWidth,
            playerHeight,
            playbackQuality: playerHeight ? `${playerHeight}p` : "",
            availableQualities,
            newest,
            scope: first?.scope || "current",
            confidence: id.startsWith("explicit:") ? "high" : id.startsWith("timed:") ? "medium" : "isolated",
            drm: collapsed.some(item => item.drm),
            items,
            videos,
            audios,
            subtitles,
            manifests,
            resolvers,
            attachments,
            segmentOnly,
            fallbackOnly: items.length > 0 && items.every(item => item.reconstructedRange),
            transportSegmentCount: transportSegments.length,
            hiddenFragmentCount: hiddenByManifest.size
        };
    }

    function isSafeFilterRegex(pattern) {
        const value = cleanText(pattern, 260);
        if (!value) return true;
        if (value.length > 200) return false;
        if (/\\[1-9]/.test(value)) return false;
        if (/\([^)]*[+*][^)]*\)[+*{]/.test(value)) return false;
        if (/(\.\*){2,}|(\.\+){2,}/.test(value)) return false;
        try {
            new RegExp(value, "i");
            return true;
        } catch (_error) {
            return false;
        }
    }

    function filterCandidates(rawCandidates, filters = {}) {
        const query = cleanText(filters.query, 200).toLowerCase();
        const mediaType = cleanText(filters.mediaType, 20).toLowerCase() || "all";
        const extensions = new Set(cleanText(filters.extension, 160).toLowerCase().split(/[\s,;|]+/).filter(Boolean));
        const minimumSize = Math.max(0, number(filters.minimumSize));
        const regexText = cleanText(filters.regex, 260);
        const regex = regexText && isSafeFilterRegex(regexText) ? new RegExp(regexText, "i") : null;
        const seenNames = new Set();
        const output = [];
        (Array.isArray(rawCandidates) ? rawCandidates : []).forEach((raw, index) => {
            const candidate = normalizeCandidate(raw, index);
            if (!candidate.url || !isSupportedPageResolverCandidate(candidate)) return;
            if (query && ![
                candidate.title, candidate.name, candidate.extension, candidate.type,
                candidate.label, candidate.codec, candidate.language, candidate.sourceDomain
            ].some(value => cleanText(value).toLowerCase().includes(query))) return;
            if (mediaType !== "all") {
                const matchesType = mediaType === "manifest" ? isManifest(candidate)
                    : mediaType === "other" ? ["file", "image", "subtitle"].includes(candidate.kind)
                        : candidate.kind === mediaType;
                if (!matchesType) return;
            }
            if (extensions.size && !extensions.has(candidate.extension)) return;
            if (minimumSize && candidate.size < minimumSize) return;
            if (regex && !regex.test(candidate.url)) return;
            if (filters.dedupe) {
                const nameKey = cleanText(candidate.name || `${candidate.title}.${candidate.extension}`, 320).toLowerCase();
                if (seenNames.has(nameKey)) return;
                seenNames.add(nameKey);
            }
            output.push(raw);
        });
        return output;
    }

    function groupCandidates(rawCandidates) {
        const seen = new Map();
        (Array.isArray(rawCandidates) ? rawCandidates : []).forEach((raw, index) => {
            const candidate = normalizeCandidate(raw, index);
            if (!candidate.url || !isSupportedPageResolverCandidate(candidate) || seen.has(candidate.id)) return;
            seen.set(candidate.id, candidate);
        });
        const candidates = [...seen.values()];
        // A visible player normally supplies a stable groupKey, while the
        // same bytes may also be reported through a backup CDN request that
        // has no DOM/player metadata. Attach only strong aliases (response
        // identity, or same long path + exact byte size) to one unambiguous
        // explicit group. File size by itself is intentionally insufficient.
        const explicitAliasOwners = new Map();
        for (const candidate of candidates) {
            if (!candidate.groupKey) continue;
            const alias = scopedAliasIdentity(candidate);
            if (!alias) continue;
            const explicitId = candidateGroupId(candidate);
            const existing = explicitAliasOwners.get(alias);
            explicitAliasOwners.set(alias, existing && existing !== explicitId ? "" : explicitId);
        }
        const buckets = new Map();
        for (const candidate of candidates) {
            const alias = scopedAliasIdentity(candidate);
            let id = candidateGroupId(candidate);
            if (!candidate.groupKey && alias) {
                id = explicitAliasOwners.get(alias) || `alias:${alias}`;
            }
            if (!buckets.has(id)) buckets.set(id, []);
            buckets.get(id).push(candidate);
        }
        return [...buckets.entries()]
            .map(([id, candidates]) => createGroup(id, candidates))
            .sort((a, b) => a.newest - b.newest || Number(b.confidence === "high") - Number(a.confidence === "high") || a.title.localeCompare(b.title));
    }

    function partitionGroups(groups, options = {}) {
        const all = Array.isArray(groups) ? groups : [];
        const showSegments = Boolean(options.showSegments);
        // One page resolver only proves that one content item is available.
        // It does not prove that every other complete media request in the
        // same tab/domain is a duplicate: feeds, boards and galleries can
        // legitimately contain several independent videos. Hide only groups
        // that are structurally known to contain transport fragments.
        const technicalReason = group => group?.segmentOnly ? "segment" : "";
        const hidden = group => Boolean(technicalReason(group));
        const hiddenSegmentCount = showSegments ? 0 : all.filter(hidden).length;
        return {
            visible: showSegments
                ? all.map(group => {
                    const reason = technicalReason(group);
                    return reason && reason !== "segment"
                        ? { ...group, technicalOnly: true, technicalReason: reason }
                        : group;
                })
                : all.filter(group => !hidden(group)),
            hiddenSegmentCount
        };
    }

    function defaultActiveGroupId(groups, previousId = "") {
        const all = Array.isArray(groups) ? groups : [];
        const previous = cleanText(previousId, 500);
        if (previous && all.some(group => group?.id === previous)) return previous;
        return cleanText(all.at(-1)?.id, 500);
    }

    function createDefaultSelection(group, previous = null) {
        const availableIds = new Set(group.items.map(item => item.id));
        if (previous) {
            const kept = {
                mode: previous.mode,
                videoId: availableIds.has(previous.videoId) ? previous.videoId : "",
                audioId: availableIds.has(previous.audioId) ? previous.audioId : "",
                directId: availableIds.has(previous.directId) ? previous.directId : "",
                manifestId: availableIds.has(previous.manifestId) ? previous.manifestId : "",
                quality: group.availableQualities.includes(previous.quality) ? previous.quality : group.availableQualities[0] || "",
                subtitleIds: (previous.subtitleIds || []).filter(id => availableIds.has(id))
            };
            if (kept.videoId || kept.audioId || kept.directId || kept.manifestId) return kept;
        }
        if (group.resolvers.length) {
            return { mode: "resolver", directId: group.resolvers[0].id, videoId: "", audioId: "", manifestId: "", quality: group.availableQualities[0] || "", subtitleIds: [] };
        }
        if (group.videos.length || group.audios.length) {
            const standaloneVideo = group.videos.find(item => !item.explicitRole);
            if (standaloneVideo && !group.videos.some(item => item.explicitRole) && !group.audios.some(item => item.explicitRole)) {
                return { mode: "direct", directId: standaloneVideo.id, videoId: "", audioId: "", manifestId: "", quality: "", subtitleIds: [] };
            }
            return {
                mode: "tracks",
                videoId: group.videos[0]?.id || "",
                audioId: group.audios[0]?.id || "",
                directId: "",
                manifestId: "",
                quality: "",
                subtitleIds: []
            };
        }
        if (group.manifests.length) {
            return { mode: "manifest", manifestId: group.manifests[0].id, videoId: "", audioId: "", directId: "", quality: group.availableQualities[0] || "", subtitleIds: [] };
        }
        const direct = group.attachments[0] || group.items[0];
        return { mode: "direct", directId: direct?.id || "", videoId: "", audioId: "", manifestId: "", quality: "", subtitleIds: [] };
    }

    function itemById(group, id) {
        return group.items.find(item => item.id === id);
    }

    function selectedCandidates(group, selection) {
        if (!group || !selection) return [];
        const primary = selection.mode === "manifest"
            ? [itemById(group, selection.manifestId)]
            : ["direct", "resolver"].includes(selection.mode)
                ? [itemById(group, selection.directId)]
                : [itemById(group, selection.videoId), itemById(group, selection.audioId)];
        const subtitles = selection.mode === "manifest" ? []
            : (selection.subtitleIds || []).map(id => itemById(group, id)).filter(item => item?.kind === "subtitle");
        const seen = new Set();
        return [...primary, ...subtitles].filter(item => item && !seen.has(item.id) && seen.add(item.id));
    }

    function previewMediaUrl(group, selection) {
        const selectedVideo = selectedCandidates(group, selection)
            .find(item => item?.kind === "video");
        const candidate = selectedVideo || group?.videos?.[0];
        if (!candidate?.url) return "";
        try {
            const url = new URL(candidate.url);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "";
        } catch (_error) {
            return "";
        }
    }

    function resolveRawItems(candidates, resolver) {
        if (!Array.isArray(candidates) || typeof resolver !== "function") return [];
        return candidates.map(candidate => resolver(candidate)).filter(Boolean);
    }

    function outputContainer(group, selection) {
        const items = selectedCandidates(group, selection);
        if (selection?.mode === "resolver") return "mp4";
        if (selection?.mode === "manifest") return "mkv";
        if (selection?.mode === "direct") return items[0]?.extension || "mp4";
        const video = items.find(item => item.kind === "video");
        const audio = items.find(item => item.kind === "audio");
        const videoCodec = cleanText(video?.codec).toLowerCase();
        const audioCodec = cleanText(audio?.codec).toLowerCase();
        const mp4Video = !videoCodec || /(avc|h264|h\.264|hevc|h265|h\.265|av01)/.test(videoCodec);
        const mp4Audio = !audioCodec || /(mp4a|aac|alac)/.test(audioCodec);
        return mp4Video && mp4Audio ? "mp4" : "mkv";
    }

    function defaultOutputName(group, selection) {
        const container = outputContainer(group, selection);
        const base = titleCore(group?.title || "media")
            .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
            .replace(/[. ]+$/g, "")
            .slice(0, 120) || "media";
        return `${base}.${container}`;
    }

    function normalizeOutputName(value) {
        const name = cleanText(value, 180)
            .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
            .replace(/[. ]+$/g, "")
            .slice(0, 160);
        const stem = name.replace(/\.[a-z0-9]{1,10}$/i, "");
        if (!name || !stem || /^[. ]+$/.test(stem)) {
            return {
                ok: false,
                value: "",
                message: "请输入有效的 Windows 文件名"
            };
        }
        return { ok: true, value: name, message: "" };
    }

    function validateSelection(group, selection, options = {}) {
        if (!group) return { ok: false, code: "no_group", message: "请选择一个媒体内容" };
        if (group.drm) return { ok: false, code: "blocked_drm", message: "检测到 DRM 保护，无法下载或合并" };
        if (group.segmentOnly) return { ok: false, code: "segment_only", message: "当前只捕获到播放分片，请继续播放片刻或使用增强捕获查找完整媒体清单" };
        if (group.technicalOnly) return { ok: false, code: "unbound_playback", message: "该播放资源无法可靠关联到页面中的某个视频；请使用同页带标题和预览的内容候选" };
        const items = selectedCandidates(group, selection);
        if (!items.length) return { ok: false, code: "empty", message: "请选择要下载的版本" };
        if (items.some(item => !item.url)) return { ok: false, code: "invalid_url", message: "所选媒体地址无效" };
        if (selection.mode === "tracks") {
            const videos = items.filter(item => item.kind === "video");
            const audios = items.filter(item => item.kind === "audio");
            if (videos.length > 1 || audios.length > 1) return { ok: false, code: "too_many_tracks", message: "每个任务只能选择一路视频和一路音频" };
            if (!videos.length && !audios.length) return { ok: false, code: "missing_tracks", message: "请选择视频或音频轨道" };
            if (items.some(isManifest)) return { ok: false, code: "mixed_manifest", message: "清单不能与直链轨道混合" };
        }
        if (selection.mode === "manifest" && !items.every(isManifest)) {
            return { ok: false, code: "invalid_manifest", message: "请选择 HLS 或 DASH 清单" };
        }
        if (selection.mode === "resolver" && (items.length !== 1
            || !["youtube", "page"].includes(items[0].resolver)
            || !isSupportedPageResolverCandidate(items[0])
            || (items[0].resolver === "youtube" && !selection.quality))) {
            return { ok: false, code: "invalid_resolver", message: "请选择可用的 YouTube 视频画质" };
        }
        if (!options.paired) {
            return { ok: false, code: "not_paired", message: "请先连接本机软件，再开始下载" };
        }
        return {
            ok: true,
            code: "ready",
            message: "",
            items,
            route: "desktop",
            outputContainer: outputContainer(group, selection),
            resolver: selection.mode === "resolver" ? items[0].resolver : "",
            merge: selection.mode === "tracks" && items.length > 1
        };
    }

    function formatBytes(value) {
        let size = number(value);
        if (size <= 0) return "大小未知";
        const units = ["B", "KB", "MB", "GB", "TB"];
        let unit = 0;
        while (size >= 1024 && unit < units.length - 1) {
            size /= 1024;
            unit += 1;
        }
        return `${size.toFixed(unit >= 2 ? 1 : 0)} ${units[unit]}`;
    }

    function formatDuration(value) {
        const total = Math.max(0, Math.round(number(value)));
        if (!total) return "";
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}` : `${minutes}:${String(seconds).padStart(2, "0")}`;
    }

    function videoLabel(candidate, recommended = false) {
        if (!candidate) return "视频";
        const quality = candidate.label || (candidate.height ? `${candidate.height}P` : "视频");
        return [recommended ? "推荐" : "", quality, candidate.codec, formatBytes(candidate.size)].filter(Boolean).join(" · ");
    }

    function manifestLabel(candidate) {
        if (!candidate) return "媒体清单 · 自动选择最佳";
        const format = candidate.kind === "dash" ? "DASH" : "HLS";
        const quality = candidate.availableQualities?.[0]
            || normalizeQualities([candidate.label, candidate.height ? `${candidate.height}p` : ""])[0]
            || "";
        return [format, quality ? `最高 ${quality}` : "自动质量", "自动选择最佳"].join(" · ");
    }

    function directLabel(candidate, recommended = false) {
        if (!candidate) return "不可用";
        if (candidate.kind === "resolver") {
            return [recommended ? "推荐" : "", candidate.availableQualities?.[0] || candidate.label || "自动画质", "桌面解析"]
                .filter(Boolean).join(" · ");
        }
        if (isManifest(candidate)) return manifestLabel(candidate);
        const quality = normalizeQualities([
            candidate.label,
            ...(candidate.availableQualities || []),
            candidate.height ? `${candidate.height}p` : ""
        ])[0];
        const kind = candidate.kind === "video" ? (quality || "清晰度未知")
            : candidate.kind === "audio" ? (candidate.language || candidate.label || "音频")
                : candidate.label || candidate.extension.toUpperCase() || candidate.kind;
        return [recommended ? "推荐" : "", kind, candidate.extension.toUpperCase(), candidate.codec, formatBytes(candidate.size)]
            .filter(Boolean).join(" · ");
    }

    function audioLabel(candidate) {
        if (!candidate) return "不选择音频";
        const bitrate = candidate.bitrate ? `${Math.round(candidate.bitrate / 1000)}K` : "";
        return [candidate.language || candidate.label || "音频", candidate.codec, bitrate || formatBytes(candidate.size)].filter(Boolean).join(" · ");
    }

    function groupSummary(group, selection) {
        const items = selectedCandidates(group, selection);
        if (!items.length) return "尚未选择版本";
        if (selection.mode === "resolver") {
            const resolver = items[0]?.resolver;
            return resolver === "youtube"
                ? `YouTube · ${selection.quality || "自动画质"} · 本机解析并合并`
                : `${items[0]?.label || "最佳可用"} · 本机解析并合并`;
        }
        if (selection.mode === "manifest") {
            const format = items[0].kind === "dash" ? "DASH" : "HLS";
            return selection.quality ? `${format} · ${selection.quality} · 本机自动合并` : manifestLabel(items[0]);
        }
        if (selection.mode === "direct") {
            const item = items[0];
            if (item.kind === "video") return `${item.label || (item.height ? `${item.height}P` : "视频")} · ${formatBytes(item.size)}`;
            if (item.kind === "audio") return `${item.label || "音频"} · ${formatBytes(item.size)}`;
            return `${item.extension?.toUpperCase() || "文件"} · ${formatBytes(item.size)}`;
        }
        const video = items.find(item => item.kind === "video");
        const audio = items.find(item => item.kind === "audio");
        return [video ? (video.label || (video.height ? `${video.height}P 视频` : "视频")) : "", audio ? (audio.language || audio.label || "音频") : ""].filter(Boolean).join(" + ");
    }

    function taskView(plan) {
        let status = cleanText(plan?.status, 60) || "creating";
        const jobStatus = cleanText(plan?.job_status || plan?.jobStatus, 60);
        if (status === "ready_to_import" && jobStatus === "waiting_eagle") status = "waiting_eagle";
        if (status === "ready_to_import" && jobStatus === "failed_permanent") status = "import_failed";
        const labels = {
            selected: "准备任务", creating: "正在创建", queued: "等待本机下载",
            downloading: "本机正在下载", merging: "本机正在合并", validating: "正在校验媒体",
            ready_to_import: "等待导入 Eagle", waiting_eagle: "正在等待 Eagle",
            importing: "正在导入 Eagle", imported: "已导入 Eagle", completed_local: "已下载到本机",
            retry: "下载失败", import_failed: "Eagle 导入失败",
            failed_permanent: "无法继续", canceled: "已停止", blocked_drm: "DRM 已阻断",
            needs_rebuild: "需要回到来源重建"
        };
        let progress = Math.max(0, Math.min(100, number(plan?.progress)));
        if (status === "imported" || status === "completed_local") progress = 100;
        else progress = Math.min(progress, 99);
        const finalPath = String(plan?.final_path || plan?.finalPath || "").replaceAll("\x00", "").slice(0, 1200);
        const previewPath = String(plan?.preview_path || plan?.previewPath || "").replaceAll("\x00", "").slice(0, 1200);
        const pageUrl = safeUrl(plan?.page_url || plan?.pageUrl);
        return {
            id: cleanText(plan?.id, 100),
            title: cleanText(plan?.output_name || plan?.outputName || plan?.title, 220) || "未命名任务",
            status,
            statusLabel: labels[status] || status,
            progress,
            active: ACTIVE_TASK_STATUSES.has(status),
            terminal: TERMINAL_TASK_STATUSES.has(status),
            error: cleanText(plan?.error_message || plan?.job_error, 500),
            detail: cleanText(plan?.phase_detail, 220),
            processed: formatBytes(plan?.downloaded_bytes || plan?.downloadedBytes),
            total: formatBytes(plan?.total_bytes || plan?.totalBytes),
            thumbnailUrl: safeUrl(plan?.thumbnail_url || plan?.thumbnailUrl),
            finalPath,
            pageUrl,
            canOpenOutput: Boolean(finalPath),
            canOpenSource: Boolean(pageUrl),
            canImportExisting: status === "completed_local" && Boolean(finalPath),
            canRetry: status === "retry",
            hasLocalPreview: Boolean(previewPath),
            createdAt: number(plan?.created_at || plan?.createdAt),
            raw: plan
        };
    }

    function hasActiveTasks(plans) {
        return (Array.isArray(plans) ? plans : []).some(plan => ACTIVE_TASK_STATUSES.has(cleanText(plan?.status, 60)));
    }

    async function startValidatedTask(validation, createPlan) {
        if (!validation?.ok) {
            return {
                started: false,
                plan: null,
                error: cleanText(validation?.message, 500) || "当前选择无法开始下载"
            };
        }
        const plan = await createPlan();
        if (!plan) {
            return {
                started: false,
                plan: null,
                error: "本机软件没有返回下载任务"
            };
        }
        return { started: true, plan, error: "" };
    }

    function replaceScrollableContent(element, markup, options = {}) {
        if (!element) return;
        const preserve = options.preserve !== false;
        const previousScrollTop = preserve ? Math.max(0, number(element.scrollTop)) : 0;
        element.innerHTML = String(markup ?? "");
        if (!preserve) return;
        const maximumScrollTop = Math.max(
            0,
            number(element.scrollHeight) - number(element.clientHeight)
        );
        element.scrollTop = Math.min(previousScrollTop, maximumScrollTop);
    }

    return {
        MANIFEST_EXTENSIONS,
        ACTIVE_TASK_STATUSES,
        TERMINAL_TASK_STATUSES,
        kindCode,
        isManifest,
        normalizeCandidate,
        isSupportedPageResolverCandidate,
        isSafeFilterRegex,
        filterCandidates,
        groupCandidates,
        partitionGroups,
        defaultActiveGroupId,
        createDefaultSelection,
        selectedCandidates,
        previewMediaUrl,
        resolveRawItems,
        validateSelection,
        outputContainer,
        defaultOutputName,
        normalizeOutputName,
        formatBytes,
        formatDuration,
        qualityCatalogInfo,
        videoLabel,
        manifestLabel,
        directLabel,
        audioLabel,
        groupSummary,
        taskView,
        hasActiveTasks,
        startValidatedTask,
        replaceScrollableContent
    };
});
