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
| 全局 | 字体 Segoe UI / Microsoft YaHei UI（无 Inter） | 保持系统字体 |
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
