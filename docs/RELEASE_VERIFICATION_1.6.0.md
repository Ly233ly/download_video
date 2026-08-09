# 1.6.0 发布验证

验证日期：2026-08-09

## 发行载荷

- Windows ZIP：`liudi-downloader-1.6.0-windows-x64.zip`
- ZIP 大小：`147722068` 字节。
- ZIP SHA-256：`2064d4d266d81594a41c070b772d6f04474473b4d3e971a0f2c00f10181503bf`。
- 内嵌安装器 SHA-256：`0f9a59a50c2f5f3b142674987e64fd87c931b36bc1b7fc9a9adab248487f4198`。
- 对应源码 ZIP：`liudi-downloader-1.6.0-source.zip`，大小 `8430128` 字节，SHA-256 `4859bf5d897b9292e668c835409c601b1a60ec2aa78b576d3ef8a3a162511fa5`。
- 用户 ZIP 只包含单文件内嵌安装器、使用说明、许可、二进制清单和源码获取说明。
- 用户 ZIP 不包含外置 `app`、项目源码、构建脚本或 source map；运行载荷禁止文件扫描为 0。
- 当前对应源码：<https://github.com/Ly233ly/download_video>
- 数据库结构：6
- 扩展协议：1

## 自动验证

- Python：347/347 通过。
- Node：6 组扩展逻辑测试通过。
- 活动扩展 JavaScript 语法与 Chrome、Firefox 双清单解析通过。
- 桌面 UI：79/79 通过，并人工检查亮色、深色主要页面与首次绘制截图。
- 后端：208/208 定向测试通过。
- 留底桌面启动器与留底安装器 C# 编译通过。
- PyInstaller 6.21.0 冻结运行时、隔离安装器的新装、覆盖升级、故障回滚和卸载全部通过。
- 冻结运行时报告 FFmpeg、FFprobe、yt-dlp、Deno 就绪，视频号捕获默认关闭。

## 本机覆盖安装

- 注册表 `DisplayVersion`、健康接口和后台文件版本均为 1.6.0。
- 后台标题为 `留底下载器 v1.6.0 by阿毅i`。
- 健康接口报告媒体和 YouTube 解析工具就绪，视频号捕获为关闭状态。
- 数据库 `integrity_check` 为 `ok`，结构版本为 6。
- 覆盖安装前后均为 31 条下载计划、0 条 IDM 任务、4 条网站规则和 4 条设置，用户数据得到保留。
- 安装目录不存在更新备份残留。

## 缓存清理

- 应用缓存清理 2 个预览文件，共释放 61888 字节；清理后应用缓存为 0。
- 项目构建与测试缓存共 5256 个文件、835130765 字节，已移入回收站。
- `.build-tools`、`.scratch`、`build`、`dist`、`.pytest_cache` 和全部 `__pycache__` 复查为 0 个残留。
- 发行 ZIP、源码 ZIP、CodeGraph 索引和用户数据库未作为缓存删除。

## 发布说明

- GitHub 仓库：<https://github.com/Ly233ly/download_video>
- GitHub Release：<https://github.com/Ly233ly/download_video/releases/tag/v1.6.0>
- 仓库通过 Git LFS 保存 Windows ZIP、源码 ZIP 和单文件安装器；Release 附带两个 ZIP 与各自校验文件。
- 普通 GitHub Release 不依赖更新签名私钥。
- 当前环境缺少既有 RSA 更新签名私钥，因此本次不生成 `update.json`；这只影响旧客户端的自动更新提示，不影响安装包下载、覆盖安装或 GitHub Release。
