FROM ubuntu:22.04

# Build Chromium inside Docker — avoids polluting the host system.
# Usage:
#   docker build -t chromium-builder .
#   docker run --rm -v /mnt/big-disk/chromium:/chromium chromium-builder
#
# The /chromium volume needs ~100GB free.

ENV DEBIAN_FRONTEND=noninteractive \
    CHROMIUM_DIR=/chromium \
    BUILD_TYPE=Release

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl python3 python3-pip sudo lsb-release \
    build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

# depot_tools
RUN git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git \
    /opt/depot_tools
ENV PATH="/opt/depot_tools:${PATH}"

WORKDIR /chromium

COPY build-chromium.sh /usr/local/bin/build-chromium
RUN chmod +x /usr/local/bin/build-chromium

CMD ["build-chromium", "all"]
