# 前端重构功能保全清单

> 目的：在重构 Chrome 扩展弹窗或桌面界面时，逐项确认现有能力没有丢失，也没有把已经退役的旧下载器重新带回运行时。
>
> 当前基线：`1.4.0`、SQLite `user_version=6`、扩展协议 `1`。最后核对：2026-07-26。

## 1. 使用方法

1. 重构开始前，给受影响的功能 ID 建立迁移映射。
2. 每完成一个界面区域，同时迁移该行列出的状态、动作、错误与恢复路径。
3. 重构完成后逐行勾选本文末尾的验收清单，并运行“回归证据”列中的测试。
4. 只有界面名称可以调整；核心语义、安全边界和 API 契约不能静默改变。
5. 如果实现与本文不一致，先核对 [`ACCEPTANCE.md`](../ACCEPTANCE.md)、[`docs/DECISIONS.md`](DECISIONS.md) 和实际代码，再同步更新本文。

本文中的“前端”包括：

- Chrome/Edge/Firefox 扩展弹窗、侧栏和内容发现脚本。
- Tk 桌面主窗口及其内嵌网站规则、网络与更新设置。
- Windows Forms 托盘菜单及其到桌面窗口的控制入口。

本文不把 `third_party/cat-catch` 归为活动前端。该目录是固定上游源码与许可证据。

## 2. 不可改变的职责边界

| 边界 | 当前规则 | 主要实现 |
| --- | --- | --- |
| 扩展 | 只发现、归组、预览、筛选、配对、记录可靠来源、提交计划和控制任务 | `chrome-extension/js/background.js`、`eagle-bridge-ui.js`、`eagle-bridge-ui-logic.js`、`eagle-bridge.js` |
| 桌面媒体引擎 | 独占远程下载、HLS/DASH、页面解析、FFmpeg 合并、FFprobe 校验、字幕、预览、文件交付和 Eagle 入队 | `src/idm_eagle_bridge/media.py:MediaCoordinator` |
| IDM | Hook 只快速写队列和唤醒；不做哈希、网络请求或媒体下载 | `src/idm_eagle_bridge/hook.py:main` |
| Eagle | 只使用 Eagle 官方本地 Web API，不修改 `.library` | `src/idm_eagle_bridge/eagle.py:EagleClient` |
| 来源 | 只有浏览器或视频号提供可靠内容页时才写入；禁止从文件名、CDN 或无来源任务猜网址 | `Database.attach_best_source`、`WechatCandidateRegistry.plan_payload` |
| 删除 | 用户原文件和 IDM 文件永不移动、删除或修改；只有明确的新版导入计划在 Eagle 成功并通过计划/目录双重归属校验后，才删除本程序创建的最终副本 | `JobProcessor._cleanup_imported_desktop_output` |

## 2.1 本次前端重构迁移映射

本次重构只替换视觉外壳、信息架构和状态型操作呈现。下列映射是实施与验收索引；消息名、API 路径、`planId` 身份、数据库状态和安全边界保持不变。

| 功能 ID | 重构后位置 | 继续复用的实现接缝 | 验收重点 |
| --- | --- | --- | --- |
| EXT-001–EXT-009 | 扩展统一标题栏、`媒体 / 任务` 主导航、设置浮层 | `initShell`、`switchView`、`refreshConnection`、`renderSettings`、现有 bridge 消息 | 单根 DOM、三语、Escape、配对/离线/来源规则和发现工具均可达 |
| EXT-010–EXT-018 | 扩展媒体列表、预览区和主动作附近阻断提示 | 现有发现脚本、`mediaPreviewMarkup`、`validateSelection` | 不改变候选身份；DRM、blob、固定 Range、纯分片与无身份内容继续阻断 |
| EXT-019–EXT-029 | 扩展紧凑候选行、检查器、筛选浮层、批量模式和技术信息 | `groupCandidates`、`partitionGroups`、逐组 `selection/draft`、`createPlanForGroup` | 归组/排序/筛选/质量/音轨/字幕/输出名和两个明确交付动作完整保留 |
| EXT-030–EXT-034 | 扩展任务页紧凑分隔列表 | `taskView`、`refreshPlans`、单一轮询器、停止/重试/打开/补导消息 | 同一 `planId`、真实进度、大小、错误、预览、终态动作和补导不重下载 |
| DESK-001–DESK-006 | 桌面左侧导航、顶部全局状态、设置页和底部诊断入口 | `MainWindow`、外层滚动、异步 Eagle 探测、增量列表、控制信号 | 四个主入口和诊断均可达；隐藏降频、更新、配对、托盘职责不变 |
| DESK-007–DESK-011 | `下载任务` 主从页 | `list_plans`、`_media_plan_view`、现有任务动作 | 媒体任务不混入 IDM；合并/校验不显示 100%；动作随状态启停 |
| DESK-012–DESK-015 | `IDM 导入` 表格与上下文操作栏 | `Database.ui_snapshot/list_jobs/retry_job/assign_source` | 状态原因完整；补来源更新既有 Eagle item；清理不碰文件或 Eagle |
| DESK-016–DESK-020 | `视频号` 主从页和双交付选择 | `WechatChannelsCaptureService`、候选/封面缓存、统一媒体计划 | 捕获生命周期、实际质量、封面、刷新/清空和代理安全恢复均保留 |
| DESK-021–DESK-025 | `设置` 的浏览器配对、网站规则、网络、更新四组 | `PairingManager`、网站规则数据库、`NetworkProxyManager`、updater | 网站规则完整 CRUD；代理校验/脱敏；更新须用户确认且错误可见 |
| CORE-001–CORE-007 | IDM 页、顶部 Eagle 状态和诊断文案 | 既有 Hook、Processor、Database、EagleClient | 等待/忽略/重复/离线/失败语义不被压缩或猜测来源 |
| CORE-008–CORE-014 | 桌面与扩展任务状态、动作和交付说明 | `MediaCoordinator`、`JobProcessor`、既有 plan/job 归属校验 | 统一状态机、`planId` 安全动作、补导幂等和导入后删除门禁不变 |
| CORE-015–CORE-017 | 全局恢复、配对/离线、视频号状态和诊断 | schema 6、loopback API、视频号证书/代理/候选服务 | 不改 schema/API；秘密不进入 UI 持久数据或诊断；恢复状态可操作 |

## 3. Chrome 扩展功能

### 3.1 应用外壳、连接与来源规则

| ID | 重构后必须保留的功能 | 前端文件与函数 | 后端/API | 回归证据 |
| --- | --- | --- | --- | --- |
| EXT-001 | 单一应用根；只有“媒体 / 任务”两级主导航，设置以面板显示，不出现第二套旧 popup | `popup.html:#eagleBridgeRoot`；`eagle-bridge-ui.js:initShell`、`switchView` | 无 | `tests/test_extension.py`、`tests/js/test_popup_logic.js`；A96、A148 |
| EXT-002 | 显示当前页面标题、域名、候选数、本机连接状态、任务数和刷新入口 | `patchHeader`、`refreshTab`、`refreshConnection`、`refreshCandidates`、`refreshPlans` | bridge 消息 `currentTab`、`health`、`plans` | `tests/js/test_popup_logic.js`；A99、A105、A125 |
| EXT-003 | popup 打开时主动探测当前 HTTP(S) 标签页；内容脚本丢失时只注入发现逻辑并立即扫描 | `refreshAll`；`eagle-bridge.js:eagleBridgeEnsureDiscovery`；`eagle-bridge-candidate-logic.js:ensureContentDiscovery` | bridge 消息 `ensureDiscovery` | `tests/test_extension.py`；A179 |
| EXT-004 | 手工六位码配对、安装器一次性自动配对、配对后健康确认、持久连接和明确离线状态 | `eagle-bridge-ui.js:pair`、`refreshConnection`；`eagle-bridge.js:eagleBridgePair`、`eagleBridgeTryAutoPair` | `POST /api/pair`、`POST /api/pair/auto`、`POST /api/media/health`；`PairingManager.pair`、`pair_with_bootstrap` | `tests/js/test_auth_race.js`、`tests/test_security_api.py`；A129、A131、A133、A135 |
| EXT-005 | 401 竞态不能清除刚写入的新令牌；所有扩展持久状态使用串行读改写队列 | `eagle-bridge-auth-logic.js:createStateUpdateQueue`、`unauthorizedAction`；`eagle-bridge.js:eagleBridgeUpdateState`、`eagleBridgeApi` | `PairingManager.authenticate` | `tests/js/test_auth_race.js`；A131、A133 |
| EXT-006 | 当前网站“记录来源并自动导入 Eagle”开关；规则关闭不影响媒体下载 | `eagle-bridge-ui.js:refreshSite`、`changeSite`、`renderSettings`；`eagle-bridge.js:eagleBridgeSiteStatus` | bridge 消息 `siteStatus`、`setSite`；`POST /api/site/status`、`POST /api/site`；`LocalApi.site_status`、`set_site` | `tests/test_security_api.py`、`tests/test_database.py`；A07–A10 |
| EXT-007 | 手动记录当前页、忽略下一次 IDM 导入、自动捕获下载点击；离线事件本地排队并补发 | `eagle-bridge-ui.js:settingsAction`；`eagle-bridge.js:eagleBridgeExplicitSource`、`eagleBridgeSourceClick`、`eagleBridgeQueueSourceEvent`、`eagleBridgeFlushEvents`；`content.js:downloadAction` | bridge 消息 `manualSource`、`ignoreNext`、`sourceClick`、`source`；`POST /api/source`；`LocalApi.add_source` | `tests/test_extension.py`、`tests/test_security_api.py`、`tests/test_database.py`；A08、A09 |
| EXT-008 | 暂停/继续当前捕获、清空当前页候选、打开独立窗口、增强发现入口 | `eagle-bridge-ui.js:runTool`、`settingsAction`；`background.js` 消息 `enable`、`clearData`、`script` | 无远程下载 API；仅扩展会话状态 | `tests/test_extension.py`、`tests/js/test_popup_logic.js`；A145–A148 |
| EXT-009 | 简体中文、繁体中文、英文文案；图标按钮有可读文本或 `aria-label`，键盘 Escape 可关闭浮层 | `eagle-bridge-ui.js:zhHans`、`zhHant`、`en`、`strings`、`t`、`icon` 及根节点事件处理 | 无 | `tests/test_extension.py`；A79、A101 |

### 3.2 媒体发现、身份与预览

| ID | 重构后必须保留的功能 | 前端文件与函数 | 后端/API | 回归证据 |
| --- | --- | --- | --- | --- |
| EXT-010 | 按扩展名、MIME、附件名和安全正则发现 HTTP(S) 媒体，保存当前标签快照并更新角标 | `background.js:findMedia`、`CheckExtension`、`CheckType`、`getResponseHeadersValue`、`save`、`updateVisibleMediaCount` | 无 | `tests/test_extension.py`、`tests/js/test_candidate_presentation.js`；A46、A50–A53 |
| EXT-011 | 只把白名单请求头作为短时任务上下文；Cookie、Authorization、完整签名 URL 和瞬时帧不得进入扩展持久存储 | `background.js:getRequestHeaders`、`youtubeRequestContextByTab`、`resolverRequestContextByTab`；`eagle-bridge.js:eagleBridgePrivateHeaders` | `MediaCoordinator.create_plan` 将运行时上下文保存在进程内存 | `tests/test_security_api.py`、`tests/test_media.py`；A80、A111、A114 |
| EXT-012 | 普通页面从 video、结构化元数据、附近内容和稳定内容页发现候选；持续 DOM 变化不能饿死扫描 | `content-script.js:discoverStructuredPlayerMedia`、`discoverPageResolvers`、`discoverStructuredPageResolver`、`startPageResolverDiscovery`；`eagle-bridge-candidate-logic.js:createBoundedScheduler`、`createKeyedBoundedScheduler` | 页面解析计划进入 `MediaCoordinator._resolve_page_streams` | `tests/js/test_candidate_presentation.js`、`tests/test_extension.py`；A159–A163、A169–A179 |
| EXT-013 | B 站从结构化播放数据提取同一内容的视频轨、音轨、标题、封面和质量，按同一内容组提交 | `bilibili-content.js`；`catch-script/bilibili.js:collect`、`publish`、`scan` | 普通 `createPlan`，本机 FFmpeg streamcopy | `tests/js/test_bilibili.js`、`tests/test_media.py`；A66、A67、A103 |
| EXT-014 | YouTube 从播放器目录提取 videoId、标题、缩略图、时长、实际唯一高度、视频/音频格式；SABR 无直链时仍保留高度选择 | `youtube-content.js`；`catch-script/youtube.js:collect`、`inspectPlayerResponse`、`publish`、`scan` | `MediaCoordinator._resolve_youtube_streams` | `tests/js/test_youtube.js`、`tests/test_media.py`；A152–A158 |
| EXT-015 | 通用 HLS/DASH 主清单在 2 MB/4 秒门禁内读取实际质量；读取失败不猜档位，也不阻止本机自动选择 | `background.js:readBoundedManifestText`、`enrichManifestQualities`；`eagle-bridge-candidate-logic.js:parseManifestQualities` | `MediaCoordinator._probe_manifest_stream_indexes`、`_select_manifest_stream_indexes` | `tests/js/test_candidate_presentation.js`、`tests/test_media.py`；A119–A124 |
| EXT-016 | 候选画面按真实 video 帧、精确播放器矩形裁剪、poster/内容图、候选自身直链预览逐级回退；不能用 favicon、整页截图或其他播放器冒充 | `content-script.js:captureVideoFrame`、`collectMediaVisualContext`、`embeddingFrameRect`；`background.js:captureVisibleVideoFrame`、`rememberMediaFrame`；`eagle-bridge-ui.js:mediaPreviewMarkup`、`thumbUrl` | 下载后预览：`GET/POST /api/media/preview`；`MediaCoordinator._create_preview`、`get_plan_preview` | `tests/js/test_candidate_presentation.js`、`tests/test_media.py`；A104、A113、A127、A137、A139 |
| EXT-017 | 瞬时帧只保存在 service worker/popup 内存，格式和大小受限；侧栏不为每个候选创建远程 video，检查区最多预览当前一项 | `background.js:mediaFramePreviewCache`、`mediaFramesForTab`；`eagle-bridge-ui.js:sidebarPreviewMarkup`、`mediaPreviewMarkup` | 无帧持久化接口 | `tests/js/test_candidate_presentation.js`；A114、A223 |
| EXT-018 | `blob:`、DRM、无可靠内容身份、固定 Range 分片和纯传输分片在提交前明确阻断，不能静默回退浏览器下载 | `eagle-bridge-ui-logic.js:fixedByteRange`、`isTransportSegment`、`validateSelection` | `MediaCoordinator.create_plan`、`_is_fixed_byte_range_url` 二次复验 | `tests/js/test_popup_logic.js`、`tests/test_media.py`；A84、A112、A143、A145 |

### 3.3 归组、筛选、版本选择与提交

| ID | 重构后必须保留的功能 | 前端文件与函数 | 后端/API | 回归证据 |
| --- | --- | --- | --- | --- |
| EXT-019 | 原始候选标准化，保留稳定身份；不同内容 ID、播放器、frame 或低置信度资源不能跨组配对 | `eagle-bridge-ui-logic.js:normalizeCandidate`、`candidateGroupId`、`groupCandidates`、`createGroup` | `MediaCoordinator.create_plan` 验证计划结构 | `tests/js/test_popup_logic.js`；A97、A115 |
| EXT-020 | 折叠签名轮换 URL 和有强证据的 CDN 别名；仅大小相同不能归并，不同 itag 必须保留 | `collapseRotatingStreams`、`mediaAliasIdentity`、`scopedAliasIdentity`、`candidateRichness` | 无 | `tests/js/test_candidate_presentation.js`；A115、A141、A153 |
| EXT-021 | 完整清单/完整媒体存在时隐藏普通 `.m4s`、`.ts` 和固定 Range 分片；纯分片默认隐藏，显式开启后只显示紧凑诊断行且不能下载 | `isTransportSegment`、`partitionGroups`；`eagle-bridge-ui.js:renderFilter`、`renderSidebar` | 桌面仍二次拒绝固定 Range | `tests/js/test_popup_logic.js`、`tests/test_media.py`；A116、A143、A145 |
| EXT-022 | 候选按捕获时间从旧到新，最新项在底部；首次自动选择最新，用户选中旧项后新候选不能抢选择 | `partitionGroups`、`defaultActiveGroupId`；`eagle-bridge-ui.js:rebuildGroups`、`renderSidebar` | 无 | `tests/js/test_popup_logic.js`；A146 |
| EXT-023 | 搜索、媒体类型、扩展名、最小大小、安全 URL 正则、同名去重和技术分片开关 | `eagle-bridge-ui.js:renderFilter`、`sourceCandidates`；`eagle-bridge-ui-logic.js:isSafeFilterRegex`、`filterCandidates` | 无 | `tests/js/test_popup_logic.js`；A56、A145 |
| EXT-024 | 每个内容组独立保存视频清晰度、音轨、字幕、清单/直链模式、输出名和预计动作 | `eagle-bridge-ui.js:renderInspector`；`eagle-bridge-ui-logic.js:createDefaultSelection`、`selectedCandidates`、`outputContainer`、`defaultOutputName`、`groupSummary` | 计划字段由 `eagleBridgeCreatePlan` 发送到 `MediaCoordinator.create_plan` | `tests/js/test_popup_logic.js`；A47、A57、A98 |
| EXT-025 | 推荐规则：完整直链优先；分轨只选一路视频和一路音频；清单与直链互斥；动态质量降序且最高档推荐 | `sortVideo`、`sortAudio`、`createDefaultSelection`、`qualityCatalogInfo`、`videoLabel`、`audioLabel`、`manifestLabel` | `MediaCoordinator._select_manifest_stream_indexes` | `tests/js/test_popup_logic.js`、`tests/js/test_youtube.js`；A66、A120–A122 |
| EXT-026 | 提交前校验配对、DRM、URL、模式、轨道数量、内容身份和清单/直链混选；只有本机返回真实计划后才显示已开始 | `eagle-bridge-ui-logic.js:validateSelection`、`startValidatedTask`；`eagle-bridge-ui.js:createPlanForGroup`、`createPlan`、`downloadOnlyForGroup` | bridge 消息 `createPlan`；`POST /api/media/plan`；`MediaCoordinator.create_plan` | `tests/js/test_popup_logic.js`、`tests/test_security_api.py`；A98、A129 |
| EXT-027 | “导入 Eagle（成功后删除本机文件）”与“仅下载”是两个明确动作；前者发送 `importToEagle=1`、`deleteAfterImport=1`，后者保留本机文件 | `createPlanForGroup`、`createPlan`、`downloadOnly` | `MediaCoordinator.create_plan`；`JobProcessor._cleanup_imported_desktop_output` | `tests/js/test_popup_logic.js`、`tests/test_media.py`、`tests/test_processor.py`；A107、A225 |
| EXT-028 | 批量模式支持全选、反选、复制链接、批量导入、批量仅下载；每个内容创建独立计划，绝不跨内容合并 | `renderBatchInspector`、`setBatchSelection`、`bulkCreatePlans`、`bulkDownloadOnly`、`bulkCopyLinks` | 每组独立调用 `POST /api/media/plan` | `tests/js/test_popup_logic.js`；A97、A106 |
| EXT-029 | 技术信息可查看脱敏 URL、类型、编码、来源并复制当前技术链接；不能新增二维码或第二下载通道 | `eagle-bridge-ui.js:rawItem`、`candidateAction`；`eagle-bridge-ui-logic.js:directLabel`、`manifestLabel` | `media.py:redact_media_url` 用于持久/诊断视图 | `tests/js/test_popup_logic.js`；A117、A148 |

### 3.4 任务页

| ID | 重构后必须保留的功能 | 前端文件与函数 | 后端/API | 回归证据 |
| --- | --- | --- | --- | --- |
| EXT-030 | 从桌面 `plans` 恢复多个任务；显示标题、缩略图、创建时间、阶段、真实百分比、处理大小、错误和输出路径 | `eagle-bridge-ui.js:renderTasks`、`refreshPlans`、`refreshTaskPreviews`；`eagle-bridge-ui-logic.js:taskView` | bridge `plans`、`planPreview`；`POST /api/media/plans`、`POST /api/media/preview`；`MediaCoordinator.list_plans`、`get_plan_preview` | `tests/js/test_popup_logic.js`、`tests/test_media.py`；A99、A107、A125 |
| EXT-031 | 所有活跃任务共用一个轮询调度器；终态停止高频轮询，重开 popup 状态不丢 | `scheduleTaskPoll`；`eagle-bridge-ui-logic.js:hasActiveTasks` | `MediaCoordinator.list_plans` | `tests/js/test_popup_logic.js`；A99、A125 |
| EXT-032 | 活跃任务可停止，失败任务可在同次运行重试；操作只影响目标 `planId` | `stopTask`、`retryTask` | bridge `stopPlan`、`retryPlan`；`POST /api/media/stop`、`POST /api/media/retry`；`MediaCoordinator.stop_plan`、`retry_plan` | `tests/js/test_popup_logic.js`、`tests/test_media.py`；A83、A99 |
| EXT-033 | `completed_local` 显示 100%、最终路径和“打开所在文件夹”；接口只接收 `planId`，不能传任意路径 | `openTaskFolder`、`taskView` | bridge `openPlanOutput`；`POST /api/media/open`；`MediaCoordinator.open_plan_output`、`_owned_plan_file` | `tests/js/test_popup_logic.js`、`tests/test_media.py`；A107、A126 |
| EXT-034 | `completed_local` 可补导 Eagle，不重新下载；重复操作幂等，进入 `ready_to_import`/Eagle 队列 | `importExistingTask`、`taskView` | bridge `importPlan`；`POST /api/media/import`；`MediaCoordinator.import_completed_plan` | `tests/js/test_popup_logic.js`、`tests/test_media.py`、`tests/test_processor.py`；A147 |

## 4. 桌面界面功能

### 4.1 主窗口与全局入口

| ID | 重构后必须保留的功能 | 桌面文件与函数 | 依赖 | 回归证据 |
| --- | --- | --- | --- | --- |
| DESK-001 | 主窗口左侧显示“下载任务 / 视频号 / IDM 导入 / 设置”，底部为诊断；顶部显示 Eagle、服务、Chrome 与版本 | `ui.py:MainWindow._build`、`_show_page` | `Database`、`LocalApiServer`、`ProcessingService` | `tests/test_ui_layout.py`、视觉 QA；A227 |
| DESK-002 | 五个页面都可到达；窗口高度不足时外层纵向滚动，Treeview/Combobox 保留自身滚轮 | `_VerticalScrolledFrame`、`MainWindow._build_*_tab` | Tk | `tests/test_ui_layout.py`、视觉 QA；A221、A228 |
| DESK-003 | 手动刷新、自动刷新和窗口隐藏降频；Eagle 慢探测后台单飞，表格只更新变化行，预览缓存复用 | `_AsyncProbe`、`_PreviewImageCache`、`_sync_tree_rows`、`MainWindow.refresh` | `Database.ui_snapshot`、`MediaCoordinator.health` | `tests/test_ui_layout.py`；A224 |
| DESK-004 | 复制六位配对码、解除 Chrome 配对并即时刷新状态 | `copy_pairing_code`、`unpair` | `PairingManager.pairing_code`、`unpair` | `tests/test_security_api.py` |
| DESK-005 | 导出脱敏诊断；不包含令牌、Cookie、完整路径、完整来源、网站规则或代理认证信息 | `export_diagnostics` | `security.py`、`network_proxy.py:proxy_endpoint_label`、各子系统 `health` | `tests/test_security_api.py`、`tests/test_wechat_channels.py`；A30、A81、A195、A212 |
| DESK-006 | 窗口可隐藏/最小化；外部 WinForms 托盘负责显示、规则、更新、唤醒、退出和单实例 | `MainWindow.show`、`hide`、`_poll_control_signals`、`quit`；`launcher/Launcher.cs:TrayApplicationContext`、`SignalEvent` | `control_signal.py` | `tests/test_control_signal.py`、`tests/test_shutdown_order.py` |

### 4.2 媒体下载标签

| ID | 重构后必须保留的功能 | 桌面文件与函数 | 后端 | 回归证据 |
| --- | --- | --- | --- | --- |
| DESK-007 | 任务表显示标题、来源、阶段、百分比、处理大小和说明 | `MainWindow._build_media_tab`、`_refresh_media_tasks` | `MediaCoordinator.list_plans` | `tests/test_ui_layout.py`、`tests/test_media.py`；A109 |
| DESK-008 | 选中任务显示本机预览、输出位置、错误和详细状态；未完成时显示明确预览状态 | `selected_plan`、`_update_plan_detail` | `MediaCoordinator.get_plan_preview` | `tests/test_ui_layout.py`、`tests/test_media.py` |
| DESK-009 | 停止、重试、打开文件位置、打开来源网页 | `stop_selected_plan`、`retry_selected_plan`、`open_plan_location`、`open_plan_source` | `MediaCoordinator.stop_plan`、`retry_plan`、`open_plan_output` | `tests/test_media.py` |
| DESK-010 | 已完成的仅下载文件可补导 Eagle，不重新下载 | `import_selected_plan` | `MediaCoordinator.import_completed_plan` | `tests/test_media.py`、`tests/test_processor.py`；A147 |
| DESK-011 | 清除已完成媒体记录只删除终态记录；不删下载/预览文件，不影响活动任务或 Eagle | `clear_media_history` | `MediaCoordinator.clear_terminal_history` | `tests/test_media.py`；A222 |

### 4.3 IDM 导入记录标签

| ID | 重构后必须保留的功能 | 桌面文件与函数 | 后端 | 回归证据 |
| --- | --- | --- | --- | --- |
| DESK-012 | 表格显示时间、状态、文件、来源网站和说明 | `MainWindow._build_idm_tab`、`refresh` | `Database.list_jobs`、`ui_snapshot` | `tests/test_ui_layout.py`、`tests/test_processor.py` |
| DESK-013 | 失败/等待任务可重试；打开文件位置和可靠来源网页 | `retry_selected`、`open_file_location`、`open_source` | `Database.retry_job` | `tests/test_processor.py` |
| DESK-014 | 可为未导入任务补充来源；已导入且有 Eagle item ID 时直接更新来源，不重复导入文件 | `assign_source` | `Database.assign_source`、`record_imported_source`；`EagleClient.update_source` | `tests/test_database.py`、`tests/test_eagle.py`；A12 |
| DESK-015 | 清除已完成 IDM 记录只删终态记录，不删 IDM/用户文件，不修改 Eagle | `clear_history` | `Database.clear_terminal_history` | `tests/test_database.py`；A222 |

### 4.4 微信视频号标签

| ID | 重构后必须保留的功能 | 桌面文件与函数 | 后端 | 回归证据 |
| --- | --- | --- | --- | --- |
| DESK-016 | 显式开始/停止受控捕获；显示关闭、准备、等待、捕获、恢复和失败状态；退出优先恢复系统代理 | `toggle_wechat_capture`、`_run_wechat_operation`、`_poll_wechat_operation` | `WechatChannelsCaptureService.start`、`stop`、`close`、`health` | `tests/test_wechat_channels.py`、`tests/test_shutdown_order.py`；A197–A201 |
| DESK-017 | 候选表显示同一 objectId 的标题、作者、时长、实际质量和捕获时间，支持刷新和选择 | `_refresh_wechat_candidates`、`_selected_wechat_candidate` | `WechatCandidateRegistry.list`、`WechatChannelsCaptureService.candidates` | `tests/test_wechat_channels.py`；A202、A203、A206 |
| DESK-018 | 候选详情显示封面、标题、作者、时长、质量、预计输出和来源；封面异步加载且复用缓存 | `_update_wechat_detail`、`_load_wechat_preview`、`_drain_wechat_preview_events` | `WechatCandidateRegistry.preview_request`、`WechatChannelsCaptureService.preview_png` | `tests/test_wechat_channels.py`、`tests/test_ui_layout.py` |
| DESK-019 | 可选择实际质量并创建统一媒体计划；可选择仅下载，或“导入 Eagle，成功后删除本机下载文件” | `submit_selected_wechat_candidate` | `WechatChannelsCaptureService.submit`、`WechatCandidateRegistry.plan_payload`、`MediaCoordinator.create_plan` | `tests/test_wechat_channels.py`、`tests/test_media.py`；A204–A211、A225 |
| DESK-020 | 清空候选不停止捕获、不删除文件、不影响已有媒体任务 | `clear_wechat_candidates` | `WechatChannelsCaptureService.clear_candidates`、`WechatCandidateRegistry.clear` | `tests/test_wechat_channels.py`；A222 |

### 4.5 网站规则、网络和更新

| ID | 重构后必须保留的功能 | 桌面文件与函数 | 后端 | 回归证据 |
| --- | --- | --- | --- | --- |
| DESK-021 | 设置页网站规则列表显示域名、启用状态、子域名和修改时间 | `MainWindow._build_settings_tab`、`_refresh_settings` | `Database.list_site_rules` | `tests/test_database.py`、`tests/test_ui_layout.py` |
| DESK-022 | 新增并开启、启停、切换子域名、删除选中、清空全部规则；清空后默认关闭，不从无来源文件反推网站 | `MainWindow._settings_add_rule`、`_settings_toggle_rule`、`_settings_toggle_subdomains`、`_settings_delete_rule`、`_settings_clear_rules` | `Database.set_site_rule`、`delete_site_rule`、`clear_site_rules` | `tests/test_database.py`；A07–A10、A222 |
| DESK-023 | 设置页网络模式支持“自动（推荐）/始终直连/手动代理”；手动地址校验，显示检测来源和脱敏端点 | `MainWindow._build_settings_tab`、`_settings_proxy_mode_changed`、`_settings_save_proxy`、`_refresh_settings` | `NetworkProxyManager.configuration`、`configure`、`status`、`normalize_proxy_url` | `tests/test_network_proxy.py`；A192–A195 |
| DESK-024 | 自动及手动检查更新；发现版本后由用户确认下载和安装；错误可见，不能静默安装 | `MainWindow._automatic_update_check`、`check_for_updates`、`_handle_update_check`、`_start_update_download`、`_handle_download_ready` | `updater.py:check_for_update`、`prepare_update`、`launch_installer` | `tests/test_updater.py`；A42–A45 |
| DESK-025 | 更新清单 RSA 验签、仓库限制、大小/SHA-256 校验，以及安装器健康回滚和数据保留 | `updater.py:_verify_rsa_signature`、`parse_manifest`、`prepare_update`；`installer/Setup.cs` | 安装器更新/回滚流程 | `tests/test_updater.py`、安装器门禁；A43–A45 |

## 5. 前端依赖的核心业务能力

这些能力可能没有独立按钮，但前端状态、文案和操作可用性依赖它们。重构时不能把状态压缩成简单的“成功/失败”。

| ID | 必须保留的业务能力 | 主要文件与函数 | 前端可见结果 | 回归证据 |
| --- | --- | --- | --- | --- |
| CORE-001 | IDM Hook 只验证绝对路径、合并/写入任务并唤醒；无监听者时静默启动助手 | `hook.py:main`、`start_assistant_hidden`；`Database.add_job`；`wake_signal.py:notify_processing_service` | 新任务快速出现，Hook 不阻塞 IDM | `tests/test_hook.py` |
| CORE-002 | 后台按下一可执行时间等待，新任务/API 计划可立即唤醒；每日清理历史 | `service.py:ProcessingService._run`、`wake`；`JobProcessor.process_once` | 任务快速开始，空闲时不高频轮询 | `tests/test_end_to_end.py` |
| CORE-003 | 非视频忽略；文件不存在、为空或刚写完时分类重试；稳定性最多 20 次 | `processor.py:JobProcessor.process_job`、`_retry` | “非视频忽略”“文件尚未稳定”等明确状态 | `tests/test_processor.py`；A13、A17、A37 |
| CORE-004 | 短暂等待浏览器来源；没有可靠来源仍导入且 Eagle website 为空 | `JobProcessor.process_job`；`Database.attach_best_source`、`_choose_source` | 无来源任务不会永久卡住，也不出现猜测网址 | `tests/test_processor.py`、`tests/test_database.py`；A03、A11 |
| CORE-005 | SHA-256 内容去重；同名不同内容不能误判；已成功任务的竞态重试保持 imported | `fingerprint.py:sha256_file`；`Database.fingerprint_owner`、`remember_fingerprint`；`JobProcessor.process_job` | “相同内容已经导入”或正确导入 | `tests/test_processor.py`；A15、A38 |
| CORE-006 | Eagle 离线进入低频等待，恢复后继续；普通错误最多 12 次，Eagle 等待有上限 | `JobProcessor._wait_for_eagle`、`_retry`；`EagleClient.is_available` | 等待、重试、永久失败状态可区分 | `tests/test_processor.py`；A05、A39 |
| CORE-007 | Eagle v2 API 优先，兼容旧本地接口；导入路径和更新来源只调用官方 API | `eagle.py:EagleClient.app_info`、`add_from_path`、`update_source` | Eagle 健康、导入和来源更新 | `tests/test_eagle.py` |
| CORE-008 | 媒体计划验证输出名、容器、流数量、URL、DRM、固定 Range、来源和删除选择 | `media.py:safe_output_name`、`canonical_page_resolver_url`、`MediaCoordinator.create_plan` | 非法选择在创建阶段返回具体错误码 | `tests/test_media.py` |
| CORE-009 | 普通直链、视频+音频、HLS/DASH、YouTube、通用页面和视频号都走同一个计划状态机 | `MediaCoordinator._process_remote`、`_resolve_youtube_streams`、`_resolve_page_streams`、`_download_and_decrypt_wechat_stream` | `queued → downloading → validating → ready_to_import/imported` 或 `completed_local` | `tests/test_media.py`、`tests/test_wechat_channels.py`；A106、A110、A209 |
| CORE-010 | FFmpeg/ffprobe 使用固定参数数组；分轨 streamcopy、清单节目选择、字幕 sidecar、时长/音视频流校验 | `MediaCoordinator._ffmpeg_input_arguments`、`_select_manifest_stream_indexes`、`_probe`、`_validate_output_duration`、`_download_subtitles` | 合并/校验阶段、正确清晰度、可播放最终文件 | `tests/test_media.py`；A59–A67、A121 |
| CORE-011 | 系统代理自动检测、手动/直连路由，以及自动模式单次代理→直连切换；本机和 Eagle 永远直连 | `network_proxy.py:NetworkProxyManager.routes_for`、`_is_local_target`；`MediaCoordinator._prepare_network_route_retry`、`_network_failure_with_guidance` | 网络错误提供代理建议，不无限重试 | `tests/test_network_proxy.py`、`tests/test_media.py`；A192–A195 |
| CORE-012 | 任务取消、重试、进度、终态、预览、打开目录和补导都以 `planId` 为身份 | `MediaCoordinator.retry_plan`、`stop_plan`、`_set_progress`、`_set_status`、`get_plan`、`list_plans`、`get_plan_preview`、`open_plan_output`、`import_completed_plan` | popup 与桌面显示同一任务状态 | `tests/test_media.py` |
| CORE-013 | 只有最终文件存在且位于程序“已完成”目录时才能打开或补导；目录逃逸和任意客户端路径被拒绝 | `MediaCoordinator._owned_plan_file`、`open_plan_output`、`import_completed_plan` | 安全打开目录/补导，错误路径明确拒绝 | `tests/test_media.py`；A126、A147 |
| CORE-014 | 导入后删除必须满足：计划明确选择、Eagle API 成功、job imported、plan/job 路径一致、文件属于“已完成”；删除失败不回滚 Eagle 成功 | `JobProcessor._cleanup_imported_desktop_output`；`Database.imported_plan_output_for_cleanup`、`pending_imported_output_cleanups`、`record_plan_output_cleanup` | 成功后清空本机路径，失败保留路径和可见错误 | `tests/test_processor.py`、`tests/test_database.py`；A225 |
| CORE-015 | SQLite 迁移用 `PRAGMA user_version`；任务、规则、配对、进度、预览路径、导入/删除选择和历史在升级后保留 | `database.py:Database.initialize` | 重开窗口/升级后状态恢复 | `tests/test_database.py`、`tests/test_media.py`；A108 |
| CORE-016 | 本机 API 只监听 loopback，限制 JSON 大小，只接受扩展 Origin 和有效配对令牌；健康、配对例外受严格限制 | `api_server.py:build_handler`、`LocalApiServer`；`security.py:PairingManager` | 离线/未配对/失效状态明确，任意网页不能调用 | `tests/test_security_api.py`；A27、A83、A135 |
| CORE-017 | 视频号每机证书、目标主机代理、系统代理租约、候选身份、质量、短时解密上下文和异常恢复 | `wechat_channels.py:WechatChannelsCaptureService`、`WechatCandidateRegistry`；`wechat_channels_proxy.py`；`wechat_channels_certificate.py`；`wechat_channels_crypto.py` | 视频号状态、候选、质量和可操作错误 | `tests/test_wechat_channels.py`；A197–A214 |

## 6. 扩展消息与本机 API 契约

前端重构可以替换组件结构，但下列动作必须仍有唯一可达路径。

| 用户动作/读取 | 扩展消息 | 本机接口 | 服务端函数 |
| --- | --- | --- | --- |
| 读取认证状态 | `authState` | 扩展本地状态 | `eagleBridgeGetState` |
| 尝试自动配对 | `autoPair` | `POST /api/pair/auto` | `LocalApi.pair_automatically` |
| 手工配对 | `pair` | `POST /api/pair` | `LocalApi.pair`、`PairingManager.pair` |
| 媒体健康 | `health` | `POST /api/media/health` | `MediaCoordinator.health` |
| 当前网站规则 | `siteStatus` | `POST /api/site/status` | `LocalApi.site_status` |
| 修改网站规则 | `setSite` | `POST /api/site` | `LocalApi.set_site` |
| 保存/忽略来源 | `manualSource`、`ignoreNext`、`sourceClick`、`source` | `POST /api/source` | `LocalApi.add_source`、`Database.add_source_event` |
| 创建媒体计划 | `createPlan` | `POST /api/media/plan` | `MediaCoordinator.create_plan` |
| 单个计划详情 | `plan` | `POST /api/media/plan/get` | `MediaCoordinator.get_plan` |
| 计划列表 | `plans` | `POST /api/media/plans` | `MediaCoordinator.list_plans` |
| 计划预览 | `planPreview` | `POST /api/media/preview` | `MediaCoordinator.get_plan_preview` |
| 停止计划 | `stopPlan` | `POST /api/media/stop` | `MediaCoordinator.stop_plan` |
| 重试计划 | `retryPlan` | `POST /api/media/retry` | `MediaCoordinator.retry_plan` |
| 打开输出目录 | `openPlanOutput` | `POST /api/media/open` | `MediaCoordinator.open_plan_output` |
| 补导现有文件 | `importPlan` | `POST /api/media/import` | `MediaCoordinator.import_completed_plan` |

兼容 GET 路由仍由 `api_server.py:build_handler` 保留，但活动 popup 的认证读取必须使用带 JSON 请求体的 POST。

## 7. 必须保留的可见状态和错误

### 7.1 连接状态

- `checking`：正在检查。
- `paired`：已连接并通过受认证健康检查。
- `needs_pairing`：需要输入配对码。
- `offline`：助手离线；候选仍可浏览，但两个下载动作必须禁用。

### 7.2 媒体计划状态

- `queued`
- `downloading`
- `validating`
- `ready_to_import`
- `waiting_eagle`
- `imported`
- `completed_local`
- `retry`
- `failed_permanent`
- `import_failed`
- `canceled`
- `needs_rebuild`

`completed_local` 和 `imported` 必须显示 100%。下载完成但仍在校验或等待 Eagle 时不能提前显示 100%。

### 7.3 IDM 任务状态

至少区分：

- 排队/等待来源。
- 等待 Eagle。
- 文件不存在、为空或尚未稳定。
- 非视频忽略。
- 用户忽略。
- 内容重复跳过。
- 导入成功。
- 临时错误重试。
- 永久失败。

### 7.4 创建计划前的阻断

以下错误必须在主动作附近显示，并保持按钮不可提交：

- 尚未配对或助手离线。
- DRM。
- `blob:` 或非法 URL。
- 只有技术分片/固定 Range 分片。
- 无可靠内容身份。
- 清单与直链混选。
- 超过一路视频或一路音频。
- YouTube/页面解析候选没有有效质量或稳定内容页。
- 输出名中的 Windows 非法字符需要安全规范化；无法形成合法名称时阻断。

## 8. 明确退役：重构时不得重新加入

下列能力不是“漏做”，而是已经退出活动产品边界：

| 退役能力 | 当前替代 |
| --- | --- |
| 浏览器直链/HLS/DASH 下载器、`chrome.downloads` 远程媒体旁路 | 桌面 `MediaCoordinator` |
| 浏览器 FFmpeg/WASM、在线 FFmpeg、第三方合并服务 | 本机 FFmpeg/ffprobe |
| Aria2、N_m3u8DL-RE、send2local、MQTT、自定义命令/URL 模板 | 认证回环媒体计划 |
| MediaSource 缓存下载、MediaRecorder、屏幕/WebRTC 录制 | 只发现真实 HTTP(S) 媒体；不可达 Blob 明确阻断 |
| 移动 UA、DNR 请求头修改、疑似密钥面板 | 不属于当前产品 |
| 旧预览页、解析页、下载页、二维码和第二套媒体列表 | 单一 popup 媒体检查器 |
| 自动下载快捷键、右键远程下载、捕获即下载 | 用户明确提交本机计划 |
| 猫抓图标、旧 popup DOM、jQuery/MQTT/HLS 浏览器运行时 | 下载中转站自有 UI 与图标 |
| DRM 绕过或解密 | 仅检测并明确阻断 |

活动扩展文件以 [`chrome-extension/manifest.json`](../chrome-extension/manifest.json) 和 [`manifest.firefox.json`](../chrome-extension/manifest.firefox.json) 为准。

## 9. 重构完成检查表

### Chrome 扩展

- [x] EXT-001–EXT-009：应用外壳、连接、配对、来源规则和设置均已迁移。
- [x] EXT-010–EXT-018：发现、站点适配、身份、预览和安全阻断均已迁移。
- [x] EXT-019–EXT-029：归组、筛选、选择、批量和两个提交动作均已迁移。
- [x] EXT-030–EXT-034：任务恢复、进度、停止、重试、打开目录和补导均已迁移。
- [x] Chrome 与 Firefox 清单仍只包含当前权限和活动脚本。
- [x] 不存在第二套下载器、旧工具箱或远程媒体旁路。

### 桌面界面

- [x] DESK-001–DESK-006：主窗口、滚动、刷新、托盘和全局入口均已迁移。
- [x] DESK-007–DESK-011：媒体任务列表和全部任务动作均已迁移。
- [x] DESK-012–DESK-015：IDM 记录和来源补写均已迁移。
- [x] DESK-016–DESK-020：视频号捕获、候选、质量和提交均已迁移。
- [x] DESK-021–DESK-025：网站规则、网络代理和更新均已迁移。
- [x] 清理操作只清理允许的记录，不删除文件或修改 Eagle。

### 跨界面行为

- [x] CORE-001–CORE-017 的状态与错误仍能在前端正确表达。
- [x] popup 与桌面显示同一个 `planId`、进度、阶段和终态。
- [x] “导入 Eagle”明确表达成功后删除本程序副本；“仅下载”明确保留。
- [x] 无来源、DRM、分片、代理、Eagle 离线和上下文失效都有可操作文案。
- [x] 完成 [`DEVELOPMENT.md`](../DEVELOPMENT.md) 中的全部 unittest、Node 测试、活动 JS 语法和双清单 JSON 检查。

## 10. 维护规则

- 新增、删除或改名用户可达功能时，必须在同一变更中更新本文。
- 修改扩展消息、API 路径、计划状态或错误码时，必须同步更新第 6、7 节。
- 修改前端职责边界时，必须先更新 [`docs/DECISIONS.md`](DECISIONS.md)。
- 完成功能不能只从本文删除；需要移入第 8 节并记录替代路径，防止后续误判为遗漏。
- 本文是重构保全索引，不替代详细验收；最终行为以 [`ACCEPTANCE.md`](../ACCEPTANCE.md) 为准。
