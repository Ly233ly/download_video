# 1.4.3 发布验证报告

验证日期：2026-07-28

## 发布范围

- 深色桌面 UI 接入真实数据库、媒体下载、视频号捕获、IDM、设置、诊断和更新服务。
- 恢复按真实状态启用的停止、重试、打开位置、打开来源和补导动作。
- 修正媒体标题单行省略、预览图、视频号捕获控制栏、圆角、滚动条、OPPO Sans 字级和明暗层级。
- 删除未使用的窗口、方法、扩展脚本、样式和重复图标。
- 合并 1.4.2 的更新清单 404 兼容；发行 ZIP 改用 ASCII 文件名，避免 GitHub 上传时截断中文前缀。
- 冻结运行时和隔离安装器脚本动态读取当前版本，不再生成错误的 1.4.0 证据。

## 版本与兼容性

- 产品版本：1.4.3
- SQLite schema：6
- 扩展协议：1
- 下载引擎：`desktop_ffmpeg`
- 用户数据目录：`%LOCALAPPDATA%\IdmEagleAutoImport`，不参与程序目录替换。

## 自动验证

- 188 项 Python 回归通过。
- 6 组 Node 逻辑回归、17 个活动扩展 JavaScript、视频号桥脚本语法和 Chrome/Firefox 双清单解析通过。
- [冻结运行时证据](evidence/frozen-runtime-1.4.3.json)：健康版本 1.4.3、schema 6、扩展协议 1、`desktop_ffmpeg`、FFmpeg/ffprobe、yt-dlp/Deno 与 IDM 接收模式通过。
- [隔离安装器证据](evidence/installer-1.4.3.json)：全新安装、成功升级、故障注入回滚和卸载通过。
- 签名 `update.json` 已使用客户端内置公钥反向验签，版本、ASCII 下载地址、字节数和 SHA-256 一致。

## 发行物

- ZIP：`download-transfer-station-1.4.3-windows-x64.zip`
- 字节数：155,791,883
- SHA-256：`536d65e9789279ff62a1b926b947fadda2d267858d9370af9aa8d0641be9bc2a`
- 标签：`v1.4.3`
- Release：<https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.3>
- 自动更新清单：<https://github.com/Ly233ly/download-for-eagle/releases/latest/download/update.json>
