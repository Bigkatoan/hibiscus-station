#!/usr/bin/env bash
# Release dry run (FL-12, SP-3 on Linux): build the release assets, install them the way a user does
# into a fresh, empty home with no git on PATH, and check the result.
#
#   tools/release/dry_run.sh [--keep] [--no-docker] [--port 18352]
#
# 1. web/dist (built with web/scripts/node.sh when missing), then tools/release/build_release.py and
#    tools/release/verify_assets.py.
# 2. Install with the real install.ps1 in a PowerShell 7 container (mcr.microsoft.com/powershell, no
#    git in the image; uv and the assets mounted), or with --no-docker the same `uv tool install`
#    command in bash with git hidden from PATH.
# 3. `hibiscus-station --version` must print this version.
# 4. The installed libraries must equal `uv sync --locked --no-dev` (the set the tests run on),
#    name and version, 100 %.
# 5. Smoke launch: `hibiscus-station --mock` on 127.0.0.1:$PORT, health, UI index, JS MIME type.
#
# Needs uv; docker for step 2 in the container. The uv cache is shared (UV_CACHE_DIR), nothing else
# outside the scratch directory is written. Ports: 127.0.0.1 only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KEEP=0
DOCKER=1
PORT=18352
PWSH_IMAGE="mcr.microsoft.com/powershell:7.4-ubuntu-22.04"
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --no-docker) DOCKER=0 ;;
    --port) PORT="$2"; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

UV="env -u PYTHONPATH -u AMENT_PREFIX_PATH uv"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/station-dry-run.XXXXXX")"
PID=""
cleanup() {
  if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; fi
  if [ "$KEEP" = 1 ]; then echo "kept $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT
step() { printf '\n== %s\n' "$*"; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/hibiscus_station/__init__.py")"
step "Hibiscus Station $VERSION release dry run in $WORK"

step "1. build the UI and the release assets"
if [ ! -f "$ROOT/web/dist/index.html" ]; then
  "$ROOT/web/scripts/node.sh" pnpm install --frozen-lockfile
  "$ROOT/web/scripts/node.sh" pnpm build
fi
REL="$WORK/release"
if ! (cd "$ROOT" && $UV run --frozen python tools/release/build_release.py --out "$REL") > "$WORK/build.log" 2>&1; then
  tail -40 "$WORK/build.log"; echo "FAIL: build_release.py" >&2; exit 1
fi
ls -l "$REL"
step "1b. verify the assets (checksums; resolved set == uv.lock on Windows x64, Linux x86_64, macOS arm64)"
(cd "$ROOT" && $UV run --frozen python tools/release/verify_assets.py "$REL")

HOME_T="$WORK/home"
mkdir -p "$HOME_T"
CACHE="${UV_CACHE_DIR:-$($UV cache dir)}"
TOOLS="$HOME_T/.local/share/uv/tools"
BIN="$HOME_T/.local/bin"

step "2. install (no git on PATH, empty home)"
if [ "$DOCKER" = 1 ] && command -v docker >/dev/null && { docker image inspect "$PWSH_IMAGE" >/dev/null 2>&1 || docker pull -q "$PWSH_IMAGE"; }; then
  mkdir -p "$WORK/uvbin"
  cp "$(command -v uv)" "$WORK/uvbin/uv"
  # Same absolute paths inside and outside, so the tool environment also runs on the host.
  docker run --rm --network host -u "$(id -u):$(id -g)" \
    -v "$WORK:$WORK" -v "$CACHE:$CACHE" \
    -e HOME="$HOME_T" -e UV_CACHE_DIR="$CACHE" \
    -e HIBISCUS_STATION_BASE_URL="$REL" -e HIBISCUS_STATION_UV="$WORK/uvbin/uv" \
    -e PATH=/opt/microsoft/powershell/7 \
    "$PWSH_IMAGE" /opt/microsoft/powershell/7/pwsh -NoProfile -NonInteractive -Command \
    "if (Get-Command git -ErrorAction SilentlyContinue) { throw 'git is on PATH' }; Get-Content -Raw '$REL/install.ps1' | Invoke-Expression"
else
  echo "(no docker: running the installer's uv command in bash)"
  NOGIT="$WORK/nogit-bin"
  mkdir -p "$NOGIT"
  ln -s "$(command -v uv)" "$NOGIT/uv"
  sed "s#https://github.com/Bigkatoan/hibiscus-station/releases/download/v$VERSION#file://$REL#" \
    "$REL/overrides.txt" > "$WORK/overrides.txt"
  env -i HOME="$HOME_T" PATH="$NOGIT" UV_CACHE_DIR="$CACHE" \
    uv --no-config tool install --force --python 3.12 --managed-python \
    --constraints "$REL/constraints.txt" --overrides "$WORK/overrides.txt" \
    "$REL/hibiscus_station-$VERSION-py3-none-any.whl"
fi

step "3. version"
GOT="$("$BIN/hibiscus-station" --version)"
echo "$GOT"
[ "$GOT" = "hibiscus-station $VERSION" ] || { echo "FAIL: expected hibiscus-station $VERSION" >&2; exit 1; }

step "4. installed libraries == uv.lock (uv sync --locked --no-dev)"
REF="$WORK/ref-venv"
(cd "$ROOT" && UV_PROJECT_ENVIRONMENT="$REF" $UV sync --locked --no-dev --no-install-project --python 3.12 -q)
list() { $UV pip list --python "$1" --format json; }
list "$TOOLS/hibiscus-station/bin/python" > "$WORK/installed.json"
list "$REF/bin/python" > "$WORK/reference.json"
$UV run --project "$ROOT" --frozen python - "$WORK/installed.json" "$WORK/reference.json" "$VERSION" <<'PY'
import json, re, sys
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
inst = {norm(p["name"]): p["version"] for p in json.load(open(sys.argv[1]))}
ref = {norm(p["name"]): p["version"] for p in json.load(open(sys.argv[2]))}
station = inst.pop("hibiscus-station", None)
diff = sorted(set(inst.items()) ^ set(ref.items()))
print(f"installed {len(inst)} packages + hibiscus-station {station}; reference {len(ref)}")
for name, ver in diff:
    side = "installed only" if inst.get(name) == ver else "lock only"
    print(f"  {side}: {name}=={ver}")
if diff or station != sys.argv[3]:
    sys.exit("FAIL: the installed set differs from uv.lock")
print("OK: 100 % identical")
PY

step "5. smoke launch on 127.0.0.1:$PORT"
"$BIN/hibiscus-station" --mock --no-browser --port "$PORT" --home "$WORK/station" > "$WORK/station.log" 2>&1 &
PID=$!
ok=0
for _ in $(seq 90); do
  if "$BIN/hibiscus-station" health --home "$WORK/station" >/dev/null 2>&1; then ok=1; break; fi
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
[ "$ok" = 1 ] || { cat "$WORK/station.log"; echo "FAIL: Station did not become healthy" >&2; exit 1; }
"$BIN/hibiscus-station" health --home "$WORK/station"
INDEX="$(curl -fsS "http://127.0.0.1:$PORT/")"
grep -q "<title>Hibiscus Station</title>" <<<"$INDEX" || { echo "FAIL: no UI index" >&2; exit 1; }
JS="$(grep -o 'src="/assets/[^"]*\.js"' <<<"$INDEX" | head -1 | cut -d'"' -f2)"
MIME="$(curl -fsS -o /dev/null -w '%{content_type}' "http://127.0.0.1:$PORT$JS")"
echo "$JS -> $MIME"
grep -q javascript <<<"$MIME" || { echo "FAIL: bad JS MIME type" >&2; exit 1; }
kill "$PID"; wait "$PID" 2>/dev/null || true; PID=""

step "DRY RUN OK: hibiscus-station $VERSION installs without git, with the locked libraries, and serves the UI"
