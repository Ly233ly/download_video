# 1.4.4 发布验证报告

验证日期：2026-07-28

## 发布范围

- Windows Per-Monitor DPI 下使用点值字体和统一逻辑尺寸，避免 4K/200% 显示器整体过小。
- 媒体任务、视频号候选和 IDM 记录改为有界分页投影，完整事实仍保存在数据库或候选注册表中。
- 浏览器与视频号计划共用 `MediaCoordinator` 和 `download_plans`，桌面窗口通过计划变更通知立即投影新任务。
- 视频号证书预检移出 Tk 主线程；桌面与扩展补齐只删除终态记录的安全清理入口。

## 自动与性能验证

- 194 项 Python 回归通过。
- 6 组 Node 逻辑回归、全部活动扩展 JavaScript 语法和 Chrome/Firefox 双清单解析通过。
- 500 条 IDM、200 条媒体、200 条视频号基准：窗口初始化约 0.34 秒，媒体刷新约 0.08 秒，视频号刷新约 0.03 秒；单页最多投影 80、12、12 个控件行/卡片。
- 250 ms 慢证书查询下，“开始捕获”Tk 回调在 100 ms 内返回。
- [冻结运行时证据](evidence/frozen-runtime-1.4.4.json)：健康版本 1.4.4、schema 6、扩展协议 1、`desktop_ffmpeg`、FFmpeg/ffprobe、yt-dlp/Deno 和 IDM 接收模式通过。
- [隔离安装器证据](evidence/installer-1.4.4.json)：全新安装、成功升级、故障注入回滚和卸载通过。

## 视觉与本机覆盖

- 900×600 的[媒体任务](visual-qa/1.4.4/media-900x600.png)、[视频号](visual-qa/1.4.4/wechat-900x600.png)和 [IDM](visual-qa/1.4.4/idm-900x600.png)均保留分页、清理和状态动作，未出现工具栏或列表溢出。
- 当前电脑已从 1.4.3 使用正式 `--update` 覆盖到 1.4.4。健康门返回 schema 6、扩展协议 1、`mediaReady=true`、`youtubeResolverReady=true`、`desktop_ffmpeg` 和有效视频号桥哈希。
- 安装扩展清单为 1.4.4；覆盖前后 `%LOCALAPPDATA%\IdmEagleAutoImport\bridge.db` 均为 290,816 字节，SHA-256 均为 `75bbbe802878baf98d131183caa119372675201fcb5035ac38dfd9d1eb93eb19`，程序备份目录已正常清理。

## 发行物与稳定更新门

- ZIP：`download-transfer-station-1.4.4-windows-x64.zip`
- 字节数：155,798,415
- SHA-256：`22aea58bf80aa8d7939165da3f1ac882db02b83bd10c5ce390149a8490f27b46`
- 标签：`v1.4.4-rc.1`
- Release：<https://github.com/Ly233ly/download-for-eagle/releases/tag/v1.4.4-rc.1>
- 本机和默认项目路径均没有客户端现有公钥对应的 `secrets/update-signing-private.xml`。发行候选可上传完整 ZIP 与 SHA-256 文件，但不得生成伪签名、替换客户端公钥或把无签名清单推广到稳定自动更新通道。
- 恢复原离线私钥后，必须针对最终 ZIP 生成并反向验签 `update.json`，再创建稳定 `v1.4.4`；在此之前 A240 和任务 122 保持部分完成。
