# 1.4.7 发布验证报告

日期：2026-07-30

## 结论

1.4.7 已作为 GitHub 正式稳定版发布，并通过正式升级流程覆盖当前电脑。源码、标签、GitHub Release、更新清单、发行包和本机安装版本一致；用户数据库、浏览器配对和原有记录均完整保留。

## 自动回归与界面性能

- Python 全量回归：239/239 通过；正式构建过程中再次执行并通过。
- 双主题真实 Tk 截图：通过；原生标题显示“下载中转站 v1.4.7”。
- UI 性能夹具：启动 353.80 ms，热刷新均值 5.28 ms，强制刷新均值 5.79 ms，连续 60 次缩放 88.07 ms，待处理 Tk 回调 0。
- 数据库结构：6；浏览器扩展协议：1。

## 安装器与冻结运行时

- 全新安装：通过。
- 覆盖升级：通过；旧载荷清除，浏览器配对引导安全轮换，临时备份在健康门通过后清除。
- 故障回滚：通过；失败退出码、标记和可执行文件均恢复，临时备份清除。
- 卸载恢复：通过。
- 冻结后端健康检查、IDM 接收、FFmpeg、ffprobe、yt-dlp、Deno 和视频号桥接：全部通过。
- 机器可读证据：
  - [安装器事务](performance/release-1.4.7-installer-evidence.json)
  - [冻结运行时](performance/release-1.4.7-frozen-runtime-evidence.json)

## 发行包

- 文件：`download-transfer-station-1.4.7-windows-x64.zip`
- 大小：155,874,222 字节
- SHA-256：`bca381b8d42122fbf3725d701afe4686329fedde998d7276280a6039045f9172`
- PyInstaller：6.21.0
- FFmpeg：8.1.2
- yt-dlp：2026.06.09
- Deno：2.8.1

GitHub 远端资源状态为 `uploaded`，远端 ZIP 大小与摘要和本地产物一致。`update.json` 的 RSA 签名、UTF-8 中文说明和 Markdown 内容均由 1.4.6 客户端验证通过。

## GitHub 发布

- 正式发行：[v1.4.7](https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.7)
- GitHub `releases/latest` 已指向 v1.4.7。
- 发行状态不是草稿或预发布。
- 发布正文直接读取 [RELEASE_NOTES_1.4.7.md](RELEASE_NOTES_1.4.7.md)，远端中文显示正常。

## 当前电脑覆盖升级

- 安装目录：`C:\Users\Administrator\AppData\Local\IDM-Eagle自动导入助手`
- 注册版本、在线健康接口和已安装扩展版本均为 1.4.7。
- 启动器、IDM 接收器、扩展清单和冻结后端与正式发行载荷的 SHA-256 逐项一致。
- 在线健康：schema 6、扩展协议 1、媒体工具与 YouTube 解析器就绪；启动器和后端均正常运行。
- 升级前后数据库计数完全一致：`imported_fingerprints=38`、`settings=3`、`site_rules=3`、`source_events=415`，其余活动任务表为 0。
- 数据库 `integrity_check=ok`，浏览器配对仍有效。
- 升级前备份：`C:\Users\Administrator\AppData\Local\IdmEagleAutoImport\backups\bridge.db.pre-1.4.7-20260730-094601.bak`
- 备份 SHA-256：`62d35b8bacde084973828e9eddad3113e6fd1cc1a5729ef0f04b68f99c328ea4`
- 正式升级完成后不存在遗留 `.update-backup`。

final result: passed
