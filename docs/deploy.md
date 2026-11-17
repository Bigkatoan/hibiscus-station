# Deploying Hibiscus Station on the robot computer

Station runs on the computer the arms and cameras are plugged into. Supported hardware:

| Machine | Image variant | Notes |
|---|---|---|
| x86_64 PC or mini PC | `cpu` | Any recent CPU runs ACT at 30 fps |
| x86_64 with an NVIDIA GPU | `cuda` | NVIDIA driver ≥ 580 (CUDA 13) and the NVIDIA Container Toolkit |
| NVIDIA Jetson Orin Nano / NX / AGX | `jetson` | JetPack 6.x (L4T R36). See [first-boot-jetson.md](first-boot-jetson.md) |
| Raspberry Pi 5 (4 or 8 GB) | `cpu` (arm64) | 64-bit Raspberry Pi OS (Bookworm). See [first-boot-pi5.md](first-boot-pi5.md) |

Images: `ghcr.io/bigkatoan/hibiscus-station:<version>-<variant>`, e.g. `0.2.8-cpu` (multi-arch:
linux/amd64 and linux/arm64), `0.2.8-cuda` (amd64), `0.2.8-jetson` (arm64). Each also has the
floating tags `<major>.<minor>-<variant>` and `<variant>` (latest release).

There are two ways to install on Linux: **Docker** (recommended, below) and the **Python wheel with a
systemd user service** (at the end). **Windows 10/11 and macOS use the wheel** ([below](#windows-1011-and-macos-wheel)):
the Docker deploy is Linux only, because Docker Desktop cannot hand a USB serial port to a container
(short of usbipd + WSL, which this guide does not cover).

## Docker install

```bash
curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh
less install.sh            # read it
bash install.sh            # as your normal user; it asks before using sudo
```

`install.sh`:

1. detects the machine (Jetson by `/etc/nv_tegra_release`, Raspberry Pi by the device-tree model,
   an NVIDIA GPU by `nvidia-smi`) and picks the variant (`--variant` overrides);
2. installs Docker with Docker's convenience script if it is missing, **after asking**, and enables
   the docker service so Station comes back after a reboot;
3. offers to add you to the `dialout` and `video` groups and to install the udev rule
   (`deploy/udev/99-hibiscus-station.rules`);
4. writes `~/.config/hibiscus-station/{compose.yml,compose.cuda.yml,compose.jetson.yml,.env}`,
   creates `~/.hibiscus/station` (data), the lerobot calibration folder and the backup folder;
5. installs `hibiscus-station-ctl` into `~/.local/bin`, pulls the image, starts Station and prints
   the login link.

Options: `--variant cpu|cuda|jetson`, `--version X.Y.Z`, `--data DIR`, `--yes`, `--no-udev`,
`--no-start`, `--dry-run`. To set it up by hand instead: copy `deploy/compose*.yml` and
`deploy/.env.example` (as `.env`) into a folder, fill in `.env`, then `docker compose up -d`.

### What the container gets

| | Value | Why |
|---|---|---|
| User | your uid:gid (`PUID`/`PGID`), plus the host's `dialout` and `video` groups | files in `~/.hibiscus/station` stay yours; serial ports and cameras without root |
| `/data` | `~/.hibiscus/station` | robot profiles, settings, datasets, models, sessions, trajectories, programs, detectors, the server pairing |
| `/calibration` | `~/.cache/huggingface/lerobot/calibration` | lerobot's own place, so `lerobot-*` commands and LeLab on the same machine use the same files |
| Network | host networking, Station on `127.0.0.1:18210` | the same security model as the Python install (below) |
| Devices | `/dev` bind-mounted + cgroup rules for ttyACM (166), ttyUSB (188), video4linux (81), raw USB (189) | see the next section |
| Restart | `unless-stopped`, 30 s stop grace period | `docker stop` runs Station's safe stop: hold, park at the rest pose, torque off |
| Health | `hibiscus-station health` every 30 s | calls `GET /api/v1/status` with the instance's own token |

### Why `/dev` + cgroup rules instead of a `devices:` list

A `devices:` list is resolved once, when the container starts. Robot hardware is hot-plugged:

* an arm that is unplugged at boot would stop the container from starting at all;
* "Find by unplugging" needs to see a port disappear and come back with the container running;
* `/dev/ttyACM0` can become `/dev/ttyACM1` after a replug; Station stores the stable
  `/dev/serial/by-id/...` (and `/dev/v4l/by-id/...`) path, which only resolves when those links and
  their targets exist in the container.

So the container sees the host's `/dev` (and `/run/udev`, read-only, for device metadata), and
`device_cgroup_rules` allow read/write only on the device classes Station needs. Every other device
node in `/dev` is visible but cannot be opened. The container is not privileged.

### The udev rule

`deploy/udev/99-hibiscus-station.rules` (installed to `/etc/udev/rules.d/`) matches the servo bus
adapters of SO-100/SO-101 kits (CH343 `1a86:55d3` and CH340 `1a86:7523`):

* mode 0660, group `dialout`;
* tells ModemManager to leave them alone (it probes new ttyACM devices);
* adds `/dev/hibiscus/arm-<serial>` (or `arm-<usb path>` for adapters without a serial number).

To name your arms, uncomment the two example lines with your adapters' serial numbers
(`hibiscus-station-ctl ports` lists them), then `sudo udevadm control --reload && sudo udevadm
trigger`. Use these paths (or the `/dev/serial/by-id/...` ones) in the robot profile.

## Day-to-day: `hibiscus-station-ctl`

```text
hibiscus-station-ctl status            image, health, data folder
hibiscus-station-ctl up | down | restart
hibiscus-station-ctl logs -f
hibiscus-station-ctl url               login link (prints the token: do not paste it in chats)
hibiscus-station-ctl ports             serial adapters and their stable names
hibiscus-station-ctl backup [--full]   ~/.local/share/hibiscus-station/backups/station-<time>-<tag>.tar.gz
hibiscus-station-ctl restore FILE
hibiscus-station-ctl update [TAG]      backup → pull → restart → health check → auto-rollback
hibiscus-station-ctl rollback          back to the tag that ran before the last update
```

**Backups** contain what you cannot download again: `robots.yaml`, `settings.yaml`, the per-robot
trajectories, poses, detectors and programs (`robots/`), program run logs (`runs/`), the server
pairing (`server.json`, `hibiscus-cli/` with the access token), and the lerobot calibration files.
`--full` adds datasets, models and session logs. Files are mode 0600 in a 0700 folder; treat them
like a password because of the access token.

**Update** (`update 0.3.0-cpu`, or `update` alone to re-pull the current tag, e.g. a floating
`0.2-cpu`):

1. backup as above;
2. `docker pull` (with `--no-pull`, only a local image is used);
3. records the running tag as `STATION_PREVIOUS_TAG` (for a floating tag the old image is kept as
   `<tag>-rollback`), writes the new `STATION_TAG` and recreates the container;
4. waits for the health check (`--timeout`, default 240 s);
5. if it is not healthy: prints the last log lines, switches back to the previous tag, waits for it
   to be healthy, and exits with status 1. The backup from step 1 stays available for `restore`.

`rollback` swaps `STATION_TAG` and `STATION_PREVIOUS_TAG` (running it twice rolls forward again).
Old images are not deleted automatically; `docker image prune` when you are happy.

## Network and security

Station is a control panel for a machine that moves. By default it behaves exactly like the Python
install:

* it listens on **127.0.0.1:18210 only**;
* every browser session starts from a login link with a random token (`hibiscus-station-ctl url`);
* the Host header must be `127.0.0.1:18210`, `localhost:18210` or `[::1]:18210` (blocks DNS
  rebinding), WebSockets check the Origin, writes need the `X-Station: 1` header.

### From another computer: SSH tunnel (recommended)

```bash
ssh -N -L 18210:127.0.0.1:18210 user@robot-pc     # leave it running
# then open the login link (hibiscus-station-ctl url on the robot computer) on your laptop
```

Nothing changes on the robot computer and the traffic is encrypted.

### Open Station on the LAN (opt-in)

For a robot computer without a screen on a **trusted** network (your lab, not a café or a campus
Wi-Fi), set all three in `~/.config/hibiscus-station/.env`:

```bash
STATION_BIND=0.0.0.0                                 # or this machine's LAN address
HIBISCUS_STATION_TOKEN=<python3 -c 'import secrets; print(secrets.token_urlsafe(32))'>
HIBISCUS_STATION_ALLOWED_HOSTS=robot-pi.local,192.168.1.40
```

then `hibiscus-station-ctl up`. The login link becomes `http://robot-pi.local:18210/auth?t=<token>`.
Station refuses to start with a LAN address if the token (≥ 32 characters) or the allowed names
are missing. Only the listed names are accepted in the Host header; opening Station by any other
name or IP gets `403 forbidden_host`.

Know what this means:

* the traffic is **plain HTTP**: the token and the session cookie can be read by anyone who can
  sniff the network, and **anyone with the token can move the robot**;
* the token stays the same across restarts until you change it in `.env`;
* the e-stop is software. Keep a physical power switch within reach.

For anything beyond a trusted LAN, put a TLS reverse proxy in front (Caddy, nginx) on the same
machine, keep `STATION_BIND=127.0.0.1`, let the proxy keep the original `Host` header and list the
proxy's name in `HIBISCUS_STATION_ALLOWED_HOSTS` (a name without a port also allows the default
HTTPS port). Do not expose Station to the Internet.

## Python wheel + systemd (without Docker)

Needs Python 3.12 via [uv](https://docs.astral.sh/uv/) and your user in the `dialout` and `video`
groups (install the udev rule above as well).

```bash
# x86_64 with an NVIDIA GPU (CUDA wheels from PyPI):
uv tool install https://github.com/Bigkatoan/hibiscus-station/releases/download/v0.2.8/hibiscus_station-0.2.8-py3-none-any.whl
# CPU only (Raspberry Pi 5, PCs without NVIDIA, Jetson without the GPU): CPU PyTorch, much smaller
uv tool install --torch-backend cpu https://github.com/Bigkatoan/hibiscus-station/releases/download/v0.2.8/hibiscus_station-0.2.8-py3-none-any.whl

hibiscus-station --mock          # try it; Ctrl+C to stop
```

On a Jetson the wheel install can only use the CPU (there is no CUDA PyTorch for Python 3.12 on
JetPack 6 outside NVIDIA's containers): use the Docker image for the GPU.

## Windows 10/11 and macOS (wheel)

**Windows 10/11 x64**: one line in PowerShell, no admin rights, no git, no Python (ADR-13):

```powershell
irm https://github.com/Bigkatoan/hibiscus-station/releases/latest/download/install.ps1 | iex
```

The release's `install.ps1` downloads uv (pinned, checked by SHA-256) into
`%LOCALAPPDATA%\HibiscusStation`, then runs `uv tool install --force` of that release's wheel with
its `constraints.txt` (every library of `uv.lock`, exact versions) and `overrides.txt` (lerobot and
the Hibiscus CLI as prebuilt wheels of the release, so no git), all checked against `SHA256SUMS`.
Every install of a release gets the same libraries QC tested (CPU PyTorch). Run the same line again
to update; `irm https://github.com/Bigkatoan/hibiscus-station/releases/download/vX.Y.Z/install.ps1 | iex`
installs exactly version X.Y.Z (roll back). A pre-release is only reachable by its versioned link.
QC / offline: `$env:HIBISCUS_STATION_BASE_URL = "C:\path\to\downloaded\assets"` before the line
installs from a folder (e.g. `gh release download` of a draft).

**macOS** (preview, Apple silicon): the same release assets with uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
base=https://github.com/Bigkatoan/hibiscus-station/releases/download/vX.Y.Z
uv tool install --python 3.12 -c $base/constraints.txt --overrides $base/overrides.txt $base/hibiscus_station-X.Y.Z-py3-none-any.whl
hibiscus-station --mock          # try it; Ctrl+C to stop
```

Windows notes (driver for the CH340/CH343 USB-serial chip of the servo board, `COM3`-style port
names, camera numbers, closing LeLab first) are in the [README](../README.md#windows-1011). There is
no udev rule or systemd unit on these systems: start `hibiscus-station` yourself (or from Task Scheduler / a
launchd agent). Data lives in `~/.hibiscus/station` (`%USERPROFILE%\.hibiscus\station`).

Run it as a user service that starts at boot:

```bash
install -Dm644 deploy/systemd/hibiscus-station.service ~/.config/systemd/user/hibiscus-station.service
systemctl --user daemon-reload
systemctl --user enable --now hibiscus-station
sudo loginctl enable-linger "$USER"          # start at boot without logging in
hibiscus-station url                          # the login link
journalctl --user -u hibiscus-station -f      # logs (also ~/.hibiscus/station/logs/station.log)
```

LAN mode with the service: put `HIBISCUS_STATION_TOKEN`, `HIBISCUS_STATION_ALLOWED_HOSTS` and
`STATION_ARGS=--host 0.0.0.0` in `~/.config/hibiscus-station/station.env`.

Update: `uv tool install --force <new wheel URL>` then `systemctl --user restart hibiscus-station`.
Back up `~/.hibiscus/station` and `~/.cache/huggingface/lerobot/calibration` first (the same
folders as `hibiscus-station-ctl backup`). Roll back by installing the previous wheel.
