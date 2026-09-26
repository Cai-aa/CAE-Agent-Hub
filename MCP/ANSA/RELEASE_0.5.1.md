# ANSA MCP Bridge Runtime 0.5.1 — 2026-09-26

## 中文

本次为 Runtime 界面补丁，外部 MCP 工具接口及求解功能不变（外部服务版本仍为 0.5.0）。

- 用原生可伸缩滚动区域隔离内容的最小宽度约束，窄面板可横向滚动查看完整内容。
- 记录、模型、诊断页签采用短标题，双语名称保留在悬停提示中。
- 只读详情编辑器按可用宽度换行；320 像素是初始尺寸，不是固定最小宽度。
- 停止桥接按钮保留在滚动内容之外；认证配置、模型和桥接生命周期不变。

[下载便携安装包](dist/ANSA_MCP_Bridge-0.5.1-release/ANSA_MCP_Bridge-0.5.1.bpkg)，
SHA-256 见 [校验清单](dist/SHA256SUMS)。通过 Development → BETA Packager Installer →
Installer 安装；保存模型并重启 ANSA，再选择 Plugins → ANSA MCP → Start。
仅 Stop/Start 不足以清除缓存模块。本包不含认证配置和个人入口路径。

验证：针对性测试 18 项通过；完整 Python 测试 241 项通过，2 个第三方依赖弃用警告。
ANSA 25.1.2 官方打包成功；原生隐藏窗口构建成功。
**隐藏窗口尺寸测试不能证明停靠拖动效果**：后续显示窗口对比未返回，MCP 报告
OUTCOME_UNKNOWN，未重复该测试。实际停靠拖动下限仍待安装后验证，且受 ANSA
和同组其他面板影响；其他 ANSA 版本未验证。本次验证未执行模型修改。

## English

Runtime-only UI patch; external MCP tools and solver functionality are unchanged
(the external server remains version 0.5.0).

- A native resizable scroll area isolates content minimum-size hints; narrow panels
  retain full content through horizontal scrolling.
- Compact tabs retain bilingual tooltips; read-only detail editors wrap to width.
- 320 pixels is an initial size, not a fixed minimum. Stop remains outside the
  scrolling content. Authentication and bridge lifetime behavior are unchanged.

Install the portable package linked above through BETA Packager Installer. Save
your model, restart ANSA, then choose Plugins → ANSA MCP → Start. Stop/Start alone
does not clear cached Python modules. No credentials or personal entry path are bundled.

Validation: 18 focused tests and 241 full-suite tests passed, with two third-party
deprecation warnings. Official ANSA 25.1.2 packaging and hidden-window construction
succeeded. **Displayed dock drag behavior remains unverified**: the subsequent
shown-window comparison did not return and reported OUTCOME_UNKNOWN; it was not
retried. Other dock tabs may impose independent limits. Other ANSA versions remain
unverified. No model modification was performed by this validation.
