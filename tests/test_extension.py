from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from idm_eagle_bridge.constants import (
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_NAME,
    APP_SLOGAN,
    BRAND_NAME,
    DESKTOP_COMPONENT_NAME,
    EXTENSION_COMPONENT_NAME,
    INSTALLER_COMPONENT_NAME,
)


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "chrome-extension"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for extension checks")
class ExtensionTests(unittest.TestCase):
    def test_product_brand_hierarchy_is_consistent(self) -> None:
        self.assertEqual(BRAND_NAME, "留底")
        self.assertEqual(APP_NAME, "留底下载器")
        self.assertEqual(APP_DESCRIPTION, "免费开源的 Windows 本机媒体下载与归档工具")
        self.assertEqual(APP_SLOGAN, "想留的，留个底。")
        self.assertEqual(DESKTOP_COMPONENT_NAME, "留底桌面端")
        self.assertEqual(EXTENSION_COMPONENT_NAME, "留底浏览器扩展")
        self.assertEqual(INSTALLER_COMPONENT_NAME, "留底安装器")
        self.assertEqual(APP_AUTHOR, "阿毅i")

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
            self.assertEqual(manifest["version"], "1.6.0")
            self.assertEqual(manifest["name"], "留底浏览器扩展")
            self.assertEqual(manifest["action"]["default_title"], "留底浏览器扩展")
            self.assertEqual(manifest["description"], "免费开源的 Windows 本机媒体下载与归档工具")
            scripts = [script for entry in manifest["content_scripts"] for script in entry["js"]]
            self.assertIn("js/bilibili-content.js", scripts)
            self.assertIn("js/youtube-content.js", scripts)
            resources = [resource for entry in manifest["web_accessible_resources"] for resource in entry["resources"]]
            self.assertIn("catch-script/bilibili.js", resources)
            self.assertIn("catch-script/youtube.js", resources)
        setup = (ROOT / "installer" / "Setup.cs").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
        self.assertIn('internal const string Version = "1.6.0"', setup)
        self.assertIn('AssemblyFileVersion("1.6.0.0")', setup)
        self.assertIn('AssemblyFileVersion("1.6.0.0")', launcher)
        version_resource = (ROOT / "packaging" / "liudi-downloader-version.txt").read_text(encoding="utf-8")
        self.assertIn("filevers=(1, 6, 0, 0)", version_resource)
        self.assertIn("prodvers=(1, 6, 0, 0)", version_resource)
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

    def test_clicking_a_sidebar_candidate_does_not_rebuild_the_scroller(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        click_start = ui.index('const groupButton = event.target.closest("[data-group-id]")')
        click_end = ui.index('const batchAction = event.target.closest("[data-batch-action]")', click_start)
        click_source = ui[click_start:click_end]

        self.assertIn("logic.patchSidebarSelection", click_source)
        self.assertNotIn("renderSidebar();", click_source)

    def test_spa_navigation_restarts_generic_discovery(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        content = (EXTENSION / "js" / "content-script.js").read_text(encoding="utf-8")
        candidate_logic = (EXTENSION / "js" / "eagle-bridge-candidate-logic.js").read_text(
            encoding="utf-8"
        )
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
        self.assertIn("function shouldClearCapturedCandidates", candidate_logic)
        self.assertIn('"tabLocationChanged"', ui)

        apply_start = background.index("function applyTabLocationChange")
        apply_end = background.index("\nfunction handleTabLocationChange", apply_start)
        spa_navigation_handler = background[apply_start:apply_end]
        self.assertIn("shouldClearCapturedCandidates", spa_navigation_handler)
        self.assertIn("invalidateCapturedTabContext", spa_navigation_handler)
        self.assertNotIn("[1, 2].includes", spa_navigation_handler)

        handler_start = background.index("function handleTabLocationChange")
        handler_end = background.index("\nfunction isSupportedWebTab", handler_start)
        generic_handler = background[handler_start:handler_end].lower()
        for site_name in ("bilibili", "youtube", "douyin", "vimeo"):
            self.assertNotIn(site_name, generic_handler)

    def test_navigation_cleanup_cannot_delete_media_from_a_new_document_late(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        before_start = background.index("chrome.webNavigation.onBeforeNavigate.addListener")
        before_end = background.index(
            "chrome.webNavigation.onHistoryStateUpdated.addListener",
            before_start,
        )
        before_navigate = background[before_start:before_end]
        updated_start = background.index("chrome.tabs.onUpdated.addListener")
        updated_end = background.index(
            "chrome.webNavigation.onCommitted.addListener",
            updated_start,
        )
        tab_updated = background[updated_start:updated_end]
        committed_start = updated_end
        committed_end = background.index(
            "chrome.tabs.onRemoved.addListener",
            committed_start,
        )
        committed = background[committed_start:committed_end]
        find_start = background.index("function findMedia")
        find_end = background.index("//正则匹配", find_start)
        media_startup = background[find_start:find_end]

        self.assertIn(
            'clearCapturedTabForNavigation(details.tabId, "loading")',
            before_navigate,
        )
        self.assertNotIn('chrome.alarms.get("save"', tab_updated)
        self.assertNotIn("delete cacheData[tabId]", tab_updated)
        self.assertIn(
            'clearCapturedTabForNavigation(details.tabId, "committed")',
            committed,
        )
        self.assertLess(
            media_startup.index("flushPendingDocumentCleanup(data.tabId)"),
            media_startup.index("data.getTime = Date.now()"),
        )

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

    def test_popup_uses_automatic_desktop_connection_without_pairing_code(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")

        self.assertIn('data-action="auto-connect"', ui)
        self.assertIn('eagleBridge: "autoPair"', ui)
        self.assertIn('"/api/pair/recover"', bridge)
        self.assertNotIn("bridgePairCode", ui)
        self.assertNotIn("pairPlaceholder", ui)
        self.assertNotIn('case "pair":', bridge)

        connect_start = ui.index("async function autoConnect()")
        connect_end = ui.index("async function changeSite", connect_start)
        connect_source = ui[connect_start:connect_end]
        self.assertLess(
            connect_source.index("await refreshConnection()"),
            connect_source.index('showToast(t("connectionDone"))'),
        )
        self.assertIn("response.data?.paired", connect_source)
        connection_start = ui.index("async function refreshConnection()")
        connection_end = ui.index("async function refreshCandidates", connection_start)
        self.assertIn('eagleBridge: "health"', ui[connection_start:connection_end])

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
        self.assertIn("deleteAfterImport: false", ui)
        self.assertIn("本机下载文件会保留", ui)
        self.assertNotIn('downloadImport: "导入 Eagle（成功后删本机文件）"', ui)
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

    def test_popup_connection_and_polling_are_race_safe(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        self.assertIn("logic.createLatestRequestGate()", ui)
        self.assertIn("connectionRequestGate.isCurrent(requestTicket)", ui)
        self.assertIn("planRequestGate.isCurrent(requestTicket)", ui)
        self.assertIn("candidateRequestGate.isCurrent(requestTicket)", ui)
        poll_start = ui.index("function scheduleTaskPoll")
        poll_end = ui.index("async function stopTask", poll_start)
        poll_source = ui[poll_start:poll_end]
        self.assertNotIn(
            "if (!state.paired) return;",
            poll_source,
            "an open popup must keep probing so a restarted desktop reconnects automatically",
        )
        self.assertIn("if (state.disposed) return;", poll_source)
        refresh_connection = poll_source.index("await refreshConnection()")
        repaint = poll_source.index("renderInspector();", refresh_connection)
        self.assertIn("if (state.disposed) return;", poll_source[refresh_connection:repaint])

    def test_page_switch_async_reads_use_latest_request_gates(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        for gate in (
            "tabRequestGate",
            "candidateRequestGate",
            "toolStateRequestGate",
            "siteRequestGate",
        ):
            self.assertIn(f"const {gate} = logic.createLatestRequestGate();", ui)
            self.assertIn(f"{gate}.isCurrent(requestTicket)", ui)
            self.assertIn(f"{gate}.invalidate()", ui)
        tracked_start = ui.index("async function refreshTrackedPage()")
        tracked_end = ui.index("function scheduleTrackedPageRefresh", tracked_start)
        self.assertIn("if (!await refreshTab()) return false;", ui[tracked_start:tracked_end])

    def test_site_status_refresh_cannot_cancel_an_active_site_change(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        site_start = ui.index("async function refreshSite()")
        site_end = ui.index("async function refreshToolState", site_start)
        site_source = ui[site_start:site_end]
        self.assertLess(
            site_source.index("if (state.siteLoading) return false;"),
            site_source.index("siteRequestGate.begin()"),
        )

    def test_bulk_local_download_disables_actions_while_submitting(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bulk_start = ui.index("async function bulkDownloadOnly()")
        bulk_end = ui.index("function bulkCopyLinks", bulk_start)
        bulk_source = ui[bulk_start:bulk_end]
        busy_start = bulk_source.index("state.busy = true;")
        first_submit = bulk_source.index("createPlanForGroup(group, false)")
        self.assertIn("renderInspector();", bulk_source[busy_start:first_submit])

    def test_popup_and_bridge_requests_have_bounded_waits(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        send_start = ui.index("function send(payload)")
        send_end = ui.index("function asset", send_start)
        self.assertIn("setTimeout", ui[send_start:send_end])
        self.assertIn("clearTimeout", ui[send_start:send_end])
        self.assertIn("EagleBridgeAuthLogic.fetchJsonWithTimeout", bridge)
        self.assertNotIn("await fetch(", bridge)

    def test_candidate_refresh_preserves_visible_media_on_transport_failure(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        refresh_start = ui.index("async function refreshCandidates()")
        refresh_end = ui.index("function resetTabScopedUi", refresh_start)
        refresh_source = ui[refresh_start:refresh_end]
        self.assertIn("Promise.allSettled", refresh_source)
        self.assertIn('allResult.status !== "fulfilled"', refresh_source)
        self.assertNotIn("send({ Message: \"getAllData\" }).catch", refresh_source)

    def test_large_capture_sessions_persist_a_recent_bounded_window(self) -> None:
        background = (EXTENSION / "js" / "background.js").read_text(encoding="utf-8")
        functions = (EXTENSION / "js" / "function.js").read_text(encoding="utf-8")
        self.assertNotIn("cacheData[tabId]?.length <= 99", background)
        self.assertIn("boundedMediaSnapshot", functions)
        self.assertNotIn("cacheData[data.tabId] = [];", background)

    def test_popup_wait_budget_covers_auth_recovery_and_one_retry(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        bridge = (EXTENSION / "js" / "eagle-bridge.js").read_text(encoding="utf-8")
        popup_timeout = int(re.search(r"POPUP_REQUEST_TIMEOUT_MS\s*=\s*(\d+)", ui).group(1))
        api_timeout = int(re.search(r"EAGLE_BRIDGE_API_TIMEOUT_MS\s*=\s*(\d+)", bridge).group(1))
        pair_timeout = int(re.search(r"EAGLE_BRIDGE_AUTO_PAIR_TIMEOUT_MS\s*=\s*(\d+)", bridge).group(1))
        self.assertGreaterEqual(popup_timeout, api_timeout * 2 + pair_timeout * 2 + 500)

    def test_popup_teardown_cancels_every_owned_timer(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        teardown = ui[ui.index('window.addEventListener("beforeunload"'):]
        for timer in (
            "state.taskTimer",
            "state.candidateTimer",
            "state.snapshotTimer",
            "state.locationTimer",
            "toastTimer",
        ):
            self.assertIn(f"clearTimeout({timer})", teardown)
        self.assertIn("state.disposed = true", teardown)
        self.assertIn(".invalidate()", teardown)

    def test_desktop_delivery_fallback_immediately_switches_to_local_mode(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        self.assertIn('plan?.deliveryFallback !== "local"', ui)
        self.assertIn("state.eagleAvailable = false", ui)
        self.assertIn('t("deliveryFallbackLocal")', ui)

    def test_optional_eagle_and_task_status_text_cover_all_locales(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        for key in (
            "desktopUnavailable",
            "desktopUnavailableHint",
            "eagleUnavailable",
            "eagleOptionalHint",
            "deliveryFallbackLocal",
            "resolverYoutubeInfo",
            "resolverInfo",
        ):
            self.assertEqual(ui.count(f"{key}:"), 3, f"{key} must have Simplified Chinese, Traditional Chinese, and English text")
        self.assertIn("const taskStatusLabels = {", ui)
        self.assertIn("const taskStatusLabel = task =>", ui)
        self.assertIn("escapeHtml(taskStatusLabel(task))", ui)

    def test_popup_locales_do_not_fall_back_to_simplified_chinese(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")

        def locale_keys(name: str, next_name: str) -> set[str]:
            start = ui.index(f"const {name} = {{")
            end = ui.index(f"const {next_name} =", start)
            return set(re.findall(r'(?:^|,)\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*"', ui[start:end]))

        simplified = locale_keys("zhHans", "zhHant")
        self.assertEqual(locale_keys("zhHant", "en"), simplified)
        self.assertEqual(locale_keys("en", "taskStatusLabels"), simplified)

    def test_visual_popup_fixture_can_render_connection_matrix(self) -> None:
        fixture = (ROOT / "tests" / "visual_popup_fixture.js").read_text(encoding="utf-8")
        self.assertIn('fixtureParams.get("eagle") !== "0"', fixture)
        self.assertIn('fixtureParams.get("desktop") !== "0"', fixture)
        self.assertIn("{ ok: true, data: { eagleAvailable } }", fixture)
        self.assertIn("serviceReachable: desktopAvailable", fixture)

    def test_live_candidate_message_invalidates_older_snapshot_reads(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        message_start = ui.index('if (message?.Message !== "popupAddData") return;')
        message_end = ui.index("clearTimeout(state.candidateTimer)", message_start)
        self.assertIn("candidateRequestGate.invalidate()", ui[message_start:message_end])

    def test_every_rendered_popup_action_has_a_dispatch_branch(self) -> None:
        ui = (EXTENSION / "js" / "eagle-bridge-ui.js").read_text(encoding="utf-8")
        rendered = set(re.findall(r'data-action=["\']([^"\']+)', ui))
        handled = set(re.findall(r'action === ["\']([^"\']+)', ui))
        self.assertTrue(rendered)
        self.assertEqual(rendered - handled, set())

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
