# 深色桌面 UI 重构进度

> 实施合同：`docs/UI_FIGMA_DIFF_AUDIT.md`  
> 开始日期：2026-07-28  
> 约束：Tkinter/ttk、Python 标准库零新增运行时依赖；不改业务语义、schema、API、状态机、`planId` 或文件删除门禁。

## 正式功能接入（2026-07-28）

状态：**完成**

- 深色界面已确认由正式 `idm_eagle_bridge.main:main`、`launcher/assistant.pyw` 和托盘启动链路创建，不存在单独的演示窗口。
- 新版 `MainWindow` 直接持有真实数据库、本机 API、媒体协调器、视频号服务和处理服务；测试已验证真实计划能进入媒体卡片、自动选中并显示完整标题与来源域名。
- 产品 PNG 与 21 个实际使用的 UI 图标已进入 `src/idm_eagle_bridge/assets`，并接入普通 Python 包与 PyInstaller `onedir`；39 个未使用状态组合和仓库根 60 个重复副本已清理。
- 验证：185 项 Python unittest、6 组 Node、17 个活动 JavaScript 语法、Chrome 清单 JSON、PyInstaller 发行包 5 个关键资源、冻结入口 `--help` 全部通过。
- 后台截图：`docs/visual-qa/dark-redesign/phase-3/production-integration-1120x720.png`。截图仅使用夹具窗口 HWND 的 `PrintWindow`，不监听键盘、不激活或抢占用户窗口。
- 当前电脑已通过安装器 `--update` 覆盖为本轮 1.4.1 载荷；25 秒健康门通过，安装目录的启动器、后台、扩展清单、产品图和关键图标与发行包哈希一致，用户数据库和配对数据未进入替换目录。

### 视频号捕获栏实机修正

- 根因：视频号页在隐藏状态下创建时，Tk `Panedwindow` 只有 1px 可用宽度；全局响应式更新提前设置所有隐藏分栏，导致视频号主栏被永久钳制到 0。
- 修正：页面切换完成后，只恢复当前可见页面的分隔位置；不再触碰隐藏页面。新增回归验证切到视频号时只移动 `wechat_split`。
- 后台截图：
  - `docs/visual-qa/dark-redesign/phase-4/wechat-capture-controls-restored-1338x835.png`
  - `docs/visual-qa/dark-redesign/phase-4/wechat-start-capture-restored-1338x835.png`
- 修复载荷已覆盖当前电脑；安装后台 SHA-256 与新发行包一致，健康门通过。

### 媒体标题单行省略

- 页面元数据中的换行、制表符和连续空白统一折叠为空格；任务卡标题固定为一行，超过 22 个显示字符时以“…”结束。
- 右侧详情页头改为不换行标签，并按 Compact / Normal / Wide 使用 24 / 38 / 48 个显示字符上限；完整标题继续在下方完整信息与悬停提示中提供。
- 长标题夹具包含真实的多段标题结构，后台截图 `docs/visual-qa/dark-redesign/phase-3/media-single-line-title-1338x835.png` 确认状态、大小、时间和进度未被挤出。
- 185 项 Python unittest、17 个活动 JavaScript 语法和双清单通过；当前电脑安装后台与新发行包哈希一致，健康门通过。

## 阶段 1：设计系统与响应式基础

状态：**完成**

### 完成内容

- 集中补全深色颜色、间距、尺寸、字体和布局断点令牌。
- 统一 10–14px 逻辑像素字体，使用系统字体回退。
- 补全主按钮、次按钮、安静按钮、危险按钮、导航、表格、输入框、下拉框、进度条和状态文案样式。
- 新增动态换行标签、响应式动作组、响应式 Treeview 列管理器、完整文本提示、状态圆点和独立滚动卡片列表。
- 建立 Compact / Normal / Wide 断点函数：
  - Compact：`<1024`
  - Normal：`1024–1279`
  - Wide：`≥1280`

### 对应功能 ID

- DESK-001–DESK-003
- DESK-007、DESK-012、DESK-017、DESK-021
- CORE-009、CORE-012

### 截图

- `docs/visual-qa/dark-redesign/phase-1/media-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-1/media-900x600.png`

### 未解决差异

- P1：全局顶栏仍位于工作区内，尚未贯穿全窗。
- P0：下载任务仍为固定列表格。
- P1：900×600 详情动作仍被挤到首屏下方。
- P1：视频号、IDM、设置和诊断尚未迁移新结构。

这些差异分别归属后续阶段，因此阶段 1 没有阻断其自身公共组件交付的 P0/P1。

### 测试结果

- `python tests/test_ui_layout.py -v`
- 11 项通过，0 失败。

### 用户验收 Round 4：OPPO Sans 字体系统（2026-07-28）

- 全局默认字体切换为 `OPPO Sans`。
- 正文与辅助文字使用 Regular；卡片标题、选中导航、状态标签和主要操作使用 `OPPO Sans Medium`；页面与区块标题使用 `OPPOSans B`。
- 原“等宽数据”角色也改用 OPPO Sans，通过字号、亮度和间距区分，不再混用 Cascadia Mono。
- 系统实际字体检查确认三个家族均已由 Tk 加载；缺少特定字重时保留安全回退。
- 后台截图：
  - `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-1120x720.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-900x600.png`
- `python -m unittest discover -s tests -p "test_*.py"`：181 项通过，0 失败。

### 用户验收 Round 5：全局字重提升（2026-07-28）

- 字号与间距保持不变，只将每个角色提升一个真实字重。
- 正文/辅助：`OPPO Sans Medium`。
- 卡片标题/状态/主操作：`OPPOSans B`。
- 页面标题/区块重点：`OPPOSans H`。
- 后台截图：
  - `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-heavier-1120x720.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-oppo-sans-heavier-900x600.png`
- 181 项测试通过，`git diff --check` 通过。

### 用户验收 Round 6：字号层级与清晰度（2026-07-28）

- 字号重新分为 11 / 12 / 13 / 14 / 15 / 17px 六档；标题、主值、正文、标签和辅助信息不再只相差 1px。
- 一级导航提升到 13px；卡片标题 13px；详情主值 14px；区块标题 15px；详情标题 17px。
- 状态标签提升到 11px，媒体操作按钮提升到 12px。
- 创建 Tk 根窗口前启用 Windows Per-Monitor DPI Awareness V2，避免高 DPI 下由 Windows 对窗口位图缩放造成文字发糊。
- 后台截图与同画布对照：
  - `docs/visual-qa/dark-redesign/phase-3/media-type-scale-1120x720.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-type-scale-900x600.png`
  - `docs/visual-qa/dark-redesign/comparisons/downloads-type-scale-1120x720.png`
  - `docs/visual-qa/dark-redesign/comparisons/downloads-type-scale-900x600.png`
- 181 项测试通过，`git diff --check` 通过。

### 用户验收 Round 2 修正（2026-07-28）

- 媒体列表和详情重新接入真实 `preview_path`；视觉夹具使用 Figma 源码引用的原始图片资产验证有预览状态。
- 媒体任务行改为圆角卡片，缩略图槽与状态标签同样圆角；主导航、详情预览、阶段说明和媒体动作补齐圆角表面。
- 列表标题降为 11px semibold，域名、大小和相对时间降为 10px mono；未选中标题亮度降低，选中态维持主文字亮度。
- 卡片内部恢复“缩略图 + 标题/域名；状态 + 大小 + 时间；底部进度”的三层结构，状态文案改为紧凑显示。
- 详情字体优先使用 Segoe UI Variable Text，并按标题、主值、次值、标签、说明建立五档层级；当前状态动作位于页头，次级动作位于完整信息之后。
- Round 2 后台截图：
  - `docs/visual-qa/dark-redesign/phase-3/media-round2-1120x720.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-round2-900x600.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-round2-complete-1120x720.png`
- Round 2 同画布对照：
  - `docs/visual-qa/dark-redesign/comparisons/downloads-round2-1120x720.png`
  - `docs/visual-qa/dark-redesign/comparisons/downloads-round2-900x600.png`
- `python -m unittest discover -s tests -p "test_*.py"`：178 项通过，0 失败。

### 用户验收 Round 3 修正（2026-07-28）

- 媒体列表标题栏固定为 36px；标题、刷新和清除完成分别使用 11px / 10px 字体，恢复原版低密度工具栏比例。
- 持久保存 Tk 命名字体对象，修复控件字体回退导致字号异常变大的根因。
- 新增无箭头圆角滚动条，覆盖媒体任务列表、详情滚动、IDM 表格和网站规则表；圆头滑块按可见内容比例自动调节长度。
- 圆角统一改为尺寸自适应：缩略图 6px、标签 9px、控件 10px、卡片 12px、大面板 14px。
- 媒体详情进度条和任务行进度改为圆头轨道与圆头填充。
- Round 3 截图与对照：
  - `docs/visual-qa/dark-redesign/phase-3/media-round3-1120x720.png`
  - `docs/visual-qa/dark-redesign/phase-3/media-round3-900x600.png`
  - `docs/visual-qa/dark-redesign/comparisons/downloads-round3-1120x720.png`
  - `docs/visual-qa/dark-redesign/comparisons/downloads-round3-900x600.png`
  - `docs/visual-qa/dark-redesign/phase-7/idm-scrollbar-round3-900x600.png`
  - `docs/visual-qa/dark-redesign/phase-6/settings-sites-round3-900x600.png`
- `python -m unittest discover -s tests -p "test_*.py"`：181 项通过，0 失败。

## 阶段 4：视频号页

状态：**完成**

### 完成内容

- 捕获控制、真实生命周期状态、安全说明和候选操作集中到 360px / 300px 左侧主栏。
- 候选 Treeview 改为 80px 卡片列表，包含 64×40 封面位、标题、作者、时长、质量和捕获时间。
- 详情使用动态 16:9 封面、完整标题/作者/内容 ID/预计输出/来源和真实质量选择。
- “导入 Eagle（完成后删除本机副本）”与“仅下载并保留本机文件”改为两个明确动作。
- 两个交付按钮继续共用原 `submit_selected_wechat_candidate`，只设置既有交付参数，不改变删除门禁。
- 关键交付文案在 1120px 和 900px 下均完整显示；详情与候选列表各自滚动。

### 对应功能 ID

- DESK-016–DESK-020
- CORE-008、CORE-009、CORE-011、CORE-014、CORE-017

### 截图

- `docs/visual-qa/dark-redesign/phase-4/wechat-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-4/wechat-900x600.png`

### 阶段内差异结论

- 视频号页本阶段无遗留 P0/P1。
- 候选未提供封面或读取失败时使用正式图标占位，并明确显示“未提供/暂不可用”。

## 阶段 5：IDM 导入页

状态：**完成**

### 完成内容

- IDM 表格改为动态列宽：时间、状态保持紧凑，文件、来源和说明按权重分配剩余空间。
- 最小窗口下不增加主窗水平滚动；列表长文本省略，选中记录的完整内容在下方详情显示。
- 新增完整文件路径、可靠来源、状态时间和说明详情，后台刷新保持当前选择。
- 重试、打开原文件位置、打开可靠来源、补充/修改来源继续调用原方法和真实权限判断。
- 1120px 使用单行动作区；900px 自动两列换行，详情区域独立滚动。

### 对应功能 ID

- DESK-012–DESK-015
- CORE-001–CORE-007

### 截图

- `docs/visual-qa/dark-redesign/phase-5/idm-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-5/idm-900x600.png`

### 阶段内差异结论

- IDM 页本阶段无遗留 P0/P1。
- 列表不承担完整长文本展示；完整值始终在详情区可见。

## 阶段 6：设置与诊断页

状态：**完成**

### 完成内容

- 设置二级导航在 Normal / Wide 使用 160px，Compact 使用 136px；四个子页均接入独立纵向滚动。
- 浏览器配对页改为大号六位码卡片、复制即时反馈和明确解除配对动作。
- 网站规则增加行内域名输入、动态列宽和响应式操作区；新增/切换/删除/清空继续调用原数据库方法。
- 网络代理改为三张纵向模式卡片，手动地址、保存检测和真实检测结果集中展示。
- 更新页显示真实 `APP_VERSION`、检查按钮和签名/哈希校验说明，不复制原型旧版本号。
- 诊断页改为扁平深色面板，显示脱敏快照、导出说明、导出反馈和窗口操作。

### 对应功能 ID

- DESK-004、DESK-005、DESK-021–DESK-025
- CORE-011、CORE-015、CORE-016、CORE-017

### 截图

- `docs/visual-qa/dark-redesign/phase-6/settings-pairing-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-pairing-900x600.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-sites-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-sites-900x600.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-network-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-network-900x600.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-updates-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-6/settings-updates-900x600.png`
- `docs/visual-qa/dark-redesign/phase-6/diagnostics-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-6/diagnostics-900x600.png`

### 阶段内差异结论

- 设置与诊断页本阶段无遗留 P0/P1。
- 900px 下超出首屏的规则动作仍在本页纵向滚动内可达，未隐藏任何功能。

## 阶段 7：压力数据与无溢出修复

状态：**完成**

### 完成内容

- 视觉夹具增加 `standard / empty / stress` 场景、指定选中项、详情滚到底部和设置子页选择。
- 压力场景覆盖 200 条媒体任务、1000 条 IDM 记录、200 字中文标题、长 Windows 路径、长来源 URL、长错误说明和 20 档视频质量。
- 长标题在卡片中单行省略；详情头部限制为可扫读摘要，完整标题/作者/来源/输出仍在详情下部与 tooltip 中可查看。
- 错误面板在 900px 下内部换行，详情滚动到底后可完整查看；重试权限仍由真实状态决定。
- 深色 Scrollbar 和 Panedwindow sash 补齐，移除原生亮色轨道对深色界面的干扰。
- 主按钮使用与 Figma accent 近似的无障碍派生色 `#6265F1`，白字对比度为 4.515:1；进度和选中仍使用 `#6366F1`。
- 所有截图通过夹具自身 HWND 的 `PrintWindow` 后台捕获；不监听键盘鼠标，不激活窗口，不抢焦点。

### 压力与状态截图

- `docs/visual-qa/dark-redesign/phase-7/media-stress-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-7/media-stress-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/wechat-stress-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-7/wechat-stress-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/idm-stress-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-7/idm-stress-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/media-empty-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/wechat-empty-900x600.png`
- `docs/visual-qa/dark-redesign/phase-7/media-error-detail-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-7/media-error-detail-900x600.png`

### Figma 同画布对照

- `docs/visual-qa/dark-redesign/comparisons/downloads-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/downloads-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/wechat-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/wechat-900x600.png`
- `docs/visual-qa/dark-redesign/comparisons/idm-1120x720.png`
- `docs/visual-qa/dark-redesign/comparisons/idm-900x600.png`
- 设置四个子页 1120×720 对照与两个重点区域裁切对照保存在同一目录。

### 测试结果

- `python -m unittest discover -s tests -p "test_*.py"`：177 项通过，0 失败。
- `python tests/test_ui_layout.py -v`：11 项通过，0 失败。
- 44 张 PNG 结构检查通过；带尺寸标识的截图均与 1120×720 / 900×600 一致。
- schema、API、状态机、`planId`、Eagle 删除门禁和扩展目录均未由本轮 UI 实施修改。

### 最终差异结论

- 阶段 7 无遗留 P0/P1/P2。
- P3 环境覆盖缺口：本轮在当前 Windows 逻辑像素环境完成后台截图；125% / 150% 物理显示缩放仍需在对应显示器环境复核，但负像素字体、逻辑像素断点和无水平溢出规则已按审计合同实现。

## 阶段 2：全局窗口外壳

状态：**完成**

### 完成内容

- 顶栏改为贯穿全窗，品牌、真实版本号和 Eagle / 本机服务 / Chrome 三项健康状态形成统一外壳。
- 一级导航在 Normal / Wide 下保持 200px，在 Compact 下收窄到 168px；诊断入口仍固定可达。
- 1120px 使用 40px 单行顶栏；900px 使用紧凑双行状态布局，不隐藏版本或健康状态。
- 页面容器、媒体/视频号主从分隔和设置二级导航接入 Compact / Normal / Wide 布局更新。
- 视觉测试夹具增加 Windows 后台窗口截图：只读取夹具自身窗口像素，不监听键盘鼠标、不激活窗口、不抢焦点。

### 对应功能 ID

- DESK-001–DESK-006
- CORE-006、CORE-007、CORE-016

### 截图

- `docs/visual-qa/dark-redesign/phase-2/media-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-2/media-900x600.png`

### 阶段内差异结论

- 全局外壳本阶段无遗留 P0/P1。
- 下载列表、详情动作和预览的结构差异仍存在，归入阶段 3，不作为阶段 2 阻断项。

## 阶段 3：下载任务页

状态：**完成**

### 完成内容

- 以 360px / 300px 主列表锚点替换固定列 Treeview，任务行使用 92px 卡片结构。
- 卡片包含 48×32 正式占位/真实预览位、标题、来源、真实状态、大小、时间和 4px 进度条。
- 用户选择在后台刷新中保持稳定；新任务不会无故抢走当前选择。
- 详情区改为动态 16:9 预览、四项信息网格、完整来源/输出、阶段说明和独立错误面板。
- 停止、重试、补导 Eagle、打开文件位置和来源网页继续调用原有真实方法；按钮仅重排，不改变状态权限。
- 2026-07-28 功能复核修正：以上五个动作不再因当前状态不可用而消失，始终保留入口并按真实权限置灰；完整审计见 `docs/FUNCTIONAL_UI_AUDIT_2026-07-28.md`。
- 1120px 与 900px 下动作自动换行且均可到达；详情内容不足高度时独立纵向滚动。

### 对应功能 ID

- DESK-007–DESK-011
- CORE-008–CORE-014

### 截图

- `docs/visual-qa/dark-redesign/phase-3/media-1120x720.png`
- `docs/visual-qa/dark-redesign/phase-3/media-900x600.png`

### 阶段内差异结论

- 下载任务页本阶段无遗留 P0/P1。
- 缩略图缺失时显示项目正式图标占位，不抓取 favicon、不伪造媒体画面。

### 测试结果

- `python tests/test_ui_layout.py -v`
- 11 项通过，0 失败。
