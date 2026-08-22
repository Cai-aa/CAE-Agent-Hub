# syntax=docker/dockerfile:1
# Devcontainer Dockerfile for Lumerical MCP Server
# Requires BuildKit for bind mount support (default in Docker Desktop)

FROM --platform=linux/amd64 rockylinux:9

LABEL maintainer="Lumerical MCP"
LABEL description="Development container for Lumerical MCP Server with Ansys Lumerical"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies and Python 3.12
RUN dnf install -y \
        python3.12 \
        python3.12-pip \
        python3.12-devel \
        git \
        which \
        util-linux-user \
        && \
    dnf clean all

# Set Python 3.12 as default
RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    alternatives --install /usr/bin/pip pip /usr/bin/pip3.12 1

# Install uv package manager
RUN pip install uv

# Optionally install Lumerical from any Lumerical-*.rpm dropped into
# .devcontainer/. The RPM is read directly from the build context via a bind
# mount, so it never enters image layers. No install runs if no RPM is found.
RUN --mount=type=bind,target=/ctx \
    rpm_file="$(ls /ctx/Lumerical-*.rpm 2>/dev/null | sort -V | tail -n 1 || true)"; \
    if [ -n "$rpm_file" ] && rpm -qp "$rpm_file" >/dev/null 2>&1; then \
        echo "Installing $(basename "$rpm_file")"; \
        dnf install -y "$rpm_file"; \
    else \
        echo "No Lumerical RPM found in build context; skipping install."; \
    fi && \
    dnf clean all

# Set offscreen for running in headless mode
ENV QT_QPA_PLATFORM=offscreen

# Create workspace directory
WORKDIR /workspaces/pylumerical-mcp

# Default command
CMD ["bash"]
