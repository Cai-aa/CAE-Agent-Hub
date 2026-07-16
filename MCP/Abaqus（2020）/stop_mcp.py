#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Request the Abaqus MCP socket bridge to stop."""

from __future__ import annotations

import json
import os
import socket
import uuid


HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10"))


def _read_message(sock: socket.socket) -> dict:
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed before response")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


payload = {
    "id": str(uuid.uuid4()),
    "method": "stop",
    "params": {"timeout": TIMEOUT},
}

with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as sock:
    sock.settimeout(TIMEOUT)
    sock.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
    response = _read_message(sock)

print(json.dumps(response, indent=2, ensure_ascii=False))
