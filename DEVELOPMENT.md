# 开发、测试与发行

本文只描述当前开发流程。

## 环境

- Windows 10/11 x64
- Python 3.11+
- Node.js，用于扩展测试和压缩
- .NET/C# 编译环境，用于启动器与安装器
- PyInstaller 和发行脚本声明的固定工具版本

业务运行时代码只使用 Python 标准库。SQLite、Tk、本机 HTTP 和 Eagle API 不引入第三方业务依赖。

## 入口

- 留底桌面端：`src/idm_eagle_bridge/main.py`
- IDM 接收器：`src/idm_eagle_bridge/hook.py`
- 留底浏览器扩展：`chrome-extension/`
- Windows 托盘与启动器：`launcher/Launcher.cs`
- 留底安装器：`installer/Setup.cs`
- PyInstaller 入口：`launcher/assistant.pyw`
- PyInstaller 配置：`packaging/LiudiDownloader.spec`

## 运行测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_*.py" -v
```

扩展逻辑测试：

```powershell
node tests/js/test_youtube.js
node tests/js/test_popup_logic.js
node tests/js/test_candidate_presentation.js
node tests/js/test_auth_race.js
node tests/js/test_bilibili.js
node tests/js/test_wechat_channels_bridge.js
```

提交前还必须检查全部活动 JavaScript 语法，并解析 Chrome、Firefox 两份清单 JSON。

## 当前测试边界

测试覆盖浏览器候选归组、质量选择、滚动位置、SPA/完整文档导航与冷启动清理顺序、认证与断线自动恢复、跨页面异步请求代次、卡住的响应头/正文超时、桌面下载、FFmpeg 合并、输出校验、系统代理、Eagle 可选降级、并发幂等补导、停止与完成竞态、重复内容状态、文件所有权、三重路径删除校验、后台线程异常恢复、健康探测 single-flight、大任务查询索引、缓存统计与安全清理、数据库迁移、Tk UI 键盘焦点、圆角/圆形抗锯齿像素、首次主题初始化、单次主题切换与响应式布局、微信视频号 feed、原始参数、VPN/PAC 上游、证书生命周期和退出恢复顺序。

真实 Chrome 工具栏操作、Windows 证书确认和用户实际 VPN/微信环境仍属于人工复验边界。

## 构建

```powershell
powershell -ExecutionPolicy Bypass -File packaging/Build-Release.ps1
```

构建脚本会：

1. 校验版本同步。
2. 运行 Python、Node、JavaScript 和清单门禁。
3. 构建冻结后端和 Windows 启动器。
4. 压缩浏览器扩展运行文件。
5. 嵌入 FFmpeg、FFprobe、yt-dlp、Deno 和许可证。
6. 构建单文件安装器。
7. 扫描用户载荷，拒绝外置源码、构建配置和 source map。
8. 生成用户 ZIP、哈希和对应源码材料。

发行验证：

```powershell
powershell -ExecutionPolicy Bypass -File packaging/Test-Installer.ps1
powershell -ExecutionPolicy Bypass -File packaging/Test-FrozenRuntime.ps1
```

## 版本规则

以下位置必须保持一致：

- `pyproject.toml`
- `src/idm_eagle_bridge/constants.py`
- `chrome-extension/manifest.json`
- `chrome-extension/manifest.firefox.json`
- 安装器、启动器和发行脚本中的版本资源

数据库结构变化必须使用 SQLite `PRAGMA user_version` 迁移。

## 发行规则

- 用户 ZIP 不包含开发机数据、配对令牌、网站规则、任务记录或用户路径。
- 用户可见载荷不包含外置 Python、C#、PowerShell、spec、TOML 或 source map。
- GPL 对应源码、固定上游源码、构建材料和许可证必须与二进制发行同时可得。
- 稳定更新清单必须使用现有 RSA 私钥签名，并核对 ZIP 大小与 SHA-256。
- 缺少原签名私钥时只能提供手动下载，不得伪造稳定自动更新。
