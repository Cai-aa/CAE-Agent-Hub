FROM ghcr.io/ansys/mapdl:v25.2-ubuntu-cicd

ENV USERNAME=mapdl
USER root

# General libraries
ENV DEBIAN_FRONTEND=noninteractive
ENV ON_CODESPACES=false
ENV ON_LOCAL=true
ENV ON_UBUNTU=true
ENV ON_CI=true

# Installing libs for testing and docs
RUN apt-get -qq update && apt-get install -qq -y \
    gcc mono-mcs g++ \
    libgl1 \
    libglx-mesa0 \
    libgomp1 \
    python3-pip \
    python3.11-venv \
    xvfb \
    zip \
    && \
    apt-get -qq clean  && rm -rf /var/lib/apt/lists/* && \
    usermod -s /bin/bash $USERNAME && \
    usermod -a -G sudo $USERNAME

# Setting up locales
RUN apt-get install -y --no-install-recommends locales && \
    locale-gen 'en_US.UTF-8' && \
    update-locale LC_ALL='en_US.UTF-8' && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen && \
    echo 'export LANG=en_US.UTF-8' >> ~/.bashrc && \
    echo 'export LANGUAGE=en_US:en' >> ~/.bashrc && \
    echo 'export LC_ALL=en_US.UTF-8' >> ~/.bashrc && \
    apt-get -qq clean  && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /home/$USERNAME/pymapdl-mcp

WORKDIR /home/$USERNAME
USER $USERNAME

COPY requirements.txt requirements.txt

# Installing Python environment
RUN python3.11 -m venv ./.venv && \
    . ./.venv/bin/activate && \
    pip install pre-commit && \
    pip install ansys-mapdl-core && \
    pip install -r requirements.txt && \
    echo 'source /home/mapdl/.venv/bin/activate' >> ~/.bashrc && \
    rm requirements.txt

WORKDIR /home/$USERNAME/pymapdl-mcp
