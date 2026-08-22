# PyAEDT-MCP Dockerfile
# -------------------------------------------------------
# Build:
#   docker build --build-arg PYANSYS_PYPI_INDEX_URL=<url> \
#                -f docker/Dockerfile -t pyaedt-mcp .
# Run:
#   docker run --rm -e AEDT_MACHINE=host.docker.internal \
#              -e AEDT_PORT=50051 pyaedt-mcp
# -------------------------------------------------------
FROM python:3.12-slim

# ---------- build-time args ----------
ARG PYANSYS_PYPI_INDEX_URL=""

# ---------- runtime env ----------
ENV AEDT_MACHINE=host.docker.internal \
    AEDT_PORT=50051 \
    AEDT_VERSION="" \
    AEDT_NON_GRAPHICAL=true \
    CONNECT_ON_STARTUP=false

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml LICENSE README.md ./
COPY src/ ./src/

# Install the package (with optional private PyPI for ansys-common-mcp)
RUN if [ -n "$PYANSYS_PYPI_INDEX_URL" ]; then \
        pip install --no-cache-dir --extra-index-url "$PYANSYS_PYPI_INDEX_URL" -e .; \
    else \
        pip install --no-cache-dir -e .; \
    fi

# Non-root user
RUN useradd -m -s /bin/bash pyaedt && \
    chown -R pyaedt:pyaedt /app
USER pyaedt

# Entrypoint script that honours CONNECT_ON_STARTUP
COPY --chown=pyaedt:pyaedt docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

# Labels
LABEL maintainer="PyAnsys Team"
LABEL description="PyAEDT-MCP for AI-driven AEDT automation"
LABEL version="0.1.0"
