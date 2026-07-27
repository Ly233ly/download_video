# Figma 深色桌面界面重构计划

日期：2026-07-27
基线：download-for-eagle `1.4.1`（commit `aecd8cc`）
Figma 原型：Figma-test-download（React + TypeScript + Tailwind，只读参考）
状态：分析完成，等待确认后进入阶段 0

> 本文档是分析产物，不是实现。所有修改必须经过用户确认后方可开始。

---

## 1. 当前正式桌面 UI 架构

### 1.1 顶层结构

`src/idm_eagle_bridge/ui.py`（约 2500 行）是唯一的 Tkinter 桌面界面文件。

| 组件 | 类型 | 职责 |
| --- | --- | --- |
| `MainWindow` | 类 | 主窗口、生命周期、刷新调度、所有页面构建和事件处理 |
| `_VerticalScrolledFrame` | 类 | 外层纵向滚动容器，支持 Treeview/Combobox 内滚不抢外层 |
| `_AsyncProbe` | 类 | Eagle 后台探测，不阻塞 Tk 主线程 |
| `_PreviewImageCache` | 类 | 预览图片缓存，按路径/大小/mtime 复用解码结果 |
| `_sync_tree_rows` | 函数 | Treeview 增量投影，只修改变化行 |
| `_media_plan_view` | 函数 | 媒体计划状态→视图模型转换 |
| `SiteRulesWindow` | 类 | 独立网站规则管理窗口（Toplevel） |
| `ProxySettingsWindow` | 类 | 独立网络代理设置窗口（Toplevel） |
| `_configure_styles` | 函数 | ttk 全局样式配置 |

### 1.2 布局层级

```
Tk root (1120×720, min 900×600)
├── Shell (App.TFrame)
│   ├── Sidebar (190px, Sidebar.TFrame)
│   │   ├── Brand (logo + "下载中转站")
│   │   ├── Nav buttons (下载任务 / 视频号 / IDM 导入 / 设置)
│   │   └── 诊断 button
│   └── Workspace (Surface.TFrame)
│       ├── Topbar (page title + status + version + refresh)
│       └── _VerticalScrolledFrame
│           └── page_host (5 个页面 frame，pack_forget 切换)
```

### 1.3 当前视觉方案

`UI` 字典定义暖灰/米色亮色主题：

| Token | 值 | 用途 |
| --- | --- | --- |
| `canvas` | `#F4F2EF` | 窗口底色 |
| `sidebar` | `#EEEAE6` | 左侧导航 |
| `surface` | `#FCFBF9` | 内容区底色 |
| `surface_alt` | `#F7F4F1` | 次级表面 |
| `selected` | `#EDE5E4` | 选中态 |
| `border` | `#DED9D4` | 边框 |
| `text` | `#272522` | 正文 |
| `muted` | `#716C67` | 次级文字 |
| `accent` | `#9A6470` | 主操作（紫灰） |
| `accent_dark` | `#80515C` | 主操作 hover |
| `success` | `#3F7D4B` | 成功 |
| `warning` | `#A66B24` | 警告 |
| `danger` | `#B24747` | 危险/失败 |

字体：`Microsoft YaHei UI`（CJK）、`Segoe UI`（Latin）
主题引擎：`clam`（禁止 `vista` 忽略自定义颜色）

### 1.4 刷新生命周期

```
MainWindow.__init__
  → _build() → _show_page("media") → refresh()
  
refresh() 循环:
  1. 检查 visible（隐藏时降频至 30s）
  2. 读取 Eagle 探测结果（_AsyncProbe.poll）
  3. 读取 db.ui_snapshot() 仪表盘
  4. 更新顶部状态文本
  5. _refresh_media_tasks（增量 _sync_tree_rows）
  6. _refresh_wechat_candidates（增量，含预览事件排空）
  7. IDM job 增量（仅 revision 变化时）
  8. 更新动作按钮启停
  9. schedule next: 1s（有活动任务）或 4s（空闲）
```

### 1.5 页面结构详情

**下载任务页（media）**：
- 工具栏（说明文字 + 清除终态 + 刷新）
- 水平 Panedwindow（weight 3:2）：左侧 Treeview（状态/标题/来源/进度）+ 右侧详情面板
- 详情面板：预览区（150px 高）、标题、状态/错误文本、进度条、来源/文件信息、5 个动作按钮

**视频号页（wechat）**：
- 头部：状态文本 + 开始/停止按钮
- 水平 Panedwindow（weight 3:2）：左侧 Treeview + 右侧详情
- 详情：封面预览、标题/作者、内容 ID/时长/输出名、质量 Combobox、交付方式 Radio、创建按钮

**IDM 导入页（idm）**：
- 工具栏（清除终态 + 刷新）
- 说明文字
- 5 列 Treeview（时间/状态/文件/来源/说明）
- 底部 4 个动作按钮

**设置页（settings）**：
- 4 个 Card TLabelframe（配对/网站规则/网络/更新）纵向排列
- 网站规则内嵌 Treeview + CRUD 按钮
- 网络：3 个 Radio + 手动输入 + 保存/状态
- 更新：说明 + 检查按钮

**诊断页（diagnostics）**：
- 脱敏诊断 Card + 导出按钮
- 窗口管理 Card（隐藏/最小化）

---

## 2. Figma 视觉结构拆解

### 2.1 全局顶部状态栏（约 40px）

```
┌────────────────────────────────────────────────────────────┐
│ [↓] 下载中转站 v1.4.0    ● Eagle  ● 服务  ● Chrome  SQLite│
└────────────────────────────────────────────────────────────┘
```
- 高度：`h-10`（40px）
- 背景：`#0d0f16`
- 底部边框：`border-white/5`
- 产品图标：3×3 的 indigo-500 色块内含 ↓ 箭头
- 产品名：`text-[13px] font-semibold text-white/90`
- 版本号：`text-[10px] font-mono text-white/25`
- 状态指示灯：绿点（正常）或灰点（离线）
- SQLite 版本：`text-white/20 text-[11px] font-mono`

### 2.2 左侧主导航（200px）

```
┌──────────────┐
│ 下载任务      │  ← indigo selection bg
│ 视频号        │
│ IDM 导入      │
│ 设置          │
│              │
│──────────────│  ← 分割线
│ 导出诊断信息   │
└──────────────┘
```
- 宽度：`w-[200px]`
- 背景：`#111318`
- 右边框：`border-white/5`
- 按钮样式：默认 `text-white/45`，选中 `bg-indigo-500/15 text-indigo-300`
- 图标：16px SVG inline
- 底部诊断：`text-white/30`，p2 + border-t 分隔

### 2.3 下载任务主从布局

**左侧任务列表（360px）**：
- 头部：`媒体任务` 标题 + `清除已完成` 按钮
- 任务行：缩略图(48×32) + 标题 + 来源域名 + 状态徽标 + 大小 + 时间
- 活跃任务显示细进度条（h-1）
- 选中态：`bg-indigo-500/10`

**右侧详情面板**：
- 顶部：标题 + 来源 + 动作按钮（停止/重试/补导/打开目录）
- 预览区：`aspect-video max-w-md` 圆角缩略图 + 时长叠加
- 2×2 状态网格：状态、进度、大小、来源
- 输出路径（全宽）
- 系统备注（圆角面板）

### 2.4 视频号主从布局

- 左侧（360px）：捕获控制栏 + 候选列表
- 捕获控制：状态指示 + 动画脉冲点 + 开始/停止按钮 + 清空
- 候选列表：缩略图(64×40) + 标题 + 作者 + 时长 + 质量
- 空状态：emoji + 提示文字
- 右侧详情：封面 + 时长/捕获时间/预计大小/质量选择 + 两个交付按钮

### 2.5 IDM 表格与详情

- 全宽表格：时间、状态、文件名、来源网站、说明
- 顶栏工具栏：标题 + 右侧动作按钮（重试/打开位置/来源网页/清除已完成）
- 底部分源面板：当选中 waiting_source 时显示输入框 + 确认按钮
- 表头：sticky top-0，`bg-[#111318]`

### 2.6 设置页二级导航

- 左侧标签栏（w-40）：配对/网站规则/网络代理/更新
- 右侧面板切换内容
- 配对：大六位码 + 复制按钮 + 浏览器配对状态 + 解除配对
- 网站规则：输入框 + 添加按钮 + 表格 + 行内 Toggle 开关 + 删除
- 网络代理：3 个 Radio 卡片（带描述） + 手动输入 + 验证保存
- 更新：已是最新状态卡 + 手动检查 + 更新历史 + 安全说明

### 2.7 状态徽标

```tsx
StatusBadge({ label, color })
// 示例: "下载中" → text-blue-400 bg-blue-400/10
// 11px, rounded, px-2 py-0.5, font-mono
```
12 种媒体计划状态色、10 种 IDM 状态色，各自独立配色。

### 2.8 进度条

```tsx
ProgressBar({ value, status })
// h-1, bg-white/5, rounded-full
// 颜色根据状态: indigo(活跃) / emerald(完成) / orange(等待Eagle) / red(失败)
// transition-all duration-700
```

### 2.9 按钮分级

| 级别 | Figma 样式 | 场景 |
| --- | --- | --- |
| 主按钮 | `bg-indigo-500 text-white` | 创建下载任务、导入 Eagle |
| 次按钮 | `bg-white/5 text-white/60` | 打开目录、来源网页、刷新 |
| 危险按钮 | `text-red-400 bg-red-400/10` | 停止任务 |
| 启停按钮 | 绿（开始）/ 红（停止）半透明 | 视频号捕获 |
| 导航按钮 | 文字 + 背景色变化 | 侧栏、设置 Tab |
| Toggle | 滑动开关，indigo | 网站规则 |

### 2.10 空/加载/错误/禁用状态

- 空状态：居中文字 + emoji 图标
- 加载状态：脉冲动画（视频号捕获中）
- 错误状态：红色文字 + 错误描述
- 禁用状态：降低不透明度（`text-white/20` 级别）

---

## 3. 功能 ID 迁移矩阵

### DESK-001 ~ DESK-025 映射

| 功能 ID | 当前 ui.py 位置 | Figma 对应区域 | 计划修改文件 | 数据来源 | 真实动作 | 按钮启用条件 | 测试 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DESK-001 | `_build`、`_show_page`、nav buttons | Sidebar + TopBar | `ui.py` | `Database`、`LocalApiServer`、`ProcessingService` | `_show_page`、nav 样式切换 | 始终可用 | `test_ui_layout.py`、视觉 QA |
| DESK-002 | `_VerticalScrolledFrame`、`_new_page` | 主内容区 scroll | `ui.py` | Tk | 同现有滚动逻辑 | 始终可用 | `test_ui_layout.py` |
| DESK-003 | `_AsyncProbe`、`_PreviewImageCache`、`_sync_tree_rows`、`refresh` | 无直接对应（Figma 无刷新概念） | `ui.py` | `Database.ui_snapshot`、`MediaCoordinator.health` | 同现有增量刷新 | 始终可用 | `test_ui_layout.py` |
| DESK-004 | `copy_pairing_code`、`unpair` | Settings > pairing | `ui.py` | `PairingManager` | `copy_pairing_code`、`unpair` | 始终可用 | `test_security_api.py` |
| DESK-005 | `export_diagnostics` | 侧栏底部诊断 | `ui.py` | `security.py`、各子系统 | `export_diagnostics` | 始终可用 | `test_security_api.py` |
| DESK-006 | `show`、`hide`、`_poll_control_signals`、`quit` | 无（Figma 是网页） | `ui.py` | `ControlSignals` | 同现有显示/隐藏 | 始终可用 | `test_control_signal.py` |
| DESK-007 | `_build_media_tab`、`_refresh_media_tasks` | DownloadsPage 左侧列表 | `ui.py` | `MediaCoordinator.list_plans` | `_sync_tree_rows` 增量投影 | 始终可见 | `test_ui_layout.py`、`test_media.py` |
| DESK-008 | `_update_plan_detail`、`preview_cache` | DownloadsPage 右侧详情 | `ui.py` | `MediaCoordinator.get_plan_preview` | `_update_plan_detail` | 选中任务时 | `test_ui_layout.py`、`test_media.py` |
| DESK-009 | `stop_selected_plan`、`retry_selected_plan`、`open_plan_location`、`open_plan_source` | 详情顶部动作按钮 | `ui.py` | `MediaCoordinator` 各方法 | 同现有 | 按 `_media_plan_view` 返回的权限 | `test_media.py` |
| DESK-010 | `import_selected_plan` | "补导 Eagle" 按钮 | `ui.py` | `MediaCoordinator.import_completed_plan` | 同现有 | `can_import_existing and final_exists` | `test_media.py`、`test_processor.py` |
| DESK-011 | `clear_media_history` | "清除已完成" | `ui.py` | `MediaCoordinator.clear_terminal_history` | 同现有 | 始终可用 | `test_media.py` |
| DESK-012 | `_build_idm_tab`、`refresh`→job sync | IDMPage 表格 | `ui.py` | `Database.list_jobs`、`ui_snapshot` | `_sync_tree_rows` | 始终可见 | `test_ui_layout.py`、`test_processor.py` |
| DESK-013 | `retry_selected`、`open_file_location`、`open_source` | IDMPage 工具栏动作 | `ui.py` | `Database.retry_job` | 同现有 | 按 `_update_idm_actions` 权限 | `test_processor.py` |
| DESK-014 | `assign_source` | IDMPage 来源面板 | `ui.py` | `Database.assign_source`、`EagleClient.update_source` | 同现有 | 非 skipped_duplicate | `test_database.py` |
| DESK-015 | `clear_history` | "清除已完成" | `ui.py` | `Database.clear_terminal_history` | 同现有 | 始终可用 | `test_database.py` |
| DESK-016 | `toggle_wechat_capture`、`_run_wechat_operation`、`_poll_wechat_operation` | WeChatPage 捕获控制 | `ui.py` | `WechatChannelsCaptureService` | 同现有 | 非 busy | `test_wechat_channels.py` |
| DESK-017 | `_refresh_wechat_candidates` | WeChatPage 候选列表 | `ui.py` | `WechatCandidateRegistry.list`、`WechatChannelsCaptureService.candidates` | `_sync_tree_rows` | 始终可见 | `test_wechat_channels.py` |
| DESK-018 | `_update_wechat_detail`、`_load_wechat_preview`、`_drain_wechat_preview_events` | WeChatPage 右侧详情 | `ui.py` | `WechatCandidateRegistry`、`WechatChannelsCaptureService.preview_png` | 同现有异步加载 | 选中候选时 | `test_wechat_channels.py`、`test_ui_layout.py` |
| DESK-019 | `submit_selected_wechat_candidate` | WeChatPage 交付按钮 | `ui.py` | `WechatChannelsCaptureService.submit`、`MediaCoordinator.create_plan` | 同现有 | 有选中候选 | `test_wechat_channels.py`、`test_media.py` |
| DESK-020 | `clear_wechat_candidates` | "清空" 按钮 | `ui.py` | `WechatChannelsCaptureService.clear_candidates` | 同现有 | 始终可用 | `test_wechat_channels.py` |
| DESK-021 | `_build_settings_tab`、`_refresh_settings` 中 site 部分 | Settings > sites | `ui.py` | `Database.list_site_rules` | `_sync_tree_rows` | 切换到设置页时 | `test_database.py`、`test_ui_layout.py` |
| DESK-022 | `_settings_add_rule` 等 5 个方法 | Settings > sites 操作 | `ui.py` | `Database` CRUD | 同现有 | 按选中状态 | `test_database.py` |
| DESK-023 | `_build_settings_tab` 中 network 部分 | Settings > network | `ui.py` | `NetworkProxyManager` | 同现有 | 始终可用 | `test_network_proxy.py` |
| DESK-024 | `check_for_updates`、`_automatic_update_check` 等 | Settings > updates | `ui.py` | `updater.py` | 同现有（异步 + event queue） | 非 checking/downloading | `test_updater.py` |
| DESK-025 | updater 内部（非 UI） | 无 | `updater.py`（不修改） | RSA/size/SHA-256 | 不变 | — | `test_updater.py` |

### CORE-001 ~ CORE-017 影响桌面的映射

| 功能 ID | 桌面可见影响 | 本次处理方式 | 数据来源不变 |
| --- | --- | --- | --- |
| CORE-001 | IDM 新任务出现在列表 | 仅 Treeview 样式 | `hook.py`、`Database.add_job` |
| CORE-002 | 任务快速响应 | 不修改 | `ProcessingService` |
| CORE-003 | 状态文案 "非视频忽略"、"文件尚未稳定" | 仅状态徽标配色 | `JobProcessor` |
| CORE-004 | 无来源任务不卡住 | 仅状态徽标配色 | `JobProcessor`、`Database` |
| CORE-005 | SHA-256 去重提示 | 仅状态徽标配色 | `fingerprint.py` |
| CORE-006 | Eagle 等待/重试次数区分 | 仅状态徽标配色 | `JobProcessor`、`EagleClient` |
| CORE-007 | Eagle 健康状态 | 顶部状态栏绿/灰点 | `EagleClient` |
| CORE-008 | 创建计划阻断提示 | 不修改（桌面只显示结果） | `MediaCoordinator.create_plan` |
| CORE-009 | 统一状态机进度 | 仅配色 + 百分比规则 | `MediaCoordinator` |
| CORE-010 | FFmpeg 校验阶段 | 仅状态文案配色 | `MediaCoordinator` |
| CORE-011 | 代理模式/错误提示 | 仅设置页配色 | `NetworkProxyManager` |
| CORE-012 | planId 动作 | 仅按钮配色 | `MediaCoordinator` |
| CORE-013 | 目录归属校验 | 仅按钮启用条件 | `MediaCoordinator._owned_plan_file` |
| CORE-014 | 导入后删除 | 仅交付 Radio 标签文案配色 | `JobProcessor` |
| CORE-015 | 升级后数据保留 | 不修改 UI | `Database.initialize` |
| CORE-016 | 配对状态 | 顶部 Chrome 绿/灰点 + 设置文案 | `PairingManager` |
| CORE-017 | 视频号状态/恢复 | 顶部状态汇总 + 视频号页状态文本 | `WechatChannelsCaptureService` |

### EXT-001 ~ EXT-034

全部标记为**本次不修改**。扩展 popup（660×574）保持不变。

---

## 4. Figma 与正式功能的冲突清单

### 4.1 Figma 缺失的真实状态

| Figma 缺失 | 正式实现必须保留 | 处理方式 |
| --- | --- | --- |
| `merging` 阶段 | `MEDIA_STATUS_TEXT["merging"]` = "本机正在合并" | 新增 `merging` 状态徽标（色值参考 `downloading` 或使用独立色） |
| `import_failed` 阶段 | Eagle 导入失败与下载失败分离 | 已有独立状态，保留 |
| `needs_rebuild` 阶段 | "需要回到来源重建" | 已有独立状态，保留 |
| `retry`（媒体任务） | 下载失败可重试 | Figma 有 `retry`，但把 `failed_permanent`/`import_failed`/`canceled`/`needs_rebuild` 全合并为 retryable，正式不可合并 |
| `waiting_wechat` 捕获状态 | "等待微信中打开视频号内容" | 新增状态，Figma 只有 ready/capturing |
| `needs_recovery` 捕获状态 | "需要确认代理恢复状态" | 新增状态，Figma 无此概念 |
| `preparing` 捕获状态 | "正在准备视频号捕获…" | 新增状态，Figma 无此概念 |
| `failed` 捕获状态 | 启动失败 | Figma 有 `error`，但无恢复引导 |
| 文件稳定性等待 | "文件不存在"、"文件为空"、"文件仍在增长" | IDM 表格说明列保留 |
| 来源等待超时 | "等待浏览器来源" + 超时解释 | IDM 表格说明列保留 |
| 12 次自动重试 vs 永久失败 | 当前重试次数和上限 | IDM 表格说明列保留 |

### 4.2 Figma 中错误或简化的进度语义

| Figma 行为 | 问题 | 正式实现 |
| --- | --- | --- |
| `waiting_eagle` 显示 progress=100、进度条绿色 | 等待 Eagle 意味着尚未导入，不应显示 100% | 仅 `completed_local` 和 `imported` 显示 100%；`waiting_eagle` 最多 99%，进度条使用 orange/amber |
| `validating` 显示 progress=98 | 接近正确但 Figma 将其与 downloading 同色（蓝） | 校验中应使用独立色（violet），表示文件正在验证 |
| Figma 无 `merging` 阶段 | 合并是独立阶段 | 新增 `merging`，使用独立色或等同于 downloading |
| Figma 把 `retry` 进度条同 downloading 显示 | `retry` 意味着上次失败 | `retry` 进度条使用 yellow/amber，表示中断后重试 |

### 4.3 Figma 中只有假实现的按钮

| Figma 按钮 | 假实现方式 | 正式实现 |
| --- | --- | --- |
| 停止任务 | `setPlans(ps => ps.map(...status: 'canceled'...))` | `MediaCoordinator.stop_plan(planId)`，需验证 plan 处于 active 状态 |
| 重试任务 | `setPlans(ps => ps.map(...status: 'queued', progress: 0...))` | `MediaCoordinator.retry_plan(planId)`，需验证 plan 处于 retryable 状态 |
| 补导 Eagle | `setPlans(ps => ps.map(...status: 'waiting_eagle'...))` | `MediaCoordinator.import_completed_plan(planId)`，需验证 completed_local + final_path 存在 |
| 打开目录 | `onClick={() => {}}` | `MediaCoordinator.open_plan_output(planId)`，需验证 final_path 存在且属于程序目录 |
| 创建下载任务 | 无实际后端调用 | `WechatChannelsCaptureService.submit()` → `MediaCoordinator.create_plan()` |
| 开始/停止捕获 | `setCaptureState(...)` | `WechatChannelsCaptureService.start()/stop()`，含证书检查、代理保存/恢复 |
| 添加网站规则 | `setSiteRules(...)` | `Database.set_site_rule(domain, enabled, subdomains)` |
| 配对码复制 | `setCopied(true)` | `root.clipboard_append(pairing_code)` |
| 解除配对 | 无实现 | `PairingManager.unpair()` |
| 检查更新 | 无实现 | `check_for_update()` → `prepare_update()` → 用户确认 → `launch_installer()` |

### 4.4 Figma 中写死的连接状态

```tsx
// Figma 写死
const [eagleOk] = useState(true)
const [serviceOk] = useState(true)
const [chromeOk] = useState(true)
```

**正式实现**：所有三个状态来自实时数据：
- Eagle：`_AsyncProbe` 后台探测 `EagleClient.is_available()`
- 服务：`api_server.address` 始终为本机后端的实际地址
- Chrome：`PairingManager.paired_origin` 非空即已配对

### 4.5 Figma 中写死的配对码

```tsx
const [pairingCode] = useState('482 917')
```

**正式实现**：`PairingManager.pairing_code` 每次生成不同。

### 4.6 Figma 中写死的网站规则

```tsx
const INITIAL_SITE_RULES = [
  { domain: 'youtube.com', enabled: true, ... },
  // ...
]
```

**正式实现**：`Database.list_site_rules()` 动态读取。

### 4.7 Figma 中写死的代理配置

```tsx
const [proxyMode, setProxyMode] = useState<'auto' | 'direct' | 'manual'>('auto')
const [proxyUrl, setProxyUrl] = useState('http://127.0.0.1:7890')
```

**正式实现**：`NetworkProxyManager.configuration()` 从持久化存储读取。

### 4.8 Figma 中写死的更新状态

```tsx
{/* 已是最新版本 */}
<p className="text-[12px] font-semibold text-emerald-400">已是最新版本</p>
```

**正式实现**：`check_for_update()` 异步获取，结果通过 `update_events` Queue 回传 UI。

### 4.9 Figma 中不存在但正式产品必须保留的错误与恢复路径

| 路径 | Figma 状态 | 正式处理 |
| --- | --- | --- |
| Eagle 探测失败 | 无（写死 true） | 顶部显示 "○ Eagle 未连接" |
| 后台线程异常 | 无 | `_AsyncProbe._run` catch Exception → result=False |
| 预览加载失败 | 无 | `_PreviewImageCache.resolve` catch → None，显示"下载完成后显示视频预览" |
| 视频号证书缺失/不受信任 | 无 | `toggle_wechat_capture` 中先检查，弹出 askokcancel 确认 |
| 视频号代理恢复冲突 | 无 | `needs_recovery` 状态，提示用户手动检查 |
| 视频号端口冲突 | 无 | `failed` 状态 + 错误信息 |
| 更新签名/哈希校验失败 | 无 | `UpdateError` → 用户可见错误弹窗 |
| 更新安装器启动失败 | 无 | `_handle_download_error` → 恢复按钮 |
| 网站规则非法域名 | 无 | `normalize_domain` 失败 → `InvalidPageUrl` 弹窗 |
| 代理地址格式无效 | 无 | `ProxyConfigurationError` → 错误弹窗 |
| 补导时文件已被删除 | 无（Figma 无此概念） | `final_exists` 检查，按钮保持 disabled |
| IDM 重试竞态（已 imported） | 无 | `Database.retry_job` 返回 False → 提示"已处理完成" |
| 来源 URL 无效 | 无 | `clean_page_url` 失败 → "网址无效" |
| 解除配对确认 | 无 | 正式无确认弹窗（`unpair` 直接执行） |

---

## 5. Tkinter 视觉实现方案

### 5.1 总体策略

- 零第三方运行时依赖（只用 stdlib tkinter + ttk）
- `clam` 主题继续使用（唯一确定性的跨 Windows 主题）
- 所有颜色在定义时预先混合（Tk 不支持 CSS rgba 透明度）
- 字体使用系统自带：中文 `Microsoft YaHei UI`、Latin `Segoe UI`

### 5.2 深色主题 Token 定义

将当前 `UI` 字典全面替换为深色 Token。所有颜色均为预混合的不透明值。

```python
UI = {
    # ── 基础层 ──
    "bg":              "#0D0F16",  # 窗口底色（Figma #0d0f16）
    "sidebar_bg":      "#111318",  # 侧栏底色
    "surface":         "#161820",  # 内容区底色（介于 bg 和 sidebar 之间）
    "surface_raised":  "#1A1D25",  # 抬起表面（卡片、详情面板）
    "surface_overlay": "#1F222B",  # 更高表面（hover、浮层）
    
    # ── 边框与分割 ──
    "border":          "#2A2D35",  # 主边框（white/5 ≈ rgba(255,255,255,0.05) 在 #161820 上的混合）
    "border_light":    "#353845",  # 次边框（white/7）
    "divider":         "#1E2029",  # 细分隔线（white/4）
    
    # ── 文字 ──
    "text":            "#E2E8F0",  # 主文字（~white/90）
    "text_secondary":  "#A0A5B0",  # 次级文字（~white/60）
    "text_muted":      "#6B7080",  # 辅助文字（~white/35）
    "text_disabled":   "#4A4E5A",  # 禁用文字（~white/20）
    
    # ── 主操作 ──
    "accent":          "#6366F1",  # indigo-500
    "accent_hover":    "#5558E6",  # indigo-500 darker
    "accent_subtle":   "rgba(99,102,241,0.15)" 上的预混合 → "#1E1F3A",
    "accent_text":     "#A5B4FC",  # indigo-300
    
    # ── 语义色 ──
    "success":         "#34D399",  # emerald-400
    "success_subtle":  "#0F2F24",  # emerald-500/10 预混合
    "warning":         "#FBBF24",  # amber-400
    "warning_subtle":  "#2F2508",  # amber-400/10 预混合
    "danger":          "#F87171",  # red-400
    "danger_subtle":   "#2F1515",  # red-400/10 预混合
    "info":            "#60A5FA",  # blue-400
    "info_subtle":     "#0F1F2F",  # blue-400/10 预混合
    
    # ── 状态专用色（完整 12 媒体状态 + 10 IDM 状态） ──
    "status_queued":         ("#9CA3AF", "#17191E"),  # slate-400
    "status_downloading":    ("#60A5FA", "#0F1F2F"),  # blue-400
    "status_merging":        ("#60A5FA", "#0F1F2F"),  # blue-400（同 downloading）
    "status_validating":     ("#A78BFA", "#1A1430"),  # violet-400
    "status_ready_to_import":("#FBBF24", "#2F2508"),  # amber-400
    "status_waiting_eagle":  ("#FB923C", "#2F1A08"),  # orange-400
    "status_imported":       ("#34D399", "#0F2F24"),  # emerald-400
    "status_completed_local":("#2DD4BF", "#0A2F2A"),  # teal-400
    "status_retry":          ("#FACC15", "#2F2A00"),  # yellow-400
    "status_failed_permanent":("#F87171", "#2F1515"),  # red-400
    "status_import_failed":  ("#FB7185", "#2F151A"),  # rose-400
    "status_canceled":       ("#6B7280", "#15171A"),  # gray-500
    "status_needs_rebuild":  ("#E879F9", "#2F1530"),  # fuchsia-400
    
    # ── 选中态 ──
    "selected":        "#1E2440",  # indigo-500/10 预混合
    "selected_border": "#2A3070",  # indigo-500/20 预混合
    
    # ── Treeview 专用 ──
    "tree_bg":         "#161820",
    "tree_field":      "#161820",
    "tree_heading_bg": "#111318",
    "tree_heading_fg": "#6B7080",
    "tree_selected_bg":"#1E2440",
    "tree_selected_fg":"#E2E8F0",
    
    # ── 进度条 ──
    "progress_track":  "#1A1D25",
    "progress_indigo": "#6366F1",
    "progress_emerald":"#34D399",
    "progress_orange": "#FB923C",
    "progress_red":    "#F87171",
    "progress_amber":  "#FBBF24",
}
```

### 5.3 ttk Style 配置策略

#### 5.3.1 基础框架

```python
style = ttk.Style(root)
style.theme_use("clam")

# 全局默认
style.configure(".", font=("Microsoft YaHei UI", 10), foreground=UI["text"])

# Frame 层级
style.configure("App.TFrame", background=UI["bg"])
style.configure("Sidebar.TFrame", background=UI["sidebar_bg"])
style.configure("Surface.TFrame", background=UI["surface"])
style.configure("SurfaceRaised.TFrame", background=UI["surface_raised"])
```

#### 5.3.2 导航按钮

```python
style.configure("Nav.TButton",
    anchor="w", padding=(12, 10),
    background=UI["sidebar_bg"], foreground=UI["text_secondary"],
    borderwidth=0, focusthickness=0,
    font=("Microsoft YaHei UI", 10),
)
style.map("Nav.TButton",
    background=[("active", UI["surface_overlay"]), ("pressed", UI["surface_overlay"])],
    foreground=[("disabled", UI["text_disabled"])],
)

style.configure("NavSelected.TButton",
    anchor="w", padding=(12, 10),
    background=UI["selected"], foreground=UI["accent_text"],
    borderwidth=0, focusthickness=0,
    font=("Microsoft YaHei UI", 10, "bold"),
)
```

#### 5.3.3 主操作按钮（Accent）

```python
style.configure("Accent.TButton",
    padding=(14, 8),
    background=UI["accent"], foreground="#FFFFFF",
    borderwidth=0, focusthickness=0, relief="flat",
    font=("Microsoft YaHei UI", 10, "bold"),
)
style.map("Accent.TButton",
    background=[
        ("disabled", UI["border"]),
        ("active", UI["accent_hover"]),
        ("pressed", UI["accent_hover"]),
    ],
    foreground=[("disabled", UI["text_disabled"])],
)
```

#### 5.3.4 次级按钮（Quiet）

```python
style.configure("Quiet.TButton",
    padding=(12, 7),
    background=UI["surface_overlay"], foreground=UI["text_secondary"],
    bordercolor=UI["border"], borderwidth=1, relief="flat",
)
style.map("Quiet.TButton",
    background=[("active", UI["surface_raised"]), ("pressed", UI["surface_raised"])],
    foreground=[("disabled", UI["text_disabled"])],
)
```

#### 5.3.5 危险按钮（Danger）

```python
style.configure("Danger.TButton",
    padding=(14, 8),
    background=UI["danger_subtle"], foreground=UI["danger"],
    borderwidth=0, focusthickness=0, relief="flat",
    font=("Microsoft YaHei UI", 10, "bold"),
)
style.map("Danger.TButton",
    background=[("active", "#3F1A1A"), ("pressed", "#3F1A1A")],
    foreground=[("disabled", UI["text_disabled"])],
)
```

#### 5.3.6 Treeview 深色

```python
style.configure("Treeview",
    background=UI["tree_bg"],
    fieldbackground=UI["tree_field"],
    foreground=UI["text"],
    bordercolor=UI["border"],
    borderwidth=1, relief="flat",
    rowheight=34,
)
style.map("Treeview",
    background=[("selected", UI["tree_selected_bg"])],
    foreground=[("selected", UI["tree_selected_fg"])],
)

style.configure("Treeview.Heading",
    background=UI["tree_heading_bg"],
    foreground=UI["tree_heading_fg"],
    padding=(8, 7), borderwidth=0, relief="flat",
    font=("Microsoft YaHei UI", 9, "bold"),
)
```

#### 5.3.7 深色 Combobox

```python
style.configure("TCombobox",
    fieldbackground=UI["surface_raised"],
    background=UI["surface_raised"],
    foreground=UI["text"],
    arrowcolor=UI["text_secondary"],
    bordercolor=UI["border"],
)
style.map("TCombobox",
    fieldbackground=[("readonly", UI["surface_raised"])],
    foreground=[("disabled", UI["text_disabled"])],
)
# 下拉列表需要通过 Toplevel 的 option_add 覆盖（clam 限制）
root.option_add("*TCombobox*Listbox.background", UI["surface_raised"])
root.option_add("*TCombobox*Listbox.foreground", UI["text"])
root.option_add("*TCombobox*Listbox.selectBackground", UI["selected"])
root.option_add("*TCombobox*Listbox.selectForeground", UI["accent_text"])
```

#### 5.3.8 深色 Scrollbar

```python
style.configure("TScrollbar",
    background=UI["surface"],
    troughcolor=UI["bg"],
    bordercolor=UI["bg"],
    arrowcolor=UI["text_muted"],
)
style.map("TScrollbar",
    background=[("active", UI["surface_overlay"])],
)
```

#### 5.3.9 深色 Canvas（滚动容器背景）

`_VerticalScrolledFrame` 中的 `Canvas` 需要 `background=UI["surface"]`。

#### 5.3.10 进度条

```python
# clam 只支持单一 trough/background。多色进度需要根据状态切换 style。
style.configure("Progress.Indigo.Horizontal.TProgressbar",
    troughcolor=UI["progress_track"],
    background=UI["progress_indigo"],
    bordercolor=UI["progress_track"],
    lightcolor=UI["progress_indigo"],
    darkcolor=UI["progress_indigo"],
)
# 同样定义 Progress.Emerald / Progress.Orange / Progress.Red / Progress.Amber
# 在 _update_plan_detail 中根据 view["status"] 动态切换 style
```

#### 5.3.11 Radiobutton 深色

```python
style.configure("TRadiobutton",
    background=UI["surface"],
    foreground=UI["text"],
)
style.map("TRadiobutton",
    foreground=[("disabled", UI["text_disabled"])],
)
```

#### 5.3.12 TLabelframe（卡片）

```python
style.configure("Card.TLabelframe",
    background=UI["surface_raised"],
    bordercolor=UI["border"],
    relief="solid", borderwidth=1,
)
style.configure("Card.TLabelframe.Label",
    background=UI["surface_raised"],
    foreground=UI["text"],
    font=("Microsoft YaHei UI", 11, "bold"),
)
```

#### 5.3.13 TEntry（输入框）

```python
style.configure("TEntry",
    fieldbackground=UI["surface_raised"],
    foreground=UI["text"],
    bordercolor=UI["border"],
)
style.map("TEntry",
    fieldbackground=[("disabled", UI["surface"])],
    foreground=[("disabled", UI["text_disabled"])],
)
```

### 5.4 字体策略

| 用途 | 字体 | 备选 |
| --- | --- | --- |
| CJK 正文 | `Microsoft YaHei UI` 10pt | `Segoe UI` |
| Latin 正文 | `Segoe UI` 10pt | `Microsoft YaHei UI` |
| 标题 | `Microsoft YaHei UI` 12-14pt bold | |
| 等宽（状态码、路径、域名） | `Cascadia Code` 9pt → `Consolas` 9pt | |
| Figma 使用 Inter | **不使用**，不加入发行包 | |

### 5.5 状态徽标实现

Tkinter 没有原生 badge 组件，方案：

```python
def _status_badge(parent, text: str, bg: str, fg: str) -> ttk.Label:
    """创建状态徽标：11px、mono、紧凑内边距"""
    style_name = f"Badge_{hash(bg)}_{hash(fg)}.TLabel"
    # 已存在的 style 复用
    style = ttk.Style(parent)
    style.configure(style_name,
        background=bg, foreground=fg,
        font=("Cascadia Code", 9, "bold"),
        padding=(6, 2),
        borderwidth=0, relief="flat",
    )
    return ttk.Label(parent, text=text, style=style_name)
```

由于 ttk.Label 不支持圆角，使用纯色背景小块。效果接近 Figma 的 `rounded text-[11px]` 但无边角圆角。

替代方案：用 `Canvas` 绘制圆角矩形 + 文字可实现真圆角，但代价过高且影响布局。本次不引入 Canvas badge。

### 5.6 TC 不支持透明度的处理

Figma 大量使用 `bg-indigo-500/15`（15% 不透明度）。Tk 必须预先混合：

```python
def _blend(fg_hex: str, bg_hex: str, alpha: float) -> str:
    """将 fg 以 alpha 透明度混合到 bg 上，返回 #RRGGBB"""
    fg = tuple(int(fg_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    bg = tuple(int(bg_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    blended = tuple(int(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))
    return f"#{blended[0]:02X}{blended[1]:02X}{blended[2]:02X}"
```

在模块加载时预计算所有混合色，避免运行时计算。

### 5.7 主从布局实现

保持当前 `Panedwindow` 方案：
- `ttk.Panedwindow(orient="horizontal")`
- 左侧 Treeview（weight=3），右侧详情面板（weight=2）
- 1120×720 下左侧约 430px、右侧约 280px
- min 900×600 下左侧约 340px、右侧约 220px

### 5.8 紧凑任务列表

当前 Treeview rowheight=34 已相对紧凑。可保持。

Figma 的封面缩略图在 Treeview 中无法原生实现（Treeview 不支持内嵌图片），方案：
- 下载任务列表：纯文本 Treeview（状态 | 标题 | 来源 | 进度），同当前
- 任务详情中的预览图独立在详情区显示（同当前）
- 视频号候选列表：纯文本 Treeview（标题 | 作者 | 时长 | 质量）
- 视频号封面在右侧详情区显示（同当前）

### 5.9 hover/pressed/disabled/focus 状态

clam 主题的 `ttk.Style.map()` 支持：
- `active`：鼠标悬停
- `pressed`：鼠标按下
- `disabled`：widget state `["disabled"]`
- `focus`：键盘焦点（clam 支持有限）

`focusthickness=0` 用于按钮去掉焦点虚线框。

---

## 6. 代码调整范围

### 6.1 保留不动

| 文件/组件 | 理由 |
| --- | --- |
| `media.py`、`processor.py`、`eagle.py`、`database.py` | 业务逻辑零修改 |
| `api_server.py`、`security.py`、`service.py`、`hook.py` | API/安全/调度零修改 |
| `wechat_channels.py`、`wechat_channels_proxy.py`、`wechat_channels_certificate.py`、`wechat_channels_crypto.py` | 视频号引擎零修改 |
| `network_proxy.py`、`updater.py`、`url_utils.py` | 代理/更新/URL 零修改 |
| `control_signal.py`、`fingerprint.py`、`paths.py` | 控制/指纹/路径零修改 |
| `constants.py`（除版本号外） | 常量定义不动 |
| `launcher/Launcher.cs` | 托盘宿主不动 |
| `chrome-extension/` 全部文件 | 扩展 UI 不动 |
| `installer/Setup.cs` | 安装器不动 |
| `SiteRulesWindow` 类 | 已独立，后续阶段视情况深色化或移入设置页 |
| `ProxySettingsWindow` 类 | 已独立，后续阶段视情况深色化或移入设置页 |

### 6.2 只调整样式

| 组件 | 调整内容 |
| --- | --- |
| `_configure_styles` | 全面替换为深色 Token |
| `UI` 字典 | 全部替换（见第 5 节） |
| 所有 `ttk.Label`、`ttk.Button`、`ttk.Frame` 的 `style=` 参数 | 调整为新 style 名 |
| `Treeview`、`Treeview.Heading` | 深色配色 |
| `TProgressbar` | 多色进度条 + 动态切换 |
| `TRadiobutton`、`TCheckbutton` | 深色适配 |
| `TCombobox`、`TEntry` | 深色适配 |
| `TScrollbar` | 深色适配 |
| `Canvas`（`_VerticalScrolledFrame` 内） | 背景色 |
| `TLabelframe`、`TLabelframe.Label` | 深色卡片 |

### 6.3 调整布局

| 区域 | 调整内容 |
| --- | --- |
| 顶部栏 | 重构为独立 `_build_topbar`：产品名+版本+状态指示点+版本号 |
| 侧栏 | 宽度从 190→200、图标（可选 Unicode 替代 SVG）、诊断入口独立分区 |
| 设置页 | 从纵向 Card 堆叠改为左侧 Tab 导航 + 右侧面板切换 |
| IDM 页 | 来源面板从底栏改为选中特定状态时侧滑/内嵌面板 |

### 6.4 可以提取为小型 UI helper

| Helper | 用途 |
| --- | --- |
| `_blend(hex, hex, alpha) → str` | 预计算混合色 |
| `_status_badge_style(bg, fg) → str` | 为状态色创建唯一 style |
| `_configure_progress_styles()` | 批量创建多色进度条 style |
| `_configure_dark_base(root)` | 全局 option_add（Listbox、Entry 等难以通过 theme 覆盖的控件） |

### 6.5 绝对不能修改

- 状态机、状态名称、进度算法
- 按钮启用条件逻辑
- API 参数和路径
- planId / job ID 身份
- 文件删除规则
- 数据库 schema
- 配对和鉴权流程
- 下载、Eagle、IDM、视频号业务流程
- 扩展 UI、托盘职责
- `DEVELOPMENT.md` 定义的测试入口

---

## 7. 分阶段实施方案

### 阶段 0：基线测试、截图和功能映射

**目标**：建立重构前的完整基线。

| 步骤 | 操作 |
| --- | --- |
| 0.1 | 运行全量 Python unittest（173 项）、6 组 Node 测试 |
| 0.2 | 运行 `python tests/visual_ui_fixture.py --page media --geometry 1120x720` 截图 |
| 0.3 | 同上对 wechat / idm / settings / diagnostics 截图 |
| 0.4 | 运行 `python tests/visual_ui_fixture.py --page media --geometry 900x600` 截图 |
| 0.5 | 逐项勾选 `FRONTEND_REFACTOR_FEATURE_INVENTORY.md` DESK-001~025 |
| 0.6 | 在 `design-qa.md` 中记录当前截图与 Figma 参考的逐区域对照 |

**验收**：所有测试通过，baseline 截图保存到 `docs/visual-qa/baseline-before-dark/`。

**回滚**：无需回滚（未修改代码）。

**预计修改文件**：无（仅生成截图和文档）。

---

### 阶段 1：主题 Token、ttk Style、顶部栏和左侧导航

**目标**：深色主题基础设施 + 全局框架。

| 步骤 | 操作 |
| --- | --- |
| 1.1 | 定义深色 `UI` 字典 |
| 1.2 | 重写 `_configure_styles` |
| 1.3 | 添加 `_configure_dark_base`（`option_add`） |
| 1.4 | 添加 `_blend` 和 `_status_badge_style` helper |
| 1.5 | 重构顶部栏为独立 `_build_topbar` 方法：产品名+版本+状态点 |
| 1.6 | 侧栏宽度 200、导航按钮深色样式、诊断分区独立 |
| 1.7 | 更新 `_VerticalScrolledFrame` canvas 背景色 |
| 1.8 | 验证 1120×720 和 900×600 下所有页面可访问 |
| 1.9 | 运行全量测试 |

**验收**：
- 顶部状态指示点正确反映 Eagle/服务/Chrome 实时状态
- 侧栏导航正常切换，选中态明显
- 外层滚动正常，Treeview/Combobox 滚轮不冲突
- `test_ui_layout.py` 通过

**回滚**：还原 `UI` 字典和 `_configure_styles` 函数。

**预计修改文件**：`ui.py`（`UI` 字典、`_configure_styles`、`_build`、`_build_topbar`（新））

---

### 阶段 2：下载任务页

**目标**：深色化下载任务主从布局。

| 步骤 | 操作 |
| --- | --- |
| 2.1 | Treeview 深色表头/行/选中态 |
| 2.2 | 任务列表行样式（状态色、进度色） |
| 2.3 | 详情面板深色表面 |
| 2.4 | 预览区域深色占位 + 完成后预览 |
| 2.5 | 多色进度条（根据状态动态切换 style） |
| 2.6 | 动作按钮：Accent/Danger/Quiet 分级 |
| 2.7 | 禁用按钮对比度检查 |
| 2.8 | 运行 `test_ui_layout.py` + 视觉验证 |

**验收**：
- `completed_local`/`imported` 显示 100% + 绿色进度条
- `waiting_eagle`/`validating`/`merging` 不超 99%，颜色正确
- 按钮正确启停（停止→Danger、补导→Accent、打开目录→Quiet）
- 预览缓存正常工作

**回滚**：git revert 阶段 2 commit。

**预计修改文件**：`ui.py`（`_build_media_tab`、`_refresh_media_tasks`、`_update_plan_detail`、`_update_plan_actions`）

---

### 阶段 3：视频号页

**目标**：深色化视频号捕获与候选页面。

| 步骤 | 操作 |
| --- | --- |
| 3.1 | Treeview 深色化（同阶段 2 复用） |
| 3.2 | 捕获控制栏深色化 |
| 3.3 | 状态文本颜色映射（off/preparing/waiting_wechat/capturing/needs_recovery/failed） |
| 3.4 | 详情面板：封面预览、质量 Combobox、交付 Radio |
| 3.5 | 深色 Combobox 下拉列表 |
| 3.6 | 空状态显示 |
| 3.7 | 运行 `test_wechat_channels.py` |

**验收**：
- 6 种捕获状态正确显示不同颜色
- 质量选择器下拉列表可读
- 交付方式 Radio 清晰
- 操作忙碌时按钮 disabled

**回滚**：git revert 阶段 3 commit。

**预计修改文件**：`ui.py`（`_build_wechat_tab`、`_refresh_wechat_candidates`、`_update_wechat_detail`、`toggle_wechat_capture`）

---

### 阶段 4：IDM 导入页

**目标**：深色化 IDM 表格与操作区。

| 步骤 | 操作 |
| --- | --- |
| 4.1 | Treeview 深色化（复用） |
| 4.2 | 表头 sticky 效果（通过固定背景色模拟） |
| 4.3 | 状态徽标颜色映射 |
| 4.4 | 底部分源面板深色化 |
| 4.5 | 动作按钮分级（Accent/Quiet） |
| 4.6 | 运行 `test_processor.py`、`test_database.py` |

**验收**：
- 10 种 IDM 状态全部可视区分
- 选中行时按钮按正确规则启停
- 来源面板仅在 waiting_source 时显示

**回滚**：git revert 阶段 4 commit。

**预计修改文件**：`ui.py`（`_build_idm_tab`、`_update_idm_actions`、IDM action methods）

---

### 阶段 5：设置页

**目标**：设置页二级导航 + 四面板深色化。

| 步骤 | 操作 |
| --- | --- |
| 5.1 | 左侧 Tab 导航替代纵向 Card 堆叠 |
| 5.2 | 四面板 `pack_forget` 切换 |
| 5.3 | 配对：六位码样式、复制按钮、解除配对按钮 |
| 5.4 | 网站规则：Toggle 模拟（Checkbutton 替代） |
| 5.5 | 网络：Radio 卡片样式、输入框、状态文本 |
| 5.6 | 更新：状态卡（已是最新/发现更新/下载中/错误） |
| 5.7 | 运行 `test_network_proxy.py`、`test_updater.py` |

**验收**：
- 设置 Tab 切换流畅，独立滚动区域
- 网站规则表格 CRUD 功能正常
- 代理保存后刷新全局状态
- 更新按钮状态正确（检查中/下载中/已完成）

**回滚**：git revert 阶段 5 commit。

**预计修改文件**：`ui.py`（`_build_settings_tab`、`_refresh_settings`、all settings methods）

---

### 阶段 6：诊断入口、最小窗口和可访问性

**目标**：收尾工作和边界条件。

| 步骤 | 操作 |
| --- | --- |
| 6.1 | 诊断页深色化 |
| 6.2 | 900×600 最小窗口下所有动作可达 |
| 6.3 | disabled 文字对比度 ≥ 3:1（WCAG AA） |
| 6.4 | 高 DPI（150%+ 缩放）下布局正常 |
| 6.5 | `SiteRulesWindow` 和 `ProxySettingsWindow` 深色化（或纳入设置页） |
| 6.6 | 检查所有 `after` 回调正确取消 |
| 6.7 | 检查滚轮绑定在页面切换后不泄漏 |

**验收**：
- `test_ui_layout.py` 通过（含 900×600 + 滚轮测试）
- 所有 Treeview/Combobox 在 overlay 中保留自身滚轮
- 窗口隐藏后降频至 30s

**回滚**：git revert 阶段 6 commit。

**预计修改文件**：`ui.py`（`_build_diagnostics_tab`、`SiteRulesWindow`、`ProxySettingsWindow`）

---

### 阶段 7：全量回归、截图对照和文档更新

**目标**：最终验证。

| 步骤 | 操作 |
| --- | --- |
| 7.1 | 运行全量 Python unittest（173 项） |
| 7.2 | 运行 6 组 Node 测试 |
| 7.3 | 运行活动 JS 语法检查 + 双清单 JSON 解析 |
| 7.4 | 冻结运行时测试（`Test-FrozenRuntime.ps1`） |
| 7.5 | 隔离安装器四路径测试 |
| 7.6 | 所有 5 个页面 × 1120×720 + 900×600 截图 |
| 7.7 | 与 Figma 参考 + 阶段 0 baseline 同画布对照 |
| 7.8 | 更新 `design-qa.md` |
| 7.9 | 更新 `FRONTEND_REFACTOR_FEATURE_INVENTORY.md`（如有需要） |
| 7.10 | 更新 `STATUS.md`、`TASKS.md` |

**验收**：全部测试通过，视觉对照无 P0/P1 问题。

**回滚**：回到阶段 0 baseline。

**预计修改文件**：`ui.py`（如果发现 bug）、`design-qa.md`、`STATUS.md`

---

## 8. 验证方案

### 8.1 自动测试

| 测试 | 覆盖内容 | 命令 |
| --- | --- | --- |
| `test_ui_layout.py` | Treeview 增量、进度封顶、异步探测、预览缓存、滚轮隔离、外层滚动 | `python -m unittest tests.test_ui_layout -v` |
| `test_media.py` | 媒体计划状态、动作启停 | `python -m unittest tests.test_media -v` |
| `test_processor.py` | IDM 任务状态、重试、补来源 | `python -m unittest tests.test_processor -v` |
| `test_wechat_channels.py` | 视频号全部 6 种状态、候选、提交 | `python -m unittest tests.test_wechat_channels -v` |
| `test_database.py` | 网站规则 CRUD、历史清理 | `python -m unittest tests.test_database -v` |
| `test_security_api.py` | 配对、脱敏、认证 | `python -m unittest tests.test_security_api -v` |
| `test_network_proxy.py` | 代理模式、保存、检测 | `python -m unittest tests.test_network_proxy -v` |
| `test_updater.py` | 更新检查、签名校验 | `python -m unittest tests.test_updater -v` |
| 全量 | 173 项 unittest | `python -m unittest discover -s tests -p "test_*.py" -v` |
| 全量 Node | 6 组 JS 测试 | 见 `DEVELOPMENT.md` |

### 8.2 视觉验证清单

所有条目均需在 1120×720 和 900×600 两个尺寸下检查。

- [ ] 侧栏导航：4 个按钮 + 诊断入口，选中态清晰
- [ ] 顶部栏：Eagle/服务/Chrome 状态点正确，版本号显示
- [ ] 下载任务 Treeview：状态色区分度、进度文字可读
- [ ] 下载任务详情：预览占位、进度条颜色随状态变化、按钮分级
- [ ] `completed_local` 显示 100% 绿色进度条，补导按钮可用
- [ ] `waiting_eagle` 显示 ≤99%，进度条橙色，补导按钮不可用
- [ ] `downloading` 显示 <100%，进度条 indigo
- [ ] `validating` 显示 <100%，进度条 violet
- [ ] `merging` 显示 <100%，进度条同 downloading
- [ ] `retry` 按钮可用，进度条 yellow
- [ ] `failed_permanent` 重试按钮可用
- [ ] `import_failed` 重试按钮可用
- [ ] `needs_rebuild` 重试按钮可用
- [ ] 禁用按钮文字对比度可读（≥3:1）
- [ ] 视频号 Treeview：候选列表、质量选择器可读
- [ ] 视频号状态：6 种状态颜色区分
- [ ] IDM Treeview：10 种状态颜色区分
- [ ] IDM 来源面板仅在 waiting_source 时出现
- [ ] 设置二级导航：Tab 切换流畅
- [ ] 设置各项：配对码可复制、Toggle 正常、代理保存生效
- [ ] 外层滚动：900×600 下所有动作可达
- [ ] Treeview 自身滚动：鼠标在 Treeview 上时不触发外层滚动
- [ ] Combobox 自身滚动：下拉列表滚动不触发外层滚动
- [ ] 窗口隐藏后刷新降频
- [ ] Eagle 探测不阻塞 UI
- [ ] 列表增量更新不闪屏
- [ ] 任务选择不被刷新错误重置
- [ ] 清除记录不删除文件
- [ ] 视频号退出恢复代理
- [ ] 诊断脱敏（无令牌/完整路径/来源）

### 8.3 视觉夹具截图

```bash
# 自动截图（需在桌面环境运行）
python tests/visual_ui_fixture.py --page media --geometry 1120x720
python tests/visual_ui_fixture.py --page wechat --geometry 1120x720
python tests/visual_ui_fixture.py --page idm --geometry 1120x720
python tests/visual_ui_fixture.py --page settings --geometry 1120x720
python tests/visual_ui_fixture.py --page diagnostics --geometry 1120x720
python tests/visual_ui_fixture.py --page media --geometry 900x600
```

---

## 9. 风险清单

### 9.1 高风险

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| **clam 主题 button disabled 颜色不可控** | 禁用按钮文字看不见 | 预验证 clam 的 disabled foreground 映射；必要时用 `!disabled` 绕过并用 state 管理 |
| **Tk Combobox 下拉列表不受 ttk style 控制** | 下拉列表白底黑字与深色主题冲突 | `root.option_add("*TCombobox*Listbox.*")` 全局覆盖 |
| **多色进度条需动态切换 style** | 进度条颜色不随状态变化 | 创建 5 个 Progressbar style，`_update_plan_detail` 中 `configure(style=...)` |
| **深色 Treeview 中 selected 行文字对比度不足** | 选中行不可读 | 预验证 indigo-500/10 bg + white/90 fg 组合；必要时调高选中背景不透明度 |
| **图片引用被 GC** | 预览图消失 | 保持 `self.preview_image = image` 引用模式不变 |

### 9.2 中风险

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| Windows 高 DPI（150%+）下 ttk 控件变形 | 布局错乱 | 在 150%/200% 缩放下人工验证；Tk 应自动跟随系统 DPI |
| 设置页从纵向改横向 Tab 布局时的 scroll 嵌套 | 滚动混乱 | 设置页每个 Tab 面板独立使用垂直滚动；不使用嵌套 scroller |
| 页面切换后事件绑定泄漏 | 按钮重复触发 | `pack_forget` 不销毁 widget，现有逻辑已无泄漏；阶段 6 专项检查 |
| 后台线程更新已销毁的 widget | TclError | 所有 UI 更新通过 `after` 回主线程；`winfo_exists()` 守卫 |

### 9.3 低风险

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 深色主题下原生对话框（messagebox、filedialog）仍为系统亮色 | 视觉不一致 | Windows 系统对话框跟随系统主题，无需程序处理 |
| `SiteRulesWindow` 和 `ProxySettingsWindow` 独立窗口深色化 | 需额外适配 | 共享同一 `_configure_styles` 调用 |
| Segoe UI 在旧版 Windows 不存在 | 回退字体 | Tk `font=` 元组支持备选；Segoe UI 从 Vista 起存在 |

---

## 10. 预计修改文件

### 必定修改

| 文件 | 修改理由 |
| --- | --- |
| `src/idm_eagle_bridge/ui.py` | 唯一 UI 文件，全部视觉重构在此 |

### 可能修改

| 文件 | 修改条件 |
| --- | --- |
| `tests/visual_ui_fixture.py` | 如果夹具的颜色断言需要更新（`_FakeMedia` 等不需要，因为夹具只验证行为不验证颜色） |
| `tests/test_ui_layout.py` | 如果新增 UI helper 需要单元测试 |
| `docs/design-qa.md` | 阶段 7 更新视觉 QA 记录 |
| `docs/FRONTEND_REFACTOR_FEATURE_INVENTORY.md` | 如有功能入口位置变化需同步 |
| `STATUS.md` | 阶段 7 更新项目状态 |
| `TASKS.md` | 阶段 7 更新任务状态 |

### 绝不可能修改（如被要求需解释原因）

| 文件 | 原因 |
| --- | --- |
| 任何 `src/idm_eagle_bridge/*.py` 除 `ui.py` 外 | 纯视觉重构，不改业务逻辑 |
| 任何 `chrome-extension/**` | 本次只重构桌面 UI |
| `launcher/Launcher.cs` | 托盘职责不变 |
| `installer/Setup.cs` | 安装器不涉及 UI |
| `packaging/**` | 发行结构不变 |
| `pyproject.toml` | 不改依赖 |
| `tests/**` 除上述两个文件外 | 行为不变，测试不变 |
