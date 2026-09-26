# 0.4.0 Windows 发布与验证记录 / Release evidence

Date: 2026-09-25. Scope: generic ANSA automation, not a solver or engineering certification.

## 交付 / Artifacts

- 第三方分发 / portable: [ANSA_MCP_Bridge-0.4.0.bpkg](dist/ANSA_MCP_Bridge-0.4.0-release/ANSA_MCP_Bridge-0.4.0.bpkg)
  SHA256: `5009432ac4c993ccaade65f8cd3b34ed4022f36033ce57be7182e2f14303a938`
- 当前电脑升级 / machine-specific upgrade: [ANSA_MCP_Bridge-0.4.0.bpkg](dist/ANSA_MCP_Bridge-0.4.0-upgrade/ANSA_MCP_Bridge-0.4.0.bpkg)
  SHA256: `db3de63b2db3914d352c19bfd3f6370017eabd31ab42c5661d926ba2ed7808d5`
- 每个目录还包含目录包 ZIP、manifest 和官方打包报告。安装与配置见 [指南](GENERAL_OPERATIONS.md)。
- 旧的 `0.4.0-portable` 是失败候选，不能安装；`portable-final` 为通过测试的代码包，
  `release` 仅进一步更新双语安装说明。两份交付包的全部 9 个 Runtime 源文件哈希均与实测包一致。
- 本机升级包携带现有配置入口路径，但不含令牌，不能作为第三方分发包。

## 已验证 / Verified

- `python -m pytest -q`: **187 passed**, 2 existing Authlib deprecation warnings, no skipped tests.
- Tests cover default 18-tool contract, FastMCP persistent-write forwarding, capability absence,
  strict input validation, session/database/deck preconditions, same-ID replay, post-mutation
  uncertain outcomes, native descriptor lifetime, portable config, and Python3.9 grammar parsing.
- Real host: Windows, ANSA25.1.2, embedded Python3.11.9, disposable GUI PID36172.
- Official package install to isolated profile, restart, native Plugins callback, HMAC-authenticated
  bridge requests, API symbol/docstring lookup, actual entity card field enumeration.
- Created one GRID and verified count delta+1. Created a curve, isolated/hidden/deleted it;
  switched ABAQUS/NASTRAN deck; saved .ansa and reopened it. Seven generic operation calls
  (six distinct operations) plus same-ID replay checks passed.
- Dashboard recorded32 requests. Real checkbox and selection callbacks, diagnostic export,
  intentional Python failure marked OUTCOME_UNKNOWN, bridge shutdown and process exit passed.
- Evidence: `output/general_smoke_040_final/general_operations_report.json`,
  `gui_report.json`, `install_report.json`, logs. These local test directories contain temporary
  credentials and must NOT be distributed. Release archives do not include them.
- User's existing PID41736/session/database were read-only checked and not replaced by the test.

## 未验证与边界 / Not verified

- Solid smoothing and shell reconstruction have offline contract tests and native-symbol probes,
  but no live mesh-quality validation in this release.
- Other ANSA releases, actual Python3.9 execution, other vendor package containers, production
  geometry cleanup and solver/engineering results remain unverified. Grammar parsing is not a
  runtime compatibility proof. Minimum descriptor gate25.0.0 is not certification of all25.x.
- No pixel-level GUI automation was used. Redraw API evidence is not screenshot evidence.
- No new solver was launched, no user model was changed, no installed plugin/config was replaced,
  and no remote repository publication was performed.
- The live test used the authenticated bridge client. Offline FastMCP tests establish tool schema
  and forwarding; the existing MCP server and user's plugin must be restarted/upgraded before
  newly registered tools can be used in the current client.

## 升级 / Upgrade

保存模型后，通过 ANSA 的 BETA Packager Installer 安装本机升级包，重启 ANSA 并点击
Plugins > ANSA MCP > Start。再重启 MCP 服务／重新加载客户端工具，确认 Runtime0.4.0、
默认18个通用工具，并重新读取能力与会话。不要仅凭面板版本号判定连接成功。

Save the model, install the machine-specific upgrade through BETA Packager Installer,
restart ANSA and Start the plugin. Restart the MCP server/tool discovery, then read live
capabilities/session again. Portable third-party installs need their own shared config file.
