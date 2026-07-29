from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "chrome-extension"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for extension checks")
class ExtensionTests(unittest.TestCase):
    def test_all_javascript_has_valid_syntax(self) -> None:
        files = sorted(EXTENSION.rglob("*.js"))
        self.assertGreaterEqual(len(files), 10)
        for file in files:
            with self.subTest(file=file.relative_to(ROOT)):
                subprocess.run(
                    ["node", "--check", str(file)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )

    def test_manifests_are_versioned_and_include_structured_site_bridges(self) -> None:
        for name in ("manifest.json", "manifest.firefox.json"):
            manifest = json.loads((EXTENSION / name).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "1.4.5")
            self.assertEqual(manifest["name"], "下载中转站")
            scripts = [script for entry in manifest["content_scripts"] for script in entry["js"]]
            self.assertIn("js/bilibili-content.js", scripts)
            self.assertIn("js/youtube-content.js", scripts)
            resources = [resource for entry in manifest["web_accessible_resources"] for resource in entry["resources"]]
            self.assertIn("catch-script/bilibili.js", resources)
            self.assertIn("catch-script/youtube.js", resources)
        setup = (ROOT / "installer" / "Setup.cs").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
        self.assertIn('internal const string Version = "1.4.5"', setup)
        self.assertIn('AssemblyFileVersion("1.4.5.0")', setup)
        self.assertIn('AssemblyFileVersion("1.4.5.0")', launcher)
        version_resource = (ROOT / "packaging" / "download-transfer-station-version.txt").read_text(encoding="utf-8")
        self.assertIn("filevers=(1, 4, 5, 0)", version_resource)
        self.assertIn("prodvers=(1, 4, 5, 0)", version_resource)
        self.assertGreaterEqual(setup.count("WriteBootstrapPairing(extensionDirectory"), 3)

    def test_bilibili_playinfo_becomes_grouped_video_and_audio(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_bilibili.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("Bilibili metadata bridge OK", result.stdout)

    def test_wechat_channels_bridge_submits_registered_current_video_without_downloading_in_page(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_wechat_channels_bridge.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("wechat channels bridge tests passed", result.stdout)
        bridge = (
            ROOT / "src" / "idm_eagle_bridge" / "assets" / "wechat_channels_bridge.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("chrome.downloads", bridge)
        self.assertNotIn("WebAssembly", bridge)
        self.assertNotIn("/poll?token=", bridge)
        self.assertNotIn("eval(", bridge)
        self.assertNotIn('action: "submit"', bridge)
        self.assertIn('action: "download"', bridge)
        self.assertIn("objectId: entry.feed.objectId", bridge)
        self.assertIn("variantId: variantId", bridge)
        self.assertIn(".slides-item .click-box.op-item", bridge)
        self.assertIn("download-station-wechat-control", bridge)

    def test_youtube_player_response_becomes_grouped_video_and_audio(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_youtube.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("YouTube structured format bridge OK", result.stdout)
        youtube = (EXTENSION / "catch-script" / "youtube.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertIn('resolver: "youtube"', youtube)
        self.assertIn('qualitySource: "youtube_player_catalog"', youtube)
        self.assertIn("youtubeRequestContextByTab", background)
        self.assertIn('data.mediaMeta?.resolver === "youtube"', background)
        self.assertIn('resolver: ["youtube", "page"].includes(data.resolver) ? data.resolver : ""', bridge)

    def test_popup_groups_content_and_validates_actions(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_popup_logic.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("Popup grouping and task logic OK", result.stdout)

        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        css = (EXTENSION / "css" / "eagle-bridge.css").read_text(encoding="utf-8")
        self.assertIn('video class="bridge-remote-preview', ui)
        self.assertIn('preload="metadata"', ui)
        self.assertIn('root.addEventListener("loadedmetadata"', ui)
        self.assertIn(".bridge-remote-preview", css)
        logic = (EXTENSION / "js" / "eagle-bridge-ui-logic.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        self.assertIn("function mediaAliasIdentity", logic)
        self.assertNotIn("const unboundPlayback", logic)
        self.assertIn('group?.segmentOnly ? "segment" : ""', logic)
        self.assertIn("technicalOnly", logic)
        self.assertIn("explicitAliasOwners", logic)
        self.assertIn("function fixedByteRange", logic)
        self.assertIn("fixedByteRange(candidate)", logic)
        self.assertIn('item.name == "content-md5"', background)
        self.assertIn("contentIdentity: data.header?.contentIdentity", background)

    def test_task_history_can_be_cleared_from_the_popup(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")

        self.assertIn('data-action="clear-tasks"', ui)
        self.assertIn('eagleBridge: "clearPlans"', ui)
        self.assertIn('case "clearPlans"', bridge)
        self.assertIn('"/api/media/clear"', bridge)

    def test_each_popup_task_can_be_removed_while_preserving_downloads(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")

        self.assertIn('data-action="remove-task"', ui)
        self.assertIn('eagleBridge: "removePlan"', ui)
        self.assertIn('case "removePlan"', bridge)
        self.assertIn('"/api/media/remove"', bridge)
        self.assertIn("Downloaded files and Eagle content will be kept.", ui)

    def test_clearing_current_media_invalidates_in_flight_capture_callbacks(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")

        self.assertIn("const captureGenerationByTab = new Map()", background)
        self.assertIn("function clearCapturedTab(tabId, resetDedupe = false)", background)
        self.assertGreaterEqual(
            background.count(
                "(captureGenerationByTab.get(data.tabId) || 0) !== captureGeneration"
            ),
            3,
        )

    def test_large_candidate_bursts_do_not_regroup_or_load_every_preview_eagerly(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        css = (EXTENSION / "css" / "eagle-bridge.css").read_text(encoding="utf-8")

        ingest_start = background.index("// 储存数据")
        ingest_end = background.index("// 当前标签媒体数量大于100", ingest_start)
        ingest_source = background[ingest_start:ingest_end]
        self.assertIn("scheduleVisibleMediaCount(info.tabId)", ingest_source)
        self.assertNotIn("visibleMediaCount(cacheData[info.tabId])", ingest_source)

        sidebar_start = ui.index("function renderSidebar")
        sidebar_end = ui.index("function candidateOption", sidebar_start)
        sidebar_source = ui[sidebar_start:sidebar_end]
        self.assertNotIn("mediaPreviewMarkup(", sidebar_source)
        self.assertIn("sidebarPreviewMarkup(", sidebar_source)
        self.assertIn("content-visibility: auto", css)

    def test_spa_navigation_restarts_generic_discovery(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        content = (EXTENSION / "js" / "content-script.js").read_text(encoding="utf-8")
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")

        self.assertNotIn(
            "chrome.webNavigation.onHistoryStateUpdated.addListener(function () { return; });",
            background,
        )
        self.assertIn("function handleTabLocationChange", background)
        self.assertIn("onReferenceFragmentUpdated", background)
        self.assertIn('"pageLocationChanged"', background)
        self.assertIn('"notifyPageLocationChanged"', content)
        self.assertIn("function resetPageDiscovery", content)
        self.assertIn("_framePreviewCache.clear()", content)
        self.assertIn("_structuredCatalogSent.clear()", content)
        self.assertIn("_pageResolverSent.clear()", content)
        self.assertIn("createLocationChangeTracker", content)
        self.assertIn('"tabLocationChanged"', ui)

        handler_start = background.index("function handleTabLocationChange")
        handler_end = background.index("\nfunction isSupportedWebTab", handler_start)
        generic_handler = background[handler_start:handler_end].lower()
        for site_name in ("bilibili", "youtube", "douyin", "vimeo"):
            self.assertNotIn(site_name, generic_handler)

    def test_standalone_window_follows_the_latest_active_web_tab(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")

        self.assertIn("function rememberActiveWebTab", background)
        self.assertIn("function resolveActiveWebTab", background)
        self.assertIn('"activeWebTabChanged"', background)
        self.assertIn('Message.Message == "getActiveWebTab"', background)
        self.assertIn("popup.html?standalone=1&sourceTabId=", ui)
        self.assertIn("if (isStandaloneWindow)", ui)
        self.assertIn('Message: "getActiveWebTab"', ui)
        self.assertIn('message?.Message === "activeWebTabChanged"', ui)
        self.assertNotIn("popup.html?tabId=${state.tab?.id", ui)

    def test_candidate_presentation_is_cross_site_and_snapshot_safe(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_candidate_presentation.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("Cross-site candidate presentation and startup snapshot OK", result.stdout)
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        scripts = manifest["content_scripts"][0]["js"]
        self.assertLess(scripts.index("js/eagle-bridge-candidate-logic.js"), scripts.index("js/content-script.js"))
        content = (EXTENSION / "js" / "content-script.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        init = (EXTENSION / "js" / "init.js").read_text(encoding="utf-8")
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertIn('Message.Message == "getMediaVisualContext"', content)
        self.assertIn("captureVideoFrame", content)
        self.assertIn("stableVisualKey", content)
        self.assertIn("discoverStructuredPlayerMedia", content)
        self.assertIn("parseVimeoPlayerConfig", content)
        self.assertIn("parseManifestQualities", background)
        self.assertIn("parseInstagramCdnMetadata", background)
        self.assertIn("reconstructByteRangeUrl", (EXTENSION / "js" / "eagle-bridge-candidate-logic.js").read_text(encoding="utf-8"))
        self.assertIn("chooseContentPageUrl", content)
        self.assertIn("chooseNearbyContentPageUrl", content)
        self.assertIn("nearbyVideoContent", content)
        self.assertIn("chooseStructuredVideoPageUrl", content)
        self.assertIn('qualitySource: "structured_page_metadata"', content)
        self.assertIn("selectContentTitle", content)
        self.assertIn("discoverPageResolvers", content)
        self.assertIn('Message.Message == "discoverPageResolvers"', content)
        self.assertIn('eagleBridge: "ensureDiscovery"', ui)
        self.assertIn('case "ensureDiscovery"', bridge)
        self.assertIn("resolverRequestContextByTab", background)
        self.assertIn('data.mediaMeta?.resolver === "page"', background)
        self.assertIn('["youtube", "page"].includes(data.resolver)', (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8"))
        self.assertIn("enrichManifestQualities(info)", background)
        self.assertIn("getMediaVisualContext(data.tabId, data.frameId, data.url)", background)
        self.assertIn("info.playerHeight", background)
        self.assertIn("info.availableQualities", background)
        candidate_logic = (EXTENSION / "js" / "eagle-bridge-candidate-logic.js").read_text(encoding="utf-8")
        self.assertIn("canonicalDouyinVideoUrl", candidate_logic)
        self.assertIn("selectPrimaryPageVideo", candidate_logic)
        self.assertIn("douyin_current_player", content)
        self.assertIn("douyin_feed_player", content)
        self.assertIn("douyinVideoIdFromSignals", content)
        self.assertIn("unboundDouyinMedia", background)
        self.assertNotIn("videoIndex !== douyinPrimaryIndex", content)
        self.assertIn('first.resolver === "page" ? first.url', bridge)
        self.assertIn("mediaFramePreviewCache", background)
        self.assertIn('Message.Message == "getMediaPreviews"', background)
        self.assertIn("waitForSnapshot", background)
        self.assertIn("G.initMediaComplete = true", init)
        self.assertIn("EagleBridgeUILogic.groupCandidates", background)
        self.assertIn("framePreviews: new Map()", ui)
        self.assertNotIn("captureVisiblePreview", ui)

    def test_pairing_token_is_not_cleared_by_a_stale_unauthorized_response(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "js" / "test_auth_race.js")],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertIn("Pairing token race recovery OK", result.stdout)
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertLess(
            background.index("eagle-bridge-auth-logic.js"),
            background.index("/bootstrap.js", background.index("eagle-bridge-auth-logic.js")),
        )
        self.assertIn("EagleBridgeAuthLogic.unauthorizedAction", bridge)
        self.assertIn("EagleBridgeAuthLogic.createStateUpdateQueue", bridge)
        self.assertIn("current.token === requestToken", bridge)
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        pair_start = ui.index("async function pair()")
        pair_end = ui.index("async function changeSite", pair_start)
        pair_source = ui[pair_start:pair_end]
        self.assertLess(pair_source.index('eagleBridge: "health"'), pair_source.index('showToast(t("pairingDone"))'))
        self.assertIn("auth.data?.paired", pair_source)

    def test_popup_has_one_visible_ui_and_only_discovery_routes(self) -> None:
        popup = (EXTENSION / "popup.html").read_text(encoding="utf-8")
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        css = (EXTENSION / "css" / "eagle-bridge.css").read_text(encoding="utf-8")
        self.assertEqual(popup.count('id="eagleBridgeRoot"'), 1)
        self.assertNotIn('id="legacyCatCatchRuntime"', popup)
        self.assertNotIn("#legacyCatCatchRuntime[hidden]", css)
        self.assertNotIn('src="js/popup.js"', popup)
        self.assertNotIn('src="js/media-control.js"', popup)
        self.assertNotIn('src="lib/mqtt.min.js"', popup)
        self.assertNotIn('src="lib/hls.min.js"', popup)
        self.assertIn('src="js/eagle-bridge-ui-logic.js"', popup)
        for route in ("script:search", "data-batch-action", "data-filter", "showSegments", "import-task"):
            self.assertIn(route, ui)
        for removed_route in (
            "script:catch", "script:recorder", "script:webrtc", "script:recorder2",
            "advanced-tools", "possible-keys", "open-options", "data-player-action",
        ):
            self.assertNotIn(removed_route, ui)
        self.assertFalse((EXTENSION / "background.js").exists())
        self.assertFalse((EXTENSION / "js" / "popup.js").exists())
        self.assertFalse((EXTENSION / "js" / "media-control.js").exists())
        setup = (ROOT / "installer" / "Setup.cs").read_text(encoding="utf-8")
        self.assertIn("DeleteObsoleteOwnedExtensionFiles(installDirectory)", setup)
        for obsolete_path in ("background.js", "popup.js", "media-control.js"):
            self.assertIn(f'"{obsolete_path}"', setup)
        for removed_route in (
            "open:downloader.html", "browser-ffmpeg-add", "browser-merge",
            "header-download", 'toolButton("auto"', 'data-batch-action="send-local"',
            "open:json.html", "legacy:keys", "send-keys",
        ):
            self.assertNotIn(removed_route, ui)
        self.assertIn('document.documentElement.classList.add("bridge-expanded")', ui)
        self.assertIn("@media (max-width: 599px)", css)
        self.assertIn("logic.manifestLabel", ui)
        self.assertIn("logic.directLabel", ui)
        self.assertIn("qualityCountLabel", ui)
        self.assertIn("qualitySourceHint", ui)

    def test_obsolete_browser_download_entrypoints_are_removed(self) -> None:
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        init = (EXTENSION / "js" / "init.js").read_text(encoding="utf-8")
        self.assertEqual(set(manifest.get("commands", {})), {"_execute_action"})
        self.assertNotIn("contextMenus", manifest.get("permissions", []))
        self.assertNotIn("downloads", manifest.get("permissions", []))
        self.assertNotIn("declarativeNetRequest", manifest.get("permissions", []))
        self.assertNotIn("options_ui", manifest)
        self.assertNotIn("chrome.commands.onCommand", background)
        self.assertNotIn("chrome.contextMenus", background)
        self.assertNotIn("catCatchFFmpeg", background)
        self.assertNotIn("mobileUserAgent", background)
        self.assertNotIn("contextMenusInit", init)
        for obsolete in (
            "downloader.html", "install.html", "json.html", "m3u8.html", "mpd.html",
            "options.html", "preview.html", "popup.js",
        ):
            self.assertFalse((EXTENSION / obsolete).exists(), obsolete)
        setup = (ROOT / "installer" / "Setup.cs").read_text(encoding="utf-8")
        for obsolete in ('"downloader.html"', '"options.html"', '"preview.html"', '"img"', '"lib"', '"tools"', '"_locales"'):
            self.assertIn(obsolete, setup)
        self.assertIn("Directory.Delete(target, true)", setup)

    def test_loaded_extension_can_reload_after_desktop_patch_upgrade(self) -> None:
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertIn("eagleBridgeCheckDesktopVersion", bridge)
        self.assertIn("chrome.runtime.reload()", bridge)
        self.assertIn("eagleBridgeVersionCheck", bridge)

    def test_popup_referenced_design_assets_exist(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        for asset in (
            "icons/icon-16.png", "icons/icon-128.png", "icons/action-search.svg",
        ):
            with self.subTest(asset=asset):
                self.assertIn(asset, ui)
                self.assertTrue((EXTENSION / asset).is_file())
        self.assertFalse((EXTENSION / "img").exists())

    def test_popup_uses_per_group_selection_and_multi_task_state(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertIn("selections: new Map()", ui)
        self.assertIn("drafts: new Map()", ui)
        self.assertIn('eagleBridge: "plans"', ui)
        self.assertIn('eagleBridge: "retryPlan"', ui)
        self.assertNotIn('eagleBridge: "planDownloads"', ui)
        self.assertNotIn('case "planDownloads"', bridge)
        self.assertNotIn("model.planId", ui)

    def test_sensitive_media_cache_never_falls_back_to_local_storage(self) -> None:
        function_js = (EXTENSION / "js" / "function.js").read_text(encoding="utf-8")
        background_js = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        self.assertIn("if (!chrome.storage.session)", function_js)
        self.assertNotIn("chrome.storage.session ?? chrome.storage.local).set({ MediaData", background_js)
        self.assertNotIn("chrome.storage.local.clear", background_js)
        self.assertIn('chrome.storage.local.remove(["MediaData"]', background_js)

    def test_unsafe_regular_expressions_are_disabled(self) -> None:
        function_js = (EXTENSION / "js" / "function.js").read_text(encoding="utf-8")
        init_js = (EXTENSION / "js" / "init.js").read_text(encoding="utf-8")
        self.assertIn("function isSafeRegularExpression", function_js)
        self.assertIn("!isSafeRegularExpression(item.regex)", init_js)

    def test_primary_ui_has_no_browser_or_third_party_download_route(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        init_js = (EXTENSION / "js" / "init.js").read_text(encoding="utf-8")
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("browserFfmpeg", ui)
        self.assertNotIn("chrome.downloads", bridge)
        self.assertIn('route: "desktop"', bridge)
        self.assertIn("importToEagle: options.importToEagle !== false", bridge)
        self.assertIn(
            "deleteAfterImport: options.deleteAfterImport === true",
            bridge,
        )
        self.assertIn("deleteAfterImport: importToEagle", ui)
        self.assertIn("成功后删除本机下载文件", ui)
        self.assertNotIn('command == "auto_down"', background)
        self.assertNotIn('Message.Message == "autoDown"', background)
        self.assertNotIn('if (G.send2local)', background)
        self.assertNotIn('id: "auto_down"', init_js)
        self.assertNotIn("auto_down", manifest.get("commands", {}))
        for obsolete in ("preview.js", "downloader.js", "desktop-parser-route.js", "m3u8.js", "mpd.js"):
            self.assertFalse((EXTENSION / "js" / obsolete).exists(), obsolete)
        self.assertNotIn("downloads", manifest.get("permissions", []))

    def test_content_script_only_exposes_discovery_and_preview_context(self) -> None:
        content = (EXTENSION / "js" / "content-script.js").read_text(encoding="utf-8")
        for kept in ("getMediaVisualContext", "getEmbeddingFrameRect", "downloadTransferAddMedia"):
            self.assertIn(kept, content)
        for removed in (
            "getVideoState", "getKey", "getM3u8Text", "getM3u8Cache", "catCatchFFmpeg",
            "catCatchAddKey", "send2local", "screenshot", "ArrayToBase64",
        ):
            self.assertNotIn(removed, content)

    def test_eagle_plan_never_uses_site_favicon_as_media_thumbnail(self) -> None:
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        logic = (EXTENSION / "js" / "eagle-bridge-ui-logic.js").read_text(encoding="utf-8")
        self.assertIn('thumbnailUrl: String(first.thumbnailUrl || "")', bridge)
        self.assertIn("thumbnailUrl: safeUrl(item?.thumbnailUrl)", logic)
        self.assertNotIn("item?.thumbnailUrl || item?.favIconUrl", logic)

    def test_task_preview_and_output_actions_are_site_agnostic(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        content = (EXTENSION / "js" / "content-script.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        self.assertIn('eagleBridge: "planPreview"', ui)
        self.assertIn('data-action="open-task-folder"', ui)
        self.assertIn('document.querySelectorAll("video")', content)
        self.assertIn("captureRect", content)
        self.assertIn("logic.resolveVisualMatch(videos, target)", content)
        self.assertIn('visualContext.visualMatch === "exact"', background)
        for site in ("behance.net", "detail.tmall.com", "douyin.com"):
            self.assertNotIn(site, ui.lower())

    def test_all_media_headers_are_forwarded_to_the_desktop_plan_only(self) -> None:
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        firefox = json.loads((EXTENSION / "manifest.firefox.json").read_text(encoding="utf-8"))
        self.assertIn("runtimeHeaders: items.map", bridge)
        self.assertIn('"authorization", "cookie", "user-agent"', background)
        self.assertNotIn("headerRuleId", bridge)
        self.assertNotIn("chrome.downloads", bridge)
        self.assertNotIn('"/js/eagle-bridge-download-logic.js"', background)
        self.assertFalse((EXTENSION / "js" / "eagle-bridge-download-logic.js").exists())
        scripts = firefox["background"]["scripts"]
        self.assertLess(scripts.index("js/eagle-bridge.js"), scripts.index("js/background.js"))

    def test_connection_health_uses_existing_authenticated_endpoint(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        self.assertIn('case "health":\n                return eagleBridgeRead("/api/media/health");', bridge)
        self.assertIn('return eagleBridgeApi(path, {\n        method: "POST"', bridge)
        self.assertIn('return eagleBridgeRead("/api/media/plans");', bridge)
        self.assertIn('return eagleBridgeRead("/api/media/plan/get", { planId:', bridge)
        self.assertIn('return eagleBridgeRead("/api/media/preview", { planId:', bridge)
        self.assertNotIn('eagleBridgeApi("/api/media/plans")', bridge)
        self.assertNotIn('eagleBridgeApi("/api/health")', bridge)
        self.assertIn('response.status === 401', bridge)
        self.assertIn('case "autoPair":', bridge)
        self.assertIn('send({ eagleBridge: "autoPair" })', ui)
        self.assertIn('if (plan) showToast(t("downloadStarted"));', ui)
        self.assertNotIn('await downloadOnlyForGroup(group);\n            showToast(t("downloadStarted"));', ui)
        self.assertIn('case "planPreview":', bridge)
        self.assertIn('case "openPlanOutput":', bridge)

    def test_first_popup_open_revalidates_actions_after_connection_finishes(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        refresh_start = ui.index("async function refreshAll()")
        refresh_end = ui.index("function scheduleTaskPoll", refresh_start)
        refresh_source = ui[refresh_start:refresh_end]
        connection_settled = refresh_source.index("await connection;")
        inspector_refresh = refresh_source.index("renderInspector();", connection_settled)
        remaining_refreshes = refresh_source.index(
            "await Promise.allSettled", connection_settled
        )
        self.assertLess(
            connection_settled,
            inspector_refresh,
            "the popup must repaint download actions after pairing is known",
        )
        self.assertLess(
            inspector_refresh,
            remaining_refreshes,
            "the connection repaint must not wait behind discovery or plan requests",
        )

    def test_legacy_listener_never_intercepts_bridge_messages(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        listener = background.index("chrome.runtime.onMessage.addListener(function (Message, sender, sendResponse)")
        initialization_guard = background.index(
            "if (!G.initLocalComplete || !G.initSyncComplete)", listener
        )
        bridge_guard = background.index("if (Message?.eagleBridge) { return false; }", listener)
        self.assertLess(bridge_guard, initialization_guard)


if __name__ == "__main__":
    unittest.main()
