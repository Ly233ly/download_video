# 上游来源与对应源码

本文件记录当前发行所需的来源和许可证信息。

## cat-catch

- 项目：`xifangczy/cat-catch`
- 固定版本：`2.7.1`
- 固定提交：`7a77612b3e2a01cedacae6e43eb88a89eee3034f`
- 来源：<https://github.com/xifangczy/cat-catch/tree/7a77612b3e2a01cedacae6e43eb88a89eee3034f>
- 许可证：GNU GPL v3

固定对应源码、原许可证、主说明、变更记录和第三方库许可表保存在 `third_party/cat-catch/source/`。该目录只用于版权、对应源码和审计，不由活动浏览器清单加载。

当前活动扩展保留由本项目继续维护的媒体发现与内容适配代码；上游完整 popup、图标、下载页、解析页、录制工具、在线 FFmpeg、移动 UA、密钥面板和浏览器库不进入运行时。

因此当前组合发行继续采用 GPL-3.0，并保留固定上游源码、版权通知、修改范围和构建材料。

## ltaoo/wx_channels_download

- 项目：`ltaoo/wx_channels_download`
- 来源：<https://github.com/ltaoo/wx_channels_download>

该项目只用于研究用户可观察的微信视频号交互链路。本项目没有复制、修改或分发其 Go/JavaScript、SunnyNet、Gopeed、证书、图标、UI、构建产物或 `WechatSphDecrypt` 源码。

当前证书、回环代理、feed 规范化、候选、下载、流式处理和 UI 均由本项目按照自身安全边界独立实现。ISAAC-64 依据 Bob Jenkins 的公共领域算法说明独立实现，并以测试向量验证。

该外部仓库不是当前发行组件，不进入安装包第三方组件清单。

## yt-dlp 与 Deno

- yt-dlp：`2026.06.09` Windows x64 官方发行文件
- Deno：`2.8.1` Windows x64 官方运行时
- 固定版本、下载地址和 SHA-256：`media-tools/YOUTUBE-RESOLVER-VERSION.json`
- 可复现获取脚本：`packaging/Fetch-YouTube-Resolver.ps1`
- yt-dlp 对应源码：`third_party/yt-dlp/yt-dlp-2026.06.09-source.tar.gz`

yt-dlp 与 Deno 用于本机页面格式解析，不增加逐站远程下载服务。许可证和第三方通知随二进制发行提供。

## FFmpeg

- 固定版本和 SHA-256：`media-tools/FFMPEG-VERSION.json`
- 可复现获取脚本：`packaging/Fetch-FFmpeg.ps1`
- 许可证：见 `licenses/FFMPEG-GPL-3.0.txt` 和安装包第三方通知

FFmpeg 与 FFprobe 只在本机执行下载、合并、封装和校验。
