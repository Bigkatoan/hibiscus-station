#!/usr/bin/env bash
# Build a Hibiscus Station image variant from the repository root.
#   docker/build.sh cpu|cuda|jetson [--platform linux/amd64[,linux/arm64]] [--tag TAG] [--push]
# The tag defaults to ghcr.io/bigkatoan/hibiscus-station:<version>-<variant>.
# Build args for each variant are defined here and mirrored in .github/workflows/docker.yml.
# Without --push the result is loaded into the local image store; a multi-platform load needs
# Docker's containerd image store. Other platforms build under QEMU (tonistiigi/binfmt).
# Env: BUILD_NETWORK=host for hosts whose bridge network has no DNS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VARIANT="${1:-}"
shift || true
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/hibiscus_station/__init__.py")"
IMAGE="${STATION_IMAGE:-ghcr.io/bigkatoan/hibiscus-station}"
TAG=""
PLATFORM=""
PUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --push) PUSH=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

args=()
case "$VARIANT" in
  cpu)
    FILE="$ROOT/docker/Dockerfile"
    PLATFORM="${PLATFORM:-linux/$(docker version --format '{{.Server.Arch}}')}"
    args+=(--build-arg RUNTIME_BASE=debian:trixie-slim
           --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
           --build-arg "TORCH_PACKAGES=torch==2.15.0+cpu torchvision==0.29.1+cpu torchcodec==0.17.0+cpu")
    ;;
  cuda)
    FILE="$ROOT/docker/Dockerfile"
    PLATFORM="${PLATFORM:-linux/amd64}"
    args+=(--build-arg RUNTIME_BASE=nvidia/cuda:13.2.0-base-ubuntu24.04
           --build-arg TORCH_INDEX_URL=https://pypi.org/simple
           --build-arg "TORCH_PACKAGES=torch==2.15.0 torchvision==0.29.2 torchcodec==0.17.0")
    ;;
  jetson)
    FILE="$ROOT/docker/Dockerfile.jetson"
    PLATFORM="${PLATFORM:-linux/arm64}"
    args+=(--build-arg JETSON_BASE=nvcr.io/nvidia/pytorch:26.02-py3-igpu)
    ;;
  *) sed -n 2,8p "$0"; exit 2 ;;
esac
TAG="${TAG:-$IMAGE:$VERSION-$VARIANT}"
args+=(--build-arg "VARIANT=$VARIANT" --build-arg "VERSION=$VERSION"
       --build-arg "VCS_REF=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
       --network "${BUILD_NETWORK:-default}" -f "$FILE" -t "$TAG" --platform "$PLATFORM")

if [ "$PUSH" = 1 ]; then
  args+=(--push)
else
  # A multi-platform --load needs Docker's containerd image store (default since Docker 29).
  args+=(--load)
fi
echo "+ docker buildx build ${args[*]} $ROOT" >&2
exec docker buildx build "${args[@]}" "$ROOT"
