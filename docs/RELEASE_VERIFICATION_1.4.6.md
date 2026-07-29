# 1.4.6 发布验证报告

验证日期：2026-07-29

## 结论

1.4.6 重新发布 1.4.5 的完整性能与可靠性修复，并把 GitHub 发布说明改为从仓库内 UTF-8 Markdown 文件读取，避免中文再次被命令行编码转换为问号。程序功能、数据库结构和扩展协议保持兼容。

## 自动回归

- 238 项 Python 测试执行成功。
- 6 组 Node 回归执行成功。
- Chrome/Firefox 扩展 JavaScript 语法和双清单校验通过。
- 安装器全新安装、覆盖升级、注入失败回滚和卸载恢复通过。
- 冻结运行时健康检查、IDM 接收、FFmpeg/ffprobe、yt-dlp/Deno 和视频号桥通过。

证据：

- [安装器事务](performance/release-1.4.6-installer-evidence.json)
- [冻结运行时](performance/release-1.4.6-frozen-runtime-evidence.json)

## 正式包

- 文件：`download-transfer-station-1.4.6-windows-x64.zip`
- 字节数：`155857874`
- SHA-256：`ba1a7b49facd6f0fbc2b9c7960cc8e0f8ae2b908aa85fb51878b7f02b225093c`
- PyInstaller：6.21.0
- FFmpeg：8.1.2
- yt-dlp：2026.06.09
- Deno：2.8.1

## 更新与发布说明

- `update.json` 使用维护者离线私钥签署，并已由客户端内置公钥反向验证。
- 从 1.4.5 检查时可识别 1.4.6；从 1.4.6 检查时不会重复提示。
- 发布说明源文件为 [RELEASE_NOTES_1.4.6.md](RELEASE_NOTES_1.4.6.md)，UTF-8 解码通过，未包含乱码问号序列。
