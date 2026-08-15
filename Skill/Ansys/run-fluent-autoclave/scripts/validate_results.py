import argparse
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate a Fluent autoclave result JSON.")
    parser.add_argument("results", type=Path)
    parser.add_argument("--max-mass-imbalance-percent", type=float, default=0.5)
    args = parser.parse_args()

    data = json.loads(args.results.read_text(encoding="utf-8"))
    result = data["results"]
    required = [
        "inlet_mass_flow_kg_s", "outlet_mass_flow_kg_s",
        "outlet_area_average_speed_m_s", "outlet_max_speed_m_s",
        "global_max_speed_m_s", "global_max_speed_location_xyz_m",
    ]
    missing = [name for name in required if name not in result]
    if missing:
        raise SystemExit("FAIL missing fields: " + ", ".join(missing))

    inlet = float(result["inlet_mass_flow_kg_s"])
    outlet = float(result["outlet_mass_flow_kg_s"])
    imbalance = abs(inlet + outlet) / max(abs(inlet), 1e-30) * 100.0
    values = [inlet, outlet, result["outlet_area_average_speed_m_s"],
              result["outlet_max_speed_m_s"], result["global_max_speed_m_s"]]
    if not all(math.isfinite(float(value)) for value in values):
        raise SystemExit("FAIL non-finite result value")
    if imbalance > args.max_mass_imbalance_percent:
        raise SystemExit(f"FAIL mass imbalance {imbalance:.6g}%")
    if result["global_max_speed_m_s"] < result["outlet_max_speed_m_s"]:
        raise SystemExit("FAIL global maximum is below outlet maximum")

    print(json.dumps({
        "status": "PASS",
        "mass_imbalance_percent_recomputed": imbalance,
        "outlet_is_not_forced_to_global_maximum": (
            result["outlet_max_speed_m_s"] < result["global_max_speed_m_s"]),
        "global_max_speed_location_xyz_m": result["global_max_speed_location_xyz_m"],
    }, indent=2))


if __name__ == "__main__":
    main()
