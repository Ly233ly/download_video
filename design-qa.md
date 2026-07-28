# 1.4.0 前端视觉 QA

日期：2026-07-26
密度：Windows 1×；浏览器 1×
最后更新：2026-07-27（深色主题重构记录）

## 证据

| 类型 | 路径 | 视口 / 像素 |
| --- | --- | --- |
| 视觉参考 | `docs/visual-qa/reference.png` | 1563×1006 |
| 桌面下载任务（全窗口） | `docs/visual-qa/desktop-media-1120x720.jpg` | 客户区 1120×720；截图 1122×752 |
| 桌面视频号（重点状态） | `docs/visual-qa/desktop-wechat-1120x720.jpg` | 客户区 1120×720；截图 1122×752 |
| 桌面设置（重点状态） | `docs/visual-qa/desktop-settings-1120x720.jpg` | 客户区 1120×720；截图 1122×752 |
| 桌面最小窗口（全窗口） | `docs/visual-qa/desktop-media-900x600.jpg` | 客户区 900×600；截图 902×632 |
| 扩展媒体检查器（全视口） | `docs/visual-qa/extension-media-660x574.png` | 660×574 |
| 扩展任务状态（全视口） | `docs/visual-qa/extension-tasks-660x574.png` | 660×574 |
| 同画布对照 | `docs/visual-qa/comparison-round-1.jpg` | 1440×1100 |
| 深色主题基线 | `docs/visual-qa/baseline-before-dark/phase-0-results.txt` | — |

桌面截图来自真实 Tk 窗口与确定性 SQLite/任务夹具；扩展截图来自实际 popup HTML、CSS、逻辑脚本和受控 Chrome API 夹具。扩展控制台没有 error/warning。

## 1.4.0 对照结果与修复历史

1. 第一轮 P1：Windows `vista` 主题忽略紫灰按钮与进度色，禁用动作文字几乎不可见。改用确定性的 `clam` 主题并补齐 enabled/disabled 映射。
2. 第一轮 P1：视频号 Treeview 的请求宽度挤压详情，交付方式文案被截断。收缩列表列并保留 3:2 主从分区，1120×720 可完整显示候选、质量和两个交付动作。
3. 第一轮 P1：IDM 表格请求高度使动作区落到首屏外，说明列在 1120 宽度被截断。说明移到独立行，表格高度和列宽收敛；外层滚动仍覆盖 900×600。
4. 第一轮 P2：桌面原生表头和次级按钮层级过重。统一为暖灰表面、扁平边框、34 px 行高和紫灰选中态。
5. 第一轮 P2：扩展缺少当前页上下文，任务只显示百分比。加入标题/域名、处理大小、阶段、时间、来源和状态型动作；技术 URL 默认折叠且去除查询与片段。
6. 最终复查：暖灰/白层级、左侧导航、紫灰主操作、主从任务布局、较大圆角和克制阴影与参考一致；900×600 通过滚动可达动作，660×574 内部检查器可滚动；无 P0/P1 遗留。

Final result: passed

## 深色主题重构（2026-07-27，分支 refactor/figma-dark-tk-ui）

### 对照结果：亮→深

| 区域 | 检查项 | 状态 |
| --- | --- | --- |
| 全局 | 应用背景 #0D0F16 | 已实现 |
| 全局 | 侧栏 #111318 | 已实现 |
| 全局 | 正文 #E2E8F0 层级 | 已实现 |
| 全局 | 主操作 indigo-500 (#6366F1) | 已实现 |
| 全局 | 成功/等待/警告/失败状态色 | 已实现（10 媒体 + 10 IDM 状态色） |
| 全局 | ttk clam 主题确定性 | 保持 |
| 全局 | OPPO Sans Regular / Medium / Bold | 已实现分层 |
| 顶部 | 紧凑全局状态栏 + 版本 | 已实现 |
| 侧栏 | 200px 主导航 + 底部诊断 | 已实现 |
| 下载任务 | 列表 + 详情主从布局 | 已实现（SurfaceRaised 详情面板） |
| 下载任务 | 多色进度条（Indigo/Emerald/Orange） | 已实现（动态切换） |
| 下载任务 | Danger 停止按钮 | 已实现 |
| 视频号 | 候选列表 + 详情主从布局 | 已实现 |
| 视频号 | 动态 Accent/Danger 按钮切换 | 已实现 |
| 视频号 | 6 种捕获状态文案 | 保持 |
| IDM | 紧凑表格 + 上下文操作栏 | 已实现 |
| 设置 | 二级左侧导航（配对/网站规则/网络/更新） | 已实现 |
| 诊断 | 脱敏导出入口 | 保持 |
| 布局 | 1120×720 主尺寸 | 保持 |
| 布局 | 900×600 最小窗口 | 保持 |
| 滚动 | 外层滚动 + Treeview/Combobox 内滚隔离 | 已测试通过 |
| 性能 | Eagle 异步探测 / 增量列表 / 预览缓存 | 保持 |
| 状态 | completed_local/imported→100% / 未完成<100% | 保持（_media_plan_view 不变） |
| 安全 | 所有动作继续调用真实方法 | 保持 |

### 深色主题自动验证证据（2026-07-27）

| 验证项 | 方法 | 结果 |
| --- | --- | --- |
| 全量 Python unittest | `discover -s tests -p "test_*.py"` | 173/173 PASS |
| UI 布局测试 | `test_ui_layout.py` (7 tests) | 7/7 PASS |
| 6 组 Node 测试 | test_youtube/popup_logic/candidate_presentation/auth_race/bilibili/wechat_channels_bridge | 6/6 PASS |
| JS 语法检查 | `node --check` 全部 12 个文件 | 12/12 PASS |
| 双清单 JSON 解析 | manifest.json + manifest.firefox.json | 2/2 PASS |
| 13 种状态进度封顶 | `_media_plan_view` 单元测试 | ALL PASS |
| DESK-001~025 源码扫描 | 全部 `self.*` 属性存在 | 25/25 PASS |
| CORE 动作真实调用 | 全部调用 media/database/wechat_channels/pairing 真实对象 | 14/14 PASS |
| WCAG AA 对比度 | 数学计算 | 5/6 PASS (accent 修复后全通过) |
| EXT-001~034 未修改 | `git diff --name-only` | 0 个扩展文件变更 |
| 业务文件未修改 | `git diff --name-only -- src/idm_eagle_bridge/` | 仅 ui.py |
| 无第三方依赖 | `git diff` 扫描 | 无 customtkinter/Pillow/PySide 等 |
| 无 Figma Mock Data | `git diff` 扫描 | 无 Unsplash/useState/假配对码 |
| 无业务契约修改 | `git diff` 扫描 | 无 schema/API/path 变更 |
| 模块导入 | `from idm_eagle_bridge.ui import MainWindow` | OK |
| 视觉夹具可加载 | `from tests.visual_ui_fixture import main` | OK |

### 深色主题 WCAG AA 对比度

| 元素 | 颜色 | 背景 | 比率 | 阈值 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 正文 | `#E2E8F0` | `#161820` | 14.4:1 | ≥4.5:1 | PASS |
| 禁用文字 | `#686E7A` | `#161820` | 3.5:1 | ≥3.0:1 | PASS |
| 白字/主按钮 | `#FFFFFF` | `#5D5FEE` | 4.84:1 | ≥4.5:1 | PASS |
| 红字/危险按钮 | `#F87171` | `#2F1515` | 6.1:1 | ≥4.5:1 | PASS |
| 次级/侧栏 | `#A0A5B0` | `#111318` | 7.5:1 | ≥4.5:1 | PASS |
| 辅助/表面 | `#6B7080` | `#161820` | 3.6:1 | ≥3.0:1 | PASS |

### 待人工视觉确认

- [ ] 1120×720 深色桌面截图（5 个页面）
- [ ] 900×600 深色最小窗口截图
- [ ] Combobox 下拉深色验证
- [ ] Windows 高 DPI（150%+）验证
- [ ] 冻结运行时视觉验证
- [ ] 与 Figma 参考同画布对照

> 注：以上 6 项需在 Windows 桌面环境运行 `python tests/visual_ui_fixture.py` 完成。

---

# 1.4.1 Figma 深色桌面重构最终 Design QA

日期：2026-07-28

实现合同：`docs/UI_FIGMA_DIFF_AUDIT.md`

视觉真相：本地 `Figma-test-download` 的 1120×720 / 900×600 实际运行截图。
实现证据：`docs/visual-qa/dark-redesign/phase-3` 至 `phase-7`。

## 视口、像素与状态

| 对照 | 源像素 | 实现像素 | 客户区 / 密度 | 状态 |
| --- | ---: | ---: | --- | --- |
| 下载任务 Normal | 1120×720 | 1120×720 | 1120×720，Windows 1× | 活跃任务 |
| 下载任务 Compact | 900×600 | 900×600 | 900×600，Windows 1× | 活跃任务 |
| 视频号 Normal | 1120×720 | 1120×720 | 1120×720，Windows 1× | 捕获中、有候选 |
| 视频号 Compact | 900×600 | 900×600 | 900×600，Windows 1× | 捕获中、有候选 |
| IDM Normal / Compact | 1120×720 / 900×600 | 同左 | Windows 1× | 等待、成功、失败 |
| 设置四子页 | 1120×720 | 1120×720 | Windows 1× | 默认设置状态 |

源和实现均为同尺寸客户区截图，无浏览器或 Windows 标题栏，不需要密度下采样。实现截图由测试夹具自身窗口的后台 `PrintWindow` 读取，不包含用户桌面。

## 同画布全视图证据

- `docs/visual-qa/dark-redesign/comparisons/downloads-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/wechat-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/wechat-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/idm-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/idm-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/settings-pairing-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/settings-sites-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/settings-network-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/settings-updates-1120x720.png`

## 重点区域证据

- `docs/visual-qa/dark-redesign/comparisons/focused-shell-1120x240.png`
- `docs/visual-qa/dark-redesign/comparisons/focused-pairing-content.png`

重点裁切用于检查品牌/导航密度、字体层级、六位码比例、按钮和状态色。下载、视频号和 IDM 的表格/主从比例已能在 2240px 宽的原尺寸同画布证据中清楚读取，无需额外缩放裁切。

## 必查视觉面

- **字体与排版**：正文使用 OPPO Sans Regular，卡片标题、选中导航、状态标签和主要操作使用 OPPO Sans Medium，页面与区块标题使用 OPPOSans B；10–14px 逻辑像素按标题、主值、次值、标签和说明分层。长标题在列表单行省略、详情头部限制为可扫读摘要，完整内容在详情下部和 tooltip 保留。
- **间距与布局**：1120px 为 40px 顶栏、200px 一级侧栏、360px 下载/视频号主列表；900px 为 56px 双行顶栏、168px 一级侧栏、300px 主列表。按钮换行和局部滚动没有产生页面水平溢出。
- **颜色与令牌**：背景、表面、文本、状态和进度映射审计令牌。主按钮使用 `#6265F1` 无障碍派生色，白字 4.515:1；进度和选中保留 Figma `#6366F1`。
- **图像与资产**：导航和动作使用从 Figma 图标定义生成的本地 PNG；没有 emoji、内联 SVG、字符画或在线字体。运行时列表与详情读取真实 `preview_path`；视觉夹具使用 Figma 源码引用的原始 Unsplash 图像作为本地预览测试资产，缺图时仍回退正式项目图标和状态文案。
- **文案与内容**：真实 `APP_VERSION=1.4.1`、真实状态名、错误原因、交付语义和安全说明覆盖 Figma Mock 文案。视频号两个交付动作保留完整删除条件说明。
- **状态与交互**：空、失败、禁用、长文本、20 档质量、200 条媒体计划和 1000 条 IDM 数据均有夹具证据。181 项单元测试验证动作仍调用原媒体、数据库、配对和视频号服务方法。
- **可访问性**：重要按钮保留键盘焦点；状态同时使用文字和颜色；正文/次级/危险/禁用对比度满足相应阈值。详情与列表使用独立滚动，900×600 下功能仍可达。

## 对照迭代历史

1. 审计基线发现 P0/P1：下载和视频号仍为固定 Treeview、详情动作纵向溢出、IDM 固定列宽、顶栏未贯穿全窗、设置与诊断结构漂移。阶段 1–6 分页迁移为响应式主从结构、动态表格和扁平设置/诊断页；后证据为 `phase-3` 至 `phase-6`。
2. 第一轮最终同画布检查发现 P2：原生 Scrollbar/Panedwindow sash 在深色界面中过亮；配对码视觉权重不足。修复为深色 11px 滚动条/4px sash，并把配对码改为 32px mono、三位分组。后证据为最新 `comparisons` 和 `focused-pairing-content.png`。
3. 压力检查发现 P2：超长媒体/视频号标题会把关键动作推离首屏。详情头部改为两行左右摘要，完整标题、作者、输出和来源移入可滚动完整信息区并保留 tooltip。后证据为 `phase-7/media-stress-900x600.png` 和 `phase-7/wechat-stress-900x600.png`。
4. 用户视觉验收指出下载列表仍缺预览、圆角不足、列表文字过亮过大、任务行内部排列偏差、详情字体与亮度层级不足。修复后媒体行使用 48×32 真实预览、圆角卡片与状态标签，状态/大小/相对时间回到同一基线；导航、预览、说明面板和状态动作使用 Canvas 圆角表面；详情改用 Segoe UI Variable Text 优先的无衬线策略，并拉开标签、主值、次值和说明亮度。后证据为 `downloads-round2-1120x720.png` 和 `downloads-round2-900x600.png`。

## 最终发现

没有遗留可执行的 P0/P1/P2。

可接受的差异：

- 运行时没有真实 `preview_path` 时必须展示正式缺图状态，不能伪造媒体画面；视觉夹具只用本地测试资产覆盖有预览状态。
- Figma 网站规则使用 React 开关；Tkinter 版采用选中行加明确的“启用/停用、切换子域名”按钮，保留全部键盘可达 CRUD 和确认门禁。
- Figma IDM 固定表格会产生水平溢出；实现按合同改为动态列宽和下方完整详情，这是有意修正。

P3 环境测试缺口：125% / 150% 物理显示缩放仍需在对应显示器环境复核；当前实现使用负像素字体和逻辑像素断点，当前 1× 环境的 1120×720、900×600 及压力矩阵已通过。

final result: passed

## 用户验收回流：下载任务页 Round 2

日期：2026-07-28

| 用户反馈 | 修正 | 结果 |
| --- | --- | --- |
| 媒体列表无预览 | 卡片与详情统一读取真实 `preview_path`；夹具补入本地真实图片资产 | PASS |
| 全界面矩形 | 主导航、媒体卡、缩略图槽、状态标签、预览、说明面板和媒体动作改为圆角 Canvas 表面 | PASS |
| 左侧间距、字号、亮度不符 | 标题降为 11px semibold，域名/大小/时间降为 10px mono；状态移回缩略图下方，大小与时间同一基线 | PASS |
| 中间媒体行与参考不同 | 任务行恢复 92px 密度、48×32 预览、紧凑状态文案、“今天/昨天”时间和 3px 底部进度 | PASS |
| 右侧详情无层级 | Segoe UI Variable Text 优先；标题、主值、次值、标签、说明使用五档字号/亮度，状态动作按当前任务排列 | PASS |

同画布证据：

- `docs/visual-qa/dark-redesign/comparisons/downloads-round2-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-round2-900x600.png`
- `docs/visual-qa/dark-redesign/phase-3/media-round2-complete-1120x720.png`

验证：178 项 Python 单元测试通过；`git diff --check` 通过；截图继续只用夹具自身 HWND 的后台 `PrintWindow`，不监听输入、不激活窗口、不抢焦点。

final result: passed

## 用户验收回流：密度、滚动条与自适应圆角 Round 3

日期：2026-07-28

目标截图：用户标注的媒体标题栏、双侧滚动条、无箭头圆角滚动条参考和高圆角控件参考。

### 修正结果

- 媒体列表标题栏固定为 36px，标题使用 11px semibold，刷新/清除使用 10px 弱操作样式；不再由系统按钮默认字体撑高。
- 修复 Tk 命名字体对象被回收的问题，所有 `Ui10`–`Ui14Bold` / `Mono10`–`Mono24Bold` 字体在窗口生命周期内持续存在，避免按钮字号回退后异常放大。
- 下载列表、详情、IDM 表格和网站规则表全部改用无上下箭头的 Canvas 滚动条；轨道融入当前表面，6–8px 圆头滑块按可见比例自适应长度。
- 圆角改为尺寸分级令牌：缩略图 6px、标签 9px、控件 10px、卡片 12px、大面板 14px；小组件不使用大面板半径，大组件不再只有轻微圆角。
- 媒体详情进度条和任务行底部进度改为圆头轨道/圆头填充，状态色和真实进度语义不变。

### 同画布与状态证据

- `docs/visual-qa/dark-redesign/comparisons/downloads-round3-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-round3-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/idm-scrollbar-round3-900x600.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-sites-round3-900x600.png`

验证：181 项 Python 单元测试通过；新增命名字体持久化、圆角滚动条和圆头进度条单元测试；`git diff --check` 通过。截图继续只读取夹具自身 HWND，不监听输入、不激活窗口、不抢焦点。

final result: passed

## 用户验收回流：OPPO Sans 字体系统 Round 4

日期：2026-07-28

### 字体层级

- 正文、辅助文字和数据：`OPPO Sans` Regular，10–12px。
- 卡片标题、选中导航、状态标签和主操作：`OPPO Sans Medium`，10–13px。
- 页面标题、区块标题和配对码：`OPPOSans B`，13–24px。
- 系统未安装对应字重时，依次回退到 OPPO Sans 可用字重，再回退 Windows 中文 UI 字体。
- Tk 命名字体对象继续由根窗口持有，避免运行中被回收后退回系统默认字体。

### 视觉证据

- `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-900x600.png`

系统字体枚举和 Tk 实际字体检查均确认：Regular=`OPPO Sans`、Medium=`OPPO Sans Medium`、Bold=`OPPOSans B`。181 项 Python 单元测试通过，`git diff --check` 通过。

final result: passed

## 用户验收回流：全局字重提升 Round 5

日期：2026-07-28

- 字号保持不变。
- 原 Regular 角色从 `OPPO Sans` 提升为 `OPPO Sans Medium`。
- 原 Medium 角色从 `OPPO Sans Medium` 提升为 `OPPOSans B`。
- 原 Bold 角色从 `OPPOSans B` 提升为 `OPPOSans H`。
- Tk 实际字体检查确认三档字体均正确加载，没有回退到系统默认字体。

视觉证据：

- `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-heavier-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-heavier-900x600.png`

181 项 Python 单元测试通过，`git diff --check` 通过。

final result: passed

## 用户验收回流：字号层级与高 DPI 清晰度 Round 6

日期：2026-07-28

### 修正

- 字体角色从原先集中在 10–13px，调整为 11–17px：辅助标签 11px、次级正文 12px、卡片标题 13px、主值 14px、区块标题 15px、详情标题 17px。
- 导航文字从 11px 提升到 13px；选中导航继续使用更高字重。
- 媒体状态标签和操作按钮分别提升到 11px / 12px，保持与卡片标题、元数据的层级差。
- Windows 进程在创建 Tk 根窗口前启用 Per-Monitor DPI Awareness V2，避免系统在 125% / 150% 缩放下对整个窗口做位图拉伸。
- OPPO Sans Medium / OPPOSans B / OPPOSans H 的上一轮字重要求保持不变。

### 证据

- `docs/visual-qa/dark-redesign/phase-3/media-type-scale-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-3/media-type-scale-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-type-scale-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-type-scale-900x600.png`

Windows API 验证进程 DPI awareness=`2`（Per-Monitor aware）；181 项 Python 单元测试通过，`git diff --check` 通过。

final result: passed
