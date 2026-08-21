# 1.6.3 发布验证

更新时间：2026-08-22（Asia/Shanghai）

## 当前结论

1.6.3 已正式发布，本机覆盖、公共资产重新下载和更新器端到端验证全部通过。标签 `v1.6.3` 固定到提交 `0730ae89b66db6f1b9a36bdb2957ca053a4eabc7`，GitHub 发布时间为 2026-08-22 00:37:57（Asia/Shanghai）。

本版把自动更新从遗失私钥所阻塞的 RSA `update.json` 迁移到固定 GitHub Releases API。1.6.2 无法自动识别新机制，用户需要手动覆盖安装一次 1.6.3；从 1.6.3 开始才支持后续正式版本的 GitHub 自动更新。

## 发布门禁

- [x] 版本源、安装器、启动器、扩展清单和文件资源全部为 1.6.3。
- [x] 377 项 Python、6 组 Node、17 个活动 JavaScript、双清单和构建门禁全部通过。
- [x] 冻结运行时、隔离新装、覆盖升级、模拟失败回滚和卸载通过。
- [x] 本机从 1.6.2 后台覆盖到 1.6.3；数据库 SHA-256 保持 `3411D89F1A3B33A3F11BB547E6B4F47DD62085F6D325595EA01FEE065082A2C5`，41 条计划、48 条任务、8 条设置、3 条网站规则及系统直连状态保持。
- [x] 独立验收代理已复核更新信任边界、最终发行产物和本机安装，发布前复核通过。
- [x] 源码提交、标签 `v1.6.3` 和正式 GitHub Release 完成。
- [x] Windows ZIP、源码 ZIP 和两份 SHA-256 文件从公共地址重新下载并复算一致。
- [x] 公共 API 端到端验证：1.6.2 能发现 1.6.3、安全下载和解压唯一根目录安装器；1.6.3 检查结果为最新版。

## 发行资产

以下是从公共 GitHub Release 重新下载后复算一致的正式校验值。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `liudi-downloader-1.6.3-windows-x64.zip` | 147,272,131 | `20488A30027B59738CB3E72E7664DA07DF767516EB373E795EC29CDF5BE37F49` |
| `liudi-downloader-1.6.3-source.zip` | 16,639,534 | `F07E0DF9A5AFC482D26F098C05A1235C721B5DB05464B46FEC7341BB9F8BE206` |

本地单文件安装器为 147,756,032 字节，SHA-256 为 `9D89DCB4CED1EE9D834F6CAF3F2B312171CE68CBB3882E6BAFB6FC9F512BDA4F`。最终构建后端与已安装后端 SHA-256 均为 `12134F4B1C62E1380E8653086D2AA6DA6B3F02C37825F08225A53840A95988FE`。

## 公共发布复核

- 正式页：<https://github.com/Ly233ly/download_video/releases/tag/v1.6.3>
- GitHub API 返回 `draft=false`、`prerelease=false`，4 个资产均为 `uploaded`；Windows ZIP 资产 ID 为 `523987701`，源码 ZIP 资产 ID 为 `523987703`。
- 4 个公开资产重新下载后，字节数和 GitHub `digest` 与本页校验值一致；两份校验文件的内容也与实际 ZIP 一致。
- 用新更新器从公共 API 检查 `1.6.2`，实际下载 147,272,131 字节的 Windows ZIP，完成哈希校验和安全解压；提取的唯一安装器大小与 SHA-256 均与本地正式产物一致。
- 用当前版本 `1.6.3` 检查同一公共 API，返回已是最新版本。

## 更新安全边界

- 只读取 `https://api.github.com/repos/Ly233ly/download_video/releases/latest`，禁止元数据跳转。
- 只接受非草稿、非预发布、严格 `vX.Y.Z` 且高于当前版本的 Release。
- Windows 资产必须唯一、状态为 uploaded，并同时匹配固定名称、资产 API 地址、公开下载地址、正数大小和 GitHub `sha256`。
- 资产下载只允许 GitHub API 直接返回，或一次跳转到 `release-assets.githubusercontent.com` 的 HTTPS 443 地址。
- 实际下载需匹配响应大小、Release 大小和 SHA-256；失败清理临时文件。
- ZIP 拒绝路径穿越、绝对/盘符/UNC 路径、Windows 保留名、符号链接、大小写冲突、文件目录冲突、异常文件数/大小/压缩比以及多个或深层安装器。

## GitHub 账号边界

不再需要或保存 RSA 更新私钥。相应取舍是更新安全依赖 GitHub 账号与仓库发布权限：维护者应开启两步验证或通行密钥，并只给必要人员发布权限。视频号捕获证书的 RSA 逻辑与自动更新无关，仍然保留。
