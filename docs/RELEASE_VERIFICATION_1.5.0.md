# 1.5.0 发布验证

验证日期：2026-08-08

## 发行载荷

- ZIP：`download-transfer-station-1.5.0-windows-x64.zip`
- 大小：147690676 字节
- SHA-256：`384cd962cbea6ebfa5032db966f7919d6ad9c3e597d0ac621e2f6476cf411809`
- 用户 ZIP 只包含单文件内嵌安装器、使用说明、许可、二进制清单和源码获取说明。
- 用户 ZIP 不包含外置 `app`、项目源码、构建脚本或 source map。
- 当前对应源码：<https://github.com/Ly233ly/download_video>
- 数据库结构：6
- 扩展协议：1

## 自动验证

- Python：251/251 通过。
- Node：6 组扩展逻辑测试通过。
- 活动扩展 JavaScript 语法与 Chrome、Firefox 双清单解析通过。
- PyInstaller 冻结运行时通过。
- 隔离安装器的新装、覆盖升级、故障回滚和卸载通过。
- 运行载荷扫描不存在 `.py`、`.pyw`、`.cs`、`.ps1`、`.spec`、`.toml` 或 `.map`。
- 17 个扩展 JavaScript 运行文件均已压缩。

## 本机覆盖安装

- 注册表 `DisplayVersion` 与健康接口均为 1.5.0。
- 健康接口报告媒体、YouTube 与桌面 FFmpeg 就绪，视频号捕获默认关闭。
- 数据库 `integrity_check` 为 `ok`，结构版本为 6。
- 设置、网站规则、下载计划、任务和导入指纹均得到保留。
- 启动器、IDM hook、后端、扩展清单和 UI 脚本哈希与发行载荷一致。
- 不存在残留更新备份或视频号代理租约；可信视频号证书得到保留。

## 安装安全门

- 证书命令最长运行 15 秒。
- 安装器等待超过 20 秒会终止清理子进程并中止升级。
- 没有活动捕获租约时不会无条件删除可复用证书。
- 新版本健康检查失败时恢复覆盖前程序目录。

## 发布状态

- 当前源码与 Windows ZIP 已上传到 `Ly233ly/download_video`。
- ZIP 使用 Git LFS 保存。
- 稳定自动更新仍需项目现有 RSA 私钥生成并验证 `update.json`。
- 原私钥恢复前不得生成替代密钥或发布未签名的稳定更新清单。
