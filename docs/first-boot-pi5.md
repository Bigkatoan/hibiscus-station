# First boot: Raspberry Pi 5

A checklist for turning a fresh Raspberry Pi 5 into a Hibiscus Station box. Tick each line; keep the
filled-in copy with your lab notes. Afterwards run the hardware checklist
([user-guide/en/station-hardware-uat.md](user-guide/en/station-hardware-uat.md)).

## Hardware

* [ ] Raspberry Pi 5, **8 GB** recommended (4 GB works for teleop, recording and ACT; not for bigger
      models).
* [ ] The official 27 W USB-C power supply. With a weaker supply the Pi limits USB current and the
      servo adapters or cameras drop out under load.
* [ ] Active cooler fitted (models and video encoding keep the CPU busy; it throttles at 85 °C).
* [ ] Storage: a 64 GB+ A2 microSD, or better an NVMe SSD on an M.2 HAT (datasets are written while
      recording; slow cards cause dropped frames).
* [ ] Servo bus adapters and cameras on the **blue USB 3 ports**; with two cameras or more, a
      powered USB 3 hub. The arms' servos are powered by their own supply, never by the Pi.
* [ ] A way to cut the arms' power by hand.

## Operating system

* [ ] **Raspberry Pi OS (64-bit), Bookworm or newer**, Lite is enough (Raspberry Pi Imager: set the
      host name, e.g. `robot-pi`, your user, SSH with a key, Wi-Fi country, time zone).
* [ ] `sudo apt update && sudo apt full-upgrade -y && sudo reboot`
* [ ] `uname -m` prints `aarch64`.
* [ ] Page size: `getconf PAGESIZE`. The Pi 5 kernel uses 16384 by default. If Station later fails
      to start with a page-size or `jemalloc` error in `hibiscus-station-ctl logs`, switch to the
      4 KB kernel: add `kernel=kernel8.img` to `/boot/firmware/config.txt` and reboot
      (`getconf PAGESIZE` then prints 4096). Note what you use: ______
* [ ] Time is right (`timedatectl`; NTP synchronized: yes). Recording timestamps and TLS depend on it.
* [ ] Free space ≥ 20 GB: `df -h /` (the image is about 3 GB, datasets grow fast).
* [ ] USB current: with the 27 W supply the Pi 5 allows 1.6 A in total on its USB ports
      (`vcgencmd get_config usb_max_current_enable` prints 1). With another supply it stays at
      600 mA: use a powered hub for the cameras.

## Install

* [ ] `curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh`
* [ ] `bash install.sh` → variant `cpu` detected; answer yes to Docker, groups and the udev rule.
* [ ] Log out and back in (new groups), then `hibiscus-station-ctl status` → `healthy`.
* [ ] On your laptop: `ssh -N -L 18210:127.0.0.1:18210 <user>@robot-pi.local`, then open the link from
      `hibiscus-station-ctl url`. Or set up LAN mode ([deploy.md](deploy.md#open-station-on-the-lan-opt-in)).
* [ ] Plug in the follower and leader adapters: `hibiscus-station-ctl ports` lists two ports with
      `/dev/serial/by-id/...` and `/dev/hibiscus/arm-...` names.
* [ ] Cameras: `ls /dev/v4l/by-id/` lists each camera.

## First run

* [ ] Robot screen: create the profile with the by-id ports; connect; temperatures shown.
* [ ] Calibrate both arms; check the Robot 3D view follows the real arm (UAT 7.1, 7.2).
* [ ] Cameras: add them; the measured fps is ≥ 90 % of the requested fps (else lower the resolution
      or use MJPG, or move a camera to the other USB 3 port).
* [ ] Teleop for 10 minutes: no overrun warning (Pi 5 at 30 Hz with two 640×480 cameras is the
      target); CPU temperature `vcgencmd measure_temp` stays below 80 °C.
* [ ] Reboot without logging in; Station is healthy again within 3 minutes (UAT 8.4).
* [ ] `hibiscus-station-ctl backup` works; copy one backup off the Pi.

## Expectations on a Pi 5

* Teleop, recording, upload, trajectories, programs and colour detectors: full speed.
* Models run on the CPU. ACT at 30 fps is borderline: note the inference p95 on the Run-model
  screen. Station pauses the run instead of queueing stale actions when the model is too slow;
  lower the fps (15) or run the model on a PC/Jetson. Diffusion, SmolVLA and π0 are too slow.
