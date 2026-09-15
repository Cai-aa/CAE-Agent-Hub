# FluentOps 离线运行器

`pyfluent_runner.py` 是界面之外的本地编排入口。它会为每次工况创建独立工程目录，写入固定规范清单，并以可见 GUI 模式启动 `fluent 3ddp -g`。停止时只终止自己持有的 Fluent 进程，不会静默伪造求解结果。

在 Windows 上执行 `scripts\build-offline-cfd.ps1` 可生成桌面 `zhinengti\4\FluentOps` 源码包；安装 PyInstaller 后同一脚本会输出 `FluentOps.exe`。Ansys Fluent 与合法本地许可证必须由用户自行安装，软件不包含 Ansys 二进制或许可证。
