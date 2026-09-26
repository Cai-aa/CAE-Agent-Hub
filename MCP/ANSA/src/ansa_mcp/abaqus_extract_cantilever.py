"""Read an Abaqus ODB for the fixed cantilever demo; run by Abaqus Python."""

from __future__ import print_function

import json
import os
import sys


def main():
    from odbAccess import openOdb

    run_dir = os.path.abspath(sys.argv[-1])
    odb_path = os.path.join(run_dir, "cantilever.odb")
    report_path = os.path.join(run_dir, "results.json")
    odb = openOdb(odb_path, readOnly=True)
    try:
        step = list(odb.steps.values())[-1]
        frame = step.frames[-1]
        u = frame.fieldOutputs["U"]
        rf = frame.fieldOutputs["RF"]
        s = frame.fieldOutputs["S"]

        # ANSA may renumber entities during import/export, so identify faces
        # from ODB coordinates rather than relying on the original labels.
        fixed_ids = set()
        tip_ids = set()
        for instance in odb.rootAssembly.instances.values():
            for node in instance.nodes:
                key = (instance.name, node.label)
                if abs(node.coordinates[0]) < 1e-5:
                    fixed_ids.add(key)
                if abs(node.coordinates[0] - 200.0) < 1e-5:
                    tip_ids.add(key)
        tip_u3 = [float(v.data[2]) for v in u.values
                  if (v.instance.name, v.nodeLabel) in tip_ids]
        fixed_rf3 = [float(v.data[2]) for v in rf.values
                     if (v.instance.name, v.nodeLabel) in fixed_ids]
        if len(tip_u3) != 15 or len(fixed_rf3) != 15:
            raise RuntimeError("The ODB does not contain all fixed and tip nodes")
        mises = [float(v.mises) for v in s.values if hasattr(v, "mises")]
        if not mises:
            raise RuntimeError("The ODB has no Mises stress values")
        result = {
            "ok": True,
            "step": step.name,
            "frame_count": len(step.frames),
            "tip_u3_average_mm": sum(tip_u3) / len(tip_u3),
            "tip_u3_min_mm": min(tip_u3),
            "tip_u3_max_mm": max(tip_u3),
            "fixed_reaction_z_n": sum(fixed_rf3),
            "maximum_mises_mpa": max(mises),
            "tip_node_count": len(tip_u3),
            "fixed_node_count": len(fixed_rf3),
            "stress_value_count": len(mises),
        }
        with open(report_path, "w") as stream:
            json.dump(result, stream, indent=2)
    finally:
        odb.close()


if __name__ == "__main__":
    main()
