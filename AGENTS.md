# 项目协作规则

- 这是 Windows 本机工具；业务运行时代码保持 Python 3.11+ 标准库零第三方依赖，发行版用 PyInstaller 自带解释器与 Tcl/Tk。
- 核心行为：IDM 视频无来源也导入；有可靠来源才写入 Eagle，禁止猜测网址。
- 网站关闭依赖 Chrome 明确的 `site_disabled`/`ignore` 事件，不能从无来源文件反推网站。
- IDM 与用户原下载文件不移动、不删除、不修改，不直接修改 Eagle `.library` 内容；只有新版计划明确记录 `delete_after_import=1`、Eagle 官方 API 已确认导入成功且最终文件同时通过计划路径与“已完成”目录归属校验时，才删除本程序创建的本机下载副本。
- Eagle 导入与来源更新只调用官方本地 Web API。
- IDM hook 必须快速完成：只入队、合并活动任务和发送唤醒信号，不做哈希或网络调用。
- 系统托盘必须由 `launcher/Launcher.cs` 的 Windows Forms 宿主管理；禁止在 Python 中用 `ctypes` 替换窗口过程。
- 数据库结构迁移使用 SQLite `PRAGMA user_version`；不得用启动时反复执行的大范围更新代替版本迁移。
- `pyproject.toml`、`src/idm_eagle_bridge/constants.py` 和 `chrome-extension/manifest.json` 的版本必须一致。
- 安装器不得覆盖 IDM 已有的其他杀毒软件路径；备份、恢复和删除目录都必须校验归属。
- 发行包不得包含开发机 `data`、配对令牌、网站规则、任务记录或用户路径。
- 修改流程后同步 README、ACCEPTANCE、TASKS、STATUS 和相关 docs，完成项不能保留为未来计划。
- 自动测试入口见 `DEVELOPMENT.md`；提交前运行全部 unittest、扩展 JS 语法检查和清单 JSON 解析。
- 深入文档：架构见 `docs/ARCHITECTURE.md`，决策边界见 `docs/DECISIONS.md`，安装运维见 `docs/INSTALLATION_AND_ROLLBACK.md`。
- `cat-catch` 功能对等是已经完成的 1.0.0 历史目标；1.2.0 起活动扩展只保留媒体发现/候选/预览/提交能力，旧下载器、解析页、录制器、在线 FFmpeg 与第三方路由不得重新进入运行时。
- 浏览器捕获、解析、预览和下载候选统一使用 `媒体候选组` 领域模型；DASH 的视频流和音频流必须属于同一候选组，禁止按两个无关 URL 呈现。
- 下载前必须默认展示可识别的标题、封面或预览、媒体类型、清晰度、音轨和预计输出；原始 URL 只能作为展开后的技术信息。
- 音视频合并默认走本机 FFmpeg streamcopy；浏览器内 FFmpeg/WASM 是受 2GB 限制的可选兼容路径，不得把媒体静默上传到第三方服务器。
- DRM 内容只允许识别并明确提示，不实现、迁移或测试任何 DRM 绕过能力。
- 默认只删除本程序创建且带任务归属记录的临时分片/中间文件；显式“导入后删除”计划可在 Eagle 成功后删除带计划归属的最终本机副本。用户原下载文件、IDM 文件、目录外文件和导入失败文件仍禁止移动、删除或修改。
- 若复用或修改 `cat-catch` GPL-3.0 源码，必须先完成许可门禁，保留版权、许可证、对应源码和构建信息；未通过门禁前只能研究行为和独立实现。

## Agent skills

### Issue tracker

本仓库使用本地 Markdown：`TASKS.md` 保存总览，详细任务位于 `.scratch/<feature>/issues/`。见 `docs/agents/issue-tracker.md`。

### Triage labels

本地任务使用 `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human` 和 `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库采用单一上下文：领域词汇见根目录 `CONTEXT.md`，架构决策统一见 `docs/DECISIONS.md`。见 `docs/agents/domain.md`。
