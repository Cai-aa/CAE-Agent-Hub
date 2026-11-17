"""Build a read-only, paged Abaqus history query for the CAE kernel."""

import json


def history_query(
    odb_path: str, step_name: str, region_name: str, variable: str, offset: int, limit: int
) -> str:
    for label, name in (
        ("odb_path", odb_path), ("step_name", step_name),
        ("region_name", region_name), ("variable", variable),
    ):
        if not name.strip():
            raise ValueError(f"{label} must not be empty")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")

    args = json.dumps([odb_path, step_name, region_name, variable, offset, limit])
    return _KERNEL_QUERY + "\nresult = _read_odb_history(" + repr(args) + ")\n"


_KERNEL_QUERY = '''
def _read_odb_history(arguments):
    import json
    import math
    from itertools import islice
    from pathlib import Path
    from odbAccess import openOdb

    odb_path, step_name, region_name, variable, offset, limit = json.loads(arguments)
    if not Path(odb_path).is_absolute():
        raise ValueError("odb_path must be absolute on the Abaqus/CAE host")

    def named(repository, name, label):
        keys = repository.keys()
        if name in keys:
            return repository[name]
        available = list(islice(keys, 20))
        raise KeyError("{} {!r} not found. Available names (up to 20): {}".format(label, name, available))

    odb = openOdb(path=odb_path, readOnly=True)
    try:
        step = named(odb.steps, step_name, "Step")
        region = named(step.historyRegions, region_name, "History region")
        history = named(region.historyOutputs, variable, "History variable")
        if getattr(history, "conjugateData", ()):
            raise ValueError("Complex history is not supported by read_odb_history")
        data = history.data
        total_points = len(data)
        if offset > total_points:
            raise ValueError("offset {} exceeds the series length {}".format(offset, total_points))
        stop = min(offset + limit, total_points)
        points = []
        for index in range(offset, stop):
            x, y = data[index]
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError("Non-finite history data at sample {}".format(index))
            points.append([x, y])

        return {
            "step": step_name,
            "region": region_name,
            "variable": variable,
            "domain": str(step.domain),
            "total_points": total_points,
            "offset": offset,
            "points": points,
            "next_offset": stop if stop < total_points else None,
        }
    finally:
        odb.close()
'''
