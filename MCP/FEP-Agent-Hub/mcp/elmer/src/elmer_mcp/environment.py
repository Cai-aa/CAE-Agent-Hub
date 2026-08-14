from __future__ import annotations

from pathlib import Path
from typing import Any

from open_cae_core.config import OpenCAEConfig
from open_cae_core.discovery import command_version, extract_version, first_executable


def probe_elmer(config: OpenCAEConfig) -> dict[str, Any]:
    base = Path("E:/Elmer/Elmer 26.2-Release/bin")
    solver = first_executable([config.executable("elmer", "solver"), "ElmerSolver.exe", base / "ElmerSolver.exe"])
    grid = first_executable([config.executable("elmer", "grid"), "ElmerGrid.exe", base / "ElmerGrid.exe"])
    gui = first_executable([config.executable("elmer", "gui"), "ElmerGUI.exe", base / "ElmerGUI.exe"])
    solver_mpi = first_executable([config.executable("elmer", "solver_mpi"), "ElmerSolver_mpi.exe", base / "ElmerSolver_mpi.exe"])
    mpiexec = first_executable([config.executable("elmer", "mpiexec"), "mpiexec.exe"])
    gmsh = first_executable(
        [
            config.executable("gmsh", "exe"),
            "gmsh.exe",
            Path("E:/FreeCAD/bin/gmsh.exe"),
        ]
    )
    grid_output = command_version(grid, [])
    gmsh_output = command_version(gmsh, ["--version"])
    version = extract_version(grid_output)
    return {
        "elmer_solver": str(solver) if solver else None,
        "elmer_grid": str(grid) if grid else None,
        "elmer_gui": str(gui) if gui else None,
        "elmer_solver_mpi": str(solver_mpi) if solver_mpi else None,
        "mpiexec": str(mpiexec) if mpiexec else None,
        "gmsh": str(gmsh) if gmsh else None,
        "version_detected": version,
        "gmsh_version": extract_version(gmsh_output),
        "serial_available": bool(solver and grid),
        "mpi_available": bool(solver_mpi and mpiexec),
        "gmsh_available": bool(gmsh),
    }

