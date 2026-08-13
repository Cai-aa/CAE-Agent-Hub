"""Line-delimited JSON worker executed by pvpython.

Only whitelisted ParaView operations are dispatched. stdout is reserved for
protocol responses; diagnostics are written to stderr by the parent process.
"""

from __future__ import annotations

import json
import glob
import math
import os
import sys
import traceback

from paraview.simple import (
    Calculator,
    Clip,
    ColorBy,
    Contour,
    GetActiveViewOrCreate,
    GetAnimationScene,
    GetScalarBar,
    GetColorTransferFunction,
    GetTimeKeeper,
    Glyph,
    Hide,
    OpenDataFile,
    PlotOverLine,
    Render,
    ResetCamera,
    SaveData,
    SaveAnimation,
    SaveScreenshot,
    SaveState,
    Show,
    Slice,
    StreamTracer,
    Threshold,
    WarpByVector,
)


PROXIES = {}
ALIASES = {}
COUNTERS = {}
VIEW = GetActiveViewOrCreate("RenderView")


def new_id(kind):
    COUNTERS[kind] = COUNTERS.get(kind, 0) + 1
    return "%s_%03d" % (kind, COUNTERS[kind])


def resolve(value):
    proxy_id = ALIASES.get(value, value)
    if proxy_id not in PROXIES:
        raise KeyError("Unknown proxy: %s" % value)
    return proxy_id, PROXIES[proxy_id]


def array_records(info):
    records = []
    for index in range(info.GetNumberOfArrays()):
        array = info.GetArray(index)
        components = array.GetNumberOfComponents()
        component_range = array.GetRange(-1 if components > 1 else 0)
        records.append(
            {
                "name": array.Name,
                "components": components,
                "range": [float(component_range[0]), float(component_range[1])],
                "finite": all(math.isfinite(float(value)) for value in component_range),
            }
        )
    return records


def inspect_proxy(proxy):
    proxy.UpdatePipeline()
    info = proxy.GetDataInformation()
    timesteps = list(getattr(proxy, "TimestepValues", []) or [])
    if not timesteps:
        timesteps = list(getattr(GetTimeKeeper(), "TimestepValues", []) or [])
    return {
        "dataset_type": info.GetDataClassName(),
        "bounds": [float(value) for value in info.GetBounds()],
        "points": int(info.GetNumberOfPoints()),
        "cells": int(info.GetNumberOfCells()),
        "point_arrays": array_records(proxy.GetPointDataInformation()),
        "cell_arrays": array_records(proxy.GetCellDataInformation()),
        "time_steps": [float(value) for value in timesteps],
    }


def require_array(proxy, association, name):
    info = proxy.GetPointDataInformation() if association.upper() in ("POINTS", "POINT_DATA") else proxy.GetCellDataInformation()
    names = list(info.keys())
    if name not in names:
        raise ValueError("Array %s not found in %s; available=%s" % (name, association, names))


def open_dataset(params):
    path = params["path"]
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    proxy = OpenDataFile(path)
    if proxy is None:
        raise RuntimeError("ParaView could not create a reader")
    proxy.UpdatePipeline()
    proxy_id = new_id("dataset")
    PROXIES[proxy_id] = proxy
    alias = params.get("alias")
    if alias:
        ALIASES[alias] = proxy_id
    Show(proxy, VIEW)
    return {"id": proxy_id, "alias": alias, "path": path, "inspection": inspect_proxy(proxy)}


def create_filter(params):
    source_id, source = resolve(params["input"])
    kind = params["filter_type"].lower()
    values = params.get("parameters", {})
    if kind == "slice":
        proxy = Slice(Input=source)
        proxy.SliceType = "Plane"
        proxy.SliceType.Origin = values.get("origin", [0, 0, 0])
        proxy.SliceType.Normal = values.get("normal", [1, 0, 0])
    elif kind == "clip":
        proxy = Clip(Input=source)
        proxy.ClipType = "Plane"
        proxy.ClipType.Origin = values.get("origin", [0, 0, 0])
        proxy.ClipType.Normal = values.get("normal", [1, 0, 0])
        proxy.Invert = int(bool(values.get("invert", False)))
    elif kind == "contour":
        array = values["array"]
        association = values.get("association", "POINTS")
        require_array(source, association, array)
        proxy = Contour(Input=source)
        proxy.ContourBy = [association, array]
        proxy.Isosurfaces = values.get("values", [values.get("value", 0.0)])
    elif kind == "glyph":
        array = values["array"]
        association = values.get("association", "POINTS")
        require_array(source, association, array)
        proxy = Glyph(Input=source, GlyphType="Arrow")
        proxy.OrientationArray = [association, array]
        proxy.ScaleArray = [association, array]
        proxy.ScaleFactor = float(values.get("scale_factor", 1.0))
    elif kind == "stream_tracer":
        array = values["array"]
        association = values.get("association", "POINTS")
        require_array(source, association, array)
        proxy = StreamTracer(Input=source, SeedType="Point Cloud")
        proxy.Vectors = [association, array]
    elif kind == "warp":
        array = values["array"]
        association = values.get("association", "POINTS")
        require_array(source, association, array)
        proxy = WarpByVector(Input=source)
        proxy.Vectors = [association, array]
        proxy.ScaleFactor = float(values.get("scale_factor", 1.0))
    elif kind == "threshold":
        array = values["array"]
        association = values.get("association", "POINTS")
        require_array(source, association, array)
        proxy = Threshold(Input=source)
        proxy.Scalars = [association, array]
        if "range" in values:
            proxy.LowerThreshold = float(values["range"][0])
            proxy.UpperThreshold = float(values["range"][1])
    elif kind == "calculator":
        proxy = Calculator(Input=source)
        proxy.ResultArrayName = values["result_array"]
        proxy.Function = values["function"]
    elif kind == "plot_over_line":
        proxy = PlotOverLine(Input=source)
        proxy.Point1 = values["point1"]
        proxy.Point2 = values["point2"]
        proxy.Resolution = int(values.get("resolution", 200))
    else:
        raise ValueError("Unsupported filter type: %s" % kind)
    proxy.UpdatePipeline()
    proxy_id = new_id(kind)
    PROXIES[proxy_id] = proxy
    alias = params.get("alias")
    if alias:
        ALIASES[alias] = proxy_id
    Hide(source, VIEW)
    Show(proxy, VIEW)
    return {"id": proxy_id, "alias": alias, "input": source_id, "filter_type": kind, "inspection": inspect_proxy(proxy)}


def color_by(params):
    proxy_id, proxy = resolve(params["proxy"])
    association = params.get("association", "POINTS")
    array = params["array"]
    require_array(proxy, association, array)
    display = Show(proxy, VIEW)
    ColorBy(display, (association, array))
    display.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(VIEW, True)
    lut = GetColorTransferFunction(array)
    preset = params.get("preset")
    if preset:
        lut.ApplyPreset(preset, True)
    scalar_bar = GetScalarBar(lut, VIEW)
    scalar_bar.Title = "Temperature (K)" if array.lower() == "temperature" else array
    scalar_bar.ComponentTitle = ""
    scalar_bar.Orientation = "Horizontal"
    scalar_bar.WindowLocation = "Upper Right Corner"
    scalar_bar.TitleFontSize = 10
    scalar_bar.LabelFontSize = 9
    scalar_bar.ScalarBarLength = 0.33
    scalar_bar.ScalarBarThickness = 16
    Render(VIEW)
    return {"proxy": proxy_id, "array": array, "association": association, "preset": preset}


def scalar_range(params):
    _, proxy = resolve(params["proxy"])
    association = params.get("association", "POINTS")
    array = params["array"]
    info = inspect_proxy(proxy)
    records = info["point_arrays"] if association.upper() in ("POINTS", "POINT_DATA") else info["cell_arrays"]
    record = next((item for item in records if item["name"] == array), None)
    if not record:
        raise ValueError("Array not found: %s" % array)
    return {"array": array, "association": association, "range": record["range"], "finite": record["finite"]}


def export_animation(params):
    proxy_id, proxy = resolve(params["proxy"])
    timesteps = list(getattr(proxy, "TimestepValues", []) or [])
    if not timesteps:
        timesteps = list(getattr(GetTimeKeeper(), "TimestepValues", []) or [])
    if len(timesteps) < 2:
        raise ValueError("Animation export requires at least two verified dataset time steps")
    output = params["output"]
    os.makedirs(os.path.dirname(output), exist_ok=True)
    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    scene.PlayMode = "Snap To TimeSteps"
    VIEW.ViewTime = timesteps[-1]
    proxy.UpdatePipeline(timesteps[-1])
    display = Show(proxy, VIEW)
    display.RescaleTransferFunctionToDataRange(True, False)
    VIEW.ViewTime = timesteps[0]
    proxy.UpdatePipeline(timesteps[0])
    VIEW.Background = params.get("background", [0.015, 0.025, 0.06])
    SaveAnimation(
        output,
        VIEW,
        ImageResolution=params.get("resolution", [1920, 1080]),
        FrameRate=int(params.get("frame_rate", 10)),
        FrameWindow=[0, len(timesteps) - 1],
    )
    stem, _ = os.path.splitext(output)
    files = sorted(glob.glob(stem + "*.png"))
    return {
        "proxy": proxy_id,
        "time_steps": [float(value) for value in timesteps],
        "frame_count": len(files),
        "files": files,
    }


def camera_set(params):
    for source, target in (
        ("position", "CameraPosition"),
        ("focal_point", "CameraFocalPoint"),
        ("view_up", "CameraViewUp"),
        ("parallel_scale", "CameraParallelScale"),
    ):
        if source in params:
            setattr(VIEW, target, params[source])
    Render(VIEW)
    return camera_state()


def camera_state():
    return {
        "position": list(VIEW.CameraPosition),
        "focal_point": list(VIEW.CameraFocalPoint),
        "view_up": list(VIEW.CameraViewUp),
        "parallel_scale": float(VIEW.CameraParallelScale),
    }


def dispatch(method, params):
    if method == "ping":
        return {"status": "READY", "pid": os.getpid()}
    if method == "dataset_open":
        return open_dataset(params)
    if method == "dataset_inspect":
        proxy_id, proxy = resolve(params["proxy"])
        return {"id": proxy_id, **inspect_proxy(proxy)}
    if method == "pipeline_inspect":
        return {
            "proxies": [
                {"id": proxy_id, "type": proxy.GetXMLName(), "aliases": [name for name, value in ALIASES.items() if value == proxy_id]}
                for proxy_id, proxy in PROXIES.items()
            ]
        }
    if method == "filter_create":
        return create_filter(params)
    if method == "color_by":
        return color_by(params)
    if method == "scalar_range":
        return scalar_range(params)
    if method == "camera_set":
        return camera_set(params)
    if method == "camera_fit":
        ResetCamera(VIEW)
        Render(VIEW)
        return camera_state()
    if method == "render":
        Render(VIEW)
        return {"rendered": True, "camera": camera_state()}
    if method == "export_image":
        output = params["output"]
        os.makedirs(os.path.dirname(output), exist_ok=True)
        VIEW.Background = params.get("background", [1.0, 1.0, 1.0])
        SaveScreenshot(output, VIEW, ImageResolution=params.get("resolution", [1920, 1080]))
        return {"output": output, "resolution": params.get("resolution", [1920, 1080]), "camera": camera_state()}
    if method == "export_csv":
        _, proxy = resolve(params["proxy"])
        output = params["output"]
        os.makedirs(os.path.dirname(output), exist_ok=True)
        SaveData(output, proxy=proxy)
        return {"output": output}
    if method == "export_animation":
        return export_animation(params)
    if method == "state_save":
        output = params["output"]
        os.makedirs(os.path.dirname(output), exist_ok=True)
        SaveState(output)
        return {"output": output}
    if method == "stop":
        return {"stopping": True}
    raise ValueError("Unsupported worker method: %s" % method)


def main():
    input_stream = sys.__stdin__ or sys.stdin
    output_stream = sys.__stdout__ or sys.stdout
    while True:
        line = input_stream.readline()
        if not line:
            break
        try:
            request = json.loads(line)
            data = dispatch(request["method"], request.get("params", {}))
            response = {"id": request.get("id"), "ok": True, "data": data}
        except Exception as exc:
            response = {
                "id": request.get("id") if "request" in locals() else None,
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()
        if "request" in locals() and request.get("method") == "stop":
            break


if __name__ == "__main__":
    main()
