#!/usr/bin/env bash
# Devcontainer initializeCommand. Runs on the HOST before the container is
# built, so it must work in plain bash without any container dependencies.
#
# Responsibilities:
#   1. Ensure ~/.corporate-certs exists so the bind mount in devcontainer.json
#      points at a real directory (Docker silently auto-creates the source
#      path otherwise, which is surprising for users without corporate certs).
#   2. Ensure a `.env` exists at the workspace root (bootstrap from
#      `.env.example` if missing) so the `--env-file` runArg has something to
#      load.
#
# The Lumerical RPM is picked up directly by the Dockerfile via a build
# context bind mount, so no host-side preparation is needed for it.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"

ensure_corporate_certs_dir() {
    local certs_dir="${HOME}/.corporate-certs"
    if [[ -d "${certs_dir}" ]]; then
        return 0
    fi

    mkdir -p "${certs_dir}"
    echo "[setup] Created empty ${certs_dir} - drop *.crt files there to install corporate CAs in the container." >&2
}

bootstrap_env_file() {
    local env_file="${REPO_ROOT}/.env"
    local example_file="${REPO_ROOT}/.env.example"

    if [[ -f "${env_file}" ]]; then
        return 0
    fi

    if [[ -f "${example_file}" ]]; then
        cp "${example_file}" "${env_file}"
        echo "[setup] Created .env from .env.example - edit it to set ANSYSLMD_LICENSE_FILE and LLM credentials." >&2
    else
        : >"${env_file}"
        echo "[setup] WARNING: no .env.example found; created empty .env." >&2
    fi
}

ensure_corporate_certs_dir
bootstrap_env_file
