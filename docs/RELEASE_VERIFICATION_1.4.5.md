# 1.4.5 发布验证报告

验证日期：2026-07-29

## 结论

1.4.5 已通过源码回归、长列表压力、视觉检查、冻结运行时、安装器事务、稳定更新签名和当前电脑覆盖验证。当前电脑正在运行 1.4.5；启动器、冻结后端和 Chrome 扩展清单与发行包逐字节一致，原任务、浏览器配对和数据库逻辑记录均已保留。

1.4.4 确实曾覆盖安装，但它只把字体从负像素改成了近似大小的正点值，在 1920×1080/96 DPI 上视觉变化很小，并混用了 Segoe UI 与 OPPOSans B/H 中文粗体。1.4.5 根据这张真实失败截图重新定义了显示比例、字体族、字重、字号、行高和文字对比度，不把“版本号已更新”当作界面修复已完成。

## 自适应界面

- 有效比例取 Windows DPI 比例与相对 1920×1080 的屏幕像素比例较大值，不叠乘：1080p/100% 为 100%，1440p/100% 约为 133%，4K/100% 为 200%。
- 正文基准为 11pt，普通、强调和粗体统一使用微软雅黑 UI 与真实字重。
- 导航、按钮、徽章、列表行高、主分栏和弱化文字对比度使用同一有效比例。
- IDM 长字段按当前字体和列宽做像素级省略；完整值保留在详情区。
- 已安装版本的非激活窗口截图：[1920×1080 实机安装版](visual-qa/1.4.5/installed-1920x1080.png)。
- 视觉矩阵：[媒体 1120×720](visual-qa/1.4.5/media-1120x720.png)、[视频号 1120×720](visual-qa/1.4.5/wechat-1120x720.png)、[IDM 1120×720](visual-qa/1.4.5/idm-1120x720.png)、[媒体 900×600](visual-qa/1.4.5/media-900x600.png)、[视频号 900×600](visual-qa/1.4.5/wechat-900x600.png)、[IDM 900×600](visual-qa/1.4.5/idm-900x600.png)、[设置 900×600](visual-qa/1.4.5/settings-900x600.png)、[诊断 900×600](visual-qa/1.4.5/diagnostics-900x600.png)。

所有页面均保留可达的垂直滚动，不出现工具栏横向溢出；列表摘要省略不影响详情中的完整信息。

## 性能与行为回归

- 236 项 Python 通过、2 项按环境设计跳过；20 个专项子场景通过。
- 6 组 Node 回归：通过。
- 活动扩展 JavaScript `node --check` 与 Chrome/Firefox 双清单 JSON：通过。
- 三列表初始化：约 0.343 秒。
- 200 条媒体任务刷新：平均约 0.063 秒。
- 200 条视频号候选刷新：平均约 0.033 秒。
- 500 条 IDM、200 条媒体、200 条视频号全量刷新：约 0.112 秒。
- 同一时刻控件投影上限：IDM 80、媒体 12、视频号 12。

浏览器与视频号任务继续统一进入桌面下载任务事实源；视频号证书预检不占用 Tk 主线程；桌面三个列表和浏览器扩展都只清理终态记录，不停止活动任务、不删除下载文件或 Eagle 内容。

## 发行与安装器

- 最终冻结运行时证据：[release-final-frozen-runtime-evidence.json](performance/release-final-frozen-runtime-evidence.json)：健康版本 1.4.5、schema 6、扩展协议 1、FFmpeg/ffprobe、yt-dlp/Deno、视频号桥和 IDM 接收均通过。
- 最终隔离安装器证据：[release-final-installer-evidence.json](performance/release-final-installer-evidence.json)：全新安装、覆盖更新、注入失败回滚和卸载恢复均通过。
- 发行文件：`download-transfer-station-1.4.5-windows-x64.zip`
- 字节数：`155857576`
- SHA-256：`c5bd1287d0d52f14fe3476fd114dde088e78a1dd7988884c62f189c80142b13f`
- 稳定发行：[v1.4.5](https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.5)
- 发行提交：`ee1bf964ab15487edf8385a590f473d1a1392068`
- GitHub 端 ZIP 状态为 `uploaded`，远端字节数与 SHA-256 和本机一致。
- GitHub `releases/latest` 指向 v1.4.5；同一发行包含经原私钥签署并由客户端内置公钥复验通过的 `update.json`。

## 当前电脑覆盖证据

- 健康接口返回 `version=1.4.5`、`databaseSchema=6`、`extensionProtocol=1`、`mediaReady=true`、`youtubeResolverReady=true`、`downloadEngine=desktop_ffmpeg`。
- 已安装产品版本为 `1.4.5.0`。
- 已安装启动器、冻结后端和 Chrome 扩展清单的 SHA-256 均与发行包相同。
- 覆盖前已在 `%LOCALAPPDATA%\IdmEagleAutoImport\backups` 创建数据库备份；覆盖后 `integrity_check=ok`、schema 6、配对状态和各业务表记录数与覆盖前一致。
- 安装目录没有残留 `.update-backup`。
- 首次覆盖因旧后端退出超时返回失败，安装事务已自动回滚；确认旧进程退出后的第二次覆盖成功，证明正式环境也走通了失败可恢复路径。

## 稳定自动更新边界

`v1.4.5` 已替换 GitHub 的稳定 `latest`。发布用离线私钥只保存在本机忽略目录，没有提交到 Git；`update.json` 已使用该私钥签署，并由客户端内置公钥、版本号、下载地址、字节数和 SHA-256 完整复验。Chrome 扩展文件已随安装目录替换；受 Chrome 保护页限制，当前已打开的浏览器进程需要重启 Chrome，或由用户在 `chrome://extensions` 点击一次“重新加载”，才会立即启用新 service worker。
