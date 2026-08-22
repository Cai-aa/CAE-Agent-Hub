#!/usr/bin/env bash
# Devcontainer postCreateCommand. Runs once inside the container after it is
# first created. All container-side setup lives here.

set -euo pipefail

CORPORATE_CERTS_DIR="/usr/local/share/corporate-certs"
TRUST_ANCHOR_DIR="/etc/pki/ca-trust/source/anchors"
LUMERICAL_PROFILES=("${HOME}/.bashrc" "${HOME}/.zshrc")

sync_python_dependencies() {
    echo "[post-create] Syncing Python dependencies via uv..."
    uv sync --extra tests
}

install_pre_commit() {
    echo "[post-create] Installing pre-commit as a standalone uv tool..."
    uv tool install --force pre-commit

    # Ensure the uv-managed tool bin dir is on PATH for the rest of this
    # script (the devcontainer's interactive shells get it via the standard
    # ``~/.local/bin`` PATH entry shipped by Rocky Linux).
    local uv_bin
    uv_bin="$(uv tool dir --bin)"
    export PATH="${uv_bin}:${PATH}"

    echo "[post-create] Installing the git pre-commit hook..."
    pre-commit install --overwrite
}

install_corporate_certs() {
    if ! ls "${CORPORATE_CERTS_DIR}"/*.crt >/dev/null 2>&1; then
        echo "[post-create] No corporate certs found at ${CORPORATE_CERTS_DIR} (skipped)"
        return
    fi

    cp "${CORPORATE_CERTS_DIR}"/*.crt "${TRUST_ANCHOR_DIR}/"
    update-ca-trust
    echo "[post-create] Corporate certs installed"
}

configure_lumerical_path() {
    local lumerical_bin
    lumerical_bin="$(ls -d /opt/lumerical/v*/bin 2>/dev/null | sort -V | tail -n 1 || true)"

    if [[ -z "${lumerical_bin}" ]]; then
        echo "[post-create] Lumerical not installed; skipping shell PATH config."
        return
    fi

    local profile
    for profile in "${LUMERICAL_PROFILES[@]}"; do
        touch "${profile}"
        if grep -q '^export LUMERICAL_ROOT=' "${profile}"; then
            continue
        fi
        cat >>"${profile}" <<EOF

export LUMERICAL_ROOT="${lumerical_bin}"
export PATH="${lumerical_bin}:\$PATH"
EOF
    done

    echo "[post-create] Lumerical shell path configured: ${lumerical_bin}"
}

main() {
    sync_python_dependencies
    install_pre_commit
    install_corporate_certs
    configure_lumerical_path
}

main
