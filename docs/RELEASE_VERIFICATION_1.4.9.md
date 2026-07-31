# 1.4.9 发布验证报告

日期：2026-07-31

## 结论

1.4.9 修复视频号捕获的代理恢复逻辑缺陷，已作为 GitHub 正式稳定版发布，并通过正式升级流程覆盖当前电脑。源码、标签、GitHub Release、更新清单、发行包和本机安装版本一致；用户数据库、浏览器配对和原有记录均完整保留。

## 修复内容

- **系统代理被外部禁用但残留本机地址时无法恢复**：`release()` / `recover_orphan()` 原要求 `ProxyEnable=1` 才视为本实例接管；当其他程序把 `ProxyEnable` 改为 0 但 `ProxyServer` 仍残留本实例 endpoint 时，恢复被拒绝，捕获停止报“系统代理已被其他程序修改”。现识别“owned but disabled”状态并安全恢复快照。
- **“修复代理冲突”对禁用状态无作为**：系统代理禁用时 `upstream_http_proxy` 返回 None，修复直接报“未发现需要修复的系统代理”。现在会解析残留 `ProxyServer`，若为失效 loopback 代理则清除并重置状态。
- **needs_recovery 永久卡死**：`start()` 恢复失败时只要当前没有正在运行的其他系统代理（`ProxyEnable=0`），允许重置状态并重新捕获，不再需要重启程序。

## 自动回归

- Python 全量回归：243/243 通过（新增 4 项：release 禁用恢复、recover_orphan 禁用恢复、start 重置 needs_recovery、repair 清理禁用残留）。
- 既有环境敏感测试已改为 mock 端口可达性，不再依赖本机 127.0.0.1:7890 端口状态。
- 数据库结构：6；浏览器扩展协议：1。

## 发行包

- 文件：`download-transfer-station-1.4.9-windows-x64.zip`
- 大小：155,874,999 字节
- SHA-256：`ffecc0cf89f30285fc01c78237c1d785a6a247ea134c80d3b8b66c6737b63f88`
- PyInstaller：6.21.0
- FFmpeg：8.1.2
- yt-dlp：2026.06.09
- Deno：2.8.1

`update.json` 已用项目公钥验证签名有效，`sha256` 与本地 ZIP 一致，`size` 与本地 ZIP 一致。

## GitHub 发布

- 正式发行：[v1.4.9](https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.9)
- GitHub `releases/latest` 已指向 v1.4.9。
- 发行状态不是草稿或预发布。
- 发布正文直接读取 [RELEASE_NOTES_1.4.9.md](RELEASE_NOTES_1.4.9.md)。

## 当前电脑覆盖升级

- 安装目录：`C:\Users\Administrator\AppData\Local\IDM-Eagle自动导入助手`
- 在线健康接口返回 version 1.4.9，schema 6、扩展协议 1、媒体工具与 YouTube 解析器就绪。
- 安装版启动器与冻结后端正常运行；窗口标题“下载中转站 v1.4.9”，主窗口响应正常。
- 数据库 `integrity_check=ok`，用户数据完整保留：`settings=4`、`site_rules=3`、`imported_fingerprints=57`、`source_events=288`。

final result: passed
