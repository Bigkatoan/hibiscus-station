# syntax=docker/dockerfile:1.7
# Hibiscus Station images for PCs, mini PCs and the Raspberry Pi 5. Build context: the repository
# root. Variants are selected with build args (docker/build.sh and .github/workflows/docker.yml use
# exactly these values):
#
#   variant  platforms                  RUNTIME_BASE                        TORCH_INDEX_URL                         torch
#   cpu      linux/amd64, linux/arm64   debian:trixie-slim                  https://download.pytorch.org/whl/cpu    2.15.0+cpu
#   cuda     linux/amd64                nvidia/cuda:13.2.0-base-ubuntu24.04 https://pypi.org/simple (cu13 wheels)   2.15.0
#
# Python 3.12 itself comes from uv (python-build-standalone) in every variant, in /opt/python.
#
# NVIDIA Jetson (JetPack 6) has its own Dockerfile (docker/Dockerfile.jetson): it keeps the
# PyTorch that NVIDIA builds for the Orin GPU.
#
# Run: non-root, uid 10001 by default (compose runs it as the host user, see deploy/compose.yml),
# data in /data (host ~/.hibiscus/station), lerobot calibration in /calibration, port 18210.

ARG RUNTIME_BASE=debian:trixie-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.8
ARG NODE_IMAGE=node:22.12-bookworm
ARG BUILD_PYTHON_IMAGE=python:3.12.16-slim-trixie

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------------------------
# 1. The web UI (architecture independent: always built on the build machine's platform)
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS web
ENV CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 COREPACK_HOME=/opt/corepack
WORKDIR /src/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.cache/pnpm-store \
    corepack pnpm@9.15.0 install --frozen-lockfile --store-dir /root/.cache/pnpm-store
COPY openapi.json /src/openapi.json
COPY web/ ./
RUN corepack pnpm@9.15.0 build

# ---------------------------------------------------------------------------------------------
# 2. The wheel (pure Python, UI inside) and the pinned requirements, both from the lock file
FROM --platform=$BUILDPLATFORM ${BUILD_PYTHON_IMAGE} AS wheel
COPY --from=uv /uv /usr/local/bin/
WORKDIR /src
COPY pyproject.toml uv.lock hatch_build.py README.md LICENSE ASSETS-LICENSE NOTICE openapi.json ./
COPY hibiscus_station/ hibiscus_station/
COPY docker/requirements-from-lock.sh docker/
COPY --from=web /src/web/dist web/dist
RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --wheel --out-dir /dist \
 && docker/requirements-from-lock.sh > /dist/requirements.txt

# ---------------------------------------------------------------------------------------------
# 3. The virtual environment, built on the target platform (git is needed for the two git pins)
FROM ${RUNTIME_BASE} AS venv
ARG PYTHON_VERSION=3.12.16
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_PACKAGES="torch==2.15.0+cpu torchvision==0.29.1+cpu torchcodec==0.17.0+cpu"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install "${PYTHON_VERSION}" \
 && uv venv --python "${PYTHON_VERSION}" /opt/venv \
 && rm -rf /opt/python/cpython-*/lib/python3.12/ensurepip \
           /opt/python/cpython-*/lib/python3.12/site-packages/pip \
           /opt/python/cpython-*/lib/python3.12/site-packages/pip-*.dist-info
# torch stack first, from the variant's index; then everything else exactly as locked, with the
# torch stack held by a constraint so nothing replaces it.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --index-url "${TORCH_INDEX_URL}" ${TORCH_PACKAGES}
COPY --from=wheel /dist /dist
RUN --mount=type=cache,target=/root/.cache/uv \
    /opt/venv/bin/python -c "import importlib.metadata as m; print('\n'.join(f'{p}=={m.version(p)}' for p in ('torch', 'torchvision', 'torchcodec')))" > /dist/torch-pins.txt \
 && uv pip install --python /opt/venv/bin/python --index-url "${TORCH_INDEX_URL}" --extra-index-url https://pypi.org/simple \
      --index-strategy unsafe-best-match --constraint /dist/torch-pins.txt -r /dist/requirements.txt \
 && uv pip install --python /opt/venv/bin/python --no-deps /dist/hibiscus_station-*.whl \
 && /opt/venv/bin/python -c "import hibiscus_station, lerobot, torch; print('station', hibiscus_station.__version__, 'torch', torch.__version__)"

# ---------------------------------------------------------------------------------------------
# 4. Runtime
FROM ${RUNTIME_BASE} AS runtime
ARG VARIANT=cpu
ARG VERSION=0.0.0-dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="hibiscus-station" \
      org.opencontainers.image.description="Hibiscus Station: the robot-side app for SO-100/SO-101 arms (${VARIANT})" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/Bigkatoan/hibiscus-station" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      io.github.bigkatoan.hibiscus-station.variant="${VARIANT}"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
# libgl1/libglib2.0-0: OpenCV; tini: signal handling, so `docker stop` reaches Station's safe
# shutdown (hold, park, torque off) instead of a SIGKILL.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends ca-certificates tini libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && (getent passwd 1000 >/dev/null && userdel --remove "$(getent passwd 1000 | cut -d: -f1)" || true) \
 && groupadd --system --gid 10001 station \
 && useradd --system --uid 10001 --gid station --groups dialout,video \
      --home-dir /home/station --create-home --shell /usr/sbin/nologin station \
 && mkdir -p /data /calibration \
 && chown station:station /data /calibration \
 && chmod 1777 /home/station
COPY --from=venv /opt/python /opt/python
COPY --from=venv /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/station \
    HIBISCUS_STATION_HOME=/data \
    HF_LEROBOT_CALIBRATION=/calibration \
    HF_HOME=/data/cache/huggingface \
    HIBISCUS_CONFIG_DIR=/data/hibiscus-cli \
    HIBISCUS_STATE_DIR=/data/hibiscus-cli/state \
    HIBISCUS_KEYRING=0 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HIBISCUS_STATION_VARIANT=${VARIANT}

USER 10001:10001
WORKDIR /home/station
EXPOSE 18210
# `hibiscus-station health` reads /data/station.pid and /data/token and asks the running instance
# for GET /api/v1/status with its own token: it checks the process, the API and the auth path.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD ["hibiscus-station", "health", "--timeout", "8"]
ENTRYPOINT ["tini", "--", "hibiscus-station"]
CMD ["--no-browser"]
