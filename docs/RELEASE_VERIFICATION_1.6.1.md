# 1.6.1 发布验证

验证日期：2026-08-11

## 发行载荷

- Windows ZIP：`liudi-downloader-1.6.1-windows-x64.zip`，大小 `147722021` 字节，SHA-256 `ef3501e0da0f5285fc10187eb6047640d243a0587f34039de393450aa78526e7`。
- 内嵌安装器：`留底安装器.exe`，大小 `148182528` 字节，SHA-256 `0a275bfcdfe3c446a80b9ae00175736937cb27f163fe4a07e82dc70812897691`。
- 对应源码 ZIP：`liudi-downloader-1.6.1-source.zip`，大小 `16615174` 字节，SHA-256 `ca1a4367aba8ba3e11d9afbd171c886489a287920f220f2efbd96a6a0f36b77e`。
- 用户 ZIP 只包含单文件内嵌安装器、使用说明、许可、二进制清单和源码获取说明。
- 用户 ZIP 不包含外置项目源码、构建脚本或 source map；运行载荷禁止文件扫描为 0。
- 当前对应源码：<https://github.com/Ly233ly/download_video>
- 数据库结构：6
- 扩展协议：1

## 自动验证

- Python：350/350 通过。
- Node：6 组扩展逻辑测试通过。
- 19 个活动 JavaScript 文件语法与 Chrome、Firefox 双清单解析通过。
- 留底桌面启动器、IDM 接收器和留底安装器 C# 编译通过。
- PyInstaller 6.21.0 冻结运行时验证通过，FFmpeg 8.1.2、yt-dlp 2026.06.09 和 Deno 2.8.1 就绪。
- 隔离安装器的新装、覆盖升级、故障回滚和卸载全部通过。
- 新增视频号乱序预加载回归：歧义卡片拒绝创建任务，媒体路径明确时准确提交当前视频。

## 本机覆盖安装

- 注册表、健康接口、后台文件版本和安装扩展清单均为 1.6.1。
- 后台标题为 `留底下载器 v1.6.1 by阿毅i`。
- 健康接口报告媒体与 YouTube 解析工具就绪，视频号捕获默认关闭。
- 数据库 `integrity_check` 为 `ok`，结构版本为 6。
- 覆盖安装前后均为 31 条下载计划、0 条 IDM 任务、4 条网站规则和 4 条设置，用户数据得到保留。
- 安装目录不存在更新备份残留。

## 发布说明

- GitHub 仓库：<https://github.com/Ly233ly/download_video>
- GitHub Release：<https://github.com/Ly233ly/download_video/releases/tag/v1.6.1>
- 仓库通过 Git LFS 保存 Windows ZIP、源码 ZIP 和单文件安装器；Release 附带两个 ZIP 与各自校验文件。
- 普通 GitHub Release 不依赖更新签名私钥。
- 当前环境缺少既有 RSA 更新签名私钥，因此本次不生成 `update.json`；这只影响旧客户端的自动更新提示，不影响安装包下载、覆盖安装或 GitHub Release。
