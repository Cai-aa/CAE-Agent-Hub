FROM python:3.13

# Add labels for metadata
LABEL org.opencontainers.image.title="PyMechanical MCP Server"
LABEL org.opencontainers.image.description="Model Context Protocol server for Ansys Mechanical through PyMechanical"
LABEL org.opencontainers.image.source="https://github.com/ansys/pymechanical-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Tushar Bana,pyansys.core@ansys.com"
LABEL org.opencontainers.image.vendor="ANSYS, Inc."

# Legacy Contact Labels (for backward compatibility)
LABEL description="Model Context Protocol server for Ansys Mechanical through PyMechanical"
LABEL email="pyansys.core@ansys.com"

# Install utilities needed for user creation and install
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 ansys && \
    useradd -d /home/ansys -s /bin/bash -g ansys -u 1000 ansys && \
    mkdir -p /app /workspace && \
    chown -R ansys:ansys /app /workspace

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install package. ansys-common-mcp requires a private PyPI index.
# Pass PYANSYS_PYPI_INDEX_URL build-arg, or a BuildKit secret 'github_token'.
ARG PYANSYS_PYPI_INDEX_URL=""
RUN --mount=type=secret,id=github_token \
    pip install --no-cache-dir --upgrade pip && \
    if [ -n "${PYANSYS_PYPI_INDEX_URL}" ]; then \
        echo "Installing with private PyPI index..." && \
        pip install --no-cache-dir --extra-index-url "${PYANSYS_PYPI_INDEX_URL}" -e .; \
    elif [ -f /run/secrets/github_token ]; then \
        export GH_TOKEN=$(cat /run/secrets/github_token) && \
        git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/" && \
        pip install --no-cache-dir -e . && \
        git config --global --unset url."https://${GH_TOKEN}@github.com/".insteadOf; \
    else \
        echo "Warning: No private index or GitHub token provided, attempting public install..." && \
        pip install --no-cache-dir -e .; \
    fi

# Set default environment variables
ENV PYMECHANICAL_START_INSTANCE=false
ENV PYMECHANICAL_IP=host.docker.internal
ENV PYMECHANICAL_PORT=10000

# gRPC transport: auto-detects insecure/mtls based on cert availability.
# Override: PYMECHANICAL_TRANSPORT_MODE=insecure|mtls|wnua
# For mTLS: mount certs via -v /path/to/certs:/app/certs
# ENV PYMECHANICAL_TRANSPORT_MODE=auto
# ENV ANSYS_GRPC_CERTIFICATES=/app/certs

# Set to "true" to connect on startup (locks connection tools).
ENV CONNECT_ON_STARTUP=false

ENV HTTP_HOST=0.0.0.0
ENV HTTP_PORT=8080

# Expose the ports
EXPOSE ${HTTP_PORT}
EXPOSE ${PYMECHANICAL_PORT}

# Create entrypoint that honours CONNECT_ON_STARTUP and PYMECHANICAL_TRANSPORT_MODE
RUN echo '#!/bin/bash\n\
set -e\n\
echo "PyMechanical MCP | target=$PYMECHANICAL_IP:$PYMECHANICAL_PORT | http=$HTTP_HOST:$HTTP_PORT"\n\
CMD_ARGS="--transport http --http-host $HTTP_HOST --http-port $HTTP_PORT"\n\
if [ "${CONNECT_ON_STARTUP}" = "true" ]; then\n\
    CMD_ARGS="$CMD_ARGS --connect-on-startup --ip $PYMECHANICAL_IP --port $PYMECHANICAL_PORT"\n\
fi\n\
[ -n "${PYMECHANICAL_TRANSPORT_MODE}" ] && CMD_ARGS="$CMD_ARGS --transport-mode $PYMECHANICAL_TRANSPORT_MODE"\n\
[ -n "${ANSYS_GRPC_CERTIFICATES}" ] && CMD_ARGS="$CMD_ARGS --certs-dir $ANSYS_GRPC_CERTIFICATES"\n\
exec ansys-mechanical-mcp $CMD_ARGS\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
