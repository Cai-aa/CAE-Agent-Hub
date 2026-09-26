# ANSA MCP Bridge 下载 / Downloads

## 最新界面补丁 / Latest UI patch: 0.5.1

[便携安装包 / Portable package](ANSA_MCP_Bridge-0.5.1-release/ANSA_MCP_Bridge-0.5.1.bpkg)
修复 Runtime 内容撑大侧栏宽度的问题；安装后重启 ANSA。实际停靠拖动效果尚待确认。
详见 [0.5.1 改动与验证边界 / validation limits](../RELEASE_0.5.1.md)。

This Runtime-only update adds scroll containment, compact tabs and wrapped details.
Restart ANSA after installation. Displayed dock resizing remains unverified.
The package is portable and contains no credentials. Hash: [SHA256SUMS](SHA256SUMS).

## 历史版本 / Previous release: 0.5.0

## 中文

- **第三方用户**：[release 便携包](ANSA_MCP_Bridge-0.5.0-release/ANSA_MCP_Bridge-0.5.0.bpkg)。不绑定个人目录，需要按 [中文安装指南](../README.zh-CN.md) 先安装外部 MCP、生成共享认证配置，并让 ANSA 与 MCP 使用同一份配置。
- **原工作站升级**：[upgrade 本机包](ANSA_MCP_Bridge-0.5.0-upgrade/ANSA_MCP_Bridge-0.5.0.bpkg)。这是用户指定的原始本机升级文件，字节保持不变；内置配置定位入口为 `E:\Users\Cai\Documents\ANSAMCP\ansa_plugin\ansa_mcp_plugin.py`，**其他电脑优先使用 release 包**。该路径不是认证令牌。
- 两个包都不包含认证配置或令牌。不要把 `bridge.json`、运行日志或模型文件提交到 GitHub。

在 ANSA 中打开 **Development → BETA Packager Installer → Installer**，选择对应 `.bpkg`，安装到 **Your .BETA plugins directory**。保存模型并重启 ANSA，然后使用 **Plugins → ANSA MCP → Start**。升级后也重启外部 MCP 服务，使用认证状态查询确认 Runtime 0.5.0。插件入口持久保存，桥服务仍须由 Start 启动。

Windows ANSA 25.1.2 已做过原生/GUI/MCP 验证；其他版本待实测。详见 [0.5.0 验证及限制](../RELEASE_0.5.0.md)。API 执行成功不代表工程验证通过。

## English

Use the **release** package for third-party Windows installations. Follow the
[setup guide](../README.md) to install the external MCP process and create the
shared authentication configuration first. The **upgrade** package is the
original workstation-specific artifact, published unchanged at the owner's
request; it embeds the entry path shown above and is not the default for other
computers. Neither package includes authentication credentials.

Install through **Development → BETA Packager Installer → Installer**, choosing
**Your .BETA plugins directory**. Save the model, restart ANSA and the external
MCP, then select **Plugins → ANSA MCP → Start**. Verify Runtime 0.5.0 through an
authenticated query. Only Windows ANSA 25.1.2 has native validation evidence;
other versions remain unverified. Operation completion is not engineering approval.

## SHA-256

Expected hashes are in [SHA256SUMS](SHA256SUMS). From this directory:

```powershell
Get-FileHash .\ANSA_MCP_Bridge-0.5.0-upgrade\ANSA_MCP_Bridge-0.5.0.bpkg -Algorithm SHA256
Get-FileHash .\ANSA_MCP_Bridge-0.5.0-release\ANSA_MCP_Bridge-0.5.0.bpkg -Algorithm SHA256
```

The two packages bundle the same 10 runtime modules. Build logs, local profiles,
generated models, historical package candidates and authentication configuration
are intentionally excluded from this repository payload. Local test-report paths
in the release notes identify development evidence, not downloadable artifacts.
