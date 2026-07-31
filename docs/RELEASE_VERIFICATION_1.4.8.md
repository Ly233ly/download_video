# 1.4.8 发布验证报告

日期：2026-07-31

## 结论

1.4.8 修复 1.4.7 引入的启动后主窗口无响应（卡死）问题，已作为 GitHub 正式稳定版发布，并通过正式升级流程覆盖当前电脑。源码、标签、GitHub Release、更新清单、发行包和本机安装版本一致；用户数据库、浏览器配对和原有记录均完整保留。

## 卡死问题与修复

- 根因：`_apply_windows_dark_title_bar` 调用 `window.update_idletasks()`，该方法同步处理所有待定 Tk 回调，与 `_DynamicWrapLabel` 的 `<Configure>` 换行刷新互相触发，形成不收敛循环，UI 主线程永不空闲，窗口显示 Not Responding。
- 修复：移除该 `update_idletasks()` 调用并注释原因，`winfo_id()` 仍能取得有效句柄，深色标题栏功能保留。
- 复现与验证：修复前启动 10 秒后窗口 Not Responding，CPU 持续空转（25 秒约 13.8 秒）；修复后主窗口模式与 `--external-tray` 托盘模式均响应正常，CPU 长时间稳定（主窗口 20 秒仅 0.06 秒，托盘实例 35 秒零增长）。

## 自动回归

- Python 全量回归：239/239 通过；正式构建过程中再次执行并通过。
- 数据库结构：6；浏览器扩展协议：1。

## 发行包

- 文件：`download-transfer-station-1.4.8-windows-x64.zip`
- 大小：155,873,181 字节
- SHA-256：`d29a75459b377e94f1c27d1dc7e933f295fbba00b70a8523ac76dce7816f8ebe`
- PyInstaller：6.21.0
- FFmpeg：8.1.2
- yt-dlp：2026.06.09
- Deno：2.8.1

`update.json` 已用项目公钥验证签名有效，`sha256` 与本地 ZIP 一致，`size` 与本地 ZIP 一致。

## GitHub 发布

- 正式发行：[v1.4.8](https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.8)
- GitHub `releases/latest` 已指向 v1.4.8。
- 发行状态不是草稿或预发布。
- 发布正文直接读取 [RELEASE_NOTES_1.4.8.md](RELEASE_NOTES_1.4.8.md)。

## 当前电脑覆盖升级

- 安装目录：`C:\Users\Administrator\AppData\Local\IDM-Eagle自动导入助手`
- 在线健康接口返回 version 1.4.8，schema 6、扩展协议 1、媒体工具与 YouTube 解析器就绪。
- 安装版启动器与冻结后端正常运行；窗口标题“下载中转站 v1.4.8”，主窗口响应正常。
- 数据库 `integrity_check=ok`，用户数据完整保留：`settings=4`、`site_rules=3`、`imported_fingerprints=55`、`source_events=288`。

final result: passed
