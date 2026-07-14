#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abaqus MCP Server v5.0.

This stdio MCP server talks to a live Abaqus/CAE GUI bridge over a local TCP
socket. The socket bridge gives lower-latency interaction than the older
commands/results file queue while preserving the existing Abaqus-specific tools.
"""

from __future__ import annotations

import json
import socket
import uuid
from typing import Any
import os
import asyncio

from mcp.server.fastmcp import FastMCP


DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))
MAX_MESSAGE_BYTES = int(os.environ.get("ABAQUS_MCP_MAX_MESSAGE_BYTES", str(32 * 1024 * 1024)))

INSTRUCTIONS = """You are controlling a live Abaqus/CAE session through MCP.

Use small validated Python chunks instead of one large script. Set a clean
working directory before creating jobs. Prefer named sets and named surfaces
over fragile raw-coordinate selections for loads, boundary conditions, section
assignments, and interactions. When API behavior is uncertain, inspect the live
Abaqus objects first with run_python before continuing.
"""

mcp = FastMCP("abaqus-mcp-server", instructions=INSTRUCTIONS)


class ProtocolError(RuntimeError):
    """Raised when the Abaqus GUI bridge returns malformed protocol data."""


def _send_message(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")


def _read_message(sock: socket.socket, max_bytes: int = MAX_MESSAGE_BYTES) -> dict[str, Any]:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise ProtocolError("socket closed before a complete message was received")

        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break

        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ProtocolError(f"message exceeded {max_bytes} bytes")

    raw = b"".join(chunks)
    # Try UTF-8 first, fall back to GBK (Chinese Windows + Python 2.7 Abaqus)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    message = json.loads(text)
    if not isinstance(message, dict):
        raise ProtocolError("protocol message must be a JSON object")
    return message


def _request(method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    payload = {
        "id": str(uuid.uuid4()),
        "method": method,
        "params": {**(params or {}), "timeout": effective_timeout},
    }

    with socket.create_connection((DEFAULT_HOST, DEFAULT_PORT), timeout=effective_timeout) as sock:
        sock.settimeout(effective_timeout)
        _send_message(sock, payload)
        response = _read_message(sock)

    if response.get("id") != payload["id"]:
        raise ProtocolError("Abaqus bridge returned a mismatched response id")
    if not response.get("ok", False):
        error = response.get("error") or {}
        if isinstance(error, dict):
            raise RuntimeError(error.get("message") or json.dumps(error, ensure_ascii=False))
        raise RuntimeError(str(error))

    result = response.get("result")
    if not isinstance(result, dict):
        raise ProtocolError("Abaqus bridge returned an invalid result envelope")
    return result


async def _bridge_request(method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_request, method, params, timeout)
    except ConnectionRefusedError as exc:
        raise RuntimeError(
            "Cannot connect to the Abaqus GUI bridge. Start Abaqus/CAE and run "
            "Plug-ins > Abaqus MCP > Start Socket Bridge. "
            f"Bridge endpoint: {DEFAULT_HOST}:{DEFAULT_PORT}. Original error: {exc}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            "Timed out waiting for the Abaqus GUI bridge. Abaqus may be busy or "
            "the bridge may need to be restarted from the Plug-ins menu. "
            f"Original error: {exc}"
        ) from exc


async def _exec(code: str, timeout: float | None = None) -> dict[str, Any]:
    return await _bridge_request("execute", {"code": code}, timeout)


def _json_string(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _format_error_to_markdown(result: dict[str, Any]) -> str:
    error_type = str(result.get("error_type", "Error")).rsplit(".", 1)[-1]
    core_error = result.get("core_error", "Unknown error")
    error_line = result.get("error_line")
    location = f" at line {error_line}" if error_line else ""
    parts = [f"{error_type}{location}: {core_error}"]

    recovery = result.get("recovery")
    if isinstance(recovery, dict) and recovery:
        if recovery.get("parent_object_path"):
            parts.append(f"  Object: {recovery['parent_object_path']}")
        if recovery.get("available_keys_sample"):
            sample = recovery["available_keys_sample"]
            if isinstance(sample, list) and len(sample) > 20:
                sample = sample[:20] + ["..."]
            parts.append(f"  Available: {sample}")
        if recovery.get("possible_keys"):
            parts.append(f"  Similar keys: {recovery['possible_keys']}")
        if recovery.get("possible_members"):
            parts.append(f"  Similar members: {recovery['possible_members']}")
        if recovery.get("callable_signature"):
            parts.append(f"  Signature: {recovery['callable_signature']}")
        if recovery.get("possible_keywords"):
            parts.append(f"  Similar keywords: {recovery['possible_keywords']}")
        if recovery.get("import_suggestion"):
            parts.append(f"  Import suggestion: {recovery['import_suggestion']}")

    code_excerpt = result.get("code_excerpt")
    if code_excerpt:
        parts.append("  Code excerpt:")
        parts.extend("    " + line for line in str(code_excerpt).splitlines())

    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    if stdout:
        parts.append(f"  stdout: {stdout}")
    if stderr:
        parts.append(f"  stderr: {stderr}")
    return "\n".join(parts)


def _unwrap_execution_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok", False):
        raise RuntimeError(_format_error_to_markdown(result))
    return result


@mcp.tool()
async def ping(timeout: float | None = None) -> dict[str, Any]:
    """Check whether the Abaqus-side socket bridge is reachable."""
    return await _bridge_request("ping", timeout=timeout or 10.0)


@mcp.tool()
async def check_abaqus_connection(timeout: float | None = None) -> str:
    """Return a concise human-readable bridge status."""
    info = await ping(timeout=timeout or 10.0)
    models = info.get("models", [])
    viewports = info.get("viewports", [])
    version = info.get("abaqus_version") or "unknown"
    return (
        f"Connected to Abaqus socket bridge at {DEFAULT_HOST}:{DEFAULT_PORT}.\n"
        f"Abaqus version: {version}\n"
        f"Models: {models}\n"
        f"Viewports: {viewports}"
    )


@mcp.tool()
async def run_python(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code in the active Abaqus/CAE kernel.

    Single-line expressions are evaluated and returned. Multi-line scripts are
    executed; set a variable named ``result`` to return structured data.
    """
    if not code.strip():
        raise ValueError("code must not be empty")
    return _unwrap_execution_result(await _exec(code, timeout))


@mcp.tool()
async def execute_script(script: str, timeout: float | None = None) -> str:
    """Compatibility wrapper around run_python that returns stdout/text."""
    result = await run_python(script, timeout)
    stdout = str(result.get("stdout") or "")
    returned = result.get("return_value")
    if returned is not None:
        if stdout:
            return stdout + "\n" + _json_string(returned)
        return _json_string(returned)
    return stdout if stdout else "(Script executed successfully, no output)"


@mcp.tool()
async def set_workdir(path: str, timeout: float | None = None) -> dict[str, Any]:
    """Change the current Abaqus working directory."""
    if not path.strip():
        raise ValueError("path must not be empty")
    code = r"""
import os

new_path = __PATH__
old_dir = os.getcwd()
if not os.path.isdir(new_path):
    raise OSError("Directory does not exist: " + new_path)
os.chdir(new_path)
result = {"success": True, "previous": old_dir, "current": os.getcwd()}
""".replace("__PATH__", json.dumps(path.strip()))
    return (await run_python(code, timeout)).get("return_value")


@mcp.tool()
async def get_model_info(timeout: float | None = None) -> str:
    """Get parts, materials, steps, loads, BCs, interactions, jobs, and viewports."""
    code = r"""
from abaqus import mdb, session

def _keys(obj):
    try:
        return list(obj.keys())
    except Exception:
        return []

models = {}
for model_name in mdb.models.keys():
    model = mdb.models[model_name]
    model_info = {
        "parts": _keys(model.parts),
        "materials": _keys(model.materials),
        "sections": _keys(model.sections),
        "steps": _keys(model.steps),
        "loads": _keys(model.loads),
        "boundary_conditions": _keys(model.boundaryConditions),
        "interactions": _keys(model.interactions),
        "constraints": _keys(model.constraints),
        "amplitudes": _keys(model.amplitudes),
        "assembly_instances": _keys(model.rootAssembly.instances),
        "sets": _keys(model.rootAssembly.sets),
        "surfaces": _keys(model.rootAssembly.surfaces),
    }
    part_details = {}
    for part_name in model.parts.keys():
        part = model.parts[part_name]
        part_details[part_name] = {
            "cells": len(getattr(part, "cells", [])),
            "faces": len(getattr(part, "faces", [])),
            "edges": len(getattr(part, "edges", [])),
            "vertices": len(getattr(part, "vertices", [])),
            "sets": _keys(part.sets),
            "surfaces": _keys(part.surfaces),
        }
    model_info["part_details"] = part_details
    models[model_name] = model_info

jobs = []
for job_name in mdb.jobs.keys():
    job = mdb.jobs[job_name]
    item = {"name": job_name}
    for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)

result = {
    "models": models,
    "jobs": jobs,
    "current_viewport": getattr(session, "currentViewportName", None),
    "viewports": list(session.viewports.keys()) if hasattr(session, "viewports") else [],
}
"""
    return _json_string((await run_python(code, timeout)).get("return_value"))


@mcp.tool()
async def list_jobs(timeout: float | None = None) -> str:
    """List all Abaqus jobs in the current CAE session."""
    code = r"""
from abaqus import mdb

jobs = []
for name in mdb.jobs.keys():
    job = mdb.jobs[name]
    item = {"name": name}
    for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory", "explicitPrecision"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)
result = {"jobs": jobs}
"""
    return _json_string((await run_python(code, timeout)).get("return_value"))


@mcp.tool()
async def submit_job(job_name: str, timeout: float | None = None) -> str:
    """Submit an existing Abaqus job and wait for completion."""
    if not job_name.strip():
        raise ValueError("job_name must not be empty")
    code = r"""
from abaqus import mdb

job_name = __JOB_NAME__
if job_name not in mdb.jobs:
    raise KeyError("Job not found: " + job_name)
job = mdb.jobs[job_name]
job.submit(consistencyChecking=False)
job.waitForCompletion()
result = {"success": True, "job": job_name, "status": str(getattr(job, "status", "UNKNOWN"))}
""".replace("__JOB_NAME__", json.dumps(job_name.strip()))
    return _json_string((await run_python(code, timeout or 3600.0)).get("return_value"))


@mcp.tool()
async def monitor_job_status(job_name: str = "", timeout: float | None = None) -> dict[str, Any]:
    """Inspect job objects and, when a job is named, tail .sta/.msg diagnostics."""
    code = r"""
import os
import re
from abaqus import mdb

job_name = __JOB_NAME__

def _tail_lines(path, count):
    try:
        with open(path, "r") as handle:
            lines = handle.read().splitlines()
        return lines[-count:]
    except Exception:
        return []

def _grep_tail(path, patterns, limit):
    try:
        rx = re.compile("|".join(patterns))
        matches = []
        with open(path, "r") as handle:
            for line in handle:
                if rx.search(line):
                    matches.append(line.rstrip())
        return matches[-limit:]
    except Exception:
        return []

if not job_name:
    jobs = []
    for name in mdb.jobs.keys():
        job = mdb.jobs[name]
        item = {"name": name}
        for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
            try:
                value = getattr(job, attr, None)
                if value is not None:
                    item[attr] = str(value)
            except Exception:
                pass
        jobs.append(item)
    result = {"jobs": jobs, "workdir": os.getcwd()}
else:
    sta_path = os.path.join(os.getcwd(), job_name + ".sta")
    msg_path = os.path.join(os.getcwd(), job_name + ".msg")
    result = {
        "job_name": job_name,
        "workdir": os.getcwd(),
        "sta_path": sta_path,
        "msg_path": msg_path,
        "progress_tail": _tail_lines(sta_path, 8),
        "diagnostics_tail": _grep_tail(msg_path, [r"^\*\*\*ERROR", r"^\*\*\*WARNING"], 12),
    }
""".replace("__JOB_NAME__", json.dumps(job_name.strip()))
    return (await run_python(code, timeout)).get("return_value")


@mcp.tool()
async def inspect_odb(odb_path: str, timeout: float | None = None) -> dict[str, Any]:
    """Open an ODB read-only and return metadata about steps, frames, and outputs."""
    if not odb_path.strip():
        raise ValueError("odb_path must not be empty")
    code = r"""
from odbAccess import openOdb

odb_path = __ODB_PATH__
odb = None
try:
    odb = openOdb(path=odb_path, readOnly=True)
    steps = []

    def _slice_frames(frames):
        count = len(frames)
        if count <= 5:
            return [(i, frames[i]) for i in range(count)]
        idxs = [0, int(round((count - 1) * 0.25)), int(round((count - 1) * 0.5)), int(round((count - 1) * 0.75)), count - 1]
        seen = []
        for idx in idxs:
            if idx not in seen:
                seen.append(idx)
        return [(i, frames[i]) for i in seen]

    for step_name in odb.steps.keys():
        step = odb.steps[step_name]
        frame_items = []
        for idx, frame in _slice_frames(step.frames):
            frame_items.append({
                "index": idx,
                "frameId": frame.frameId,
                "frameValue": frame.frameValue,
                "description": str(getattr(frame, "description", "")),
            })

        field_outputs = []
        history_outputs = []
        if step.frames:
            try:
                for key in step.frames[-1].fieldOutputs.keys():
                    field = step.frames[-1].fieldOutputs[key]
                    field_outputs.append({
                        "name": key,
                        "position": str(getattr(field, "position", "")),
                        "components": list(getattr(field, "componentLabels", []) or []),
                        "validInvariants": [str(x) for x in (getattr(field, "validInvariants", []) or [])],
                    })
            except Exception:
                pass
            try:
                history_outputs = list(step.historyRegions.keys())
            except Exception:
                pass

        steps.append({
            "name": step_name,
            "procedure": str(getattr(step, "procedure", "")),
            "totalTime": getattr(step, "totalTime", 0.0),
            "frame_count": len(step.frames),
            "frames": frame_items,
            "fieldOutputs": field_outputs,
            "historyRegions": history_outputs,
        })

    result = {
        "title": str(getattr(odb, "title", "")),
        "description": str(getattr(odb, "description", "")),
        "parts": list(odb.parts.keys()) if hasattr(odb, "parts") else [],
        "instances": list(odb.rootAssembly.instances.keys()) if hasattr(odb, "rootAssembly") else [],
        "steps": steps,
    }
finally:
    if odb is not None:
        odb.close()
""".replace("__ODB_PATH__", json.dumps(odb_path.strip()))
    return (await run_python(code, timeout or 120.0)).get("return_value")


@mcp.tool()
async def get_odb_info(odb_path: str, timeout: float | None = None) -> str:
    """Compatibility wrapper for inspect_odb returning formatted JSON."""
    return _json_string(await inspect_odb(odb_path, timeout))


@mcp.tool()
async def capture_viewport(
    viewport_name: str = "",
    image_format: str = "PNG",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Capture an Abaqus viewport as base64 image data."""
    code = r"""
import os
import tempfile
import base64
from abaqus import session
import abaqusConstants

vp_name = __VP_NAME__
fmt_name = __FORMAT__.upper()
fmt_map = {
    "PNG": abaqusConstants.PNG,
    "TIFF": abaqusConstants.TIFF,
    "SVG": abaqusConstants.SVG,
    "EPS": abaqusConstants.EPS,
    "PS": abaqusConstants.PS,
}
fmt = fmt_map.get(fmt_name, abaqusConstants.PNG)

if not vp_name or vp_name not in session.viewports.keys():
    vp_name = session.currentViewportName
vp = session.viewports[vp_name]
suffix = "." + fmt_name.lower()
handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
tmp_path = handle.name
handle.close()

try:
    session.printToFile(fileName=tmp_path, format=fmt, canvasObjects=(vp,))
    with open(tmp_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode("ascii")
    result = {
        "success": True,
        "viewport": vp_name,
        "format": fmt_name.lower(),
        "image_base64": image_base64,
        "size_bytes": int(len(image_base64) * 3 / 4),
    }
finally:
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
""".replace("__VP_NAME__", json.dumps(viewport_name.strip())).replace("__FORMAT__", json.dumps(image_format.strip() or "PNG"))
    return (await run_python(code, timeout or 60.0)).get("return_value")


@mcp.tool()
async def get_viewport_image(viewport_name: str = "", image_format: str = "PNG", timeout: float | None = None) -> str:
    """Compatibility wrapper returning a data URI for the requested viewport."""
    data = await capture_viewport(viewport_name, image_format, timeout)
    fmt = data.get("format", "png")
    b64 = data.get("image_base64", "")
    return f"data:image/{fmt};base64,{b64}"


@mcp.resource("abaqus://session-telemetry")
def session_telemetry() -> str:
    """Live Abaqus/CAE session telemetry from the socket bridge."""
    try:
        return _json_string(_request("ping", timeout=5.0))
    except Exception as exc:
        return _json_string({"connected": False, "error": str(exc), "endpoint": f"{DEFAULT_HOST}:{DEFAULT_PORT}"})


@mcp.resource("abaqus://status")
def abaqus_status() -> str:
    """Compatibility status resource."""
    return session_telemetry()


@mcp.resource("abaqus://agent-instructions")
def agent_instructions() -> str:
    """Abaqus modeling instructions for MCP clients."""
    return INSTRUCTIONS


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
