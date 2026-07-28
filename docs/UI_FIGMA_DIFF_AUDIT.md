# 桌面 UI 与 Figma 深色原型差异审计

> 审计日期：2026-07-28  
> 审计对象：本地 `idm-eagle-auto-import`（真实产品）与本地 `Figma-test-download`（视觉参考）  
> 本轮边界：只做审计、布局规范和功能保全映射；不修改业务代码、数据库 schema、API、状态名、`planId`、Eagle 删除门禁或扩展。

## 0. 结论

当前 Tkinter 主窗口已经采用深色配色，但不能判定为“与 Figma 一致”。两者在应用外壳、任务列表形态、主从区比例、详情动作布局、视频号候选信息、IDM 表格响应式、设置控件和诊断页呈现上仍有结构性差异。

本轮建议采用 **Compact / Normal / Wide 三档响应式布局**，在 1120×720 恢复 Figma 的 200px 一级侧栏、360px 主列表和 40px 顶栏锚点；在 900×600 主动压缩侧栏、列表与动作区，不裁切功能；宽屏只增加信息密度和预览尺寸，不无上限拉长文本行。

Figma 原型不是业务真相，也不是可直接复制的实现：

- 它使用 Mock Data 和 `useState`，不得进入真实产品。
- 它显示 `v1.4.0`，而当前产品代码为 `1.4.1`。
- 它的 IDM 表格在 900×600 和 1120×720 均出现横向滚动，违反本项目 Overflow Contract。
- 它把部分真实状态和动作语义简化或写错，例如等待阶段的 100% 进度、失败/重试动作可用性。
- 它通过 Google Fonts、内联 SVG 和 emoji 呈现部分视觉资产；Tkinter 实施必须使用系统字体与正式图标资产，不新增运行时第三方依赖。

## 1. 版本门禁

### 1.1 已确认事实

| 项目 | 本地事实 | 结论 |
|---|---|---|
| 应用版本 | `pyproject.toml`、`constants.py`、扩展 manifest、安装器均为 `1.4.1` | 产品运行版本以 `1.4.1` 为准 |
| SQLite | `PRAGMA user_version = 6` | 本轮不得改 schema |
| 扩展协议 | `EXTENSION_PROTOCOL_VERSION = 1` | 本轮不得改协议 |
| 功能清单基线 | `1.4.1 / schema 6 / protocol 1` | 最后核对 2026-07-27 |
| 产品 Git | `main` | 审计开始前已有未提交修改 |
| 产品未提交修改 | `src/idm_eagle_bridge/wechat_channels.py`、`tests/test_wechat_channels.py` | 属于用户现有修改，本轮不触碰 |
| Figma Git | `main`，工作树干净 | 仅运行与截图，无源码修改 |

### 1.2 版本不一致

这是实施前必须先确认、但本轮不得自行修复的文档/原型漂移：

1. 产品真实代码与功能清单为 `1.4.1`。
2. `README.md` 仍以 `1.4.0` 为当前版本，并描述暖灰白底界面。
3. `DEVELOPMENT.md`、`ACCEPTANCE.md` 的前端重构和发行证据仍以 `1.4.0` 为主。
4. `design-qa.md` 标题仍为 `1.4.0`，虽然追加了 2026-07-27 深色主题记录，但“1120×720 深色桌面截图”“900×600 深色最小窗口截图”“Combobox 下拉深色验证”仍未勾选。
5. Figma `App.tsx` 顶栏和更新页均显示 `v1.4.0`。
6. `docs/visual-qa/` 中可复核的桌面 PNG 主要是旧暖灰版本，不能作为当前深色版“已一致”的证据。

因此，`design-qa.md` 中“深色 UI 重构完成”的文字只能视作历史记录，不能替代本次源码、实机截图和逐区测量。

## 2. 证据与判定规则

### 2.1 优先级

1. `ACCEPTANCE.md`、功能保全清单、真实业务代码：决定功能、数据、状态、动作和安全边界。
2. Figma `App.tsx`、`index.css` 与实际运行截图：决定视觉、布局、层级、尺寸和交互呈现。
3. 当前 `ui.py`：复用真实数据绑定、事件处理和业务方法；现有布局不作为目标。
4. `design-qa.md`：只作历史问题记录。

### 2.2 本次实测

Figma 原型在 900×600、1024×640、1120×720、1366×768、1440×900 下运行并截图。主要像素基线：

| 元素 | Figma 1120×720 实测 |
|---|---:|
| 顶栏 | 1120×40，左右内边距 16 |
| 一级侧栏 | 200×680 |
| 页面主区 | 920×680 |
| 下载/视频号列表 | 360×680 |
| 下载任务行 | 359×92.5 |
| 缩略图 | 48×32，3:2 |
| 任务标题 | 12px / 500 / 16.5px |
| 详情正文 | 560px 宽，20px 内边距，20px 纵向间距 |
| 设置二级导航 | 160px |

当前 Tkinter 测试夹具实机截图确认：

- 默认窗口 1120×720、最小窗口 900×600。
- 一级侧栏约 200px，已经使用深色主题。
- 顶栏位于右侧工作区而非贯穿全窗。
- 下载页仍是固定列 Treeview；没有 Figma 的缩略图任务卡、大小与创建时间行。
- 右侧详情按钮纵向堆叠，首屏信息密度和层级与 Figma 明显不同。
- 外层纵向滚动已存在，但局部固定宽度和固定 `wraplength` 仍会造成窄窗风险。

本轮截图证据只保存在审计会话临时目录，未加入仓库，以遵守“本轮只创建一个审计文档”的限制。

## 3. 最严重的 10 个差异

| 排名 | 严重度 | 差异 | 影响 | 处理原则 |
|---:|---|---|---|---|
| 1 | P0 | 下载页真实实现是固定列 Treeview，Figma 是 360px 缩略图任务卡列表 | 信息层级、选中态、状态、大小、时间、进度均无法对齐 | 重建纯视图层列表；继续调用真实 `list_plans` 和既有动作 |
| 2 | P0 | 当前详情动作纵向占满右栏；Figma 为顶部状态型横排动作 | 1120×720 已显得拥挤，900×600 更易把关键动作挤出首屏 | Normal/Wide 横排，Compact 自动两列或纵排；动作永远可达 |
| 3 | P0 | Figma IDM 表格自身在 900×600、1120×720 出现横向滚动；当前 Tk 也依赖固定总列宽 | 直接照搬仍违反“主窗无水平溢出” | 动态分配列宽，长文本列表省略、详情完整展示 |
| 4 | P0 | Figma Mock 状态与真实状态机不一致 | 可能把等待阶段显示为 100%，或让错误状态出现错误动作 | 所有状态和动作启停以 `_media_plan_view`、数据库和清单为准 |
| 5 | P0 | 视频号当前候选表缺缩略图、捕获时间，详情缺完整来源/预计输出结构 | DESK-017/018 的真实信息不可见或层级弱 | 使用真实候选与封面缓存，重排为 360px 主从页 |
| 6 | P1 | 全局顶栏结构不同：Figma 贯穿全窗 40px，当前仅位于工作区且状态较松散 | 品牌、版本和全局健康状态无法形成统一外壳 | 顶栏先于侧栏/主区构建；Compact 状态进入第二行 |
| 7 | P1 | 设置页视觉结构不一致：当前二级栏 140px、配对码弱、网站规则不是紧凑开关表格 | 关键配置难扫读，反馈与错误位置不明确 | 160px 基线；六位码卡片、行内开关、分组网络卡片 |
| 8 | P1 | Figma 没有可到达的诊断页，底部按钮无行为 | 若照搬会删除真实产品必要能力 | 保留独立诊断页，视觉与深色系统一致，继续脱敏导出 |
| 9 | P1 | Figma 依赖在线 Inter/JetBrains Mono、内联 SVG，并有 emoji 空状态 | 离线桌面不稳定，也违反正式图标要求 | 映射系统字体，使用项目品牌与本地 PNG 图标资产 |
| 10 | P1 | 空/加载/失败/禁用状态不完整，压力数据未验证 | 真实离线、代理错误、1000 条记录和长文本下不可验收 | 建立统一状态组件与压力测试矩阵，逐页面截图验证 |

严重度定义：

- **P0**：会改变业务语义、安全边界、功能可达性，或造成最小窗口硬溢出。
- **P1**：主要结构和关键交互明显偏离，影响任务完成。
- **P2**：视觉层级、密度、反馈或一致性问题。
- **P3**：不阻断使用的细节偏差。

## 4. 逐区域差异审计

### A. 全局窗口

| 子项 | Figma 参考 | 当前 Python | 差异/级别 | Tkinter 实施与真实绑定 | 窄窗及状态 |
|---|---|---|---|---|---|
| 默认/最小尺寸 | 运行参考 1120×720；根容器 `h-screen overflow-hidden` | `1120×720`，最小 `900×600` | 尺寸已对齐；P3 | 保留 `geometry`/`minsize` | 不得提高最小尺寸规避溢出 |
| 窗口背景 | `#0D0F16` | `#0D0F16` | 已对齐；P3 | 根 Frame 和滚动 Canvas 统一 token | 空白区不得露出系统浅色 |
| 顶部栏 | 全窗 40px，左右 16px，`white/5` 下边框 | 顶栏在工作区，内边距约 24/18，标题和状态同区 | 结构偏差；P1 | 顶栏移到侧栏与主区之前；状态取真实 health；DESK-001/003、CORE-006/007/016 | Compact 56px 两行；状态不裁切 |
| 品牌图标 | 12px indigo 原型符号 | 正式产品图标 | 原型只是占位；P2 | 保留现有唯一品牌资产，准备 12/16/24px PNG | 不用 emoji、内联 SVG 或 CSS 绘制 |
| 名称/版本 | 名称 13px/600；版本 10px mono，原型写死 1.4.0 | 名称更大；真实 `APP_VERSION=1.4.1` | 字级和版本偏差；P1 | 名称用 13px；版本读取 `APP_VERSION`；DESK-001 | Compact 仍显示版本，不隐藏 |
| Eagle/服务/Chrome | 右上 11px，16px 间距，彩色 6px 圆点 | 右侧工作区内文本状态，表达更长 | 层级偏差；P1 | 复用异步 Eagle 探测、本机服务、PairingManager；DESK-001/003/004、CORE-007/016 | Compact 改为第二行紧凑状态，不省略 |
| 刷新入口 | Figma 页面内局部刷新；顶栏无全局刷新按钮 | 顶栏右侧有全局刷新 | 业务要求优先；P2 | 保留全局刷新并用 14px 正式图标+文字；DESK-003 | Compact 固定右端，状态换行让位 |
| 一级侧栏 | 200px，背景 `#111318`，8px 内边距；行高约 34px、圆角 6px | 200px，12/16px 内边距，文字和间距略大 | 密度偏差；P2 | 200px Normal/Wide；DESK-001/002 | Compact 168px，标签仍完整 |
| 选中/悬停 | 选中 indigo 15%，文字 indigo-300；hover 白 5% | 已有深色 selected，但边距/圆角不同 | P2 | ttk 状态映射 selected/active/focus；DESK-001 | 键盘焦点必须可见 |
| 诊断入口 | 侧栏底部 34px，无实际行为 | 有真实诊断页 | 原型缺能力；P1 | 保留底部入口并进入诊断页；DESK-005 | 高度不足时随侧栏内容滚动或固定底部但可达 |
| 页面切换 | 单页切换，无过渡 | `_show_page` | 数据方法可复用；P3 | 只重排容器，不改刷新和生命周期 | 切页保持选中、滚动和所选任务 |
| 页面滚动 | Figma 多为局部 `overflow-y-auto` | `_VerticalScrolledFrame`，Treeview/Combobox 隔离滚轮 | 当前基础更符合真实需求 | 保留外层纵向滚动与控件滚轮隔离；DESK-002 | 禁止外层水平滚动 |

全局状态约束：

- 加载：状态点进入“检测中”，刷新按钮禁用并显示非动画的忙碌图标或短文本。
- 错误：顶栏只显示简短状态；完整错误在当前页状态条/诊断页。
- 禁用：使用禁用 token，保留文字可读性，不只靠颜色。
- 离线：Eagle、服务、Chrome 分别表达，不能合并成笼统“离线”。

### B. 下载任务页

| 子项 | Figma 参考 | 当前 Python | 差异/级别 | Tkinter 方案、数据与方法 | Compact/状态 |
|---|---|---|---|---|---|
| 主列表宽度 | 360px 固定锚点 | Panedwindow 3:2；Treeview 自适应区 | 结构偏差；P0 | Normal/Wide 360px，Compact 300px；DESK-007 | 与详情采用模式比例，不允许水平滚动 |
| 标题/清除 | 页头 39px，左右 16px；清除为低强调按钮 | 独立工具条，按钮较大 | P2 | 调用 `clear_media_history` / `clear_terminal_history`；DESK-011 | 忙碌时禁用，完成后刷新列表 |
| 单条任务 | 92.5px；上下 12、左右 16；分隔线白 4% | Treeview 34px 行高 | 信息密度完全不同；P0 | 使用可复用任务行 Frame，1000 条时采用分批/窗口化刷新；DESK-007 | Compact 88–96px，文本不撑高 |
| 缩略图 | 48×32，3:2，圆角 4 | 列表无图 | P1 | 复用 `_PreviewImageCache` 与真实 plan preview；无图用正式占位资产 | 图片不存在/异常比例时 letterbox，不拉伸 |
| 标题/域名 | 标题 12px/500 单行省略；域名 11px mono | 固定列宽，标题约 190、来源约 90 | P1 | 列表省略，详情完整；来源使用脱敏/真实展示字段 | 200 字标题不扩大行高 |
| 状态标签 | 11px mono、水平 8/垂直 2、圆角 4 | 状态为普通单元格文本 | P1 | 按真实 `_media_plan_view` 映射标签；DESK-007、CORE-009/012 | 不改状态名；未知状态用中性标签 |
| 大小/创建时间 | 同行右侧 11px 弱文本 | 列表缺创建时间，大小在说明中 | P1 | 使用 `list_plans` 真实字段；无值显示 `—` | 超长不撑宽 |
| 进度条 | 4px，行底部；非终态真实进度 | Treeview 百分比文本 | P1 | 真实 `progress`；合并/校验/等待不得显示 100%；CORE-009/012 | 无进度阶段显示轨道或不确定状态，不伪造 |
| 选中/悬停 | selected indigo 10%；hover 白 2% | Treeview selected | P2 | 显式 selected/hover/focus；键盘上下选择同步详情 | 新任务不得无故抢走用户选择 |
| 空状态 | 原型未完整覆盖 | Treeview 空白 | P1 | 正式图标、标题、说明、刷新入口 | 加载/空/错误三者分开 |
| 详情标题/来源 | 页头左右 20px、上下 12px；标题 14px，来源 12px | 标题更大，来源/文件固定 `wraplength=360` | P1 | `<Configure>` 动态计算 wraplength；DESK-008 | 长标题最多首屏 2 行，完整内容可复制/展开 |
| 状态型动作 | Figma 顶部水平按钮 | 当前全部纵向大按钮 | P0 | 调用 `stop_selected_plan`、`retry_selected_plan`、`import_selected_plan`、`open_plan_location`、`open_plan_source`；DESK-009/010 | Normal/Wide 单行；Compact 两列或纵向 |
| 动作启停 | 原型 Mock 对 retry/failed 有误 | `_media_plan_view` 和真实状态决定 | 原型不可复制；P0 | 停止仅活跃状态；重试仅真实可重试；补导仅安全的 `completed_local` | 禁用必须保留解释 tooltip/说明 |
| 预览 | 详情 p20；16:9，最大宽约 448 | 固定 150px 高预览 | P1 | 比例容器，异步加载；DESK-008 | Compact 高 160–220；Normal 220–300；Wide 最大 448 |
| 时长角标 | 预览右下角深色角标 | 无 | P2 | 仅真实时长存在时显示 | 不猜测 |
| 状态信息区 | 两列：状态、进度、大小、来源；间距 12 | 分散在标题、进度、来源/文件标签 | P1 | 2×2 信息网格，数据来自 plan view | 详情窄于 360 时单列 |
| 错误/输出路径 | 原型只给简短说明 | 当前可显示错误和文件，但层级弱 | P1 | 错误用 danger surface；路径单独可复制，依然执行 owned-path 门禁；CORE-013/014 | 400 字错误与 260 字路径内部换行/滚动 |
| 未完成预览 | 文字提示 | 已有“下载完成后显示视频预览” | 可复用；P3 | 根据阶段给“等待下载/处理中/预览生成中/失败” | 不显示伪缩略图 |

### C. 视频号页

| 子项 | Figma 参考 | 当前 Python | 差异/级别 | Tkinter 方案、数据与方法 | Compact/状态 |
|---|---|---|---|---|---|
| 捕获控制区 | 列表顶部；39px 标题行+约 87px 控制区；开始按钮 253×34 | 顶部说明、状态、按钮，结构较松 | P1 | 使用 `WechatChannelsCaptureService.health/start/stop`；DESK-016 | Compact 开始/停止占主列，清空为次按钮 |
| 生命周期状态 | 就绪、准备、等待、捕获、恢复、失败 | 真实状态完整：off/preparing/waiting/capturing/needs_recovery/failed | 真实实现优先 | 不改状态名和恢复逻辑；DESK-016、CORE-017 | 状态条可换行，错误进入详情 |
| 候选计数/刷新/清空 | 计数和刷新 35px 行；清空 66×34 | 已有刷新和清空 | P2 | 复用候选 registry；清空不停止捕获；DESK-017/020 | 操作中禁用，完成后即时刷新 |
| 候选行 | 360px 列表；行约 79px；缩略图 64×40 | Treeview 34px；无缩略图、捕获时间 | P0 | 复用真实封面缓存与 candidate list；DESK-017/018 | 图片失败显示正式占位，行不增高 |
| 标题/作者 | 12px/500 单行；作者 11px 弱文本 | 标题、作者列 | 层级偏差；P1 | 列表省略，详情完整 | 200 字标题不撑宽 |
| 时长/质量/时间 | 11px mono；真实质量；应含捕获时间 | 当前表只含时长/质量，缺捕获时间 | P1 | 使用 objectId 对应真实字段；DESK-017 | 缺值显示 `—`，不得推测 |
| 选中/空状态 | selected indigo 10%；空状态有图标和说明 | Treeview selected；空白区弱 | P1 | 统一 empty/loading/error 状态组件 | Figma 的 emoji 不得复制；空状态图标需本地资产 |
| 右侧封面 | 16:9 大图，1120 下约 448×252 | 固定 150px 高 | P1 | `preview_png` 异步加载，比例适配；DESK-018 | 同下载页预览尺寸规则 |
| 质量选择 | 真实候选质量下拉，11px | Combobox 已有真实质量 | 基础可复用；P2 | 继续绑定实际 quality，不复制 20 项 Mock | Combobox 自身滚轮，20 项有内部滚动 |
| 输出/来源 | 两列信息 | 当前输出存在，来源不完整 | P1 | 使用真实 candidate/plan payload | 500 字 URL 脱敏/换行，完整值按安全规则可查 |
| 双交付动作 | “导入 Eagle（完成后删除本机文件）”与“仅下载”并列 | radio 选择交付模式后单个创建按钮 | 呈现偏差；P1 | 两个明确按钮，共用 `submit_selected_wechat_candidate` 的真实选择参数；DESK-019、CORE-014 | 900 下两列可换两行；不得隐藏任一动作 |
| 警告与错误 | 原型覆盖不足 | 真实代理/证书/恢复错误存在 | P0 若遗漏 | 捕获区显示简短错误，详情显示可操作说明；DESK-016、CORE-011/017 | 恢复按钮只在真实可恢复状态启用 |

### D. IDM 导入页

| 子项 | Figma 参考 | 当前 Python | 差异/级别 | Tkinter 方案、数据与方法 | Compact/状态 |
|---|---|---|---|---|---|
| 标题/工具栏 | 51px，标题 13px，清除终态右对齐 | 顶部说明+表格+底部动作 | P1 | 标题工具栏固定；`clear_history`；DESK-015 | 清除时禁用并确认结果 |
| 表头/行高 | 表头约 36px；行约 43–44px | Treeview 行高 34px | P2 | 表头 34–36、行 40–44；DESK-012 | 1000 行使用 Treeview 增量更新 |
| 列宽 | 原型视觉约 100/80/176/160/余量，但实际发生水平溢出 | 固定 118/102/235/120/275 | P0 | 动态分配：时间 min90、状态 min88、文件 min150 flex2、来源 min100 flex1、说明 min160 flex2 | 总宽始终等于可用宽；无主窗水平滚动 |
| 状态标签 | 10–11px 彩色 tag | 普通状态文本 | P1 | 状态来源 `ui_snapshot/list_jobs`，语义不压缩；DESK-012、CORE-003–006 | 未知状态中性显示 |
| 长内容 | 原型用 truncate，但没有完整查看 | Treeview 直接截断，动作区也不提供完整统一详情 | P0 | 列表省略；选中后下方/右侧上下文详情显示完整文件、来源、说明，可复制 | 260/500/400 字压力数据不撑表格 |
| 行选中 | indigo 10% | Treeview selected | P2 | 同全局 selected/focus | 用户选择不被后台刷新抢走 |
| 状态动作 | Figma 仅等待来源时出现 256px 侧面板，其他动作缺失 | 当前底部有重试、打开位置、打开来源、补来源 | Figma 功能不完整；P0 | 保留全部真实动作；DESK-013/014、CORE-004/006/007 | Compact 动作两列；无可用动作时显示原因 |
| 补来源 | 右侧输入+确认 | 当前对话/输入区 | 可采用原型呈现但必须用真实方法 | `assign_source`；已导入时 `record_imported_source`/`EagleClient.update_source`，不得重复导入 | URL 校验错误就地显示，可重试 |
| 无数据 | 原型无专门状态 | 空表 | P1 | 正式图标+“暂无 IDM 导入记录”+说明 | 不显示无意义清除动作 |
| 错误/恢复 | Mock 错误文案 | 真实 retry/waiting/permanent 原因 | 真实优先；P0 | 错误详情完整；允许动作由数据库状态决定 | 永久失败不可伪装成可重试 |

### E. 设置页

| 子项 | Figma 参考 | 当前 Python | 差异/级别 | Tkinter 方案、数据与方法 | Compact/状态 |
|---|---|---|---|---|---|
| 二级导航 | 160px，背景沿用 root，8px 内边距，选中 indigo 15% | 140px | P2 | Normal/Wide 160；Compact 136；DESK-021–025 | 高度不足可随页面纵向滚动 |
| 浏览器配对 | 标题/说明；大号码卡片约 296×70；30px 码 | 码与状态在一行，层级弱 | P1 | `PairingManager.pairing_code`；码用 30px semibold mono | 码始终完整，不能截断 |
| 复制反馈 | 仅图标，原型无清晰反馈 | 复制方法存在 | P1 | 复制后按钮短暂显示“已复制”，并保留码 | 不用 toast 遮挡其他控件 |
| 解除配对 | danger 文本动作 | 可解除 Chrome | 原型虚构 Firefox 独立状态 | 调用真实 `unpair`，不复制 Mock 浏览器列表；DESK-004 | 需要确认，失败就地显示 |
| 网站规则输入 | 单行输入+“添加并启用” | 规则区已有增删改 | P2 | `Database.set_site_rule`；DESK-021/022 | Compact 按钮换到第二行 |
| 规则表/开关 | 行内 enable/subdomain toggle、删除图标 | Treeview+外部按钮 | P1 | 使用可点击自绘 toggle 或单元格操作；保留 CRUD | 900 下修改时间可缩短，域名列优先 |
| 删除/清空 | 行内删除；底部 danger 清空 | 外部按钮 | P2 | `delete_site_rule` / `clear_site_rules`；不得反推规则 | 二次确认；失败后保留数据 |
| 网络模式 | 3 个纵向卡片，单选圆点 | 当前 3 个 radio 水平排列 | P1 | 纵向卡片；`NetworkProxyManager.configuration/configure/status`；DESK-023 | 手动模式展开地址、保存与检测结果 |
| 代理信息 | 原型没有完整输入/检测/脱敏反馈 | 真实产品有校验和脱敏 | 原型缺功能；P0 | 必须显示检测来源、脱敏端点、保存结果和可操作错误；CORE-011 | 500 字输入不撑宽，错误换行 |
| 更新 | 状态卡、检查按钮、原型虚构“查看更新历史” | 真实检查、确认下载/安装、错误 | 原型动作不可信；P0 | 只保留 `check_for_updates`、`prepare_update`、`launch_installer` 真实流程；DESK-024/025 | 检查中禁用；下载/安装必须用户确认 |
| 安全状态 | 原型写死 RSA/SHA 文案 | 真实 updater 校验 | P1 | 只显示真实检查结果，不用静态“已安全” | 错误包含恢复建议，不泄露路径 |

### F. 诊断页

Figma 只有侧栏底部入口且没有行为，不能作为功能实现参考。真实产品必须保留可达诊断页。

建议页面结构：

1. 40px 页面工具栏：标题“诊断”、右侧“刷新”。
2. 24px 内容内边距；顶部隐私说明 surface。
3. 两列健康摘要：应用/数据库/服务/Eagle/浏览器配对/网络/视频号；Compact 改为单列。
4. “导出脱敏诊断”作为主按钮，旁边明确列出不会包含的内容。
5. 可选的“打开日志目录”只能调用真实、安全的既有路径方法；若没有现成安全方法，本轮不新增。

绑定与约束：

- 对应 DESK-005、CORE-015/016/017。
- 继续调用 `export_diagnostics` 与各子系统 `health`。
- 永不包含令牌、Cookie、完整路径、完整来源、网站规则、代理认证信息。
- 空状态显示“尚未刷新”；加载状态禁用导出；失败状态保留已成功的分项，不把全部健康项抹掉。
- 900×600 使用外层纵向滚动，按钮始终可达。

## 5. 视觉设计令牌

### 5.1 色彩

| Token | Figma/CSS 依据 | Tkinter 目标值 | 用途 |
|---|---|---|---|
| `app.bg` | `#0D0F16` | `#0D0F16` | 应用根背景 |
| `topbar.bg` | `#0D0F16` | `#0D0F16` | 顶栏 |
| `sidebar.bg` | `#111318` | `#111318` | 一级侧栏 |
| `surface.1` | 低透明白叠加 | `#161820` | 一级表面 |
| `surface.2` | `white/5` 近似叠加 | `#1A1D25` | 二级表面、输入框 |
| `surface.hover` | `white/5` | `#1F222B` | hover |
| `surface.selected` | `indigo-500/10–15` | `#1E2440` | 选中行/导航 |
| `text.primary` | 根文本 `#E2E8F0` | `#E2E8F0` | 主文字 |
| `text.secondary` | `white/55–65` | `#A0A5B0` | 次文字 |
| `text.muted` | `white/30–40` | `#6B7080` | 弱文字 |
| `border` | `white/5` | `#2A2D35` | 控件边框 |
| `divider` | `white/4–5` | `#1E2029` | 分隔线 |
| `accent` | Tailwind indigo-500 `#6366F1` | `#6366F1` | 主按钮、选中、焦点 |
| `accent.hover` | indigo-600 | `#5558E6` | 主按钮 hover |
| `accent.text` | indigo-300 | `#A5B4FC` | 选中文字 |
| `success` | emerald-400 | `#34D399` | 已导入、在线 |
| `downloading` | blue-400 | `#60A5FA` | 下载中 |
| `waiting_eagle` | amber-400 | `#FBBF24` | 等待 Eagle |
| `warning` | orange/yellow-400 | `#FB923C` | 校验、等待、提示 |
| `danger` | red-400 | `#F87171` | 失败、危险动作 |
| `disabled` | slate-500 降透明 | `#686E7A` | 禁用文字 |
| `progress.track` | 深色二级表面 | `#1A1D25` | 进度轨道 |

状态色只能作为辅助；所有状态必须同时有文字。

### 5.2 字体

Figma 使用 Inter 与 JetBrains Mono，但 `index.css` 通过 Google Fonts 加载。桌面实施不新增网络或第三方运行时依赖：

| 角色 | Figma | Tkinter named font |
|---|---|---|
| 中文 UI | Inter fallback | `Microsoft YaHei UI` |
| 英文/数字 UI | Inter | `Segoe UI` 或随中文统一 |
| 代码/版本/域名 | JetBrains Mono | `Cascadia Mono`，不存在时 `Consolas` |
| 10px | 10px / 400–500 | `size=-10`，normal；必要标签 bold |
| 11px | 11px / 400–500 | `size=-11`，normal |
| 12px | 12px / 500 | `size=-12`，normal；关键标题 bold |
| 13px | 13px / 500–600 | `size=-13`，bold |
| 14px | 14px / 600 | `size=-14`，bold |

Tk 字号使用负值表示逻辑像素，避免 point 与 Windows DPI 换算造成尺寸漂移。字体不存在时按上述顺序回退。

建议行高：

- 10px：14px
- 11px：16px
- 12px：17px
- 13px：20px
- 14px：21px

### 5.3 圆角、间距和尺寸

| 类别 | 令牌 |
|---|---|
| 圆角 | 4px：tag/缩略图；6px：按钮/导航；8px：输入框/小卡片；12px 仅配对码大卡片 |
| Tk 替代 | 用 Canvas 圆角背景或预生成 9-slice `PhotoImage` ttk element；不以 emoji/字符画代替 |
| 间距 | 2、4、6、8、12、16、20、24px |
| 图标 | 12px 顶栏状态/小动作；14px 按钮；16px 导航；24px 空状态；品牌按 12/16/24px 多尺寸资产 |
| 顶栏 | Normal/Wide 40px；Compact 56px |
| 一级侧栏 | Compact 168px；Normal/Wide 200px |
| 二级侧栏 | Compact 136px；Normal/Wide 160px |
| 主列表 | Compact 300px；Normal 320–360px；Wide 360px |
| 列表行 | 下载 92px；视频号 79–84px；IDM 40–44px；Treeview 基线 42px |
| 按钮 | 常规 34px；主动作 38px；最小可点击高度 32px |
| 主从比例 | 见 Overflow Contract；1120×720 精确锚点为 360:560 |

## 6. Overflow Contract

### 6.1 布局模式

断点根据 Tk `winfo_width()` 的**逻辑像素**决定；Windows 100%/125%/150% 下均以当前 client area 重算，不按物理屏幕像素猜测。

| 规则 | Compact | Normal | Wide |
|---|---|---|---|
| 客户区宽度 | 900–1023 | 1024–1279 | ≥1280 |
| 一级侧栏 | 168 | 200 | 200 |
| 顶栏 | 56px 两行；品牌/刷新第一行，3 个状态第二行 | 40px；状态紧凑单行 | 40px；完整单行 |
| 下载/视频号主从 | 列表 300；详情吃剩余宽度，约 43:57 | 列表 clamp(320, 35%, 360) | 列表 360；详情吃剩余宽度 |
| 详情动作 | 2 列；详情宽 <360 时单列 | 尽量单行，不足时 2 列 | 单行右对齐 |
| IDM 列宽 | 按最小值+权重分配，说明/来源先省略 | 同左，文件/说明获得更多 flex | 同左，最多增加文件/说明，不拉长时间/状态 |
| 文本 | 列表单行省略；详情动态换行 | 同左 | 同左，详情正文限制最大阅读宽 |
| 预览 | 16:9，高 160–220，且不超过详情可视高度 40% | 高 220–300 | 最大宽 448，保持 16:9 |
| 设置二级栏 | 136 | 160 | 160 |
| 内部纵向滚动 | 页面高度不足时必须；列表与详情各自可滚 | 按需 | 长数据按需 |

在 1120×720，目标精确结构是：40px 顶栏；200px 一级侧栏；360px 下载/视频号主列表；560px 详情。

### 6.2 强制规则

1. 主窗口外壳禁止水平滚动条。
2. 任何按钮不得超出可见区或因缩窗永久不可达。
3. 动作一行放不下时改为两行、两列或纵向，不隐藏功能。
4. 顶部状态放不下时进入 Compact 两行顶栏，不裁切 Eagle/服务/Chrome/版本。
5. 主体高度不足时使用外层纵向滚动；Treeview 和 Combobox 保留自身滚轮。
6. Treeview 总列宽必须绑定 `<Configure>` 动态重分配，并为每列保留最小值。
7. 列表允许省略，详情必须能查看完整标题、文件名、URL、路径和错误。
8. 所有动态 `wraplength` 使用当前控件宽度减去实时 padding 计算，禁止长期写死 360/800/1020。
9. 预览保持比例，使用 contain/letterbox，不能把详情动作向下挤出可达区。
10. 不得通过提高最小窗口、隐藏功能或改变业务状态规避溢出。

### 6.3 表格动态列宽

IDM 可用宽度为 `W` 时：

- 先分配最小宽：时间 90、状态 88、文件 150、来源 100、说明 160。
- 扣除边框和滚动条后，剩余宽按 `文件 2 : 来源 1 : 说明 2` 分配。
- 若 `W` 小于最小总宽，仍不启用主窗横向滚动：时间可降至 82、状态 80、来源 88、说明 140；详情面板承担完整内容。
- 只有控件自身确实需要时才允许内部水平滚动；本设计的 IDM 主表不需要。

网站规则表采用：域名 flex2、启用 64、子域名 72、修改时间 100、删除 40。Compact 下修改时间可显示短日期，但真实值在详情/提示中完整可见。

### 6.4 压力数据与预期

| 压力数据 | 预期行为 | 验证 |
|---|---|---|
| 200 个中文字符标题 | 列表单行省略；详情动态换行并可复制 | 3 模式截图+窗口拖动 |
| 260 字符 Windows 文件名/路径 | 表格不增宽；详情按可断点换行，保留完整值 | 900×600 + 150% DPI |
| 500 字符来源 URL | 列表显示脱敏域名；详情安全显示/复制，不撑宽 | 单元测试+截图 |
| 400 字符错误 | danger surface 内换行，必要时内部滚动 | 900×600 |
| 1000 条任务 | 增量同步，滚动流畅，选择不丢，后台刷新不全量重建 | 性能测试+人工滚动 |
| 20 个状态/质量选项 | Combobox 自身下拉滚动；外层不抢滚轮 | 100/125/150% DPI |
| 中英文混排 | 采用 CJK 回退字体，无方块和异常基线 | 5 个窗口尺寸 |
| 空数据 | 显示真正空状态，不与加载/错误混淆 | 各页面 |
| 图片不存在 | 正式占位图，不显示破图或空白边框 | 下载/视频号 |
| 图片比例异常 | contain+letterbox，不拉伸、不裁掉主体 | 3:2、16:9、竖图 |
| 所有动作同时出现 | Normal 可换两行；Compact 两列/纵排，全部可达 | 900×600 |

### 6.5 窗口验证矩阵

实施后必须逐页验证：

- 900×600：Compact，100%/125%/150%。
- 1024×640：Normal 下界。
- 1120×720：主要视觉基准。
- 1366×768：Wide。
- 1440×900：Wide，检查空白分配和最大阅读宽。

每个尺寸至少覆盖：下载任务、视频号、IDM、设置四个子页、诊断；并包含空、加载、错误、禁用、长文本和全部动作状态。

## 7. 功能保全映射

说明：下表中的“启用/禁用”是 UI 呈现条件，不改变后端状态机。错误必须出现在相邻状态区或详情区；恢复必须调用已有真实方法。

### 7.1 DESK-001–DESK-025

| ID | 页面/控件 | 真实数据源与方法 | 启用/禁用条件 | 错误位置与恢复 | 测试证据 |
|---|---|---|---|---|---|
| DESK-001 | 全局顶栏、一级导航、诊断入口 | `MainWindow._build/_show_page`；Database/LocalApiServer/ProcessingService | 窗口存活时导航启用；切页中短暂禁用重复操作 | 顶栏分项状态；刷新 | `test_ui_layout.py`、视觉 QA、A227 |
| DESK-002 | 五页容器、外层滚动 | `_VerticalScrolledFrame`、各 `_build_*_tab` | 页面可达；控件自身滚动时外层不接管 | 页面内错误；恢复滚动位置/重进页 | `test_ui_layout.py`、A221/A228 |
| DESK-003 | 全局/页面刷新、状态点 | `_AsyncProbe`、`_PreviewImageCache`、`_sync_tree_rows`、`refresh` | 无同类刷新在途时启用 | 顶栏简报+页面详情；再次刷新 | `test_ui_layout.py`、A224 |
| DESK-004 | 配对码复制、解除配对 | `PairingManager.pairing_code/unpair`；`copy_pairing_code/unpair` | 有码可复制；有配对可解除 | 配对卡片内；刷新/重新配对 | `test_security_api.py` |
| DESK-005 | 诊断页、导出按钮 | `export_diagnostics`、security/network/health | 健康快照就绪时导出；导出中禁用 | 诊断页 banner；重试导出 | `test_security_api.py`、`test_wechat_channels.py`、A30/A81/A195/A212 |
| DESK-006 | 窗口最小化/隐藏/退出 | `show/hide/_poll_control_signals/quit`、托盘 SignalEvent | 按真实生命周期启用 | 顶栏/托盘；重新显示或安全退出 | `test_control_signal.py`、`test_shutdown_order.py` |
| DESK-007 | 下载任务列表 | `MediaCoordinator.list_plans`、`_refresh_media_tasks` | 有数据可选；加载时列表只读 | 列表空/错误状态；刷新 | `test_ui_layout.py`、`test_media.py`、A109 |
| DESK-008 | 任务详情与预览 | `selected_plan/_update_plan_detail/get_plan_preview` | 有选中任务时启用详情 | 预览区/错误卡；重选或刷新预览 | `test_ui_layout.py`、`test_media.py` |
| DESK-009 | 停止/重试/打开目录/来源 | `stop_selected_plan/retry_selected_plan/open_plan_location/open_plan_source` | 仅真实状态和安全字段允许时启用 | 动作邻近错误；刷新后重试 | `test_media.py` |
| DESK-010 | 补导 Eagle | `import_selected_plan/import_completed_plan` | 仅安全 `completed_local` 且文件仍受管控 | 详情错误卡；Eagle 恢复后重试 | `test_media.py`、`test_processor.py`、A147 |
| DESK-011 | 清除媒体终态记录 | `clear_media_history/clear_terminal_history` | 存在终态记录且无清理在途 | 页头反馈；刷新 | `test_media.py`、A222 |
| DESK-012 | IDM 表格 | `Database.list_jobs/ui_snapshot`、`refresh` | 有记录可选；加载时只读 | 空/错误状态；刷新 | `test_ui_layout.py`、`test_processor.py` |
| DESK-013 | IDM 重试/打开位置/来源 | `retry_selected/open_file_location/open_source`、`retry_job` | 状态可重试、路径/可靠来源存在 | 详情动作区；修复条件后重试 | `test_processor.py` |
| DESK-014 | IDM 补充/修改来源 | `assign_source/record_imported_source/EagleClient.update_source` | 未导入可补；已导入且有 Eagle item ID 可更新 | 来源输入下方；修正 URL/恢复 Eagle | `test_database.py`、`test_eagle.py`、A12 |
| DESK-015 | 清除 IDM 终态记录 | `clear_history/Database.clear_terminal_history` | 有终态记录时启用 | 工具栏反馈；刷新 | `test_database.py`、A222 |
| DESK-016 | 视频号捕获开关和状态 | `toggle_wechat_capture/_run/_poll`、service `start/stop/close/health` | 按 off/active/operation-in-flight 决定 | 捕获控制区；停止/恢复/重试 | `test_wechat_channels.py`、`test_shutdown_order.py`、A197–A201 |
| DESK-017 | 视频号候选列表/刷新 | registry `list`、service `candidates`、`_refresh_wechat_candidates` | 捕获可不在运行；候选存在可选 | 列表错误状态；刷新 | `test_wechat_channels.py`、A202/A203/A206 |
| DESK-018 | 候选详情/封面 | `_update_wechat_detail/_load/_drain`、`preview_request/preview_png` | 有选中 objectId 时加载 | 预览区；重试加载/换候选 | `test_wechat_channels.py`、`test_ui_layout.py` |
| DESK-019 | 质量与双交付动作 | `submit_selected_wechat_candidate`、service `submit`、`plan_payload/create_plan` | 有真实质量和有效候选；提交中禁用 | 动作区；修正质量/恢复网络后重试 | `test_wechat_channels.py`、`test_media.py`、A204–A211/A225 |
| DESK-020 | 清空视频号候选 | `clear_wechat_candidates`、service/registry `clear` | 候选存在且无清理在途 | 控制区反馈；刷新 | `test_wechat_channels.py`、A222 |
| DESK-021 | 网站规则表 | `Database.list_site_rules`、`_refresh_settings` | 设置页可读；加载中只读 | 表格状态；刷新 | `test_database.py`、`test_ui_layout.py` |
| DESK-022 | 规则新增/启停/子域/删除/清空 | `_settings_*`、`set/delete/clear_site_rule(s)` | 输入有效/有选中/有规则时启用 | 输入或表格行内；修正后重试 | `test_database.py`、A07–A10/A222 |
| DESK-023 | 网络模式、代理输入/保存 | `_settings_proxy_mode_changed/_save/_refresh`、NetworkProxyManager | 手动模式才启用地址；保存中禁用 | 网络卡片内；修正地址/切自动或直连 | `test_network_proxy.py`、A192–A195 |
| DESK-024 | 检查更新/确认下载安装 | `_automatic_update_check/check_for_updates/_handle_*`、updater | 无检查/下载在途；安装必须用户确认 | 更新卡片；重试检查/下载 | `test_updater.py`、A42–A45 |
| DESK-025 | 更新安全校验状态 | `_verify_rsa_signature/parse_manifest/prepare_update`、安装器回滚 | 只有全部校验通过才允许安装 | 更新错误卡；重新下载或取消 | `test_updater.py`、安装器门禁、A43–A45 |

### 7.2 CORE-001–CORE-017

| ID | 页面/控件 | 真实数据源与方法 | 启用/禁用条件 | 错误位置与恢复 | 测试证据 |
|---|---|---|---|---|---|
| CORE-001 | IDM 新任务行/全局唤醒状态 | `hook.main/start_assistant_hidden/Database.add_job/notify_processing_service` | 路径通过后端验证才出现 | IDM 说明列；后端重试/重新捕获 | `test_hook.py` |
| CORE-002 | IDM/媒体活动状态与刷新 | `ProcessingService._run/wake`、`JobProcessor.process_once` | UI 不提供伪启动开关 | 顶栏服务状态；唤醒/刷新 | `test_end_to_end.py` |
| CORE-003 | IDM 状态标签/说明 | `process_job/_retry` | 仅真实 retry 状态可重试 | IDM 详情；等待文件稳定或重试 | `test_processor.py`、A13/A17/A37 |
| CORE-004 | IDM 来源字段/补来源 | `attach_best_source/_choose_source/process_job` | 无可靠来源仍可导入；不得猜 URL | IDM 来源详情；手工补来源 | `test_processor.py`、`test_database.py`、A03/A11 |
| CORE-005 | IDM 内容重复状态 | `sha256_file/fingerprint_owner/remember_fingerprint` | 重复项不提供再次导入 | IDM 说明；更换真实文件/查看已有项 | `test_processor.py`、A15/A38 |
| CORE-006 | Eagle 等待/重试/永久失败 | `_wait_for_eagle/_retry/EagleClient.is_available` | 按重试次数和等待上限 | IDM/顶栏；恢复 Eagle 后真实重试 | `test_processor.py`、A05/A39 |
| CORE-007 | Eagle 顶栏状态、导入/更新来源动作 | `EagleClient.app_info/add_from_path/update_source` | Eagle 可用且参数安全时启用 | 顶栏+详情；启动 Eagle/重试 | `test_eagle.py` |
| CORE-008 | 媒体/视频号提交错误 | `safe_output_name/canonical_page_resolver_url/create_plan` | 验证全部通过才创建计划 | 动作区错误卡；修正选择 | `test_media.py` |
| CORE-009 | 下载状态标签、进度、双交付动作 | `_process_remote/_resolve_*/_download_and_decrypt_*` | 按统一状态机启停 | 下载详情；停止/重试/补导 | `test_media.py`、`test_wechat_channels.py`、A106/A110/A209 |
| CORE-010 | 下载阶段、质量、校验说明 | `_ffmpeg_input_arguments/_select_manifest_stream_indexes/_probe/_validate_output_duration` | 有真实流/校验结果时展示 | 下载详情；重试或改质量 | `test_media.py`、A59–A67/A121 |
| CORE-011 | 网络设置、下载网络错误 | `NetworkProxyManager.routes_for/_prepare_network_route_retry/_network_failure_with_guidance` | 本机/Eagle 永远直连；手动地址有效才保存 | 网络设置与任务错误卡；切换模式/修正代理 | `test_network_proxy.py`、`test_media.py`、A192–A195 |
| CORE-012 | 任务全部状态与动作 | `retry/stop/_set_progress/_set_status/get/list/preview/open/import` | 所有动作只按目标 `planId` | 当前任务详情；对应真实动作恢复 | `test_media.py` |
| CORE-013 | 打开目录/补导 | `_owned_plan_file/open_plan_output/import_completed_plan` | 文件存在且属于完成目录 | 下载详情；无法恢复时明确拒绝 | `test_media.py`、A126/A147 |
| CORE-014 | 导入后删除说明与错误 | `_cleanup_imported_desktop_output`、数据库 cleanup 方法 | 只有五项门禁全部满足才执行 | 下载详情；删除失败保留文件并可见 | `test_processor.py`、`test_database.py`、A225 |
| CORE-015 | 全局恢复/诊断 | `Database.initialize`、schema 6 | 迁移完成后才进入正常状态 | 诊断页；安全重启/升级恢复 | `test_database.py`、`test_media.py`、A108 |
| CORE-016 | 服务/配对顶栏与诊断 | `build_handler/LocalApiServer/PairingManager` | loopback、Origin、令牌验证真实决定 | 顶栏/配对/诊断；重新配对或重启服务 | `test_security_api.py`、A27/A83/A135 |
| CORE-017 | 视频号捕获状态、候选和错误 | capture service/registry/proxy/certificate/crypto | 按真实证书、代理租约和 objectId | 视频号控制区/详情；停止并恢复代理、重试 | `test_wechat_channels.py`、A197–A214 |

### 7.3 扩展冻结边界

EXT-001–EXT-034 本轮不做视觉重写。桌面 UI 后续实施不得修改：

- 扩展 bridge 消息名与请求/响应结构。
- API 路径、配对/鉴权规则和 Origin 门禁。
- `planId` 身份、安全归属检查和动作目标。
- 媒体状态机、真实进度、预览、停止、重试、打开目录和补导语义。
- DRM、`blob:`、固定 Range、纯分片、无可靠身份等阻断边界。
- 两个明确交付动作以及成功后删除本机文件的严格门禁。

## 8. Figma 原型中不得复制的内容

1. 顶栏/更新页的 `v1.4.0`。
2. Mock 任务、Mock 视频号候选、Mock 网站规则和 Mock 浏览器配对状态。
3. `useState` 直接改变状态的假交互。
4. `waiting_eagle` 等待阶段显示 100%。
5. 以原型条件判断停止/重试/补导，而不是使用真实 plan view。
6. IDM 表格的固定内容宽度与水平滚动。
7. “查看更新历史”等真实产品不存在的方法。
8. 在线字体加载。
9. 内联 SVG、emoji 和字符画作为正式资产。
10. 不做确认的解除配对、清空规则、下载/安装等危险动作。

## 9. 需要确认的设计决策

以下只影响视觉实施，不改变功能：

1. **品牌资产**：建议保留当前产品图标，替换 Figma 顶栏的通用 indigo 符号。
2. **Compact 一级侧栏**：建议在 900–1023px 使用 168px，仍保留完整文字；Normal/Wide 恢复 200px。
3. **字体策略**：建议使用 `Microsoft YaHei UI + Segoe UI + Cascadia Mono/Consolas`，不打包 Inter/JetBrains Mono。
4. **任务缩略图占位**：建议有真实 preview 就显示；没有时使用本地正式占位资产，不抓 favicon、不伪造截图。
5. **圆角实现范围**：建议只为导航、按钮、tag、输入框、预览和配对码卡片使用 Canvas/9-slice 圆角；大型容器继续用直角低透明边框，避免 Tk 绘制复杂度失控。

## 10. 后续实施门禁

在开始修改 `ui.py` 前，应先确认第 9 节决策，并建立以下验收证据：

1. 1120×720 同状态的 Figma/Tk 下载页、视频号页、IDM 页、四个设置子页和诊断页对照截图。
2. 900×600、1024×640、1366×768、1440×900 的无水平溢出截图。
3. Windows 100%/125%/150% 缩放截图。
4. 本文压力数据矩阵的 UI fixture。
5. DESK-001–025 与 CORE-001–017 对应测试全部通过。
6. 不改 EXT-001–034、schema 6、protocol 1、状态名、API、`planId` 和 Eagle 删除门禁。

本轮到此停止，不进入实现。
