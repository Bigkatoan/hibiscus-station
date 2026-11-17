# First boot: NVIDIA Jetson Orin (JetPack 6)

A checklist for a Jetson Orin Nano, Orin NX or AGX Orin running Hibiscus Station with GPU inference.
Tick each line and keep the filled-in copy. Afterwards run the hardware checklist
([user-guide/en/station-hardware-uat.md](user-guide/en/station-hardware-uat.md)).

> The `jetson` image is built on NVIDIA's NGC PyTorch container for integrated GPUs
> (`nvcr.io/nvidia/pytorch:26.02-py3-igpu`: Ubuntu 24.04, Python 3.12, CUDA 12.9 for Tegra, PyTorch
> built for the Orin GPU). It was build-checked under emulation but **not yet run on a real Jetson**:
> this checklist is how to confirm it on yours. Report the result in an issue either way.

## Hardware

* [ ] Jetson Orin Nano / Orin NX (8 GB or more recommended) or AGX Orin, on a carrier board with
      USB 3 ports. Orin Nano 4 GB: teleop and recording only.
* [ ] Storage: an **NVMe SSD** (the image is large: about 15 GB on disk; datasets come on top).
      Boot from the SSD if you can.
* [ ] The power supply that came with the kit; power mode set high enough for inference
      (`sudo nvpmodel -q`; e.g. `sudo nvpmodel -m 0` for MAXN). Note the mode: ______
* [ ] Fan running (`sudo jetson_clocks --show`; `jtop` from `jetson-stats` is handy).
* [ ] Servo bus adapters and cameras on USB 3, a powered hub for two cameras or more. The arms'
      servos have their own supply.
* [ ] A way to cut the arms' power by hand.

## JetPack

* [ ] **JetPack 6.x (L4T R36.x)**: `cat /etc/nv_tegra_release` shows `# R36`. JetPack 5 (R35) is not
      supported by the `jetson` image; the installer falls back to the `cpu` image there.
* [ ] `sudo apt update && sudo apt full-upgrade -y`, reboot.
* [ ] NVIDIA Container Toolkit for Docker (part of JetPack; else
      `sudo apt install nvidia-container-toolkit`), then
      `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.
* [ ] `docker info | grep -i runtimes` lists `nvidia`.
* [ ] Free space ≥ 40 GB: `df -h /`.
* [ ] Time is right (`timedatectl`).

## Install

* [ ] `curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh`
* [ ] `bash install.sh` → variant `jetson` detected (`COMPOSE_FILE=compose.yml:compose.jetson.yml` in
      `~/.config/hibiscus-station/.env`). The first pull takes a while (about 6 GB).
* [ ] Log out and back in, `hibiscus-station-ctl status` → `healthy`.
* [ ] GPU visible inside the container:
      `docker exec hibiscus-station python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`
      prints `True` and `Orin`. Result: ______
* [ ] Tunnel from your laptop (`ssh -N -L 18210:127.0.0.1:18210 <user>@<jetson>`) and open the link
      from `hibiscus-station-ctl url`, or set up LAN mode ([deploy.md](deploy.md#open-station-on-the-lan-opt-in)).
* [ ] `hibiscus-station-ctl ports` lists the two servo adapters with stable names.

## First run

* [ ] Robot profile, connect, calibrate both arms; Robot 3D view matches the real arm (UAT 7.1, 7.2).
* [ ] Cameras added, measured fps ≥ 90 % of the requested fps.
* [ ] Settings: device `auto` or `cuda`. Run model with an ACT bundle: the Run-model screen shows
      device `cuda` and an inference p95 well under the frame time (30 fps → 33 ms). p50/p95:
      ______ / ______ ms.
* [ ] A run of 10 minutes: no overrun pauses, GPU/CPU temperatures stable (`jtop`).
* [ ] Reboot without logging in; healthy within 3 minutes.
* [ ] `hibiscus-station-ctl backup` works; copy one backup off the Jetson.

## If the GPU is not used

* `torch.cuda.is_available()` is `False`: the container did not start with the NVIDIA runtime.
  Check `COMPOSE_FILE` in `.env` and `docker info | grep -i runtime`, then `hibiscus-station-ctl up`.
* `CUDA driver version is insufficient`: JetPack is older than the CUDA in the image. Update
  JetPack 6 to the latest 6.x release.
* As a fallback the `cpu` image runs on the Jetson's CPU (`hibiscus-station-ctl update 0.2.8-cpu`).
