"""Teleop latency bench on two emulated STS3215 chains with real wire timing (POSIX only).

Measures, for Station's control loop and for a LeLab-style loop (``app/teleoperating.py``: read the
leader, send to the follower, ``sleep(0.001)``, follower observation every 50 ms, no
``max_relative_target``) driving the same emulated arms:

* **command latency**: leader sample -> Goal_Position received by the follower servo. The leader
  follows a known sine per joint, so the moment the leader was at each written goal is solved
  exactly (writes near a turning point or clipped by the safety filter are not matched);
* **loop Hz**: goal writes per second;
* **clip fraction**: writes whose goal differs from the leader pose (the relative-target cap);
* **tracking lag**: the time shift that best aligns the follower's emulated position with the
  leader's (what the user feels), and the RMS / peak follower error in degrees.

``python tests/teleop_bench.py`` prints a table; ``tests/test_teleop_latency.py`` holds Station to a
latency budget against the LeLab loop.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sts_emulator import RES, STSEmulator, lelab_calibration

DEG = RES / 360.0


@dataclass
class Motion:
    """Leader motion: ``center + amp * sin(2 pi f t + phase)`` per joint (steps, present frame)."""

    name: str
    amp_deg: float
    freq_hz: float

    def peak_deg_s(self) -> float:
        return 2 * math.pi * self.freq_hz * self.amp_deg


NORMAL = Motion("normal", 30.0, 0.5)  # ~94 deg/s peak: an unhurried pick
FAST = Motion("fast", 45.0, 1.2)  # ~340 deg/s peak: a quick human move


def _pct(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q / 100 * (len(s) - 1))))]


@dataclass
class Result:
    loop: str
    motion: str
    latency_ms: list[float] = field(default_factory=list)  # goal age, sampled uniformly in time
    cmd_ms: list[float] = field(default_factory=list)  # leader sample -> goal received, per write
    writes: int = 0
    matched: int = 0
    duration_s: float = 0.0
    loop_hz: float = 0.0
    clip_fraction: float = 0.0
    lag_ms: float = 0.0
    rms_err_deg: float = 0.0
    peak_err_deg: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def p(self, q: float) -> float:
        return _pct(self.latency_ms, q)

    def row(self) -> dict[str, Any]:
        return {
            "loop": self.loop,
            "motion": self.motion,
            "latency_p50_ms": round(self.p(50), 2),
            "latency_p95_ms": round(self.p(95), 2),
            "cmd_p50_ms": round(_pct(self.cmd_ms, 50), 2),
            "loop_hz": round(self.loop_hz, 1),
            "clip_fraction": round(self.clip_fraction, 3),
            "tracking_lag_ms": round(self.lag_ms, 1),
            "rms_err_deg": round(self.rms_err_deg, 2),
            "peak_err_deg": round(self.peak_err_deg, 2),
            **self.extra,
        }


class Arms:
    """Two realistic emulators carrying the same calibration, the leader moving along ``motion``."""

    def __init__(self, motion: Motion, *, usb_in_s: float = 0.001, usb_out_s: float = 0.0005) -> None:
        self.cal = lelab_calibration()
        self.follower = STSEmulator(seed=1).realistic(usb_in_s=usb_in_s, usb_out_s=usb_out_s)
        self.leader = STSEmulator(seed=2).realistic(usb_in_s=usb_in_s, usb_out_s=usb_out_s)
        self.follower.preload_calibration(self.cal)
        self.leader.preload_calibration(self.cal)
        self.motion = motion
        self.center: dict[int, float] = {}
        self.amp: dict[int, float] = {}
        self.phase: dict[int, float] = {}
        for v in self.cal.values():
            i = int(v["id"])
            lo, hi = int(v["range_min"]), int(v["range_max"])
            self.center[i] = (lo + hi) / 2
            self.amp[i] = min(motion.amp_deg * DEG, (hi - lo) / 2 - 60)
            self.phase[i] = i * 0.9
        self.omega = 2 * math.pi * motion.freq_hz
        self.t0 = self.leader._t0
        self.leader.hand = lambda i, t: self.pos(i, self.t0 + t)

    def pos(self, i: int, t_abs: float) -> float:
        return self.center[i] + self.amp[i] * math.sin(self.omega * (t_abs - self.t0) + self.phase[i])

    def when(self, i: int, goal: float, t_write: float) -> float | None:
        """Latest time <= ``t_write`` the leader joint ``i`` was at ``goal`` (None near a turn)."""
        x = (goal - self.center[i]) / self.amp[i]
        if abs(x) > 0.95:  # near a turning point: ambiguous, skip
            return None
        theta_w = self.omega * (t_write - self.t0) + self.phase[i]
        best: float | None = None
        for theta_c in (math.asin(x), math.pi - math.asin(x)):
            k = math.floor((theta_w - theta_c) / (2 * math.pi))
            t = (theta_c + 2 * math.pi * k - self.phase[i]) / self.omega + self.t0
            if best is None or t > best:
                best = t
        return best

    def write_calibration_files(self, cal_root: Path, follower_id: str, leader_id: str) -> None:
        for sub, cid in (("robots/so_follower", follower_id), ("teleoperators/so_leader", leader_id)):
            d = cal_root / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{cid}.json").write_text(json.dumps(self.cal), encoding="utf-8")

    def close(self) -> None:
        self.follower.close()
        self.leader.close()


CLIPS: list[tuple[float, frozenset[str]]] = []  # (monotonic, joints clipped) per SafetyFilter.apply


def _record_clips() -> None:
    """Wrap Station's SafetyFilter so the bench knows which writes the relative cap changed."""
    from hibiscus_station.hw.safety import SafetyFilter

    if getattr(SafetyFilter.apply, "_bench", False):
        return
    orig = SafetyFilter.apply

    def apply(self: Any, action: Any, obs: Any) -> Any:
        safe, clipped = orig(self, action, obs)
        CLIPS.append((time.monotonic(), frozenset(clipped)))
        return safe, clipped

    apply._bench = True  # type: ignore[attr-defined]
    SafetyFilter.apply = apply  # type: ignore[method-assign]


MOTOR_BY_ID = {
    1: "shoulder_pan",
    2: "shoulder_lift",
    3: "elbow_flex",
    4: "wrist_flex",
    5: "wrist_roll",
    6: "gripper",
}


def measure(arms: Arms, duration_s: float, loop: str) -> Result:
    """Record goals and follower positions for ``duration_s`` and compute the metrics."""
    import bisect

    f = arms.follower
    f.goal_log.clear()
    CLIPS.clear()
    f.record_goals = True
    samples: list[tuple[float, dict[int, float]]] = []
    stop = threading.Event()

    def sampler() -> None:
        while not stop.is_set():
            samples.append((time.monotonic(), f.sample()))
            time.sleep(0.002)

    th = threading.Thread(target=sampler, daemon=True)
    t_start = time.monotonic()
    th.start()
    time.sleep(duration_s)
    stop.set()
    th.join()
    f.record_goals = False
    t_end = time.monotonic()
    res = Result(loop, arms.motion.name, duration_s=t_end - t_start)
    log = list(f.goal_log)
    res.writes = len(log)
    ids = sorted(arms.center)
    per_motor = [x for x in log if x[1] == ids[0]]
    res.loop_hz = len(per_motor) / res.duration_s
    clips = list(CLIPS)
    clip_t = [c[0] for c in clips]
    ticks = [c for c in clips if c[0] >= t_start]
    res.clip_fraction = sum(1 for c in ticks if c[1]) / len(ticks) if ticks else 0.0
    writes: dict[int, list[tuple[float, float | None]]] = {i: [] for i in arms.center}
    for t_w, i, g in log:
        if i not in arms.center:
            continue
        k = bisect.bisect_right(clip_t, t_w) - 1
        t_l = None
        if k < 0 or MOTOR_BY_ID[i] not in clips[k][1]:  # else the cap moved it: not a leader sample
            t_l = arms.when(i, float(g), t_w)
        writes[i].append((t_w, t_l))
        if t_l is None:
            continue
        res.cmd_ms.append((t_w - t_l) * 1000)
        res.matched += 1
    # goal age: at any moment, how old is the leader pose the follower is being sent to
    for ws in writes.values():
        tw = [w[0] for w in ws]
        for t, _pos in samples:
            k = bisect.bisect_right(tw, t) - 1
            if k >= 0 and ws[k][1] is not None:
                res.latency_ms.append((t - ws[k][1]) * 1000)  # type: ignore[operator]
    # tracking: follower(t) vs leader(t - tau)
    arm_ids = [i for i in ids if i != 6]  # gripper excluded (it saturates on the jaw)
    import numpy as np

    ts = np.array([t for t, _ in samples])
    fol = np.array([[pos[i] for i in arm_ids] for _, pos in samples])
    center = np.array([arms.center[i] for i in arm_ids])
    amp = np.array([arms.amp[i] for i in arm_ids])
    phase = np.array([arms.phase[i] for i in arm_ids])

    def leader_at(t: Any) -> Any:
        return center + amp * np.sin(arms.omega * (t[:, None] - arms.t0) + phase)

    taus = np.arange(0, 0.301, 0.001)
    sse = [float(((fol - leader_at(ts - tau)) ** 2).sum()) for tau in taus]
    res.lag_ms = float(taus[int(np.argmin(sse))]) * 1000
    err = np.abs(fol - leader_at(ts)) / DEG
    res.rms_err_deg = float(np.sqrt((err**2).mean())) if err.size else 0.0
    res.peak_err_deg = float(err.max()) if err.size else 0.0
    return res


# ------------------------------------------------------------------------------------ loops
def run_lelab(arms: Arms, cal_root: Path, duration_s: float, settle_s: float = 1.0) -> Result:
    """LeLab's teleoperation worker (app/teleoperating.py) on the emulated arms."""
    from lerobot.robots.so_follower import SOFollower, SOFollowerRobotConfig
    from lerobot.teleoperators.so_leader import SOLeader, SOLeaderTeleopConfig

    arms.write_calibration_files(cal_root, "lelab_follower", "lelab_leader")
    robot = SOFollower(
        SOFollowerRobotConfig(
            port=arms.follower.port, id="lelab_follower", calibration_dir=cal_root / "robots/so_follower"
        )
    )
    teleop = SOLeader(
        SOLeaderTeleopConfig(
            port=arms.leader.port, id="lelab_leader", calibration_dir=cal_root / "teleoperators/so_leader"
        )
    )
    robot.bus.connect()
    teleop.bus.connect()
    robot.bus.write_calibration(robot.calibration)
    teleop.bus.write_calibration(teleop.calibration)
    robot.configure()
    teleop.configure()
    active = threading.Event()
    active.set()

    def worker() -> None:
        last = 0.0
        while active.is_set():
            action = teleop.get_action()
            robot.send_action(action)
            now = time.time()
            if now - last >= 0.05:
                robot.get_observation()
                last = now
            time.sleep(0.001)

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    try:
        time.sleep(settle_s)
        res = measure(arms, duration_s, "lelab")
    finally:
        active.clear()
        th.join(2)
        robot.disconnect()
        teleop.disconnect()
    return res


def run_station(
    arms: Arms,
    home: Path,
    cal_root: Path,
    duration_s: float,
    *,
    fps: int | None = None,
    settle_s: float = 1.0,
    configure: Callable[[Any], None] | None = None,
) -> Result:
    """Station (real profile types, rustypot) in teleop on the emulated arms."""
    from hibiscus_station.profiles import FollowerProfile, LeaderProfile, RobotProfile
    from hibiscus_station.station import Station, TeleopRequest

    arms.write_calibration_files(cal_root, "arm_follower", "arm_leader")
    _record_clips()
    st = Station(home, mock=False, cal_root=cal_root)
    st.settings.safety.smooth_approach_s = 0.3
    st.settings.safety.max_approach_deg = 360.0  # the leader keeps moving: approach from anywhere
    st.profiles.put(
        RobotProfile(
            id="arm",
            follower=FollowerProfile(port=arms.follower.port, calibration_id="arm_follower"),
            leader=LeaderProfile(port=arms.leader.port, calibration_id="arm_leader"),
        )
    )
    if configure is not None:
        configure(st)
    st.start()
    try:
        st.owner.call("connect", robot_id="arm", timeout=30)
        hb = threading.Event()

        def beat() -> None:
            while not hb.is_set():
                st.owner.heartbeat()
                time.sleep(0.1)

        threading.Thread(target=beat, daemon=True).start()
        req = TeleopRequest() if fps is None else TeleopRequest(fps=fps)
        st.start_teleop(req)
        time.sleep(settle_s)
        assert st.owner.state == "teleop", st.owner.state
        loop0 = dict(st.owner.stats.snapshot())
        res = measure(arms, duration_s, f"station@{req.fps}")
        snap = st.owner.stats.snapshot()
        res.extra = {
            "station_fps": snap.get("fps"),
            "station_latency_ms_p50": snap.get("latency_ms_p50"),
            "telemetry_reads": st.owner.telemetry.reads,
            "overruns": int(snap.get("overruns", 0)) - int(loop0.get("overruns", 0)),
        }
        hb.set()
    finally:
        st.shutdown()
    return res


def main(argv: list[str] | None = None) -> int:
    import tempfile

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--duration", type=float, default=4.0)
    ap.add_argument("--usb-in-ms", type=float, default=1.0, help="USB latency timer (adapter -> host)")
    ap.add_argument("--usb-out-ms", type=float, default=0.5)
    ap.add_argument(
        "--fps", type=int, nargs="*", default=[], help="Station fps to try (default: its default)"
    )
    ap.add_argument("--motion", choices=["normal", "fast", "both"], default="both")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    motions = [NORMAL, FAST] if a.motion == "both" else [NORMAL if a.motion == "normal" else FAST]
    rows: list[dict[str, Any]] = []
    for m in motions:
        for which in ["lelab", *(["station"] if not a.fps else [f"station:{x}" for x in a.fps])]:
            arms = Arms(m, usb_in_s=a.usb_in_ms / 1000, usb_out_s=a.usb_out_ms / 1000)
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    if which == "lelab":
                        r = run_lelab(arms, Path(tmp) / "cal", a.duration)
                    else:
                        fps = int(which.split(":")[1]) if ":" in which else None
                        r = run_station(arms, Path(tmp) / "home", Path(tmp) / "cal", a.duration, fps=fps)
                finally:
                    arms.close()
            rows.append(r.row())
            print(json.dumps(r.row()), flush=True)
    if not a.json:
        keys = list(rows[0])
        print("| " + " | ".join(keys) + " |")
        print("|" + "---|" * len(keys))
        for row in rows:
            print("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
