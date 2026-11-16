#!/usr/bin/env bash
# Run the web tooling inside a pinned Node container, for hosts without Node (robot PCs, CI boxes).
# Usage: web/scripts/node.sh pnpm install --frozen-lockfile
#        web/scripts/node.sh pnpm build
# Notes:
#  * The repository root is mounted at /w (working directory /w/web) so `../openapi.json`
#    resolves for `pnpm gen:api`.
#  * --network host: some Docker hosts have no DNS on the default bridge network. The build/test
#    scripts start no server; `pnpm dev` binds 127.0.0.1:18211 only.
#  * The pnpm store and corepack cache live in $HIBISCUS_NODE_CACHE (default ~/.cache/hibiscus-node).
set -euo pipefail
web="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="$(cd "$web/.." && pwd)"
cache="${HIBISCUS_NODE_CACHE:-$HOME/.cache/hibiscus-node}"
mkdir -p "$cache"
if [ "$#" -gt 0 ] && [ "$1" = "pnpm" ]; then shift; set -- corepack pnpm@9.15.0 "$@"; fi
tty_flag=()
if [ -t 0 ] && [ -t 1 ]; then tty_flag=(-it); fi
exec docker run --rm "${tty_flag[@]}" --network host \
  -u "$(id -u):$(id -g)" \
  -e HOME=/cache -e COREPACK_HOME=/cache/corepack -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
  -e npm_config_store_dir=/cache/pnpm-store -e CI=true \
  -v "$repo":/w -v "$cache":/cache -w /w/web \
  node:22.12-bookworm "$@"
