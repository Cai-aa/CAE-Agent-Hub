# 实时共享桌面 / Live shared Desktop

桌面与 MPh thin client 必须连接同一个 `comsolmphserver`，并附着完全相同的模型标签。`Model1` 与 `model1` 不同；同名 MPH 加载两次仍是两个模型。独立 standalone 模式不会同步到桌面。

Desktop and MPh must share one server and the exact same model tag. Tags are case-sensitive. Loading a file twice creates separate models. Standalone mode does not synchronize with Desktop.

## 启动 / Start

在本 MCP 目录用安装了 MPh 的 Python 执行。Windows 启动器需要正常用户桌面/注册表访问权限；沙箱拦截时使用宿主审批机制。

Run from this MCP directory using Python with MPh installed. Windows launchers require normal Desktop/registry permissions; use host approval if sandboxed.

```powershell
python -m tools.shared_desktop --port 2036
```

可加 `--open-file <模型副本.mph>`，先在共享桌面加载工程后再附着 API。已有共享桌面时使用 `--no-desktop`，避免启动第二个 GUI；切换 GUI 前先从原 GUI 正常保存并断开。桌面和服务器使用独立的 configuration/workspace，减少启动状态冲突。

Use `--open-file <model-copy.mph>` to load in Desktop before attaching the API. If a shared Desktop is already running, use `--no-desktop` instead of launching a second GUI. Save and disconnect the old GUI before switching. Desktop has a separate configuration/workspace from the server.

运行目录默认 `comsol_runs/shared_desktop/`，已被 Git 忽略。服务器、桌面与 bridge 使用相同的 `preferences` 目录。认证由 COMSOL 的 `-login auto` 管理；不要提交或展示 `login.properties`。`--no-desktop` 仅启动/复用服务器，不停止已有进程。

The ignored runtime directory contains private preferences, authentication, logs and scripts. Server, Desktop and bridge use the same preferences directory. COMSOL manages authentication with `-login auto`. Never commit/display `login.properties`. `--no-desktop` starts/reuses the server without stopping other processes.

通过已有 `comsol_start_bridge_tool` 启动返回的 `bridge_command`，cwd 为本目录。选定准确的模型标签后，命令可加 `--model-tag Model1`：

Use the existing `comsol_start_bridge_tool` with the returned bridge command and this directory as cwd. Add the exact model tag after selecting it:

```powershell
python -u -m tools.shared_bridge --host 127.0.0.1 --port 2036 --prefs-dir <runtime>/preferences --script-root <runtime>/scripts --model-tag Model1
```

此 bridge 独立运行，避开 standalone JVM 不能切换客户端模式的限制。全局 Codex 配置不变；旧的 `*_session_tool` 会话与共享 bridge 彼此独立。

The isolated bridge avoids MPh's one-JVM mode restriction. Global Codex configuration is unchanged; legacy session tools operate independently.

## 模型附着与 MCP / Attach and control

1. `comsol_bridge_ping_tool`：核对 `mode=shared-server`、`standalone=false`、端口及模型标签 / Check actual shared state.
2. `comsol_list_shared_models_tool`：列出服务器模型 / List server tags.
3. `comsol_attach_shared_model_tool(model_tag)`：附着桌面正在显示的准确标签 / Attach the Desktop model.
4. 原有参数、求解、求值、导出、保存工具继续操作该模型 / Existing parameter, solve, evaluate, export and save tools use it.
5. `comsol_run_shared_script_tool(path)`：运行已审阅的本地 `run(context)` 脚本 / Run a reviewed local API script.

若 API 先创建模型，在桌面“文件 > COMSOL Multiphysics 服务器 > 从服务器导入 App”选择相同标签。也可直接附着桌面创建的空模型，或在连接服务器的桌面打开 MPH 后查询实际标签；不要再载入第二份文件。

For an API-created model, use File > COMSOL Multiphysics Server > Import Application from Server. Alternatively attach a Desktop-created empty model, or open an MPH in the connected Desktop and discover its tag. Do not load another file copy.

新增工具需要宿主重新加载 MCP 才会显示；已有 bridge/参数/求解工具当前即可使用。新增工具可以通过独立 MCP stdio 客户端验证，不能把代码注册等同于当前聊天工具已刷新。

New tool names require an MCP host reload. Existing bridge tools work immediately. Verify new registrations with a fresh real MCP client; registration code alone does not refresh the current chat.

## 分阶段演示 / Staged demo

复制 `examples/shared_live_geometry.py` 和 `examples/shared_live_physics_mesh.py` 到 runtime/scripts，在专用空模型上依次执行，观察组件/几何、材料/固体传热/网格/研究节点，再调用 `comsol_run_study_tool(study_tag="std1")`。预设 20×10×5 mm 铝块、0.2 W、h=15 W/(m^2·K)、25 °C。此为连接演示，与原散热片工程分开。

Copy the two examples into runtime/scripts, execute them on a dedicated empty shared model, observe the tree, then solve std1. The aluminum block is a small connectivity demonstration separate from the heatsink engineering model.

脚本须为 script-root 内 `.py` 并定义 `run(context)`，context 包含真实 model/client/model_tag。每阶段返回 JSON 回读。脚本拥有 Python/Java API 能力，需先审阅；路径限制不是完整 Python 沙箱。

Scripts must be .py files inside script-root, defining run(context), returning JSON readback. Context includes the real model/client/tag. Review scripts before executing; the path restriction is not a complete Python sandbox.

断开共享 bridge 仅 disconnect，不 clear/remove。停止 API 客户端后须回读桌面模型仍存在。保存必须给明确输出路径；创建模型遇到已有标签会拒绝覆盖。

Shared disconnect never clears/removes models. Verify the Desktop model survives disconnect. Saving requires an explicit path and creation refuses an existing tag.

模型树同步不是逐帧动画；需选中相关几何、网格或图组才能看到图形。长求解时界面可能忙碌，bridge 使用 10 秒 ServerBusyHandler。求解成功仍须非空解和有效结果证明。

bridge IPC 默认超时为 120 秒，可通过 `COMSOL_MCP_BRIDGE_TIMEOUT` 调整以适应长求解。超时后只结束 API worker，防止过期回复污染后续请求，不会清空或终止共享服务器；应先检查服务器/桌面，再重新附着，避免盲目重复求解。

IPC requests default to 120 seconds, configurable with `COMSOL_MCP_BRIDGE_TIMEOUT` for long solves. A timeout terminates only the API worker so a late reply cannot poison future requests. Inspect Desktop/server state before reattaching; do not blindly rerun a study.

Tree synchronization is not frame-by-frame animation. Select the relevant geometry, mesh or plot group. Long solves may keep Desktop busy; a 10-second ServerBusyHandler coordinates requests. A nonempty solution and valid results remain required.

官方说明 / Official documentation:

- [Shared model](https://doc.comsol.com/6.4/doc/com.comsol.help.llmatlab/llmatlab_ug_model.6.09.html)
- [Windows server/client commands](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_ref_running.38.31.html)
