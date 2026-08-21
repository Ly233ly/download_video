# 项目协作规则

- 这是 Windows 本机工具；业务运行时代码保持 Python 3.11+ 标准库零第三方依赖，发行版用 PyInstaller 自带解释器与 Tcl/Tk。
- 品牌名为“留底”，产品全称为“留底下载器”，产品说明为“免费开源的 Windows 本机媒体下载与归档工具”，宣传口号为“想留的，留个底。”；组件名称固定为“留底桌面端”“留底浏览器扩展”“留底安装器”，不得在产品名中增加“媒体”。
- 当前版本为 `1.6.3`，数据库结构为 `6`，扩展协议为 `1`。
- 浏览器只负责媒体发现、候选、预览、选择与任务提交；下载、合并、校验、文件和 Eagle 全部属于桌面端。
- 浏览器捕获、预览和下载统一使用“媒体候选组”；DASH 视频流和音频流必须属于同一候选组。
- 下载前默认展示标题、封面或预览、媒体类型、清晰度、音轨和预计输出；技术 URL 只能展开后查看。
- 媒体下载和音视频合并默认使用本机 FFmpeg streamcopy；不得静默上传到第三方服务。
- DRM 内容只允许识别和提示，不实现或测试绕过能力。
- IDM 视频无来源也导入；有可靠来源才写入 Eagle，禁止猜测网址。
- 网站关闭依赖扩展明确的 `site_disabled` 或 `ignore` 事件，不能从无来源文件反推网站。
- IDM hook 必须快速完成，只入队、合并活动任务和发送唤醒信号，不做哈希或网络调用。
- Eagle 导入与来源更新只调用官方本地 Web API，不直接修改 `.library`。
- 用户原下载文件、IDM 文件和目录外文件不得移动、删除或修改。
- 只有明确记录 `delete_after_import=1`、Eagle 官方 API 已确认成功，并同时通过计划路径、任务路径和“已完成”目录归属校验时，才可删除程序创建的最终副本。
- 系统托盘必须由 `launcher/Launcher.cs` 的 Windows Forms 宿主管理；禁止在 Python 中替换窗口过程。
- 数据库迁移使用 SQLite `PRAGMA user_version`；不得用启动时大范围更新代替迁移。
- `pyproject.toml`、`constants.py`、双扩展清单、安装器、启动器和发行脚本的版本必须一致。
- 安装器不得覆盖 IDM 已有的其他杀毒软件路径；备份、恢复和删除必须校验归属。
- 发行包不得包含开发机数据、配对令牌、网站规则、任务记录、用户路径或外置源码。
- 微信视频号捕获默认关闭，只能由用户明确启动；代理、证书和敏感会话必须按租约安全恢复与清理。
- 视频号当前项不得按最新候选猜测；原画不得用转码内容冒充，代理与敏感会话必须安全恢复和清理。具体身份、画质、回退和验收边界唯一维护在 `docs/WECHAT_CHANNELS.md`。
- VPN/PAC 上游无法安全解析时必须在改写 Windows 代理前停止。
- GPL 对应源码、固定上游源码、版权、许可证和构建信息必须保留并与二进制发行同时可得。
- 修改行为后同步 README、ACCEPTANCE、TASKS、STATUS 和相关当前文档。
- 自动测试入口见 `DEVELOPMENT.md`；提交前运行全部 unittest、扩展测试、JavaScript 语法检查和双清单 JSON 解析。

## 当前文档

- 产品说明：`README.md`
- 项目上下文：`CONTEXT.md`
- 当前状态：`STATUS.md`
- 当前任务：`TASKS.md`
- 验收标准：`ACCEPTANCE.md`
- 架构：`docs/ARCHITECTURE.md`
- 安装与回滚：`docs/INSTALLATION_AND_ROLLBACK.md`
- 视频号实现、故障与验收：`docs/WECHAT_CHANNELS.md`
- 开发与发行：`DEVELOPMENT.md`
- 上游来源：`docs/UPSTREAM_PROVENANCE.md`
