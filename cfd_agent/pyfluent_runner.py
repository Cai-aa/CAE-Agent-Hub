"""Offline UAV external-flow orchestrator for Ansys Fluent/PyFluent.

The UI never changes CORE_RULES.  This module is intentionally usable without
the web viewer so it can be packaged with PyInstaller for Windows.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

CORE_RULES = {
    "axis": "X nose-forward, Y starboard, Z down",
    "domain": "inlet 10L, lateral/top/bottom 10B",
    "growth_rate": 1.2,
    "trailing_edge_mm": (0.5, 2.0),
    "surface_mm": (3.0, 5.0),
    "farfield_mm": (2.0, 15.0),
    "boundary_layers": 10,
    "boundary_growth": 1.2,
    "quality": {"max_skewness": 0.85, "min_orthogonal_quality": 0.2, "max_aspect_ratio": 20.0},
    "max_mesh_retries": 3,
    "turbulence": "k-omega SST",
    "residual_target": 1e-5,
}


@dataclass
class CaseParameters:
    velocity_mps: float = 22.0
    angle_of_attack_deg: float = 3.0
    sideslip_deg: float = 0.0
    density_kg_m3: float = 1.225
    viscosity_pa_s: float = 1.7894e-5
    reference_area_m2: float = 0.42
    angles_deg: tuple[float, ...] = (-4.0, 0.0, 3.0, 6.0, 9.0)


class FluentRunner:
    """Owns one visible Fluent session and the project artefacts."""

    def __init__(self, project_dir: Path, fluent_command: str = "fluent"):
        self.project_dir = project_dir
        self.fluent_command = fluent_command
        self.process: subprocess.Popen[str] | None = None
        self.log = logging.getLogger("fluent-runner")

    def start_visible_fluent(self) -> None:
        """Start Fluent with a GUI; no hidden/background-only fallback is allowed."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [self.fluent_command, "3ddp", "-g", "-i", str(self.project_dir / "setup.jou")],
            cwd=self.project_dir,
            text=True,
        )
        self.log.info("Fluent GUI started with pid=%s", self.process.pid)

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def write_manifest(self, params: CaseParameters) -> None:
        (self.project_dir / "logs").mkdir(exist_ok=True)
        (self.project_dir / "results").mkdir(exist_ok=True)
        (self.project_dir / "reports").mkdir(exist_ok=True)
        (self.project_dir / "mesh").mkdir(exist_ok=True)
        (self.project_dir / "project.json").write_text(
            json.dumps({"parameters": asdict(params), "core_rules": CORE_RULES, "created_at": time.time()}, indent=2),
            encoding="utf-8",
        )

    def validate_mesh(self, skewness: float, orthogonal_quality: float, aspect_ratio: float) -> bool:
        limits = CORE_RULES["quality"]
        return (
            skewness <= limits["max_skewness"]
            and orthogonal_quality >= limits["min_orthogonal_quality"]
            and aspect_ratio <= limits["max_aspect_ratio"]
        )

    def run(self, params: CaseParameters) -> None:
        self.write_manifest(params)
        self.start_visible_fluent()
        try:
            self.log.info("Visible Fluent session is ready; execute setup and solve journal.")
            # Real installation-specific commands belong in setup.jou. Keeping
            # the process visible is a hard requirement of this orchestrator.
            if self.process:
                self.process.wait()
        finally:
            self.stop()


def parse_angles(value: str) -> tuple[float, ...]:
    angles = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not angles or any(not math.isfinite(angle) or abs(angle) > 20 for angle in angles):
        raise ValueError("攻角列表必须为逗号分隔的有限数值，且绝对值不超过 20°。")
    return angles


def load_parameters(path: Path) -> CaseParameters:
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return CaseParameters(
        velocity_mps=float(raw.get("velocity_mps", 22)),
        angle_of_attack_deg=float(raw.get("angle_of_attack_deg", 3)),
        sideslip_deg=float(raw.get("sideslip_deg", 0)),
        density_kg_m3=float(raw.get("density_kg_m3", 1.225)),
        viscosity_pa_s=float(raw.get("viscosity_pa_s", 1.7894e-5)),
        reference_area_m2=float(raw.get("reference_area_m2", 0.42)),
        angles_deg=parse_angles(str(raw.get("angles_deg", "-4,0,3,6,9"))),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline UAV Fluent/PyFluent runner")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--fluent", default=os.environ.get("FLUENT_COMMAND", "fluent"))
    parser.add_argument("--parameters", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    params = load_parameters(args.parameters) if args.parameters else CaseParameters()
    runner = FluentRunner(args.project, args.fluent)
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(stop_signal, lambda *_: runner.stop())
    try:
        runner.run(params)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logging.exception("CFD run failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
