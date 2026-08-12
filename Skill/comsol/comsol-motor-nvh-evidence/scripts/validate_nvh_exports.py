from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise ValueError(f"{label} contains no data rows")
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")


def finite_float(value: str, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{label} is not finite: {value}")
    return parsed


def validate(eigen_path: Path, campbell_path: Path, pole_count: int) -> dict[str, object]:
    eigen_rows = read_rows(eigen_path)
    campbell_rows = read_rows(campbell_path)
    require_columns(eigen_rows, {"mode", "frequency_hz"}, "eigenfrequency CSV")
    require_columns(campbell_rows, {"rpm", "harmonic", "frequency_hz", "spl_db"}, "Campbell CSV")

    modes = [
        {
            "mode": int(row["mode"]),
            "frequency_hz": finite_float(row["frequency_hz"], "mode frequency"),
        }
        for row in eigen_rows
    ]
    mode_frequencies = [row["frequency_hz"] for row in modes]
    if any(value <= 0 for value in mode_frequencies):
        raise ValueError("all eigenfrequencies must be positive")
    if mode_frequencies != sorted(mode_frequencies):
        raise ValueError("eigenfrequencies must be ascending")

    points: list[dict[str, float | int]] = []
    keys: set[tuple[float, int]] = set()
    max_frequency_error = 0.0
    for row in campbell_rows:
        rpm = finite_float(row["rpm"], "rpm")
        harmonic = int(row["harmonic"])
        frequency = finite_float(row["frequency_hz"], "excitation frequency")
        spl = finite_float(row["spl_db"], "SPL")
        key = (rpm, harmonic)
        if key in keys:
            raise ValueError(f"duplicate Campbell point: rpm={rpm}, harmonic={harmonic}")
        keys.add(key)
        expected_frequency = rpm * pole_count * harmonic / 120.0
        frequency_error = abs(frequency - expected_frequency)
        max_frequency_error = max(max_frequency_error, frequency_error)
        nearest_index = min(range(len(mode_frequencies)), key=lambda idx: abs(mode_frequencies[idx] - frequency))
        points.append(
            {
                "rpm": rpm,
                "harmonic": harmonic,
                "frequency_hz": frequency,
                "spl_db": spl,
                "nearest_mode": modes[nearest_index]["mode"],
                "modal_gap_hz": abs(mode_frequencies[nearest_index] - frequency),
            }
        )

    if max_frequency_error > 1e-6:
        raise ValueError(f"Campbell frequency relation failed; maximum error is {max_frequency_error:.9g} Hz")

    closest = sorted(points, key=lambda point: point["modal_gap_hz"])[:10]
    peak = max(points, key=lambda point: point["spl_db"])
    speeds = sorted({point["rpm"] for point in points})
    harmonics = sorted({point["harmonic"] for point in points})

    return {
        "status": "PASS",
        "pole_count": pole_count,
        "mode_count": len(modes),
        "campbell_point_count": len(points),
        "speed_count": len(speeds),
        "speeds_rpm": speeds,
        "harmonics": harmonics,
        "maximum_frequency_relation_error_hz": max_frequency_error,
        "peak_spl_point": peak,
        "closest_modal_intersections": closest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate COMSOL PM-motor NVH mode and Campbell CSV exports.")
    parser.add_argument("--eigenfrequencies", type=Path, required=True)
    parser.add_argument("--campbell", type=Path, required=True)
    parser.add_argument("--pole-count", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate(args.eigenfrequencies, args.campbell, args.pole_count)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
