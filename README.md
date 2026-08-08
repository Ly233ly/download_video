# 下载中转站

<p><img src="assets/download-transfer-station.png" width="128" alt="下载中转站图标"></p>

下载中转站是一款 Windows 本机媒体下载工具。它可以从浏览器、微信视频号和 IDM 接收媒体任务，在本机完成下载、音视频合并与校验，并按需导入 Eagle。

当前版本：**1.5.0**

## 主要功能

- 浏览器媒体捕获：识别普通视频、HLS、DASH、分离音视频和可解析的视频页面。
- 清晰度选择：下载前显示标题、预览、媒体类型、画质、音轨和预计输出。
- 微信视频号：支持当前画质、其他实际画质，以及具备有效凭据时的原始视频。
- IDM 自动中转：IDM 下载完成后自动加入处理队列；没有来源网页也可以导入 Eagle。
- Eagle 集成：只调用 Eagle 官方本地 API，支持仅下载、下载并导入、失败后补导。
- 本机处理：FFmpeg、FFprobe、yt-dlp 和 Deno 随安装包提供，不把媒体上传到第三方服务器。
- 系统代理支持：下载任务自动跟随 Windows 系统代理；视频号捕获兼容常见 VPN、PAC/WPAD 和 HTTP/Mixed 代理。

## 下载与安装

[下载 1.5.0 Windows x64 安装包](release/download-transfer-station-1.5.0-windows-x64.zip)

1. 解压 ZIP。
2. 双击 `一键安装.exe`，选择“一键安装”。
3. 安装器会启动下载中转站，并打开浏览器扩展目录。
4. 在 Chrome 或 Edge 的扩展管理页开启“开发者模式”，选择“加载已解压的扩展程序”。
5. 选择安装器打开的 `chrome-extension` 文件夹。

安装包已经包含程序运行所需组件，不需要另外安装 Python、FFmpeg、yt-dlp 或 Deno。

支持 Windows 10/11 x64。Eagle 和 IDM 都是可选软件：不使用 Eagle 时可以只下载文件，不使用 IDM 时仍可通过浏览器和微信视频号创建任务。

## 使用方法

### 浏览器视频

1. 打开并播放目标视频。
2. 点击浏览器工具栏中的“下载中转站”。
3. 在左侧选择媒体，在右侧核对标题、预览和画质。
4. 选择“仅下载”或“导入 Eagle”。
5. 在桌面软件的“下载任务”页面查看进度、停止、重试或打开文件位置。

### 微信视频号

1. 打开桌面软件的“微信视频号”页面。
2. 点击“开始捕获”。首次使用时，阅读提示并自行确认名称为“下载中转站 微信视频号本机捕获根证书”的 Windows 安全警告。
3. 在 Windows 微信客户端打开或重新进入视频号内容并开始播放。
4. 点击视频原操作栏中的“下载”；悬停按钮可以选择其他实际画质或原始视频。
5. 完成选择后可以停止捕获，已经创建的任务会继续运行。

原始视频只有在当前视频提供有效原始访问凭据时才会显示。程序不会把转码地址虚标为原始或最高画质。

### IDM 与 Eagle

- Eagle 正在运行时，下载完成的文件通常会在数秒内导入当前资源库。
- Eagle 没有运行时，任务会保持等待状态；启动 Eagle 后可以自动继续或手动重试。
- 安装器不会覆盖 IDM 已配置的其他杀毒软件路径。
- 用户原下载文件和 IDM 文件不会被移动、删除或修改。
- 只有明确选择“导入成功后删除”，并且 Eagle 已确认导入、文件归属校验通过时，程序才会删除自己创建的本机下载副本。

## VPN 与代理

开启 VPN 后无需先关闭 VPN 再捕获视频号。1.5.0 会保留原有 Windows 代理配置，并将视频号本机捕获代理串联到原 HTTP/Mixed 代理或按 URL 解析 PAC/WPAD。

如果 VPN 只提供 SOCKS 端口，或者 PAC 无法解析，请在 VPN 软件中启用 HTTP/Mixed 端口，并在下载中转站的网络设置中填写该端口。不要把 SOCKS 端口当成 HTTP 代理端口。

停止捕获、退出程序、升级或卸载时，程序只会恢复自己拥有且能够验证的代理设置；其他软件后来修改的设置不会被覆盖。

## 隐私与安全

- 下载、合并、校验和 Eagle 导入全部在本机完成。
- Cookie、签名地址、请求头和视频号解密信息只按当前任务最小化使用，不写入任务数据库或诊断日志。
- 视频号捕获默认关闭，只有用户明确点击“开始捕获”后才会启用。
- 不移动、不修改用户原文件，也不直接修改 Eagle 资源库目录。
- DRM 内容只识别并提示，不提供 DRM 绕过能力。
- 请只下载自己有权保存和使用的内容。

## 1.5.0 更新重点

- 修复微信视频号“原始视频”错误携带转码参数、只能得到低清版本的问题。
- 修复开启 VPN/PAC 后启动视频号捕获导致视频号无法访问的问题。
- 修复浏览器扩展媒体列表较长时，点击底部候选会自动滚回顶部的问题。
- 发布包不再把 Python、C#、PowerShell、构建配置或 source map 作为外置运行文件暴露给普通用户。

## 开发与构建

源码开发需要 Python 3.11+。业务运行时代码保持 Python 标准库零第三方依赖。

运行 Python 测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_*.py" -v
```

构建 Windows 发行包：

```powershell
powershell -ExecutionPolicy Bypass -File packaging/Build-Release.ps1
```

构建脚本会执行测试和发行门禁，并生成内嵌程序载荷的单文件安装器。更完整的环境、测试与打包说明见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 项目文档

- [开发、测试与发行](DEVELOPMENT.md)
- [安装、更新、故障排查与卸载](docs/INSTALLATION_AND_ROLLBACK.md)
- [系统架构](docs/ARCHITECTURE.md)
- [关键决策](docs/DECISIONS.md)
- [微信视频号实现与安全边界](docs/WECHAT_CHANNELS_PLAN.md)
- [当前状态](STATUS.md)

## 许可证

本项目按 [GNU GPL v3](LICENSE) 发布。第三方组件、固定上游来源和对应源码说明见 [COPYING.md](COPYING.md)、[第三方通知](installer/THIRD_PARTY_NOTICES.txt) 与 [上游来源记录](docs/UPSTREAM_PROVENANCE.md)。
