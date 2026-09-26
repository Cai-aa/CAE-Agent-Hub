# ANSA MCP Bridge 0.5.1 — Windows 通用运行时

0.5.1 修复侧栏无法进一步收窄的问题：内容放入可伸缩滚动区域，窄宽度下
可水平滚动查看完整内容；记录/模型/诊断采用短标签（悬停显示双语名称），
详情文本按可用宽度换行。320 像素为初始窗口尺寸，不是固定最小宽度；
实际停靠下限仍受 ANSA 和同组其他面板影响。安装此界面补丁后重启 ANSA。

新版安装、操作和兼容边界见 [通用指南](GENERAL_OPERATIONS.md) 和 [工程操作](ENGINEERING_OPERATIONS.md)。
第三方分发包不写个人 bridge_entry，ANSA 与 MCP 通过 ANSA_MCP_BRIDGE_CONFIG 指向同一配置。
升级后重启 ANSA 和 MCP，以刷新 Runtime 和客户端工具列表。

本包提供 Plugins 页的 Start / Status / Stop 按钮及新版 Runtime。
它复用现有 bridge 配置和认证，不包含令牌，不会在安装时启动桥。
仅本机专用包的 `manifest.json` 中 `bridge_entry` 非空，需要保留该入口目录。

## 修复内容

- 连接/会话概览：监听状态与最近认证请求分开显示，显示 ANSA、Runtime
  版本、PID、Deck、文件和运行时间；会话信息每 5 秒刷新，不遍历模型。
- 记录页保留最近 100 次认证请求，显示耗时、执行结果和可点击的参数/返回摘要。
  失败、结果不确定、幂等缓存返回分别标记；只读请求也会记录。
- 模型页提供手动统计，以及修改操作前后 GRID/NODE、单元、面、属性、材料数量
  差值。大模型可关闭自动统计；不同文件/Deck 不计算可误解的差值。
- 诊断页提供会话读取自检、复制诊断和导出 JSON。导出位于配置的第一个
  allowed_roots 下的 diagnostics 文件夹，每次生成新文件。
- 包内携带 Runtime 代码；分发包直接读取配置，本机专用包借原桥接入口定位配置。

- `.ppl` 通过全局变量保留插件元数据；ANSA v25.1.2 的
  `session.setPluginInfos` 不增加该对象的引用计数，临时对象会提前释放。
- ANSA 原生加载的按钮入口不使用 `from __future__`，通过标准 Python
  导入机制加载桥接模块，避免 ANSA 注入代码后的 future-import 编译错误。
- `.ppl` 和 `ANSA_MCP_Bridge` 目录采用相对路径，可一起移动。

## 推荐：官方 BETA Package 安装

1. 在 ANSA 中打开 **Development > BETA Packager Installer > Installer**。
2. 选择本次发布的 `ANSA_MCP_Bridge-0.5.1.bpkg`。
3. 安装位置选择 **Your .BETA plugins directory**，完成安装。
4. 保存模型并重启 ANSA，在 **Plugins > ANSA MCP** 中使用 Start / Status / Stop。
   升级时不能只点击 Stop/Start，Python 可能缓存旧模块。安装器若提示替换同名
   ANSA MCP 插件，确认替换本插件即可，不要删除其他插件或用户设置。

官方安装器负责解包并登记到 Plugin Manager。一次安装后，后续启动自动加载
插件入口；桥接服务本身仍由 Start 启动。若当前图形会话尚未刷新入口，先重启，
不要覆盖安装器写入的设置。需要使用插件时保留现有桥接目录。

## 备选：原生目录包安装

解压完整 ZIP 到一个固定的用户目录，保持 `.ppl` 和同名文件夹并列。
在 ANSA 的 Development > Plugin Manager > Add
选择新的 `ANSA_MCP_Bridge.ppl`，勾选 Active，Apply，然后保存 ANSA GUI Settings。
关闭并重新打开 ANSA，检查 Plugins 页的 ANSA MCP 组。
目录必须保留；以后无需每次 Load Script。

Start 在当前 ANSA 会话打开桥控制面板，Status 只读状态，Stop 停止桥。
Start 不会自动对模型执行操作。关闭桥控制面板也会停止桥。

不要使用旧的 `output/plugin_candidate` 中的候选；只使用本包的 `.ppl`。

## 边界与隐私

没有新增暂停、强制中断、回滚或自动求解能力。主线程长操作运行期间，面板也可能
暂时无法重绘；请将 AI 工作流拆成短 MCP 调用。界面不虚构百分比。
“已返回”仅代表 API 返回；刷新请求、数量变化、模型质量、求解成功是不同的证据。
数量不变不代表几何或属性未改动。采样失败显示不可用，不按零处理。
历史仅驻留当前进程；重启清空，需要留存时手动导出。
Python 源码仅保存哈希和长度，任意 Python 返回值不进入面板日志。认证密钥及
常见凭据字段会脱敏；文件路径和普通参数仍可包含业务信息，分享前请人工检查。
此 UI 不限制任意 Python 的本机权限，也不替代工程人员复核。

## MCP 客户端

沿用原有 MCP 注册与 bridge.json，不需要修改端口、令牌或重新注册客户端。
Runtime 0.5.0 沿用认证协议；重启 MCP 服务并重新加载工具清单，默认显示 18 个通用工具，24 个具名操作。
