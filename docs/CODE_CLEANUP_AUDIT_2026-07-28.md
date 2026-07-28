# 全仓无用代码与资源清理审计（2026-07-28）

## 结论

本轮覆盖 Python 桌面/后端、Chrome/Firefox 扩展 JavaScript 与 CSS、视频号 bridge、C# 启动器/安装器、打包入口和发行资源。

删除标准是：全仓无引用、没有清单/反射/事件/打包入口、已有正式实现替代，并能通过自动测试证明删除后行为不变。无法仅靠静态引用证明无用的兼容迁移、安全门禁和外部入口均保留。

## 已删除

### Python

- 旧版 `SiteRulesWindow` 独立网站规则弹窗；正式设置页已经完整替代。
- 旧版 `ProxySettingsWindow` 独立网络弹窗；正式设置 > 网络页已经完整替代。
- 上述旧弹窗的实例字段、打开方法和退出清理分支。
- 未使用的 `_VerticalScrolledFrame.scroll_to_top`。
- 未使用的 `SPACING` 设计令牌和 `APP_NAME` 常量。
- 未使用的 `Database.fingerprint_exists` 与 `Database.job_status_counts`；现有流程分别使用 `fingerprint_owner` 和 `ui_snapshot`。
- 未使用的 `decrypt_chunks` 包装函数及其 `Iterable` 导入。
- `updater.py` 未使用的 `sys` 导入。

### 视频号 bridge 与本机代理

- 从未有正式调用方的 `WechatChannelsCaptureService.send_command`。
- 从未有正式调用方的代理命令队列、`/poll` 长轮询端点和 `enqueue_command`。
- 页面 bridge 中对应的 100ms 轮询及动态 `eval` 执行分支。

当前视频号按钮继续通过 objectId/variantId 的受控候选提交接口创建统一媒体计划，不依赖上述旧命令通道。

### 浏览器扩展

- 未使用的 `parseBareRange`。
- 未使用的 `selectedRawItems`。
- 未使用的 `.bridge-header-divider` CSS 选择器。

### 资源

- 删除仓库根目录 60 个与包内资源完全相同、且没有任何入口引用的重复 UI 图标。
- 包内 60 个状态图标按真实引用裁剪为 21 个，删除 39 个从未加载到任何控件的组合状态。
- 产品图和 21 个实际使用图标继续由 package-data 与 PyInstaller 打包。

## 明确保留

- 数据库 schema 迁移和旧任务兼容逻辑：它们由历史数据触发，不能用当前调用次数判断。
- 安装器中的旧文件/旧快捷方式清理：覆盖安装和卸载仍需要。
- 原生托盘事件、单实例、更新回滚和 IDM hook：属于外部进程入口。
- HTTP handler 的 `server_version` 等框架反射属性。
- `third_party` 固定上游源码和许可材料：属于发布合规证据，不是运行时废代码。
- 测试夹具与视觉截图：不进入正式运行时，但属于确定性回归证据。

## 静态复核结果

- Python 无剩余未使用 import 候选。
- Python 无剩余仅定义一次且无引用的顶层函数、类、方法或模块常量候选。
- 活动扩展 CSS 无剩余未引用 class 选择器。
- 活动扩展 JavaScript 只保留一个有意命名的返回函数 `updateState`；它由 `createStateUpdateQueue` 返回并被调用，不是废代码。
- C# 启动器与安装器保持现有编译和发行入口。

## 防回归

- 测试禁止旧桌面弹窗类重新出现。
- 测试禁止恢复仓库根重复图标目录。
- 测试禁止视频号 bridge 恢复 `/poll` 和 `eval`。
- 测试禁止本机代理恢复 `enqueue_command`。
- UI 包资源测试继续确认正式产品图、导航图标和动作图标可加载。

## 验证与安装

- 187 项 Python unittest：通过。
- 6 组 Node 前端逻辑测试：通过。
- 17 个活动扩展 JavaScript 和视频号 bridge 语法：通过。
- Chrome / Firefox 两份活动清单 JSON：通过。
- PyInstaller、桌面启动器、IDM hook 和一键安装器重新构建：通过。
- 冻结发行载荷确认只包含 21 个实际使用图标，视频号 bridge 不含 `/poll` 或 `eval`。
- 当前电脑已静默覆盖安装；安装目录后台程序与发行包 SHA-256 一致。
- 安装后健康状态为 `version=1.4.1`、`databaseSchema=6`、`mediaReady=true`、`downloadEngine=desktop_ffmpeg`。
- 本轮 ZIP SHA-256：`88795dfdad5c017a58a36c30322be8e95c9fdb7b9f60cf257f848b6e0db646d0`。
