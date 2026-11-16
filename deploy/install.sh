#!/usr/bin/env bash
# Install Hibiscus Station with Docker on the computer next to the robot.
#
#   curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh
#   less install.sh && bash install.sh            # read it first, then run it as your normal user
#
# Detects the machine (x86_64 PC with or without an NVIDIA GPU, NVIDIA Jetson on JetPack 6,
# Raspberry Pi 5 / other arm64), installs Docker when missing (after asking), picks the image
# variant (cpu | cuda | jetson), writes compose files and .env to ~/.config/hibiscus-station,
# installs the udev rule for the servo bus adapters (asks for sudo), installs
# hibiscus-station-ctl into ~/.local/bin and starts Station. Docker's restart policy and the
# enabled docker service bring it back after a reboot.
#
# Options:
#   --variant cpu|cuda|jetson   skip the detection
#   --version X.Y.Z             image version (default: this script's release)
#   --data DIR                  Station data (default ~/.hibiscus/station)
#   --yes                       answer yes to every question (non-interactive)
#   --no-udev                   do not install the udev rule
#   --no-start                  write the files but do not start Station
#   --dry-run                   print what would be done, change nothing
set -euo pipefail

VERSION="0.2.0"
REPO_RAW="https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/v${VERSION}"
IMAGE="ghcr.io/bigkatoan/hibiscus-station"
VARIANT=""
DATA="$HOME/.hibiscus/station"
YES=0
UDEV=1
START=1
DRY=0
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/hibiscus-station"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --variant) VARIANT="$2"; shift ;;
    --version) VERSION="$2"; REPO_RAW="https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/v${VERSION}"; shift ;;
    --data) DATA="$2"; shift ;;
    --yes|-y) YES=1 ;;
    --no-udev) UDEV=0 ;;
    --no-start) START=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31mxx\033[0m %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
ask() { # QUESTION -> 0 yes, 1 no
  [ "$YES" = 1 ] && return 0
  [ -t 0 ] || return 1
  local reply
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy] ]]
}

[ "$(id -u)" -ne 0 ] || die "run this as the user who will use the robot, not as root (it asks for sudo when needed)"
[ "$(uname -s)" = Linux ] || die "Linux only"

# ------------------------------------------------------------------ detect the machine
ARCH="$(uname -m)"
MODEL=""
[ -r /proc/device-tree/model ] && MODEL="$(tr -d '\0' < /proc/device-tree/model)"
detect_variant() {
  if [ -f /etc/nv_tegra_release ] || [[ "$MODEL" == *Jetson* ]]; then
    local l4t
    l4t="$(sed -n 's/^# R\([0-9]*\).*/\1/p' /etc/nv_tegra_release 2>/dev/null || true)"
    if [ -n "$l4t" ] && [ "$l4t" != 36 ]; then
      warn "L4T R$l4t found: the jetson image targets JetPack 6 (L4T R36); using the cpu image instead"
      echo cpu
    else
      echo jetson
    fi
  elif [ "$ARCH" = x86_64 ] && command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    echo cuda
  else
    echo cpu
  fi
}
case "$ARCH" in
  x86_64|aarch64) ;;
  *) die "unsupported CPU architecture $ARCH (x86_64 or aarch64 only)" ;;
esac
if [ -z "$VARIANT" ]; then
  VARIANT="$(detect_variant)"
  say "machine: ${MODEL:-$ARCH} -> image variant '$VARIANT'"
  if [ "$VARIANT" = cuda ] && ! ask "NVIDIA GPU found. Use the CUDA image (larger, faster models)?"; then
    VARIANT=cpu
  fi
fi
case "$VARIANT" in
  cpu) COMPOSE_FILE=compose.yml ;;
  cuda) [ "$ARCH" = x86_64 ] || die "the cuda image is x86_64 only"; COMPOSE_FILE=compose.yml:compose.cuda.yml ;;
  jetson) [ "$ARCH" = aarch64 ] || die "the jetson image is arm64 only"; COMPOSE_FILE=compose.yml:compose.jetson.yml ;;
  *) die "unknown variant $VARIANT" ;;
esac
if [[ "$MODEL" == *"Raspberry Pi"* ]] && [[ "$MODEL" != *"Raspberry Pi 5"* ]]; then
  warn "$MODEL: only the Raspberry Pi 5 is tested (models run slowly on older boards)"
fi
[ "$ARCH" = aarch64 ] && [ "$(getconf PAGESIZE)" != 4096 ] && [ "$VARIANT" = cpu ] && \
  warn "kernel page size $(getconf PAGESIZE): if Station fails to start, see docs/first-boot-pi5.md (16K pages)"

# ------------------------------------------------------------------ Docker
if ! command -v docker >/dev/null 2>&1; then
  ask "Docker is not installed. Install it now with Docker's convenience script (get.docker.com, needs sudo)?" \
    || die "install Docker first: https://docs.docker.com/engine/install/"
  tmp="$(mktemp)"
  run curl -fsSL https://get.docker.com -o "$tmp"
  run sudo sh "$tmp"
  rm -f "$tmp"
  run sudo usermod -aG docker "$USER"
  warn "you were added to the 'docker' group: log out and back in (or reboot) if docker commands fail"
fi
if [ "$DRY" = 0 ]; then
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (package docker-compose-plugin)"
  DOCKER="docker"
  if ! docker info >/dev/null 2>&1; then
    sudo docker info >/dev/null 2>&1 || die "cannot reach the Docker daemon"
    DOCKER="sudo docker"
    warn "using sudo for docker until you log in again (docker group)"
  fi
else
  DOCKER="docker"
fi
if [ "$DRY" = 1 ]; then
  echo "[dry-run] sudo systemctl enable --now docker"
elif ! sudo systemctl enable --now docker >/dev/null 2>&1; then
  warn "could not enable the docker service; enable it so Station starts at boot"
fi
if [ "$VARIANT" = cuda ] && [ "$DRY" = 0 ] && ! $DOCKER info 2>/dev/null | grep -qi 'runtimes:.*nvidia'; then
  warn "the NVIDIA Container Toolkit is not configured for Docker: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
fi
if [ "$VARIANT" = jetson ] && [ "$DRY" = 0 ] && ! $DOCKER info 2>/dev/null | grep -qi 'runtimes:.*nvidia'; then
  warn "the NVIDIA runtime is missing from Docker: sudo apt install nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
fi

# ------------------------------------------------------------------ groups and udev
DIALOUT_GID="$(getent group dialout | cut -d: -f3 || true)"
VIDEO_GID="$(getent group video | cut -d: -f3 || true)"
[ -n "$DIALOUT_GID" ] || die "no 'dialout' group on this system"
[ -n "$VIDEO_GID" ] || die "no 'video' group on this system"
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx dialout || ! id -nG "$USER" | tr ' ' '\n' | grep -qx video; then
  ask "Add $USER to the dialout and video groups (serial ports and cameras, needs sudo)?" \
    && run sudo usermod -aG dialout,video "$USER"
fi
fetch() { # NAME DEST: from this checkout when available, else from the release on GitHub
  if [ -f "$HERE/$1" ]; then run cp "$HERE/$1" "$2"; else run curl -fsSL "$REPO_RAW/deploy/$1" -o "$2"; fi
}
if [ "$UDEV" = 1 ]; then
  if ask "Install the udev rule for the servo bus adapters (/etc/udev/rules.d/99-hibiscus-station.rules, needs sudo)?"; then
    tmp="$(mktemp)"
    fetch udev/99-hibiscus-station.rules "$tmp"
    run sudo install -m 0644 "$tmp" /etc/udev/rules.d/99-hibiscus-station.rules
    rm -f "$tmp"
    run sudo udevadm control --reload
    run sudo udevadm trigger --subsystem-match=tty
  fi
fi

# ------------------------------------------------------------------ files
CAL="$HOME/.cache/huggingface/lerobot/calibration"
BACKUPS="$HOME/.local/share/hibiscus-station/backups"
run mkdir -p "$CONF" "$DATA" "$CAL" "$BACKUPS" "$HOME/.local/bin"
run chmod 700 "$DATA" "$BACKUPS"
for f in compose.yml compose.cuda.yml compose.jetson.yml; do fetch "$f" "$CONF/$f"; done
fetch hibiscus-station-ctl "$HOME/.local/bin/hibiscus-station-ctl"
run chmod +x "$HOME/.local/bin/hibiscus-station-ctl"

ENV="$CONF/.env"
if [ -f "$ENV" ]; then
  say "keeping the existing $ENV (delete it to start over)"
else
  say "writing $ENV"
  if [ "$DRY" = 0 ]; then
    umask 077
    cat > "$ENV" <<EOF
# Hibiscus Station (Docker), written by install.sh on $(date -u +%Y-%m-%d). See .env.example in the repository.
STATION_IMAGE=$IMAGE
STATION_TAG=$VERSION-$VARIANT
STATION_PREVIOUS_TAG=
COMPOSE_FILE=$COMPOSE_FILE
STATION_DATA=$DATA
STATION_CALIBRATION=$CAL
STATION_BACKUPS=$BACKUPS
PUID=$(id -u)
PGID=$(id -g)
DIALOUT_GID=$DIALOUT_GID
VIDEO_GID=$VIDEO_GID
# 127.0.0.1 only. LAN mode needs STATION_BIND, HIBISCUS_STATION_TOKEN and HIBISCUS_STATION_ALLOWED_HOSTS (docs/deploy.md).
STATION_BIND=127.0.0.1
STATION_PORT=18210
HIBISCUS_STATION_TOKEN=
HIBISCUS_STATION_ALLOWED_HOSTS=
STATION_EXTRA_ARGS=
TZ=$(cat /etc/timezone 2>/dev/null || echo Etc/UTC)
EOF
  else
    echo "[dry-run] write $ENV (STATION_TAG=$VERSION-$VARIANT, COMPOSE_FILE=$COMPOSE_FILE)"
  fi
fi

# ------------------------------------------------------------------ start
if [ "$START" = 1 ]; then
  say "pulling $IMAGE:$VERSION-$VARIANT (the first pull is large: 1-10 GB depending on the variant)"
  run $DOCKER pull "$IMAGE:$VERSION-$VARIANT"
  run bash -c "cd '$CONF' && $DOCKER compose up -d"
  if [ "$DRY" = 0 ]; then
    say "waiting for Station to become healthy"
    for _ in $(seq 80); do
      state="$($DOCKER inspect --format '{{.State.Health.Status}}' hibiscus-station 2>/dev/null || true)"
      [ "$state" = healthy ] && break
      sleep 3
    done
    [ "$state" = healthy ] || die "Station did not become healthy: $DOCKER logs hibiscus-station"
    say "Hibiscus Station is running. Open this link in a browser on this machine:"
    $DOCKER exec hibiscus-station hibiscus-station url
  fi
fi
cat <<EOF

Next steps
  hibiscus-station-ctl status | logs -f | url | backup | update | rollback
  Data: $DATA   Calibration: $CAL   Settings: $ENV
  From another computer: ssh -L 18210:127.0.0.1:18210 $USER@$(hostname) then open the link above.
  First-boot checklists: docs/first-boot-pi5.md, docs/first-boot-jetson.md
EOF
