#!/usr/bin/env bash
# entrypoint.sh – smart launcher for PyAEDT-MCP inside Docker
set -euo pipefail

CMD_ARGS=(
    ansys-aedt-mcp
    --transport http
    --http-host 0.0.0.0
    --http-port 8080
    --machine "${AEDT_MACHINE:-host.docker.internal}"
    --port   "${AEDT_PORT:-50051}"
)

# Optionally pass --version
if [ -n "${AEDT_VERSION:-}" ]; then
    CMD_ARGS+=(--version "$AEDT_VERSION")
fi

# Honour CONNECT_ON_STARTUP (default: false)
if [ "${CONNECT_ON_STARTUP:-false}" = "true" ]; then
    CMD_ARGS+=(--connect)
fi

# Non-graphical flag
if [ "${AEDT_NON_GRAPHICAL:-true}" = "true" ]; then
    CMD_ARGS+=(--non-graphical)
else
    CMD_ARGS+=(--graphical)
fi

exec "${CMD_ARGS[@]}"
