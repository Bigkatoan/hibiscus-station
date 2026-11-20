"""QC: run the INSTALLED hibiscus-station doctor against QC's fault server, one scenario per dir."""
import json, os, subprocess, sys, time, zipfile, signal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path(sys.argv[1]); BUILD = sys.argv[5]; scen = json.loads(Path(sys.argv[2]).read_text()); outroot = Path(sys.argv[3]); par = int(sys.argv[4])
EXE = str(S.parent / f"bin-{BUILD}/hibiscus-station")
TESTS = str(S.parent / "src-head/tests")
CAL = {"shoulder_pan": {"id": 1, "drive_mode": 0, "homing_offset": 44, "range_min": 684, "range_max": 3413},
 "shoulder_lift": {"id": 2, "drive_mode": 0, "homing_offset": 81, "range_min": 887, "range_max": 3267},
 "elbow_flex": {"id": 3, "drive_mode": 0, "homing_offset": 396, "range_min": 885, "range_max": 3122},
 "wrist_flex": {"id": 4, "drive_mode": 0, "homing_offset": -347, "range_min": 859, "range_max": 3190},
 "wrist_roll": {"id": 5, "drive_mode": 0, "homing_offset": -1194, "range_min": 0, "range_max": 4095},
 "gripper": {"id": 6, "drive_mode": 0, "homing_offset": -545, "range_min": 1761, "range_max": 3231}}
def one(item):
    name, cfg = item
    d = outroot / name; d.mkdir(parents=True, exist_ok=True)
    home = d / "user"; (home / ".hibiscus/station").mkdir(parents=True, exist_ok=True)
    cfg.setdefault("follower", {}).setdefault("lelab", True)
    srv = subprocess.Popen(["/usr/bin/python3", str(S / "qc/emu_server.py"), TESTS, json.dumps(cfg), str(d / "emu")])
    for _ in range(100):
        if (d / "emu.ports").exists(): break
        time.sleep(0.05)
    ports = json.loads((d / "emu.ports").read_text())
    import yaml  # noqa
    prof = {"id": "desk", "name": "Desk", "follower": {"type": "so101_follower", "port": ports["follower"], "calibration_id": "desk_follower"},
            "leader": {"type": "so101_leader", "port": ports["leader"], "calibration_id": "desk_leader"}, "cameras": {}, "safety_ack": True}
    (home / ".hibiscus/station/robots.yaml").write_text(yaml.safe_dump({"version": 1, "active": "desk", "robots": [prof]}))
    cd = home / ".cache/huggingface/lerobot/calibration/robots/so_follower"; cd.mkdir(parents=True, exist_ok=True)
    (cd / "desk_follower.json").write_text(json.dumps(CAL, indent=4))
    args = [EXE, "doctor", "--no-cameras", "--out", str(d)] + cfg.get("args", [])
    t = time.time()
    p = subprocess.run(["env", "-i", f"HOME={home}", "PATH=/usr/bin:/bin"] + args, capture_output=True, text=True, timeout=600)
    el = time.time() - t
    srv.send_signal(signal.SIGTERM); srv.wait(10)
    (d / "stdout.txt").write_text(p.stdout); (d / "stderr.txt").write_text(p.stderr)
    z = sorted(d.glob("hibiscus-station-doctor-*.zip"))
    if z:
        with zipfile.ZipFile(z[-1]) as zf:
            (d / "report.json").write_bytes(zf.read("report.json")); (d / "report.txt").write_bytes(zf.read("report.txt"))
    return name, p.returncode, round(el, 1)
with ThreadPoolExecutor(par) as ex:
    for r in ex.map(one, scen.items()):
        print(*r, flush=True)
