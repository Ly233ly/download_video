# 架构与数据流

## 任务流程

```text
Chrome 扩展（可选）
  ├─ 已开启网站：网页来源事件
  └─ 已关闭网站或单次忽略：跳过事件
                         ┐
IDM 下载完成：最终路径 ──┴─> SQLite 持久任务
                                  │
                                  ├─ 尝试匹配来源或跳过事件
                                  ├─ 没有来源：继续处理
                                  ├─ 格式与稳定性检查
                                  ├─ 完整内容哈希去重
                                  └─ Eagle 官方本地 API
                                       ├─ 成功：记录项目编号
                                       └─ 离线/暂时失败：持久重试
```

来源是增强信息，不是导入前置条件。同一网页产生的重复请求先合并为一个候选；不同网页候选仍不唯一时保持为空。明确的关闭网站或单次忽略事件优先于导入。

新任务先给浏览器来源 4 秒宽限；服务按下一任务到期时间动态等待，不用提高空闲轮询频率。
文件稳定检查以 2–3 秒间隔最多执行 20 次；普通临时错误最多 12 次；Eagle 离线每 30 秒检查一次并在约 1 小时后停止。所有停止状态都可由用户手动重新开始。

## 进程

### Windows 托盘宿主

- `下载中转站.exe` 使用 .NET Windows Forms `NotifyIcon` 和 `ContextMenuStrip` 常驻右下角。
- 宿主负责左键打开、右键菜单、网站规则、立即检查、退出和单实例保护，并监控后端进程。
- 宿主与助手通过 Windows 命名事件传递显示、规则、退出和处理唤醒指令。
- 正常运行启动带自有名称、版本信息和图标的 `runtime/下载中转站后台/下载中转站后台.exe`；只在开发目录缺少冻结后台时保留 Python 回退能力。

### Python 桌面助手

- 提供记录窗口、配对、处理队列、文件检查、哈希、Eagle 调用和重试。
- 不再继承或替换系统窗口过程，也不直接创建托盘图标，避免原生回调破坏 Python 进程。
- 新任务通过 Windows 命名事件立即唤醒；15 秒轮询仅作为崩溃恢复保底。
- 窗口隐藏时不刷新任务表，并把界面检查间隔降为 30 秒。

### IDM 接收器

- IDM 完成下载时调用。
- 只校验绝对路径、写入或合并活动任务、发送唤醒信号，然后退出。
- 不做哈希和 Eagle 网络调用，避免阻塞 IDM。

### Chrome 扩展

- Chrome/Edge 使用 Manifest V3，Firefox 使用独立清单；持久存储保存版本化设置、配对令牌和最多 200 条待发送事件，媒体候选只进入 `storage.session`，网站规则由助手数据库统一管理。
- 本机通信使用 `127.0.0.1:47652`、扩展来源和随机令牌；手动配对仍支持六位码。
- 一键安装器把随机秘密分别写入扩展载荷和本机数据目录；扩展首次连接后换取正式令牌，服务端随即删除一次性文件。
- 助手离线时扩展仍先保存事件；恢复后重新检查网站规则并快速补发。

### 一键安装器与独立运行时

- `installer/Setup.cs` 是普通用户入口，安装范围仅为当前 Windows 用户，不需要管理员权限。
- 安装器复制只读程序载荷，用户队列与设置保存在 `%LOCALAPPDATA%/IdmEagleAutoImport`。
- IDM 原值保存在当前用户注册表的本助手状态键；卸载只在当前值仍属于本助手时恢复。
- PyInstaller `onedir` 后端包含 Python 3.14、SQLite、Tk 和 Tcl/Tk；IDM 的 C# 接收器仍保持轻量，只启动冻结后端的 `--receive` 模式。
- 网站开关主要控制来源保存与明确跳过。由于 IDM 不提供网页地址，浏览器未识别到的无来源下载无法可靠判断网站，按直接导入处理。

### 一键更新

- 桌面助手每天最多访问一次 GitHub Release 的 `update.json`，也可由主界面或托盘菜单手动触发。
- 客户端先使用内置 RSA 公钥验证规范化清单，再限制下载地址必须属于本仓库，并核对 ZIP 的大小与 SHA-256。
- 安装器停止旧进程后把旧程序目录改名为临时备份；新后台必须在 20 秒内通过 `127.0.0.1:47652/health` 版本检查，失败则恢复并重启旧版。
- Chrome 扩展每 30 分钟低频比较自身与后台版本，仅在后台版本更高时调用 `chrome.runtime.reload()`。

## 数据与状态

- 开发便携模式数据库位于 `data\bridge.db`；安装版位于 `%LOCALAPPDATA%\IdmEagleAutoImport\bridge.db`。
- 任务主要状态：`queued`、`waiting_eagle`、`retry`、`imported`、`skipped_duplicate`、`ignored_*`、`failed_permanent`。
- 0.2 数据迁移使用 SQLite `user_version=2`，把旧 `waiting_source` 转为 `queued`。
- WAL、事务、忙等待和活动任务合并保证 IDM 多进程通知时的数据一致性。
- 成功/失败/跳过记录默认保留 90 天、最多 10,000 条；重复指纹长期保留。

## Eagle

- 健康检查优先使用 `/api/v2/app/info`；尚未提供 V2 Web API 的 Eagle 4 构建返回 404/405 时回退官方 V1 `/api/application/info`。导入与来源更新同样优先 V2、按端点不可用回退 V1。
- 导入优先使用官方 V2 `/api/v2/item/add` 并保存返回的项目编号；旧 Eagle 端点不可用时回退 `/api/item/addFromPath`。
- 事后补写来源优先使用 `/api/v2/item/update` 的 `url` 字段，并保留旧接口回退。
- 绝不直接修改 `.library` 内部文件。

## 性能边界

- IDM 接收器不计算哈希。
- 哈希在单个后台处理线程中执行，使用固定 4 MiB 缓冲区，内存占用不随视频大小增长。
- 导入不再先做一次 Eagle 预检，直接调用导入接口并按异常分类，减少一次本机请求。
- UI 只在数据库版本变化时重建列表。

## 1.0.0 历史架构：可见媒体与合并

以下数据流在 1.0.0 建立；图中的上游缓存/录制分支已由 1.2.0 章节取代。`eagle-bridge` 把默认可见候选、下载计划和本机合并接到原有持久队列。历史边界见 [迁移总计划](CAT_CATCH_MIGRATION_PLAN.md) 和 [功能对照矩阵](FEATURE_PARITY_MATRIX.md)。

```text
网页与播放器
  ├─ webRequest / 下载动作 / Content-Disposition
  ├─ 深度搜索：XHR、fetch、Worker、JSON/文本
  ├─ HLS / DASH 清单发现
  └─ 显式增强发现：元素、Performance、fetch、XHR
                    │
                    v
Chrome/Edge/Firefox 扩展
  捕获会话 -> 媒体候选组 -> 可见预览 -> 认证提交本机计划
                    │              │
                    │              ├─ 直链或单文件
                    │              ├─ HLS/DASH 清单
                    │              └─ DASH 视频流 + 音频流
                    v
本机后端
  FFmpeg 访问原站 -> 下载/streamcopy -> ffprobe 验证 -> 本机预览
                    │
                    ├─ 仅下载：completed_local
                    └─ JobProcessor -> 内容去重 -> Eagle 官方本地 API
```

### 核心模型

- **捕获会话**：限定标签页、导航周期和规则快照，防止跨页面候选串线。
- **媒体候选组**：用户眼中的一个可下载媒体；可包含一个直链、多个 HLS 变体，或 DASH 的视频、音频和字幕表示。
- **媒体流**：一个候选组内可选择的具体视频、音频、字幕、初始化段或分片集合。
- **下载计划**：下载前冻结的媒体流、输出名、容器、固定本机路由、合并方式、是否导入 Eagle 和预计大小。
- **任务内存上下文**：未落盘的完整媒体 URL 与白名单请求头；只活到终态或软件退出。
- **任务临时文件**：仅由本机软件在任务专属临时目录创建的中间输出。
- **最终媒体**：经下载、streamcopy 和完整性验证后的单个文件；可以进入 Eagle，也可以作为“仅下载”结果交付。

候选组是浏览器与后端的协议边界。B 站 DASH 的视频和音频必须共享组编号和最终输出，不能作为两个无关下载展示。新表通过 SQLite `user_version` 迁移加入，旧 IDM 任务和扩展事件继续兼容。

当前数据库 `user_version=5`；保留 `capture_sessions`、`media_groups`、`media_streams` 和 `download_plans`，删除旧 `component_files` 浏览器交接表。方案新增 `import_to_eagle`、处理字节、预计字节、阶段说明和预览路径。`/health` 同时公开产品版本、schema、扩展协议 1、`desktop_ffmpeg` 引擎与媒体工具就绪状态，供安装器的原子升级门使用。

## 1.1.1 popup 架构

- `eagle-bridge-ui-logic.js` 是无 DOM 的候选规范化、内容归组、推荐、校验、输出容器与任务视图模型层，可在 Node 中独立测试。
- `eagle-bridge-candidate-logic.js` 是后台与所有页面 frame 共用的候选展示边界：选择安全的内容图并在 service worker 启动时等待 `storage.session` 快照恢复；favicon 始终保留为站点身份字段，不进入媒体缩略图。
- `eagle-bridge-ui.js` 维护唯一弹窗状态：连接、当前标签、当前/其他页候选、内容组、逐组选择与草稿、本机方案列表、瞬时帧映射和增强发现状态。
- DOM 只有 `#eagleBridgeRoot`。旧 cat-catch popup、设置、下载/解析/预览页和录制/媒体控制脚本已删除；主导航仅有“媒体 / 任务”，设置只控制来源、捕获总开关、增强发现与独立窗口。
- 浏览器后台从本机 `plans` 恢复任务；进度、阶段、停止和重试都直接操作目标本机方案，不维护第二份 Chrome 下载状态。
- UI 只在受影响区域更新：候选变化重建内容列表与检查器，任务调度器批量刷新方案，输入草稿与每组选择不会被其他任务刷新覆盖。
- 每个网络候选向产生请求的 frame 查询通用视觉上下文：优先以 canvas 获取真实 `video` 帧；跨域 canvas 被浏览器阻止时，后台用 `captureVisibleTab` 截取对应播放器矩形。帧按 `groupKey` 短时保存在 service worker 内存，popup 通过 `getMediaPreviews` 读取，不写 `storage.session`。poster、邻近内容图和 Open Graph/Twitter/JSON-LD 是回退。后台角标调用同一 `groupCandidates`，因此表示可下载内容组而非原始请求条数。
- 归组层先按稳定播放器 `groupKey` 划定内容，再删除同一路径的签名参数轮换副本；同组已有 MPD/M3U8 或完整媒体时隐藏普通 `.m4s`/`.ts` 传输分片。只有分片时保留一个不可提交的诊断项。

## 1.1.2–1.1.3 质量目录与节目流选择

- 通用归组规则把完整 HLS/DASH 清单视为播放器的下载边界；同组出现清单后，非显式分轨的 MP4/音频网络分片全部退出选择器。
- 支持结构化播放器目录时，content script 从页面公开配置中提取主清单、视频 ID、时长、封面和明确质量档位。当前 Vimeo 适配读取 `window.playerConfig`，但签名清单只进入 `storage.session` 与本机任务内存。
- `playerWidth/playerHeight` 只描述当前播放器状态；`videoWidth/videoHeight` 只用于明确流元数据。两者不得互相冒充，因此 UI 可同时显示“当前播放 1080p”和可下载质量列表。
- 质量档位按高度降序去重，最高档默认标记推荐。选择值作为 `preferredQuality` 随认证计划提交，不写长期任务历史。
- 本机在执行清单任务前用 ffprobe 获取 programs/streams，按目标高度选择对应视频流及同节目音频，再由 FFmpeg streamcopy；探测失败时退回原有安全映射。

### 合并与下载边界

- 所有媒体固定走 `desktop`。页面桥显式提供的 Referer/Origin/User-Agent 会与 `webRequest` 观测到的 Cookie/Authorization 等白名单请求头合并（观测值优先），再经认证回环 API 进入本机任务内存。普通直链、B 站/受保护分轨与 HLS/DASH 使用同一 FFmpeg 命令构造和状态机；完整签名 URL 与请求头不写数据库，数据库只保存移除查询参数的媒体摘要和来源页。
- Chrome 组件下载、逐组件 DNR session 规则、downloadId、完成/失败路径回传和浏览器进度聚合均已删除。`blob:` 等桌面不可访问地址在计划创建前明确阻断。
- popup 的连接灯通过认证后的 `/api/media/health` 检查助手及媒体工具；公开 `/health` 只用于安装器与本机健康门，不经过扩展 API 的 `data` 解包协议。
- 默认合并命令使用 FFmpeg streamcopy；只有编码/容器不兼容且用户选择时才转码。
- ffprobe 在合并前检查输入流，合并后检查容器、至少一个视频流、预期音轨、时长和非零大小。
- 新版载荷不包含浏览器 FFmpeg/WASM、第三方在线处理页、浏览器下载器、旧预览/直链/HLS/DASH 页面或外部下载目标；唯一 popup 提交 `desktop` 计划。
- 旧自动下载快捷键、右键菜单、标签状态、捕获后 Chrome download、自动 send2local 和录制 Blob 保存均已删除。
- 字幕不参与音视频 mux；由本机软件下载并移动为最终媒体同目录的 sidecar。
- FFmpeg 进度解析 `total_size/out_time`，方案在下载中记录 2–78%、校验 82%、等待 Eagle 90%，关联 job 导入后才成为 100%；“仅下载”在验证后直接成为 `completed_local/100`。
- 本机软件从最终视频抽取 240px PNG 预览，桌面任务页直接读取；预览失败不影响已验证媒体交付。
- 质量集合完全由当前媒体数据驱动，不维护 `1080p/720p/...` 固定表。UI 用动态数量说明范围；另一个视频重新计算自己的集合。
- 站点结构化目录优先。没有目录时，扩展只对完整 HTTP(S) HLS/DASH 清单做 2 MB、4 秒的有界读取：HLS 读取 `EXT-X-STREAM-INF RESOLUTION`，DASH 读取 `Representation height`；没有明确高度就保持自动质量。
- 临时清理只针对规范化后的 `下载中转站/临时/<planId>` 显式路径；用户原文件不进入该路径。

## 1.1.4 任务同步、输出目录与通用预览

- `download_plans` 仍是桌面与 popup 的唯一任务事实源。popup 创建方案时的 `queued/0` 只是瞬时快照；每次轮询均以认证后的 `/api/media/plans` 覆盖。`completed_local` 与 `imported` 在视图模型中额外钳制为 100%，兼容旧记录或传输中的字段不一致。
- 轮询失败不删除本机任务，也不继续把旧百分比描述成实时状态：连接灯转为离线、任务区显示同步中断并继续短周期重连。HTTP 401 会清除扩展中的失效令牌并尝试安装器 bootstrap 自动配对；失败后回到明确配对态。
- 创建任务前的实际画面仍只保存在扩展内存，但会以 `planId → data URL` 绑定到 popup 任务卡；popup 关闭后不持久化该映射。
- 下载完成后的恢复路径由桌面 FFmpeg 生成 `下载中转站/预览/<planId>.png`。认证接口 `/api/media/preview?id=<planId>` 只读取数据库记录并再次校验 resolved path 位于程序预览根、格式为 PNG、大小不超过 2 MB，再返回内存 data URL。它与站点域名无关。
- `/api/media/open` 只接受 `planId`，服务端从数据库取 `final_path`，校验真实文件位于 `下载中转站/已完成` 后打开父目录。客户端不能提交路径，不能用该接口浏览其他本机目录。

## 1.1.5 动作真实性与配对恢复

- `validateSelection` 是两个下载按钮和批量动作的统一前置门禁；未配对、DRM、分片不完整或选择无效时不得进入计划创建器。
- `startValidatedTask(validation, createPlan)` 把“校验通过”与“服务端真实返回计划”组成一个可测试的提交边界。UI 只有在 `started=true` 且存在计划对象时更新任务列表并显示成功，校验失败的早退不能被外层误报为成功。
- popup 连接检查先读取扩展令牌，再通过 service worker 的 `autoPair` 消息显式重试安装器 bootstrap，最后才区分 `paired / needs_pairing / offline`。自动配对失败不会把候选清空，两个下载按钮保持禁用并显示配对原因。
- 仓库开发副本的 `bootstrap.js` 必须保持空值；安装器只向受归属校验的正式安装副本写入单机一次性凭据。开发副本丢失令牌时使用六位码，不允许把本机密钥复制回源码。

## 1.1.6 配对请求的并发一致性

- 每个认证请求在发出前冻结 `requestToken`。收到 401 后先读取当前存储令牌，不得直接覆盖状态。
- 当前令牌与请求令牌不同且非空，说明配对或恢复发生在请求进行期间；使用最新令牌重试一次，禁止清空。
- 只有当前令牌仍与被服务端拒绝的 `requestToken` 完全相同时才清除它并进入自动配对恢复；无令牌请求只进入恢复流程。
- `eagle-bridge-auth-logic.js` 是无浏览器依赖的竞态决策层，Chrome service worker 与 Firefox 背景脚本必须在 `eagle-bridge.js` 前加载。
- popup 的“配对完成”不是 POST `/api/pair` 的单点成功，而是“令牌已写入 + 受认证媒体健康接口成功 + `authState.paired=true`”的组合事实。

## 1.1.7 扩展状态串行化

- `downloadTransferStation` 是一个共享状态文档；令牌、补发事件和最近任务字段必须共用同一个串行读改写器，禁止每个调用方独立读取后覆盖整份对象。
- 写入器接受对象补丁或函数式补丁。后者在轮到该操作执行时读取最新状态，适用于事件追加/消费和令牌 compare-and-clear。
- 写入失败不会永久破坏队列；队尾会吸收上一操作的拒绝并允许后续操作继续，但原调用方仍收到自己的错误。
- Firefox 与 Chrome 复用同一 `EagleBridgeAuthLogic.createStateUpdateQueue`，保证两个后台模型的状态语义一致。

## 1.1.8 认证读取统一 POST

- popup 的健康、任务列表、任务详情和任务预览均通过 `eagleBridgeRead` 发送 JSON POST；现有 GET 端点只保留给旧客户端兼容。
- `eagleBridgeApi` 在认证 POST 请求体中注入当前随机令牌，服务端仍先校验浏览器扩展 Origin，再校验令牌哈希；网页 Origin、错误令牌和无令牌请求继续拒绝。
- 统一 POST 消除 Chrome 跨源 GET 对 Origin 或 Authorization 头传递差异，不放宽回环监听、CORS 或配对来源规则。

## 1.1.9 媒体身份一致性

- `content-script.js` 为每个 `<video>` 收集真实来源集合；`resolveVisualMatch` 对请求 URL 做去签名查询规范化后，只接受同主机与同路径的精确匹配。
- 精确匹配成功后才生成稳定播放器键、抓取当前帧、读取 duration/尺寸并允许后台截图。未匹配请求保留网络候选自身信息，不借用当前播放或可见播放器。
- 结构化目录（如明确视频 ID 的播放器配置、B 站分轨元数据）继续通过 `mediaMeta` 提供内容身份，不依赖视觉回退。
- 本机下载完成后，`MediaCoordinator` 在移动到 `已完成` 前比较非清单直链的声明时长和 FFprobe 输出时长。明显不一致时删除程序临时输出并进入可重建失败态，Eagle job 不创建。

## 1.1.10 候选自身预览

- 可信页面帧仍只由 1.1.9 的 URL—播放器精确匹配或结构化播放器目录提供；未匹配网络请求不能借用当前可见播放器身份。
- 视图层的 `previewMediaUrl` 从当前内容组选择中解析唯一视频候选，只接受 `http/https`。popup 没有可信静态帧时，用该候选自己的直链创建静音、内联、metadata 预加载的视频预览。
- 版本选择和预览来源共享同一 `selection`，因此选择变化会使预览 URL 与提交给桌面方案的 URL 同步变化。音频、blob 和非法 URL 不进入该回退。
- 远程预览加载失败仅影响展示并回退占位；下载仍走认证桌面方案，不新增浏览器下载或站点白名单。

## 1.1.11 媒体别名与信息继承

- 主 CDN 请求通过 URL—播放器精确匹配获得 `groupKey`、真实帧、时长和尺寸；无 DOM 元数据的备用 CDN 请求不能自行获得这些视觉身份。
- `contentIdentity` 只在扩展会话内保存，优先来自响应 Digest、Content-MD5 或非弱 ETag。没有响应身份时，长 URL 路径与总字节数共同构成保守别名；大小单独不构成身份。
- 归组先建立“强别名 → 唯一显式播放器组”映射，再把无 `groupKey` 的备用请求并入；一个别名若对应多个显式组则标为歧义并保持隔离。
- 组内同内容 CDN 地址折叠后选取视觉帧、组键、时长和流元数据最丰富的候选用于展示和默认下载。原始 URL 只在当前会话和本机任务内使用，不持久化响应身份或签名地址。

## 1.1.12 固定字节分片识别

- 传输分片不再只由 `.m4s/.ts` 后缀定义；URL 查询、明文路径或 base64url 路径段若固定声明 `range/bytes=start-end`，且已知响应大小精确等于区间长度，也属于不可独立提交的分片。
- 扩展将其交给现有 `segmentOnly` 与“清单优先”路径：完整 HLS/DASH 存在时隐藏，否则只保留不可提交代表。
- 浏览器判定只负责交互正确性；桌面 `MediaCoordinator` 在创建计划和执行驻留重试上下文前独立复验，保证旧扩展也不能让固定分片进入 FFmpeg。
- 普通完整媒体 URL 即使服务器支持 HTTP Range，也不会只因 206 响应被阻断；安全门要求 URL 本身携带可验证的固定区间。

## 1.2.0 运行时职责与界面收口

```text
浏览器扩展
  发现网络/页面媒体 → 形成媒体候选组 → 预览/筛选/选择
                                      │
                                      └─ 认证提交 planId/所选流
                                                     │
桌面软件                                             ▼
  SQLite 事实源 ← 下载/清单解析/合并/校验 ← MediaCoordinator
        │                         │
        ├─ completed_local ───────┴─ 用户可打开目录
        │             └─“导入现有文件”→ Eagle job（不重下载）
        └─ ready_to_import → Processor → Eagle 官方本地 API
```

- 扩展的 `background.js` 是发现适配器，收集 `webRequest` 和增强捕获结果；`eagle-bridge-ui-logic.js` 负责媒体候选组排序、分片分区和选择验证；`eagle-bridge-ui.js` 只呈现并提交方案。扩展不存在远程媒体下载 Interface。
- 桌面的 `MediaCoordinator` 是下载与交付 Module：它拥有 FFmpeg/ffprobe、受控临时/完成目录、状态持久化和补导 Interface。`LocalApiServer` 只把认证 `planId` 适配到这些方法。
- `segmentOnly` 是诊断状态，不是质量档位。默认分区把它排除；显式查看时只渲染紧凑行和说明，不加载大预览、不暴露下载按钮。
- 组排序按捕获时间升序。入口跟随最后一项，但只有用户仍处于“跟随最新”状态时才随新候选移动，保持操作 Locality。
- 1.2.0 删除旧浏览器下载/解析 HTML、录制脚本、在线 FFmpeg、DNR 移动 UA、密钥 UI、旧图片/库/国际化目录；安装器覆盖升级会仅在程序拥有的扩展目录内删除同一清单的遗留项。
- 发行许可证统一为 GPL-3.0。固定上游快照位于 `third_party/cat-catch/source`，只用于版权、对应源码与行为溯源，不进入活动扩展载荷。

## 1.2.1 YouTube MSE 结构化发现

```text
YouTube MAIN world
  ytInitialPlayerResponse / youtubei player JSON
                    │
                    ▼
  adaptiveFormats（videoId + itag + 直接 URL）
                    │ postMessage（随机页面通道）
                    ▼
YouTube content bridge → background addMedia → 媒体候选组
                    │
                    ▼
popup 选择视频/音频 → 认证提交 → 桌面 FFmpeg 下载、合并、校验
```

- MSE 下 `video.currentSrc` 可能是 `blob:` 或 YouTube 同源占位地址，不能代表可下载媒体；适配器在主世界只读取播放器已经公开的格式目录，不注入下载或解密逻辑。
- `youtube-content.js` 为每次页面加载创建随机消息通道，验证来源窗口和消息形状后把结构化流转给后台；页面导航和 player API 响应都会触发重新扫描，指纹相同的目录不会重复发送。
- `groupKey=youtube:<videoId>` 保持同一内容归组，`streamId=itag` 保持不同清晰度/音轨独立。轮换 URL 的同一 itag 可折叠，不同 itag 即使共享 `/videoplayback` 路径也不得折叠。
- 只有明确的 `http/https` 直接 URL 进入候选；仅有 `signatureCipher.s` 的格式跳过并保留安全边界。浏览器不解签、不下载、不持久化 URL，桌面仍是唯一执行者。
- 网络层见到的显式 Range 和无内容身份的小于 128 KB 音视频探测进入 `segmentOnly`，默认不污染内容/质量主线。

## 1.2.2 YouTube SABR 目录与桌面解析

```text
YouTube player response
  adaptiveFormats（高度/编码/大小，无直链）+ serverAbrStreamingUrl
            │ 去重为实际高度目录
            ▼
扩展 resolver=youtube 候选组 ── 用户选择 1440p/1080p/…
            │ 配对 API：页面 + 高度 + 当前标签最小请求上下文
            ▼
桌面 MediaCoordinator
  临时 Netscape cookie ── yt-dlp + Deno ── 瞬时视频/音频 URL
          │ finally 删除                    │
          └──────────────────────────────────┴─→ FFmpeg streamcopy → FFprobe → 本地/Eagle
```

- `catch-script/youtube.js` 仍只读取页面已有播放器数据。带直接 URL 的传统自适应格式继续按 itag 建模；无直链但有 SABR 服务地址且存在多档视频高度时，改为一个解析器候选，不把 `serverAbrStreamingUrl` 伪装成 HLS/DASH。
- `background.js` 只为 `resolver=youtube` 合并当前标签页已经观测到的 YouTube 请求上下文；映射随主框架导航、标签关闭或 service worker 生命周期清理，其他候选不共享。
- popup 的 `resolver` 选择模式把编码细节折叠为用户可判断的唯一高度目录。计划只携带一个页面项和 `preferredQuality`，不把 56 条元数据当作 56 个下载 URL。
- 桌面解析器只负责把所选准确高度映射为一条视频 URL 和最佳音轨 URL；远程字节下载、合并、进度和完整性检查仍走统一 FFmpeg 状态机。解析器错误单独标记 `youtube_resolve_failed/youtube_quality_unavailable`。

## 1.2.3 通用 blob 页面解析与区间重建

```text
页面 video(blob:) ── 当前帧/标题/时长 ─┐
内容容器同源永久链接 ────────────────┼─ resolver=page 候选
首方请求最小会话上下文（仅内存） ────┘          │
                                                  ▼
                                yt-dlp + Deno 解析完整轨
                                                  │
CDN bytestart/byteend ── 去偏移、保留签名 ── 技术后备
                                                  │
                                                  ▼
                          统一 FFmpeg → FFprobe → 本地/Eagle
```

- `chooseContentPageUrl` 只接受同源稳定内容地址；路径/安全查询结构覆盖帖子、Reel、video/status/comments/pin 和 Watch `v`，不从普通主页猜测内容。抖音 `modal_id` 自 1.2.4 起由当前主播放器适配器独立规范化。
- `resolverRequestContextByTab` 只在 service worker 内存中按标签页和首方主机保存白名单请求头，主导航和标签关闭立即删除。计划 API 继续只在 `_remote_inputs` 保存完整上下文，数据库写脱敏 URL。
- `MediaCoordinator._resolve_page_streams` 使用固定 yt-dlp/Deno 将一个内容页解析为一条完整视频或视频+音频；cookie 文件位于任务临时目录并在 `finally` 删除。解析结果进入既有 FFmpeg 状态机，不新增站点下载器。
- `bytestart/byteend` 与其他固定区间先按通用传输分片判定。Instagram 的 `efg/xpv_asset_id` 只补充分轨归组、时长、码率和完整大小估算；删除偏移后的签名地址是后备，不改变下载职责边界。
- 默认分区在同一标签页/来源域存在稳定页面解析候选时隐藏重建后备；技术分片开关仍可展示，便于诊断解析器不支持或会话失效场景。

## 1.2.4 抖音当前主播放器适配

```text
精选页多个 video
      │ 视口交集 + 播放状态 + 进度 + 面积
      ▼
唯一当前主播放器 ── 标题 / 当前帧 / 223.237 秒 / 尺寸
      │
      ├─ HTTP currentSrc ───────────────→ 统一本机 FFmpeg
      │
      └─ blob + 明确 modal_id
                  │
                  ▼
       https://www.douyin.com/video/<id>
                  │ resolver=page
                  ▼
             yt-dlp + Deno ─────────────→ 统一本机 FFmpeg
```

- 适配器只确定当前内容身份和可信入口，不新增抖音下载器、任务状态机、合并器或浏览器下载分支。
- 屏外预加载播放器即使已就绪也不能成为当前候选；主播放器的 HTTP 地址优先于页面解析，避免把可直接下载的完整媒体退化为站点解析。
- `/video/<id>` 与数字 `modal_id` 是唯一可接受的抖音页面身份。直接流和页面候选使用同一 `douyin:<videoId>`，无明确 ID 的 `/jingxuan` 不可提交。
- 1.2.3 产生的旧无身份页面候选在 popup 归组前过滤；桌面仍兼容规范化带 `modal_id` 的同次运行旧任务，并把不支持地址与会话失效分开报告。

## 1.2.5 抖音逐视频内容身份

```text
feed-item A ─ video_766... ─ @作者A + 文案A ─ douyin:766...
feed-item B ─ video_765... ─ @作者B + 文案B ─ douyin:765...

blob/MSE 原始请求 ── 无法精确绑定 video ID ──→ 技术分片（默认隐藏/不可提交）
```

- 当前项和页面已预载项都可以成为内容候选，但必须从各自最近的 `feed-item` 读取身份，不能读取全局 active 容器或标签页标题。
- 适配器只产出内容身份、可信页面入口和展示元数据；每个候选仍走统一桌面解析、FFmpeg、FFprobe 与 Eagle 流程。
- 无法精确绑定的底层请求保留诊断可见性，但不再作为完整视频；这避免用错误标题掩盖内容身份未知。

## 1.2.6 通用信息流内容绑定

```text
最近内容容器 ── 同源永久链接 ── resolver=page 内容候选
      │                 ├─ 自身标题/正文
      │                 ├─ 自身 poster/当前帧
      │                 └─ 自身时长
      │
      └─ blob/MSE 底层 HLS/DASH/音视频请求
             │ 无法证明属于哪张内容卡片
             ▼
       未关联技术资源（默认隐藏、不可提交）
```

- `content-script.js` 对每个 blob/MSE 播放器只检查最近内容容器；永久链接仍由 `chooseContentPageUrl` 的同源结构规则确认，不读取浏览历史、不从主页猜内容 ID。
- `selectContentTitle` 在容器内部按语义说明、标题、可读行和图片说明排序，过滤纯计数、播放器时间轴、相对时间与控件词。标签页标题只在容器没有任何有意义文本时作为最后回退。
- `partitionGroups` 只在同一 `tabId + sourceDomain` 已存在 `resolver=page` 内容候选时降级孤立播放请求。若页面没有内容绑定替代项，完整清单仍保留在默认列表，避免通用规则误伤仅靠网络清单的网站。
- 技术开关返回带 `technicalOnly` 标记的只读诊断组；UI 紧凑显示并由 `validateSelection` 返回 `unbound_playback`，批量选择也排除这些组。
- service worker 的工具栏角标先 `groupCandidates` 再 `partitionGroups`，与 popup 的默认可见数量一致。

## 1.2.7 通用信息流发现生命周期

```text
DOM 连续变化 ── 有界合并调度 ── 250 ms 内页面候选扫描

popup 打开/刷新 ── 探测当前 HTTP(S) 标签内容脚本
                         │
              ┌──────────┴──────────┐
              │已响应               │无接收端
              ▼                     ▼
           立即扫描       注入候选逻辑 + 内容脚本
                                      │
                                      ▼
                                   立即扫描
```

- `createBoundedScheduler` 采用单个待执行任务合并连续变化；它不会像尾随防抖一样反复重置期限，因此高频信息流 DOM 更新不能饿死发现扫描。
- 内容脚本启动时立即扫描，并响应 `discoverPageResolvers` 主动探测；网络请求仍只作媒体线索，页面候选不依赖下一条请求触发。
- popup 在读取候选快照前调用 `ensureDiscovery`。后台先尝试消息探测，只有接收端不存在时才通过 `chrome.scripting` 向当前顶层 HTTP(S) 标签注入 `eagle-bridge-candidate-logic.js` 与 `content-script.js`。
- 恢复只修复浏览器发现生命周期，不新增下载器、站点路由或跨标签注入；页面候选仍进入 1.2.6 的通用内容绑定与技术资源分区。

## 1.2.8 通用页面分轨格式兼容

```text
页面解析格式目录
      │
      ├─ MP4 视频 + M4A 音频（首选）
      ├─ MP4 视频 + MP4 音频
      ├─ 合并 MP4
      ├─ MP4 视频 + 任意音频
      └─ 通用最佳分轨 / 合并格式
                    │
                    ▼
          FFmpeg streamcopy + FFprobe
```

- yt-dlp 的格式 `ext` 描述轨道容器，不等同于媒体角色；独立 AAC 音轨可以标记为 MP4，不能因为不是 M4A 就判定页面无可用格式。
- 选择顺序先保护 MP4/M4A 的既有兼容输出，再逐级放宽；页面解析只返回一条视频和可选的一条音频，实际下载、映射、合并和验证仍由统一桌面状态机完成。
- 规则只检查格式属性，不读取站点域名；Pinterest 仅作为复现与现场验收样本。

## 1.2.9 结构化视频页面发现

```text
Open Graph / Twitter Player 明确视频声明
                 │
       同源、非首页规范作品地址
                 │
                 ▼
       resolver=page 内容候选 ─────→ 桌面 yt-dlp
                 │
                 └─ 标题 / 封面 / 尺寸 / 时长

未关联播放器请求 ────────────────→ 技术区（隐藏、不可提交）
```

- 页面可能在顶层只提供视频元数据，运行时再创建跨域播放器；扩展不能依赖读取播放器内部 DOM 或 `window.playerConfig` 才建立内容身份。
- `chooseStructuredVideoPageUrl` 要求明确的视频类型、Player 卡片或媒体地址证据，并只接受当前来源的非首页规范地址；删除查询与片段后作为稳定页面入口。
- 结构化入口只补充内容身份，不暴露或持久化播放器签名 URL，不改变网络捕获、技术分区和统一本机下载边界。

## 1.2.10 多视频页面候选恢复

```text
同一标签页 / 同一来源域名
       │
       ├─ 主播放器 ── 当前作品页
       ├─ 相关播放器 ── 最近的稳定作品链接
       ├─ 独立完整 MP4/HLS/DASH ── 保持可见可选
       └─ 已确认传输分片 ── 技术区（默认隐藏）
```

- 页面解析候选只能证明它自身代表的内容，不能证明同标签页或同域名的其他完整媒体是重复项。`partitionGroups` 因此只按 `segmentOnly` 隐藏结构已确认的传输分片。
- `nearbyVideoContent` 从播放器自身逐层向外检查链接，使用第一个不同于当前页的稳定同源内容地址；没有更近地址时保留当前作品页。主作品与相关推荐不会再共享一个页面身份。
- 选择规则由通用 URL 规范化、DOM 距离和媒体结构驱动，不读取 Pinterest 或其他复现站点域名。

## 1.2.11 桌面代理路由

```text
新远程媒体任务
      │
      ├─ 自动 ── Windows 当前用户系统代理 ──┐
      │                │未检测到             │
      │                └──────────→ 直连      │失败最多一次
      │                                      └──→ 直连
      ├─ 手动 ── 用户填写 HTTP/Mixed 端口（不静默绕过）
      └─ 直连

同一任务线路 ──→ FFmpeg/ffprobe、yt-dlp、字幕请求
本机 Eagle/API ─────────────────────────────→ 始终直连
```

- `NetworkProxyManager` 从通用 settings 表读取模式；自动模式按任务查询 WinINET 当前用户代理，设置变化不需要重启软件。
- 代理选择是任务级值，不修改 Windows、代理软件或全进程环境，避免把 Eagle、本机配对和控制信号错误送入代理。
- 自动模式的线路数组最多包含“系统代理、直连”两项；状态机只对网络型错误前进一次，不会重新排队形成循环。手动和直连模式都只有一项。
- FFmpeg/ffprobe 使用输入级 HTTP proxy，yt-dlp 使用固定 `--proxy` 参数，字幕请求使用任务专用 ProxyHandler。端点验证拒绝控制字符、用户信息、无端口和非 HTTP 协议。

## 1.3.0 微信视频号本机来源

```text
下载中转站桌面 UI
      │ 显式开始/停止
      ▼
WechatChannelsCaptureService
      ├─ CertificateAuthority ── 当前用户根证书 / 多目标叶证书（每机唯一）
      ├─ WinInetProxyLease ───── 原配置快照 / 所有权 / 精确恢复
      ├─ LoopbackHttpsProxy ──── 目标 TLS、非目标隧道、上游代理链
      ├─ module hooks + bridge ─ 微信内部返回值观察、objectId 归组、原操作栏下载入口
      └─ CandidateRegistry ───── 短期 URL/头/decodeKey（只在内存）
                                      │
                                      ▼
                              MediaCoordinator.create_plan
                                      │
                         下载 → 必要解密 → 合并 → ffprobe
                                      │
                         completed_local / Eagle 官方 API
```

### 生命周期与网络所有权

- 捕获首次默认关闭。开始动作先检查端口和证书，再持久化 WinINET 的 ProxyEnable、ProxyServer、ProxyOverride、AutoConfigURL、AutoDetect 与 `Connections` 二进制值，最后把当前用户代理指向回环服务。写入失败先用租约恢复；恢复也失败时保留租约和“需要恢复”状态。
- 服务停止、应用退出或启动中途失败时先验证代理所有权并尝试恢复原配置，再结束代理监听、HTTP/媒体和旧任务线程，最后清理会话秘密。异常退出不能保证执行清理，因此下次启动读取带实例标识的租约；仅当当前配置仍指向该实例时恢复。
- 非目标 CONNECT 不解密。目标主机集合由视频号协议能力维护，不由某条视频 URL、用户账号或页面样本生成。Eagle、回环 API 和本机控制始终绕过。
- 若捕获前已有系统 HTTP/Mixed 代理，回环代理把公网连接链到原上游，避免开启视频号时切断用户既有线路。PAC/SOCKS 等无法安全链式复用时开始动作明确阻止并说明，不静默改成直连。

### 页面与候选

- 代理在视频号 HTML 的最早可用位置加入同源静态 `bridge.js`，并给页面脚本/ES 模块依赖追加本次捕获会话缓存键，确保开启后的模块确实经过本机代理。`bridge.js` 继续观察 fetch/XHR/Response JSON；代理还在 `res.wx.qq.com` 返回的微信资源模块中，按稳定的 `finderPcFlow`、`finderGetRecommend`、`finderGetCommentDetail` 等方法边界加入结果观察调用。包装使用内层 async 箭头保留原返回、异常、`this` 和 `await` 语义，只把微信已经取得的结构化对象交给同一白名单扫描器，不调用内部下载能力。
- 资源脚本已检查数、成功改写数、安装钩子数与实际内部 API 返回次数只作为整数诊断进入健康状态；不记录资源 URL、账号、feed、Cookie、签名或解密键。入口改名或结构失配会显示为“脚本已见但钩子为 0”或“钩子已装但内部数据为 0”，不再把所有失配都显示成无限等待。
- `CandidateRegistry` 以 `wechat-channel:<objectId>` 为键，把 feed 的媒体项、实际质量、作者、封面、时长和可靠来源归组。原始/最高入口保留原签名查询；每个实际 `fileFormat` 规格只追加 `X-snsvideoflag`，不重编码已有签名参数。签名 URL、请求头和 decodeKey 留在进程内存，桌面 UI/API 返回的是脱敏候选视图。
- `bridge.js` 在首页推荐和详情页已有 `.click-box.op-item` 操作栏旁加入自有下载按钮，并用 MutationObserver 处理微信复用/重建的 DOM；找不到操作栏时才创建固定悬浮后备。普通点击从当前视频 URL 的 `X-snsvideoflag` 或原始规格选择当前 variant，悬停菜单展示服务端脱敏候选视图中的实际 variants。当前内容先按 URL 中 objectId、媒体主机+路径、同一内容标题唯一匹配，再使用内部详情事件；多候选无法唯一绑定时拒绝。页面经随机会话令牌只提交 objectId/variantId，`WechatChannelsCaptureService.submit` 再调用 `MediaCoordinator.create_plan`。桌面候选页仍保留完整核对和手动入口，统一任务页显示下载、解密、合并、校验、等待 Eagle 和终态。

### 下载与解密

- 普通视频号媒体复用既有远程输入下载。带 decodeKey 的媒体在任务专属临时目录边下载边执行 ISAAC-64 密钥流异或；只有声明的加密前缀处理，后续明文字节原样写入。
- 解密器支持任意输入分块和 Range 起点，不把完整视频读入内存。输出仍需通过现有 FFmpeg/ffprobe 映射和完整性校验，错误密钥或长度不符不得进入完成态。
- 计划终态立即从 `MediaCoordinator._remote_inputs` 和视频号会话删除签名 URL、请求头、Cookie 与 decodeKey。重启只恢复安全任务状态，不恢复或猜测短期上下文。
