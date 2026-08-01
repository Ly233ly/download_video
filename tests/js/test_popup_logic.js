"use strict";

const assert = require("assert");
const logic = require("../../chrome-extension/js/eagle-bridge-ui-logic.js");

function candidate(overrides = {}) {
    return {
        requestId: overrides.requestId || `request-${Math.random()}`,
        tabId: 9,
        url: overrides.url || "https://media.example/video.m4s",
        webUrl: "https://www.bilibili.com/video/BV1test",
        title: "城市之光 - 哔哩哔哩",
        ext: "m4s",
        type: "video/mp4",
        role: "video",
        label: "1080P",
        codec: "avc1.640028",
        width: 1920,
        height: 1080,
        duration: 120,
        groupKey: "BV1test:123",
        estimatedSize: 1000,
        ...overrides
    };
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "v720", label: "720P", height: 720, estimatedSize: 600 }),
        candidate({ requestId: "v1080", label: "1080P", height: 1080, estimatedSize: 900 }),
        candidate({ requestId: "a64", role: "audio", type: "audio/mp4", label: "64K", codec: "mp4a.40.2", bitrate: 64000, estimatedSize: 100 }),
        candidate({ requestId: "a192", role: "audio", type: "audio/mp4", label: "192K", codec: "mp4a.40.2", bitrate: 192000, estimatedSize: 200 }),
        candidate({ requestId: "szh", role: "subtitle", type: "text/vtt", ext: "vtt", language: "zh-CN", label: "简体中文", url: "https://media.example/zh-CN.vtt" })
    ]);
    assert.strictEqual(groups.length, 1, "explicit Bilibili streams must form one content group");
    const selection = logic.createDefaultSelection(groups[0]);
    assert.strictEqual(selection.videoId, "9:v1080", "highest video quality should be recommended");
    assert.strictEqual(selection.audioId, "9:a192", "highest audio bitrate should be recommended");
    selection.subtitleIds = ["9:szh"];
    const selected = logic.selectedCandidates(groups[0], selection);
    assert.deepStrictEqual(selected.map(item => item.kind), ["video", "audio", "subtitle"], "checked subtitles must enter the download plan");
    assert.strictEqual(logic.groupSummary(groups[0], selection), "1080P + 192K");
    const validation = logic.validateSelection(groups[0], selection, { paired: true, importToEagle: true });
    assert.strictEqual(validation.ok, true);
    assert.strictEqual(validation.outputContainer, "mp4");
    assert.strictEqual(validation.route, "desktop", "every selected media type must use the desktop downloader");
}

{
    const sharedUrl = "https://rr1---sn.example.googlevideo.com/videoplayback";
    const group = logic.groupCandidates([
        candidate({ requestId: "yt-271", webUrl: "https://www.youtube.com/watch?v=test", title: "YouTube catalog", groupKey: "youtube:test", streamId: "271", role: "video", label: "1440p", codec: "vp9", width: 2560, height: 1440, url: `${sharedUrl}?itag=271` }),
        candidate({ requestId: "yt-137", webUrl: "https://www.youtube.com/watch?v=test", title: "YouTube catalog", groupKey: "youtube:test", streamId: "137", role: "video", label: "1080p", codec: "avc1.640028", width: 1920, height: 1080, url: `${sharedUrl}?itag=137` }),
        candidate({ requestId: "yt-251", webUrl: "https://www.youtube.com/watch?v=test", title: "YouTube catalog", groupKey: "youtube:test", streamId: "251", role: "audio", type: "audio/webm", ext: "weba", label: "160K", codec: "opus", bitrate: 160000, url: `${sharedUrl}?itag=251` })
    ])[0];
    assert.strictEqual(group.videos.length, 2, "different YouTube itags on one CDN path must remain separate quality choices");
    assert.strictEqual(group.audios.length, 1);
    assert.strictEqual(group.videos[0].label, "1440p");
    assert.strictEqual(logic.outputContainer(group, logic.createDefaultSelection(group)), "mkv", "VP9 plus Opus must use a compatible MKV container");
}

{
    const candidates = [{ id: "first" }, { id: "second" }];
    const calls = [];
    const resolved = logic.resolveRawItems(candidates, function (candidate) {
        calls.push([...arguments]);
        return { id: candidate.id };
    });
    assert.deepStrictEqual(resolved, [{ id: "first" }, { id: "second" }]);
    assert.strictEqual(calls.every(call => call.length === 1), true, "raw item resolver must not receive Array.map index/array arguments");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "video-one", groupKey: "BV1:1" }),
        candidate({ requestId: "audio-two", groupKey: "BV2:2", role: "audio", type: "audio/mp4" })
    ]);
    assert.strictEqual(groups.length, 2, "different explicit content IDs must never be merged");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "plain-video", groupKey: "", role: undefined, duration: 0, type: "video/mp4" }),
        candidate({ requestId: "plain-audio", groupKey: "", role: undefined, duration: 0, type: "audio/mp4", url: "https://media.example/audio.m4a" })
    ]);
    assert.strictEqual(groups.length, 2, "unrelated generic direct resources must stay isolated");
}

{
    const rangeToken = Buffer.from("range=9207009-13484176").toString("base64url");
    const rangeFragment = candidate({
        requestId: "fixed-range-mp4",
        groupKey: "frame-0:embedded-player",
        role: undefined,
        duration: 0,
        ext: "mp4",
        type: "video/mp4",
        url: `https://media.example/v2/range/prot/${rangeToken}/avf/video-id.mp4`,
        _size: 4_277_168
    });
    const rangeOnlyGroup = logic.groupCandidates([rangeFragment])[0];
    assert.strictEqual(rangeOnlyGroup.segmentOnly, true, "a fixed byte-range MP4 URL must not be presented as a complete video");
    assert.strictEqual(
        logic.validateSelection(rangeOnlyGroup, logic.createDefaultSelection(rangeOnlyGroup), { paired: true }).code,
        "segment_only",
        "a fixed byte-range MP4 URL must be blocked before plan creation"
    );

    const manifestGroup = logic.groupCandidates([
        rangeFragment,
        candidate({
            requestId: "complete-manifest",
            groupKey: "frame-0:embedded-player",
            role: undefined,
            duration: 40,
            ext: "m3u8",
            type: "application/vnd.apple.mpegurl",
            url: "https://media.example/v2/playlist/av/primary/playlist.m3u8"
        })
    ])[0];
    assert.strictEqual(manifestGroup.items.length, 1, "a complete manifest must hide fixed byte-range MP4 fragments from version choices");
    assert.strictEqual(manifestGroup.manifests.length, 1);
}

{
    const youtubeRange = candidate({
        requestId: "youtube-range-probe",
        webUrl: "https://www.youtube.com/watch?v=pIzs1qe-aBc",
        title: "Octane for Houdini - All About Instancing - YouTube",
        groupKey: "",
        role: undefined,
        duration: 0,
        ext: "mp4",
        type: "audio/mp4",
        url: "https://rr1---sn.example.googlevideo.com/videoplayback?itag=140&range=0-7134&clen=50000000",
        _size: 50_000_000
    });
    const group = logic.groupCandidates([youtubeRange])[0];
    assert.strictEqual(group.segmentOnly, true, "an explicit URL byte range stays a transport fragment even when Content-Range reports the full file size");

    const tinyProbe = candidate({
        requestId: "youtube-tiny-audio-probe",
        webUrl: "https://www.youtube.com/watch?v=pIzs1qe-aBc",
        title: "YouTube",
        groupKey: "",
        role: undefined,
        duration: 0,
        ext: "m4a",
        type: "audio/mp4",
        url: "https://www.youtube.com/player-audio-probe",
        _size: 7 * 1024
    });
    assert.strictEqual(logic.groupCandidates([tinyProbe])[0].segmentOnly, true, "tiny ungrouped media probes must stay out of the default content list");
}

{
    const instagramFragment = candidate({
        requestId: "instagram-byte-fragment",
        webUrl: "https://www.instagram.com/",
        title: "Instagram",
        groupKey: "",
        role: undefined,
        duration: 0,
        ext: "mp4",
        type: "video/mp4",
        url: "https://scontent-dfw5-2.cdninstagram.com/o1/v/t2/f2/m367/video.mp4?token=signed&bytestart=886&byteend=173864",
        _size: 172_979
    });
    const group = logic.groupCandidates([instagramFragment])[0];
    assert.strictEqual(group.segmentOnly, true, "bytestart/byteend requests are transport fragments, not complete Instagram videos");
    assert.strictEqual(
        logic.validateSelection(group, logic.createDefaultSelection(group), { paired: true }).code,
        "segment_only",
        "raw Instagram byte fragments must never reach the desktop downloader"
    );
}

{
    const pageResolver = candidate({
        requestId: "generic-page-resolver",
        url: "https://www.instagram.com/p/Da9rBuVjAGK/",
        webUrl: "https://www.instagram.com/",
        title: "Instagram post video",
        groupKey: "page:instagram:Da9rBuVjAGK",
        resolver: "page",
        role: "video",
        label: "最佳可用",
        duration: 10.4,
        estimatedSize: 0
    });
    const group = logic.groupCandidates([pageResolver])[0];
    const selection = logic.createDefaultSelection(group);
    assert.strictEqual(selection.mode, "resolver");
    assert.strictEqual(selection.quality, "", "generic page resolution does not invent quality levels");
    const validation = logic.validateSelection(group, selection, { paired: true });
    assert.strictEqual(validation.ok, true, "a stable content permalink must be eligible for desktop page resolution");
    assert.strictEqual(validation.resolver, "page");
    assert.match(logic.groupSummary(group, selection), /本机解析/);
}

{
    const staleDouyinResolver = candidate({
        requestId: "stale-douyin-jingxuan-resolver",
        url: "https://www.douyin.com/jingxuan",
        webUrl: "https://www.douyin.com/jingxuan?modal_id=7662692425235828009",
        title: "抖音精选电脑版",
        groupKey: "page:stale-douyin-player",
        resolver: "page",
        role: "video",
        duration: 49.041
    });
    assert.deepStrictEqual(
        logic.groupCandidates([staleDouyinResolver]),
        [],
        "an old unsupported Douyin feed resolver must disappear instead of remaining retryable after extension reload"
    );
}

{
    const unboundNetworkCandidate = candidate({
        requestId: "douyin-unbound-network",
        url: "https://v95-web-sz.douyinvod.com/raw/preload.mp4?token=signed",
        webUrl: "https://www.douyin.com/jingxuan?modal_id=7662692425235828009",
        title: "标签页标题 - 抖音",
        groupKey: "",
        role: undefined,
        ext: "mp4",
        type: "video/mp4",
        estimatedSize: 18_100_000,
        duration: 223.234,
        unboundDouyinMedia: true
    });
    const groups = logic.groupCandidates([unboundNetworkCandidate]);
    assert.strictEqual(groups.length, 1);
    assert.strictEqual(groups[0].segmentOnly, true, "an unbound Douyin network request must stay in the technical-fragment partition");
    assert.strictEqual(logic.partitionGroups(groups).visible.length, 0, "an unbound request must not appear as a fake video named after the tab");
}

{
    const distinctDouyinItems = logic.groupCandidates([
        candidate({
            requestId: "douyin-current-7662692425235828009",
            url: "https://www.douyin.com/video/7662692425235828009",
            webUrl: "https://www.douyin.com/jingxuan?modal_id=7662692425235828009",
            title: "@热话动漫 · 这一集的瑞克，终于不像个疯子，像个外公",
            groupKey: "douyin:7662692425235828009",
            resolver: "page",
            role: "video",
            duration: 223.234
        }),
        candidate({
            requestId: "douyin-feed-7653805516250025262",
            url: "https://www.douyin.com/video/7653805516250025262",
            webUrl: "https://www.douyin.com/jingxuan?modal_id=7662692425235828009",
            title: "@木板解说 · 第7集：深度拆解瑞克和莫蒂 S6E4",
            groupKey: "douyin:7653805516250025262",
            resolver: "page",
            role: "video",
            duration: 532.9
        })
    ]);
    assert.strictEqual(distinctDouyinItems.length, 2, "different explicit Douyin video IDs must remain separate content groups");
    assert.deepStrictEqual(distinctDouyinItems.map(group => group.title).sort(), [
        "@热话动漫 · 这一集的瑞克，终于不像个疯子，像个外公",
        "@木板解说 · 第7集：深度拆解瑞克和莫蒂 S6E4"
    ].sort());
}

{
    const reconstructedFallback = candidate({
        requestId: "instagram-reconstructed-track",
        webUrl: "https://www.instagram.com/",
        title: "Instagram 视频 · 10 秒",
        groupKey: "instagram:18421119973183903",
        reconstructedRange: true,
        role: "video",
        duration: 10,
        ext: "mp4",
        url: "https://scontent.example.cdninstagram.com/o1/complete.mp4?token=signed"
    });
    const pageResolver = candidate({
        requestId: "instagram-page-resolver",
        url: "https://www.instagram.com/p/Da9rBuVjAGK",
        webUrl: "https://www.instagram.com/",
        title: "真实帖子视频",
        groupKey: "page:instagram:Da9rBuVjAGK",
        resolver: "page",
        role: "video",
        duration: 10,
        estimatedSize: 0
    });
    const groups = logic.groupCandidates([reconstructedFallback, pageResolver]);
    const partitioned = logic.partitionGroups(groups);
    assert.deepStrictEqual(
        partitioned.visible.map(group => group.title).sort(),
        ["Instagram 视频 · 10 秒", "真实帖子视频"].sort(),
        "a page resolver must not hide another complete media candidate without a shared content identity"
    );
    assert.strictEqual(partitioned.hiddenSegmentCount, 0, "a reconstructed complete media URL is not a transport fragment");
    assert.strictEqual(logic.partitionGroups(groups, { showSegments: true }).visible.length, 2);
}

{
    const pageResolvers = [
        ["2078821500099125405", "我单方面宣布，Joy-Con 才是 Voice Coding 的最佳神器，没有之一。", 47.647],
        ["2078673094940745759", "28 个真实可跑项目！AI Agent 实战圣经开源", 25.966],
        ["2078466405369102834", "看完汗毛直立，提问和回答的水平都是超一流的", 3485.936]
    ].map(([id, title, duration], index) => candidate({
        requestId: `page-resolver-${id}`,
        url: `https://x.com/creator/status/${id}`,
        webUrl: "https://x.com/home",
        title,
        groupKey: `page:player-${id}`,
        streamId: `page:player-${id}`,
        resolver: "page",
        role: "video",
        duration,
        thumbnailUrl: `https://images.example/${id}.jpg`,
        getTime: 1_000 + index
    }));
    const unboundPlayback = Array.from({ length: 12 }, (_, index) => candidate({
        requestId: `unbound-hls-${index}`,
        url: `https://video-cdn-${index % 3}.example/playback/${index}/master.m3u8?token=${index}`,
        webUrl: "https://x.com/home",
        title: "主页 / X",
        groupKey: "",
        role: undefined,
        duration: 0,
        ext: "m3u8",
        type: "application/vnd.apple.mpegurl",
        getTime: 2_000 + index
    }));
    const groups = logic.groupCandidates([...pageResolvers, ...unboundPlayback]);
    assert.strictEqual(groups.length, 15, "the raw capture still keeps auditable network resources before presentation partitioning");

    const defaultView = logic.partitionGroups(groups);
    assert.strictEqual(defaultView.visible.length, 15, "a multi-video page must keep complete manifests visible beside page resolvers");
    assert.deepStrictEqual(defaultView.visible.slice(0, 3).map(group => group.title), pageResolvers.map(item => item.title));
    assert.strictEqual(defaultView.hiddenSegmentCount, 0, "a complete manifest must not be hidden by an unrelated page resolver");

    const diagnosticView = logic.partitionGroups(groups, { showSegments: true });
    const technical = diagnosticView.visible.filter(group => group.technicalOnly);
    assert.strictEqual(technical.length, 0, "complete media must remain selectable instead of being downgraded to diagnostics");
    assert.strictEqual(
        logic.validateSelection(defaultView.visible[3], logic.createDefaultSelection(defaultView.visible[3]), { paired: true }).route,
        "desktop",
        "a user-selected complete manifest must remain downloadable"
    );

    const manifestWithoutBoundContent = logic.groupCandidates([unboundPlayback[0]]);
    assert.strictEqual(
        logic.partitionGroups(manifestWithoutBoundContent).visible.length,
        1,
        "a site without a content-bound alternative must keep its only complete manifest usable"
    );
}

{
    const sharedPath = "/video/tos/cn/tos-cn-ve-15/oc1ACobO9BZIaAie2AsEWtLQ0LAdgzfN9yaBiP/";
    const groups = logic.groupCandidates([
        candidate({
            requestId: "douyin-player",
            webUrl: "https://www.douyin.com/jingxuan",
            title: "抖音精选电脑版",
            groupKey: "frame-0:player-current",
            role: undefined,
            duration: 228.345,
            ext: "mp4",
            type: "video/mp4",
            url: `https://v95-web-sz.douyinvod.com${sharedPath}?signature=one`,
            _size: 54_525_952,
            thumbnailUrl: "https://p3-sign.douyinpic.com/current-frame.webp"
        }),
        candidate({
            requestId: "douyin-cdn-alias",
            webUrl: "https://www.douyin.com/jingxuan",
            title: "douyin.com/jingxuan",
            groupKey: "",
            role: undefined,
            duration: 0,
            ext: "mp4",
            type: "video/mp4",
            url: `https://v3-web.douyinvod.com${sharedPath}?signature=two`,
            _size: 54_525_952,
            thumbnailUrl: ""
        })
    ]);
    assert.strictEqual(groups.length, 1, "one media file exposed through CDN aliases must form one content group");
    assert.strictEqual(groups[0].items.length, 1, "CDN aliases must collapse to one useful download version");
    assert.strictEqual(groups[0].title, "抖音精选电脑版", "the richer player title must win over a URL fallback");
    assert.strictEqual(groups[0].thumbnailUrl, "https://p3-sign.douyinpic.com/current-frame.webp", "the real player preview must be shared by the merged candidate");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "same-size-a", groupKey: "", role: undefined, duration: 0, url: "https://cdn-a.example/video/first-content.mp4", _size: 54_525_952 }),
        candidate({ requestId: "same-size-b", groupKey: "", role: undefined, duration: 0, url: "https://cdn-b.example/video/second-content.mp4", _size: 54_525_952 })
    ]);
    assert.strictEqual(groups.length, 2, "file size alone must never merge different media");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "digest-player", groupKey: "frame-0:player-digest", role: undefined, duration: 228, url: "https://cdn-a.example/opaque/first", _size: 54_525_952, contentIdentity: "md5:6af621f29f1d8a9f" }),
        candidate({ requestId: "digest-alias", groupKey: "", role: undefined, duration: 0, url: "https://cdn-b.example/completely/different/path", _size: 54_525_952, contentIdentity: "md5:6af621f29f1d8a9f" })
    ]);
    assert.strictEqual(groups.length, 1, "matching strong response identities must merge even when CDN paths differ");
    assert.strictEqual(groups[0].items.length, 1, "strong response aliases must expose one download version");
}

{
    const firstUrl = "https://media.example/first-video.mp4?signature=one";
    const secondUrl = "https://media.example/second-video.mp4?signature=two";
    const group = logic.groupCandidates([
        candidate({ requestId: "preview-first", groupKey: "same-player", role: undefined, duration: 0, ext: "mp4", type: "video/mp4", url: firstUrl, thumbnailUrl: "" }),
        candidate({ requestId: "preview-second", groupKey: "same-player", role: undefined, duration: 0, ext: "mp4", type: "video/mp4", url: secondUrl, thumbnailUrl: "" })
    ])[0];
    const selection = logic.createDefaultSelection(group);
    selection.directId = group.items.find(item => item.url === secondUrl).id;
    assert.strictEqual(
        logic.previewMediaUrl(group, selection),
        secondUrl,
        "a missing thumbnail must preview the exact direct URL selected for download"
    );
    selection.directId = group.items.find(item => item.url === firstUrl).id;
    assert.strictEqual(logic.previewMediaUrl(group, selection), firstUrl, "changing the selected version must change the preview source");

    const audio = logic.groupCandidates([candidate({ requestId: "preview-audio", role: "audio", type: "audio/mp4", ext: "m4a", url: "https://media.example/audio.m4a", thumbnailUrl: "" })])[0];
    assert.strictEqual(logic.previewMediaUrl(audio, logic.createDefaultSelection(audio)), "", "audio must not be rendered as a video preview");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "behance-1", webUrl: "https://www.behance.net/gallery/239656477/Song-of-the-Stars-TXT", title: "Song of the Stars - TXT :: Behance", groupKey: "frame-8:vimeo-player", role: undefined, duration: 91, ext: "mp4", type: "video/mp4", url: "https://vod.example/720/video.mp4?token=one", _size: 4_400_000 }),
        candidate({ requestId: "behance-2", webUrl: "https://www.behance.net/gallery/239656477/Song-of-the-Stars-TXT", title: "Song of the Stars - TXT :: Behance", groupKey: "frame-8:vimeo-player", role: undefined, duration: 91, ext: "mp4", type: "video/mp4", url: "https://vod.example/720/video.mp4?token=two", _size: 4_500_000 }),
        candidate({ requestId: "behance-3", webUrl: "https://www.behance.net/gallery/239656477/Song-of-the-Stars-TXT", title: "Song of the Stars - TXT :: Behance", groupKey: "frame-8:vimeo-player", role: undefined, duration: 91, ext: "mp4", type: "video/mp4", url: "https://vod.example/1080/video.mp4?token=three", _size: 8_500_000 })
    ]);
    assert.strictEqual(groups.length, 1, "requests from one Behance/Vimeo player must stay in one content group");
    assert.strictEqual(groups[0].items.length, 2, "rotating signatures for the same stream must not keep adding versions");
}

{
    const fragments = Array.from({ length: 21 }, (_, index) => candidate({
        requestId: `vimeo-fragment-${index}`,
        webUrl: "https://www.behance.net/gallery/239656477/Song-of-the-Stars-TXT",
        title: "Song of the Stars - TXT :: Behance",
        groupKey: "frame-8:vimeo:1143783367",
        role: undefined,
        label: "",
        width: 0,
        height: 0,
        playerWidth: 1920,
        playerHeight: 1080,
        duration: 103,
        ext: "mp4",
        type: "video/mp4",
        url: `https://vod.example/segment/${index}.mp4`,
        _size: index % 2 ? 74_000 : 2_000_000 + index * 120_000
    }));
    const manifest = candidate({
        requestId: "vimeo-master",
        webUrl: "https://www.behance.net/gallery/239656477/Song-of-the-Stars-TXT",
        title: "Song of the Stars - TXT :: Behance",
        groupKey: "frame-8:vimeo:1143783367",
        role: undefined,
        label: "最高 1080p",
        width: 0,
        height: 0,
        playerWidth: 1920,
        playerHeight: 1080,
        duration: 103,
        ext: "m3u8",
        type: "application/vnd.apple.mpegurl",
        url: "https://vod.example/master/playlist.m3u8",
        availableQualities: ["360p", "1080p", "720p"]
    });
    const group = logic.groupCandidates([...fragments, manifest])[0];
    assert.strictEqual(group.items.length, 1, "a complete manifest must replace the player's captured MP4 fragments");
    assert.strictEqual(group.manifests.length, 1);
    assert.deepStrictEqual(group.manifests[0].availableQualities, ["1080p", "720p", "360p"]);
    assert.strictEqual(group.playbackQuality, "1080p", "player dimensions should be shown as current playback quality, not a stream guess");
    assert.strictEqual(logic.manifestLabel(group.manifests[0]), "HLS · 最高 1080p · 自动选择最佳");
    const selection = logic.createDefaultSelection(group);
    assert.strictEqual(selection.mode, "manifest");
    assert.strictEqual(selection.quality, "1080p", "the highest advertised quality should be selected by default");
}

{
    const advertised = ["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"];
    const group = logic.groupCandidates([candidate({
        requestId: "eight-quality-master",
        groupKey: "player-eight-quality",
        role: undefined,
        ext: "m3u8",
        type: "application/vnd.apple.mpegurl",
        url: "https://vod.example/eight/master.m3u8",
        availableQualities: advertised
    })])[0];
    assert.deepStrictEqual(group.availableQualities, [...advertised].reverse(), "every quality advertised by this video must remain selectable");
    assert.deepStrictEqual(logic.qualityCatalogInfo(group.availableQualities), {
        count: 8,
        highest: "2160p",
        lowest: "144p"
    });
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "manifest", groupKey: "player-one", role: undefined, duration: 91, ext: "mpd", type: "application/dash+xml", url: "https://vod.example/master.mpd" }),
        ...Array.from({ length: 12 }, (_, index) => candidate({ requestId: `segment-${index}`, groupKey: "player-one", role: undefined, duration: 91, ext: "m4s", type: "video/mp4", url: `https://vod.example/segment-${index}.m4s` }))
    ]);
    assert.strictEqual(groups.length, 1);
    assert.strictEqual(groups[0].items.length, 1, "transport fragments must not appear as twelve downloadable videos");
    assert.strictEqual(logic.createDefaultSelection(groups[0]).mode, "manifest");
}

{
    const group = logic.groupCandidates([
        ...Array.from({ length: 6 }, (_, index) => candidate({ requestId: `orphan-${index}`, groupKey: "player-two", role: undefined, duration: 91, ext: "m4s", type: "video/mp4", url: `https://vod.example/orphan-${index}.m4s` }))
    ])[0];
    const validation = logic.validateSelection(group, logic.createDefaultSelection(group), { paired: true, importToEagle: true });
    assert.strictEqual(validation.code, "segment_only", "a partial fragment must never be presented as a complete download");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "downloadable-old", groupKey: "player-old", role: undefined, duration: 30, ext: "mp4", type: "video/mp4", url: "https://vod.example/old.mp4", getTime: 1000 }),
        candidate({ requestId: "fragment-new", groupKey: "player-fragment", role: undefined, duration: 30, ext: "m4s", type: "video/mp4", url: "https://vod.example/new.m4s", getTime: 3000 }),
        candidate({ requestId: "downloadable-latest", groupKey: "player-latest", role: undefined, duration: 30, ext: "mp4", type: "video/mp4", url: "https://vod.example/latest.mp4", getTime: 5000 })
    ]);
    assert.strictEqual(groups.at(-1).newest, 5000, "the newest captured content must be the last row");
    const defaultView = logic.partitionGroups(groups, { showSegments: false });
    assert.deepStrictEqual(defaultView.visible.map(group => group.newest), [1000, 5000]);
    assert.strictEqual(defaultView.hiddenSegmentCount, 1, "transport-only groups must be hidden by default");
    assert.strictEqual(logic.defaultActiveGroupId(defaultView.visible, ""), defaultView.visible.at(-1).id, "opening the popup must select the newest visible row");
    const diagnosticView = logic.partitionGroups(groups, { showSegments: true });
    assert.strictEqual(diagnosticView.visible.length, 3, "the filter option must reveal transport-only rows for diagnostics");
}

{
    const groups = logic.groupCandidates([
        candidate({ requestId: "manifest", groupKey: "", role: undefined, duration: 0, ext: "m3u8", type: "application/vnd.apple.mpegurl", url: "https://media.example/master.m3u8" }),
        candidate({ requestId: "direct", groupKey: "", role: undefined, duration: 0, ext: "mp4", type: "video/mp4", url: "https://media.example/full.mp4" })
    ]);
    assert.strictEqual(groups.length, 2, "manifest and direct media must not share a fallback group");
    const manifest = groups.find(group => group.manifests.length);
    const selection = logic.createDefaultSelection(manifest);
    const validation = logic.validateSelection(manifest, selection, { paired: true, importToEagle: true });
    assert.strictEqual(validation.route, "desktop");
}

{
    const group = logic.groupCandidates([candidate({ requestId: "drm", drm: true })])[0];
    const validation = logic.validateSelection(group, logic.createDefaultSelection(group), { paired: true, importToEagle: true });
    assert.strictEqual(validation.code, "blocked_drm");
}

{
    const group = logic.groupCandidates([candidate({ requestId: "unpaired" })])[0];
    const selection = logic.createDefaultSelection(group);
    assert.strictEqual(logic.validateSelection(group, selection, { paired: false, importToEagle: true }).code, "not_paired");
    assert.strictEqual(logic.validateSelection(group, selection, { paired: false, importToEagle: false }).code, "not_paired");
}

async function testValidatedTaskStart() {
    let createCalls = 0;
    const rejected = await logic.startValidatedTask(
        { ok: false, message: "请先连接本机软件" },
        async () => {
            createCalls += 1;
            return { id: "must-not-exist" };
        }
    );
    assert.deepStrictEqual(rejected, {
        started: false,
        plan: null,
        error: "请先连接本机软件"
    });
    assert.strictEqual(createCalls, 0, "an unpaired action must never create a download plan");

    const accepted = await logic.startValidatedTask(
        { ok: true },
        async () => {
            createCalls += 1;
            return { id: "created-plan" };
        }
    );
    assert.strictEqual(accepted.started, true);
    assert.strictEqual(accepted.plan.id, "created-plan");
    assert.strictEqual(createCalls, 1);
}

{
    const qualities = ["1440p", "1080p", "720p", "480p", "360p", "240p", "144p"];
    const group = logic.groupCandidates([candidate({
        requestId: "youtube-resolver",
        url: "https://www.youtube.com/watch?v=pIzs1qe-aBc",
        webUrl: "https://www.youtube.com/watch?v=pIzs1qe-aBc",
        title: "Octane for Houdini - All About Instancing",
        groupKey: "youtube:pIzs1qe-aBc",
        streamId: "resolver-pIzs1qe-aBc",
        resolver: "youtube",
        ext: "mp4",
        type: "video/mp4",
        role: "video",
        label: "1440p",
        availableQualities: qualities,
        qualitySource: "youtube_player_catalog",
        width: 0,
        height: 1440,
        estimatedSize: 0
    })])[0];
    assert.strictEqual(group.resolvers.length, 1, "a YouTube SABR catalog must be a desktop resolver group");
    assert.deepStrictEqual(group.availableQualities, qualities);
    const selection = logic.createDefaultSelection(group);
    assert.strictEqual(selection.mode, "resolver");
    assert.strictEqual(selection.quality, "1440p", "highest advertised quality should be selected by default");
    const selected = logic.selectedCandidates(group, selection);
    assert.strictEqual(selected.length, 1);
    assert.strictEqual(selected[0].resolver, "youtube");
    assert.strictEqual(logic.outputContainer(group, selection), "mp4");
    const validation = logic.validateSelection(group, selection, { paired: true, importToEagle: true });
    assert.strictEqual(validation.ok, true);
    assert.strictEqual(validation.resolver, "youtube");
    assert.strictEqual(logic.groupSummary(group, selection), "YouTube · 1440p · 本机解析并合并");
}

{
    assert.strictEqual(logic.hasActiveTasks([{ status: "merging" }]), true);
    assert.strictEqual(logic.hasActiveTasks([{ status: "imported" }, { status: "canceled" }]), false);
    const view = logic.taskView({ id: "p1", output_name: "video.mp4", status: "downloading", progress: 50, phase_detail: "本机软件正在下载" });
    assert.strictEqual(view.progress, 50);
    assert.strictEqual(view.active, true);
    assert.strictEqual(view.detail, "本机软件正在下载");

    const completed = logic.taskView({
        id: "p2",
        output_name: "finished.mp4",
        status: "completed_local",
        progress: 0,
        final_path: "C:\\Users\\Tester\\Downloads\\下载中转站\\已完成\\finished.mp4",
        preview_path: "C:\\Users\\Tester\\Downloads\\下载中转站\\预览\\p2.png"
    });
    assert.strictEqual(completed.progress, 100, "a completed desktop task must never remain at 0% in the popup");
    assert.strictEqual(completed.canOpenOutput, true);
    assert.strictEqual(completed.canImportExisting, true, "a download-only result must be importable without downloading again");
    assert.strictEqual(completed.finalPath.endsWith("finished.mp4"), true);
    assert.strictEqual(completed.hasLocalPreview, true);

    const validating = logic.taskView({ status: "validating", progress: 100 });
    assert.strictEqual(validating.progress, 99, "validation must not look complete before local delivery");
    const named = logic.normalizeOutputName("bad<>name.mp4");
    assert.strictEqual(named.ok, true);
    assert.strictEqual(named.value, "bad__name.mp4");
    assert.strictEqual(logic.normalizeOutputName("...").ok, false);
}

{
    const list = {
        scrollTop: 720,
        scrollHeight: 1400,
        clientHeight: 400,
        markup: ""
    };
    Object.defineProperty(list, "innerHTML", {
        set(value) {
            this.markup = value;
            // Replacing a scroll container's children reproduces the popup bug:
            // Chromium resets the list to its first row before the click completes.
            this.scrollTop = 0;
        }
    });

    logic.replaceScrollableContent(list, "<button>selected bottom item</button>");

    assert.strictEqual(list.markup.includes("selected bottom item"), true);
    assert.strictEqual(
        list.scrollTop,
        720,
        "selecting a candidate near the bottom must preserve the sidebar scroll position"
    );

    list.scrollTop = 900;
    list.scrollHeight = 600;
    logic.replaceScrollableContent(list, "<button>shorter list</button>");
    assert.strictEqual(
        list.scrollTop,
        200,
        "a shorter refreshed list must clamp the restored position to its new scroll range"
    );

    list.scrollTop = 200;
    logic.replaceScrollableContent(list, "<button>latest item</button>", { preserve: false });
    assert.strictEqual(list.scrollTop, 0, "follow-latest rendering must remain free to choose a new position");
}

{
    const items = [
        candidate({ requestId: "filter-video", ext: "mp4", type: "video/mp4", role: undefined, groupKey: "", duration: 0, _size: 20 * 1024 * 1024 }),
        candidate({ requestId: "filter-audio", ext: "m4a", type: "audio/mp4", role: undefined, groupKey: "", duration: 0, url: "https://media.example/audio.m4a", _size: 3 * 1024 * 1024 }),
        candidate({ requestId: "filter-duplicate", ext: "mp4", type: "video/mp4", role: undefined, groupKey: "", duration: 0, name: "same.mp4", url: "https://media.example/same-1.mp4" }),
        candidate({ requestId: "filter-duplicate-2", ext: "mp4", type: "video/mp4", role: undefined, groupKey: "", duration: 0, name: "same.mp4", url: "https://media.example/same-2.mp4" })
    ];
    assert.strictEqual(logic.filterCandidates(items, { mediaType: "video" }).length, 3);
    assert.strictEqual(logic.filterCandidates(items, { extension: "m4a" }).length, 1);
    assert.strictEqual(logic.filterCandidates(items, { minimumSize: 10 * 1024 * 1024 }).length, 1);
    assert.strictEqual(logic.filterCandidates(items, { regex: "audio\\.m4a$" }).length, 1);
    assert.strictEqual(logic.filterCandidates(items, { dedupe: true }).length, 3);
    assert.strictEqual(logic.isSafeFilterRegex("(a+)+$"), false, "nested quantifiers must be rejected");
    assert.strictEqual(logic.isSafeFilterRegex("video|audio"), true);
}

testValidatedTaskStart().then(
    () => console.log("Popup grouping and task logic OK"),
    error => {
        console.error(error);
        process.exitCode = 1;
    }
);
