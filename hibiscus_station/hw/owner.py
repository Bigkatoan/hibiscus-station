"""HardwareOwner: the ONLY thread that touches ``robot.bus`` / ``teleop.bus`` (spec §4.2-§4.5).

REST/WS handlers post a :class:`Command` and wait for its future; the owner answers between ticks.
The e-stop is a ``threading.Event`` set straight from any thread (no queue) and checked at the start
of every tick and again between inference and ``send_action``.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hibiscus_station import __version__
from hibiscus_station.data.sessions import SessionLog
from hibiscus_station.errors import StationError
from hibiscus_station.hw import calibration as calib
from hibiscus_station.hw.cameras import CameraHub, FrameSet
from hibiscus_station.hw.factory import build_follower, build_leader
from hibiscus_station.hw.locks import DeviceBusyError, DeviceLock
from hibiscus_station.hw.loop import Deadline, LoopStats
from hibiscus_station.hw.safety import EStop, SafetyFilter, Watchdog
from hibiscus_station.hw.telemetry import (
    Alert,
    CriticalEvent,
    TelemetryRead,
    TelemetryScheduler,
    ThermalGuard,
)
from hibiscus_station.profiles import ProfileStore, RobotProfile
from hibiscus_station.sessions.base import MotionSession, TickInput
from hibiscus_station.settings import Settings, StationPaths, Thresholds, threshold_problems

log = logging.getLogger(__name__)

MOTION_STATES = {
    "teleop": "teleop",
    "record": "recording",
    "replay": "replaying",
    "run": "inferring",
    # station-programs.md §3, §5.1 (sessions land with teams A/B; the loop already drives them)
    "traj_record": "recording_traj",
    "traj_play": "playing",
    "program": "programming",
}
BUS_FAIL_LIMIT = 3
MONITOR_HZ = 10.0
CALIBRATION_HZ = 50.0


@dataclass
class Command:
    name: str
    kwargs: dict[str, Any]
    future: Future[Any] = field(default_factory=Future)


Listener = Callable[[str, dict[str, Any]], None]


def normalized_ranges(device: Any) -> dict[str, tuple[float, float]]:
    """Calibrated range of each motor in lerobot's normalised units (degrees / 0-100)."""
    from lerobot.motors import MotorNormMode

    bus = device.bus
    out: dict[str, tuple[float, float]] = {}
    if not bus.calibration:
        return out
    for m, motor in bus.motors.items():
        cal = bus.calibration.get(m)
        if cal is None:
            continue
        if motor.norm_mode is MotorNormMode.DEGREES:
            mid = (cal.range_min + cal.range_max) / 2
            res = bus.resolution(motor.model) - 1
            out[f"{m}.pos"] = ((cal.range_min - mid) * 360 / res, (cal.range_max - mid) * 360 / res)
        elif motor.norm_mode is MotorNormMode.RANGE_0_100:
            out[f"{m}.pos"] = (0.0, 100.0)
        else:
            out[f"{m}.pos"] = (-100.0, 100.0)
    return out


class HardwareOwner:
    def __init__(
        self,
        paths: StationPaths,
        settings: Settings,
        profiles: ProfileStore,
        hub: CameraHub,
        *,
        cal_root: Path,
        mock: bool = False,
    ) -> None:
        self.paths = paths
        self.settings = settings
        self.profiles = profiles
        self.hub = hub
        self.cal_root = cal_root
        self.mock = mock
        self.state = "disconnected"
        self.sub: str | None = None
        self.reason: str | None = None
        self.detail: str | None = None
        self.profile: RobotProfile | None = None
        self.follower: Any = None
        self.leader: Any = None
        self.follower_calibrated = False
        self.leader_calibrated = False
        self.follower_torque = False
        self.locks: list[DeviceLock] = []
        self.telemetry = TelemetryScheduler(settings.telemetry)
        self.guard = ThermalGuard(settings.thresholds)
        self.estop = EStop(settings.safety.estop_double_press_s)
        self.watchdog = Watchdog(settings.safety.deadman_timeout_s)
        self.safety = SafetyFilter(settings.safety.max_relative_target)
        self.session: MotionSession | None = None
        self.session_log: SessionLog | None = None
        self.calibration: calib.CalibrationProcess | None = None
        self.stats = LoopStats()
        self.alerts: dict[str, Alert] = {}
        self.listeners: list[Listener] = []
        self.status_hook: Callable[[dict[str, Any]], None] | None = None
        self.tick = 0
        self.last_obs: dict[str, float] = {}
        self.last_leader: dict[str, float] = {}
        self.last_sent: dict[str, float] = {}
        self.last_clipped: list[str] = []
        self.last_action: dict[str, float] = {}
        self.bus_failures = 0
        self.relaxed_in_estop = False
        self.last_session_summary: dict[str, Any] | None = None
        self.loaded_model: str | None = None
        self.policy_clipping_alert = False
        self._q: queue.Queue[Command | None] = queue.Queue(maxsize=128)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_monitor_tel = 0.0
        self._last_session_emit = 0.0
        self._last_cal_emit = 0.0
        self._camera_alerted: set[str] = set()
        self.ident: int | None = None

    # ================================================================== lifecycle (any thread)
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="hardware-owner", daemon=True)
            self._thread.start()

    def shutdown(self, timeout: float = 15.0) -> None:
        if self._thread is None:
            return
        try:
            self.call("disconnect", timeout=timeout)
        except Exception as exc:  # pragma: no cover - best effort
            log.warning("disconnect at shutdown: %s", exc)
        self._stop.set()
        self._wake()
        self._thread.join(timeout=timeout)
        self._thread = None

    def add_listener(self, fn: Listener) -> None:
        self.listeners.append(fn)

    def remove_listener(self, fn: Listener) -> None:
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _wake(self) -> None:
        try:
            self._q.put_nowait(None)
        except queue.Full:  # pragma: no cover
            pass

    def call(self, name: str, timeout: float = 5.0, **kwargs: Any) -> Any:
        """Run a command in the owner thread and return its result (raises StationError)."""
        if self._thread is None:
            raise StationError("internal_error", "hardware owner not running")
        if threading.get_ident() == self.ident:
            return self._dispatch(name, kwargs)
        cmd = Command(name, kwargs)
        try:
            self._q.put(cmd, timeout=1.0)
        except queue.Full as exc:
            raise StationError("hardware_timeout", "command queue full") from exc
        try:
            return cmd.future.result(timeout=timeout)
        except TimeoutError as exc:
            raise StationError("hardware_timeout", f"{name} did not finish in {timeout:.0f} s") from exc

    def press_estop(
        self, reason: str = "user", *, relax: bool = False, detail: str | None = None
    ) -> dict[str, Any]:
        """Any thread, no queue: takes effect at the next check (at most one tick)."""
        press = self.estop.press(reason, relax=relax, detail=detail)
        self._wake()
        return {"relax": press.relax, "t": press.t}

    def heartbeat(self) -> None:
        self.watchdog.beat()

    # ================================================================== events
    def emit(self, kind: str, payload: dict[str, Any]) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, payload)
            except Exception:  # pragma: no cover - a listener must never break the loop
                log.exception("listener failed")

    def _set_state(
        self, state: str, sub: str | None = None, reason: str | None = None, detail: str | None = None
    ) -> None:
        self.state, self.sub, self.reason, self.detail = state, sub, reason, detail
        self.emit("state", self.status())

    def _alert(self, a: Alert) -> None:
        if a.active:
            self.alerts[a.id] = a
        else:
            self.alerts.pop(a.id, None)
        payload = a.as_dict()
        payload["t"] = round(self.session_now(), 3)
        self.emit("alert", payload)
        if self.session_log is not None:
            self.session_log.line({"t": payload["t"], "alert": payload})

    def raise_alert(
        self,
        kind: str,
        level: str,
        message_key: str,
        params: dict[str, Any] | None = None,
        *,
        active: bool = True,
        **kw: Any,
    ) -> None:
        aid = f"{kind}:{message_key}" + (f":{kw.get('camera')}" if kw.get("camera") else "")
        self._alert(
            Alert(
                aid,
                time.monotonic(),
                level,
                kind,
                message_key=message_key,
                params=params or {},
                active=active,
                **kw,
            )
        )

    def session_now(self) -> float:
        return time.monotonic() - self.session.t0 if self.session is not None else 0.0

    # ================================================================== status (any thread)
    def status(self) -> dict[str, Any]:
        p = self.profile
        robot = None
        if p is not None:
            arms: dict[str, Any] = {
                "follower": {"port": p.follower.port, "calibrated": self.follower_calibrated}
            }
            if p.leader is not None:
                arms["leader"] = {"port": p.leader.port, "calibrated": self.leader_calibrated}
            robot = {
                "id": p.id,
                "name": p.name,
                "connected": self.follower is not None,
                "follower_torque": self.follower_torque,
                "arms": arms,
            }
        sess = self.session
        try:
            cams = self.hub.status()
        except RuntimeError:  # pragma: no cover - dict changed during iteration
            cams = []
        out = {
            "station": {"version": __version__, "lerobot": "0.7.1", "mock": self.mock},
            "state": self.state,
            "sub": self.sub if sess is None else sess.episode.phase,
            "reason": self.reason,
            "detail": self.detail,
            "robot": robot,
            "cameras": cams,
            "health": self.guard.overall(),
            "alerts": [a.as_dict() for a in list(self.alerts.values())],
            "session": sess.view() if sess is not None else None,
            "last_session": self.last_session_summary,
            "loaded_model": self.loaded_model,
        }
        if self.status_hook is not None:  # the Station adds device, home, server (same on REST and WS)
            self.status_hook(out)
        return out

    # ================================================================== thread body
    def _run(self) -> None:
        self.ident = threading.get_ident()
        if sys.platform != "win32":  # Windows has no nice(); the 1 ms timer is set by the CLI
            try:
                os.nice(-5)
            except OSError:
                pass
        while not self._stop.is_set():
            try:
                if self.session is not None and self.state in MOTION_STATES.values():
                    self._motion_tick()
                elif self.state == "calibrating":
                    self._calibration_tick()
                elif self.state in ("idle", "estopped"):
                    self._monitor_tick()
                else:
                    self._wait_until(time.perf_counter() + 0.2)
            except Exception as exc:
                log.exception("hardware owner loop failed")
                self._fail("internal", f"{type(exc).__name__}: {exc}")

    def _exec(self, cmd: Command) -> None:
        if cmd.future.set_running_or_notify_cancel():
            try:
                cmd.future.set_result(self._dispatch(cmd.name, cmd.kwargs))
            except BaseException as exc:
                cmd.future.set_exception(exc)

    def _dispatch(self, name: str, kwargs: dict[str, Any]) -> Any:
        handler = getattr(self, f"_cmd_{name}", None)
        if handler is None:
            raise StationError("internal_error", f"unknown command {name}")
        return handler(**kwargs)

    def _wait_until(self, deadline: float) -> None:
        """Sleep until ``deadline`` (perf_counter) while serving commands; wakes early on e-stop."""
        while True:
            rem = deadline - time.perf_counter()
            if rem <= 0:
                return
            try:
                cmd = self._q.get(timeout=rem)
            except queue.Empty:
                return
            if cmd is not None:
                self._exec(cmd)
            if self.estop.is_set and self.state not in ("estopped", "disconnected", "error"):
                return
            if self._stop.is_set():
                return

    def _drain(self) -> None:
        while True:
            try:
                cmd = self._q.get_nowait()
            except queue.Empty:
                return
            if cmd is not None:
                self._exec(cmd)

    # ================================================================== bus helpers (owner thread)
    def _read_follower(self) -> dict[str, float] | None:
        try:
            if self.follower_calibrated:
                obs = self.follower.get_observation()
            else:
                raw = self.follower.bus.sync_read("Present_Position", normalize=False, num_retry=1)
                obs = {f"{m}.pos": float(v) for m, v in raw.items()}
        except (ConnectionError, RuntimeError, OSError) as exc:
            self.bus_failures += 1
            log.warning("follower read failed (%d): %s", self.bus_failures, exc)
            if self.bus_failures >= BUS_FAIL_LIMIT:
                self._fail("bus_lost", str(exc)[:200])
            return None
        self.bus_failures = 0
        self.last_obs = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        return obs  # type: ignore[no-any-return]

    def _read_leader(self) -> dict[str, float] | None:
        if self.leader is None:
            return None
        try:
            if self.leader_calibrated:
                act = self.leader.get_action()
            else:
                raw = self.leader.bus.sync_read("Present_Position", normalize=False, num_retry=1)
                act = {f"{m}.pos": float(v) for m, v in raw.items()}
        except (ConnectionError, RuntimeError, OSError) as exc:
            self.bus_failures += 1
            if self.bus_failures >= BUS_FAIL_LIMIT:
                self._fail("bus_lost", f"leader: {exc}"[:200])
            return None
        self.last_leader = {k: float(v) for k, v in act.items()}
        return self.last_leader

    def _hold(self) -> None:
        """Freeze: Goal_Position := Present_Position (torque stays on)."""
        if self.follower is None:
            return
        try:
            raw = self.follower.bus.sync_read("Present_Position", normalize=False, num_retry=2)
            self.follower.bus.sync_write(
                "Goal_Position", {m: int(v) for m, v in raw.items()}, normalize=False
            )
        except Exception as exc:
            log.warning("hold failed: %s", exc)

    def _torque_off(self) -> None:
        if self.follower is None:
            return
        try:
            self.follower.bus.disable_torque(num_retry=5)
            self.follower_torque = False
        except Exception as exc:
            log.error("disable_torque failed: %s", exc)

    def _torque_on(self) -> None:
        bus = self.follower.bus
        raw = bus.sync_read("Present_Position", normalize=False, num_retry=2)
        bus.sync_write("Goal_Position", {m: int(v) for m, v in raw.items()}, normalize=False)
        bus.enable_torque(num_retry=2)
        self.follower_torque = True

    def _park(self, duration_s: float) -> bool:
        """Smooth move to the profile's rest pose (each step through the SafetyFilter)."""
        p = self.profile
        if p is None or not p.follower.rest_pose or not self.follower_calibrated or not self.follower_torque:
            return False
        start = dict(self.last_obs)
        target = {k: float(v) for k, v in p.follower.rest_pose.items() if k in start}
        if not target:
            return False
        fps = 30
        steps = max(1, int(duration_s * fps))
        for i in range(1, steps + 1):
            if self.estop.relax_event.is_set():
                return False
            a = i / steps
            goal = {k: start[k] * (1 - a) + target.get(k, start[k]) * a for k in start}
            obs = self._read_follower()
            if obs is None:
                return False
            safe, _ = self.safety.apply(goal, obs)
            try:
                self.follower.send_action(safe)
            except Exception as exc:
                log.warning("park step failed: %s", exc)
                return False
            time.sleep(1.0 / fps)
        return True

    # ================================================================== telemetry
    def _handle_read(self, read: TelemetryRead) -> None:
        at = self.telemetry.arms.get(read.arm)
        if at is None:
            return
        t = round(self.session_now(), 3)
        if read.degraded:
            self.raise_alert(
                "telemetry_degraded",
                "warn",
                "telemetry.degraded",
                {"arm": read.arm, "group": read.group},
                arm=read.arm,
            )
        alerts = self.guard.update(read, at.limits) if read.ok else []
        motors = {m: at.motor_view(m, self.guard.level(read.arm, m)) for m in at.motors}
        self.emit(
            "telemetry",
            {
                "t": t,
                "arm": read.arm,
                "group": read.group,
                "motors": motors,
                "limits": at.limits.as_dict(),
                "forced": read.forced,
            },
        )
        line = {
            "t": t,
            "tick": self.tick,
            "state": self.state,
            "arm": read.arm,
            "group": read.group,
            "temp_c": dict(at.values["temp_c"]),
            "voltage_v": dict(at.values["voltage_v"]),
            "current_a": dict(at.values["current_a"]),
            "load_pct": dict(at.values["load_pct"]),
            "status": {m: v for m, v in at.values["status"].items() if v},
            "stale": at.stale_groups(),
        }
        if self.session_log is not None:
            self.session_log.line(line)
        if self.session is not None:
            self.session.on_telemetry(line)
        for a in alerts:
            self._alert(a)
        for ev in self.guard.take_critical():
            self._critical(ev)

    def _critical(self, ev: CriticalEvent) -> None:
        """Safe stop sequence (§4.5.3): e-stop, hold, park (when possible), torque off."""
        if self.state in ("disconnected", "error"):
            return
        log.error("critical motor condition: %s", ev.detail)
        already = self.estop.is_set
        self.estop.press(ev.reason, detail=ev.detail)
        if already and self.state == "estopped" and not self.follower_torque:
            return
        follower_motor = ev.arm == "follower"
        immediate = ev.immediate_torque_off
        if not immediate:
            self._hold()
        parked = False
        if not immediate and self.profile is not None and self.profile.follower.rest_pose:
            parked = self._park(self.settings.safety.park_s)
        if follower_motor:
            self._torque_off()
        self._teardown_session(reason=ev.reason)
        self.raise_alert(
            "status" if ev.kind == "status" else "temperature",
            "critical",
            "motor.critical.stopped",
            {
                "arm": ev.arm,
                "motor": ev.motor,
                "value": ev.value,
                "reason": ev.reason,
                "parked": parked,
                "torque_off": follower_motor,
                "detail": ev.detail,
            },
            arm=ev.arm,
            motor=ev.motor,
            value=ev.value,
        )
        self._set_state("estopped", reason=ev.reason, detail=ev.detail)

    # ================================================================== loops
    def _monitor_tick(self) -> None:
        deadline = time.perf_counter() + 1.0 / MONITOR_HZ
        self._drain()
        if self.state == "idle" and self.estop.is_set:
            self._enter_estop()
        if self.state == "estopped" and self.estop.relax_event.is_set() and not self.relaxed_in_estop:
            self._torque_off()
            self.relaxed_in_estop = True
            self.emit("state", self.status())
        if self.follower is None:
            self._wait_until(deadline)
            return
        obs = self._read_follower()
        leader = self._read_leader() if self.leader is not None else None
        if obs is not None and self.tick % 2 == 0:
            arms: dict[str, Any] = {"follower": self.last_obs}
            if leader is not None:
                arms["leader"] = leader
            self.emit(
                "joints",
                {
                    "t": round(time.monotonic(), 3),
                    "tick": self.tick,
                    "arms": arms,
                    "clipped": [],
                    "loop": None,
                },
            )
        now = time.monotonic()
        if now - self._last_monitor_tel >= 1.0 / self.settings.telemetry.monitor_hz:
            self._last_monitor_tel = now
            for r in self.telemetry.read_due():
                self._handle_read(r)
                if self.state not in ("idle", "estopped"):
                    break
        self.tick += 1
        self._wait_until(deadline)

    def _calibration_tick(self) -> None:
        deadline = time.perf_counter() + 1.0 / CALIBRATION_HZ
        self._drain()
        proc = self.calibration
        if self.estop.is_set:
            self.calibration = None
            if proc is not None:
                proc.cancel()
            self._enter_estop()
            return
        if proc is None:
            self._set_state("idle")
            return
        try:
            proc.sample()
        except (ConnectionError, RuntimeError, OSError) as exc:
            self.bus_failures += 1
            if self.bus_failures >= BUS_FAIL_LIMIT:
                self._fail("bus_lost", str(exc)[:200])
            return
        self.bus_failures = 0
        now = time.monotonic()
        if now - self._last_cal_emit >= 0.1:
            self._last_cal_emit = now
            self.emit("calibration", proc.view())
        if now - self._last_monitor_tel >= 1.0 / self.settings.telemetry.monitor_hz:
            self._last_monitor_tel = now
            for r in self.telemetry.read_due():
                self._handle_read(r)
        self._wait_until(deadline)

    def _motion_tick(self) -> None:
        s = self.session
        if s is None:
            return
        period = 1.0 / s.fps
        t_start = time.perf_counter()
        deadline = t_start + period
        self._drain()
        if self.session is None:
            return
        if self.estop.is_set:
            self._enter_estop()
            return
        now = self.session_now()
        obs = self._read_follower()
        if obs is None:
            self._wait_until(deadline)
            return
        cam_fps = min((c.fps for c in (self.profile.cameras.values() if self.profile else [])), default=30)
        frames, stale = self.hub.read_latest_all(max_age_ms=2000.0 / max(1, cam_fps))
        obs_full = {**obs, **frames}
        self.hub.publish(
            FrameSet(self.tick, time.monotonic(), frames, policy_input=s.policy_input, stale=stale)
        )
        self._camera_health(s, stale)
        if self.session is None:
            return
        inp = TickInput(self.tick, now, obs_full, frames, stale)
        if s.uses_leader and self.leader is not None:
            inp.leader = self._read_leader()
        action = s.step(self, inp)
        if self.estop.is_set:  # pressed during inference: never send this action
            self._enter_estop()
            return
        clipped: list[str] = []
        if action:
            safe, clipped = self.safety.apply(action, obs)
            try:
                self.follower.send_action(safe)
            except (ConnectionError, RuntimeError, OSError) as exc:
                self.bus_failures += 1
                if self.bus_failures >= BUS_FAIL_LIMIT:
                    self._fail("bus_lost", str(exc)[:200])
                    return
            self.last_sent = safe
            self.last_action = dict(action)
            self.last_clipped = clipped
            s.after_send(self, inp, action, safe)
            self._clip_health(s)
        every = max(1, round(s.fps / self.settings.telemetry.joints_hz))
        if self.tick % every == 0:
            arms: dict[str, Any] = {"follower": self.last_obs}
            if inp.leader is not None:
                arms["leader"] = inp.leader
            payload: dict[str, Any] = {
                "t": round(now, 3),
                "tick": self.tick,
                "arms": arms,
                "clipped": clipped,
                "loop": self.stats.snapshot(self.telemetry.forced),
            }
            if action:
                payload["action"] = self.last_action
                payload["sent"] = self.last_sent
            self.emit("joints", payload)
        read = self.telemetry.maybe_read(deadline - time.perf_counter())
        if read is not None:
            self._handle_read(read)
            if self.session is None:
                return
        if s.deadman and self.watchdog.expired():
            self.press_estop(
                "ui_lost",
                detail=f"no heartbeat from the UI for {self.settings.safety.deadman_timeout_s:.1f} s",
            )
            self._enter_estop()
            return
        s.poll(self, self.session_now())
        if s.phase_changed or time.monotonic() - self._last_session_emit >= 1.0:
            s.phase_changed = False
            self._last_session_emit = time.monotonic()
            self.emit("session", s.view())
        self.stats.tick(t_start, time.perf_counter() - t_start, period)
        self.tick += 1
        if s.finished:
            self._stop_session(s.outcome)
            return
        self._wait_until(deadline)

    def _camera_health(self, s: MotionSession, stale: list[str]) -> None:
        if stale:
            stale_s = max(self.hub.stale_for(n) for n in stale)
            s.camera_stale(self, stale, stale_s)
            for n in stale:
                if (
                    n not in self._camera_alerted
                    and self.hub.stale_for(n) >= self.settings.safety.camera_stale_pause_s
                ):
                    self._camera_alerted.add(n)
                    self.raise_alert("camera", "warn", "camera.stale", {"camera": n}, camera=n)
            if s.kind in ("record", "run") and stale_s >= self.settings.safety.camera_lost_stop_s:
                self.reason = "camera_lost"
                self._stop_session("camera_lost")
        for n in list(self._camera_alerted):
            if n not in stale:
                self._camera_alerted.discard(n)
                self.raise_alert("camera", "info", "camera.stale", {"camera": n}, camera=n, active=False)

    def _clip_health(self, s: MotionSession) -> None:
        frac = self.safety.clipped_fraction(2.0)
        # Spec §R safety: a *policy* fighting the limiter. In teleop/record/replay the clipped
        # targets come from the leader or a dataset, and "the policy is fighting" would be wrong.
        fighting = s.kind == "run" and frac > 0.3 and self.session_now() > 2.0
        if fighting != self.policy_clipping_alert:
            self.policy_clipping_alert = fighting
            self.raise_alert(
                "policy_clipping",
                "warn" if fighting else "info",
                "safety.clipping",
                {"fraction": round(frac, 2)},
                active=fighting,
            )

    # ================================================================== session teardown
    def _enter_estop(self) -> None:
        """Freeze within the current tick; torque off on relax (second press)."""
        reason, detail = self.estop.reason, self.estop.detail
        self._hold()
        if self.estop.relax_event.is_set():
            self._torque_off()
            self.relaxed_in_estop = True
        else:
            self.relaxed_in_estop = False
        if self.calibration is not None:
            self.calibration.cancel()
            self.calibration = None
        self._teardown_session(reason=reason)
        self._set_state("estopped", reason=reason, detail=detail)

    def _teardown_session(self, reason: str) -> None:
        s = self.session
        if s is None:
            return
        self.sub = None
        self.state = "stopping"
        self.emit("state", self.status())
        if self.policy_clipping_alert:  # the session is over: the warning must not outlive it
            self.policy_clipping_alert = False
            self.raise_alert("policy_clipping", "info", "safety.clipping", {"fraction": 0.0}, active=False)
        outcome = s.outcome if s.outcome != "running" else reason
        s.outcome = outcome
        try:
            s.end(self, reason)
        except Exception as exc:
            log.exception("session teardown failed")
            s.summary["teardown_error"] = str(exc)[:300]
        summary = {
            **s.view(),
            "outcome": outcome,
            "reason": reason,
            "summary": s.summary,
            "loop": {
                "ticks": self.stats.total_ticks,
                "overruns": self.stats.overruns,
                "tick_ms_p95": round(self.stats.session_p95_ms(), 2),
                "telemetry_reads": self.telemetry.reads,
                "telemetry_forced": self.telemetry.forced,
            },
            "max_temp_c": {f"{a}.{m}": t for (a, m), t in self.guard.temps.items()},
        }
        if self.session_log is not None:
            self.session_log.close(outcome=outcome, reason=reason, summary=summary)
            self.session_log = None
        self.last_session_summary = summary
        self.session = None
        self.hub.loop_active = False
        self.emit("session", {**summary, "ended": True})

    def _stop_session(self, outcome: str) -> None:
        s = self.session
        if s is None:
            return
        if s.outcome == "running":
            s.outcome = outcome
        self._teardown_session(reason=outcome)
        p = self.profile
        if p is not None and p.follower.on_session_end == "relax" and self.follower is not None:
            if self._park(self.settings.safety.park_s) or not p.follower.rest_pose:
                self._torque_off()
        if self.state == "stopping":
            self._set_state("idle", reason=None)

    def _fail(self, reason: str, detail: str) -> None:
        log.error("hardware error (%s): %s", reason, detail)
        self.estop.press(reason, detail=detail)
        try:
            self._teardown_session(reason=reason)
        except Exception:  # pragma: no cover
            log.exception("teardown in _fail")
        self._torque_off()
        self._close_devices()
        self._set_state("error", reason=reason, detail=detail)

    def _close_devices(self) -> None:
        for dev, kind in ((self.follower, "follower"), (self.leader, "leader")):
            if dev is None:
                continue
            try:
                dev.bus.disconnect(disable_torque=kind == "follower" and self._disable_on_disconnect())
            except Exception as exc:
                log.warning("%s disconnect: %s", kind, exc)
        self.follower = None
        self.leader = None
        self.follower_calibrated = self.leader_calibrated = False
        self.follower_torque = False
        for arm in list(self.telemetry.arms):
            self.telemetry.remove_arm(arm)
            self.guard.reset_arm(arm)
        self.hub.close_all()
        for lk in self.locks:
            lk.release()
        self.locks = []

    def _disable_on_disconnect(self) -> bool:
        return self.profile.follower.disable_torque_on_disconnect if self.profile else True

    # ================================================================== commands (owner thread)
    def _require(self, *states: str) -> None:
        if self.state not in states:
            if self.state == "estopped":
                raise StationError(
                    "estopped", "reset the e-stop first", params={"state": self.state, "reason": self.reason}
                )
            if self.state in ("disconnected", "error"):
                raise StationError("not_connected", "connect a robot first", params={"state": self.state})
            raise StationError("busy", f"not possible while {self.state}", params={"state": self.state})

    def _cmd_status(self) -> dict[str, Any]:
        return self.status()

    def _cmd_connect(self, robot_id: str) -> dict[str, Any]:
        if self.state not in ("disconnected", "error"):
            raise StationError("busy", "already connected", params={"state": self.state})
        p = self.profiles.get(robot_id)
        if p is None:
            raise StationError("not_found", f"no robot profile {robot_id!r}")
        self.profile = p
        self.estop.clear()
        self._set_state("connecting")
        try:
            self._connect(p)
        except StationError:
            self._close_devices()
            self._set_state("disconnected")
            raise
        except Exception as exc:
            self._close_devices()
            self._set_state("disconnected")
            raise StationError("not_connected", f"connect failed: {exc}") from exc
        self.profiles.set_active(p.id)
        self._set_state("idle")
        return self.status()

    def _lock_port(self, port: str) -> None:
        if port.startswith("mock://"):
            return
        lk = DeviceLock(self.paths.locks, port)
        try:
            lk.acquire()
        except DeviceBusyError as exc:
            raise StationError(
                "port_busy",
                f"{port} is used by another Station (pid {exc.holder})",
                params={"port": port, "holder": exc.holder},
            ) from exc
        self.locks.append(lk)

    def _open_device(self, dev: Any, port: str) -> None:
        try:
            dev.connect(calibrate=False)
        except (ConnectionError, OSError) as exc:
            raise StationError(
                "port_busy",
                f"cannot open {port}: {exc}. Another program (LeLab? lerobot?) may be using this port",
                params={"port": port, "holder": None},
            ) from exc

    def _connect(self, p: RobotProfile) -> None:
        self._lock_port(p.follower.port)
        if p.leader is not None:
            self._lock_port(p.leader.port)
        follower = build_follower(p.follower, self.cal_root)
        self._open_device(follower, p.follower.port)
        self.follower = follower
        self.follower_calibrated = bool(follower.bus.is_calibrated)
        if not self.follower_calibrated and follower.calibration:
            calib.apply_existing(follower)
            follower.configure()
            self.follower_calibrated = bool(follower.bus.is_calibrated)
        self.follower_torque = True
        if p.leader is not None:
            leader = build_leader(p.leader, self.cal_root)
            self._open_device(leader, p.leader.port)
            self.leader = leader
            self.leader_calibrated = bool(leader.bus.is_calibrated)
            if not self.leader_calibrated and leader.calibration:
                calib.apply_existing(leader)
                leader.configure()
                self.leader_calibrated = bool(leader.bus.is_calibrated)
        self._setup_safety()
        self.telemetry = TelemetryScheduler(self.settings.telemetry)
        self.guard = ThermalGuard(self._effective_thresholds(None))
        for arm, dev in (("follower", self.follower), ("leader", self.leader)):
            if dev is None:
                continue
            self.telemetry.add_arm(arm, dev.bus)
            lim = self.telemetry.read_limits(arm)
            if arm == "follower":
                self.guard.set_thresholds(self._effective_thresholds(lim.max_temp_c))
        for r in self.telemetry.read_all():
            self._handle_read(r)
        errors = self.hub.configure(p.cameras)
        for name, err in errors.items():
            self.raise_alert(
                "camera", "warn", "camera.open_failed", {"camera": name, "error": err}, camera=name
            )

    def _effective_thresholds(self, max_temp: float | None) -> Thresholds:
        base = (
            self.profile.thresholds if self.profile and self.profile.thresholds else self.settings.thresholds
        )
        if max_temp is None or not threshold_problems(base, max_temp):
            return base
        # Safety first: keep Station's controlled stop below the servo's own cutoff.
        crit = max_temp - 3
        hot = min(base.temp_hot_c, crit - 3)
        warn = min(base.temp_warn_c, hot - 5)
        log.warning("thresholds lowered under Max_Temperature_Limit %.0f C: critical %.0f", max_temp, crit)
        return base.model_copy(update={"temp_critical_c": crit, "temp_hot_c": hot, "temp_warn_c": warn})

    def _setup_safety(self, max_rel: float | dict[str, float] | None = None) -> None:
        p = self.profile
        rel = max_rel if max_rel is not None else (p.follower.max_relative_target if p else None)
        if rel is None:
            rel = self.settings.safety.max_relative_target
        ranges = (
            normalized_ranges(self.follower) if self.follower is not None and self.follower_calibrated else {}
        )
        self.safety = SafetyFilter(rel, ranges)

    def _cmd_disconnect(self, relax: bool = False) -> dict[str, Any]:
        if self.session is not None:
            self._teardown_session("disconnect")
        if self.calibration is not None:
            self.calibration = None
        if relax:
            self._torque_off()
        self._close_devices()
        self.estop.clear()
        self.alerts.clear()
        self._set_state("disconnected")
        return self.status()

    def _cmd_torque(self, arm: str, enabled: bool, confirm: bool = False) -> dict[str, Any]:
        self._require("idle", "estopped")
        if arm != "follower":
            raise StationError("validation_failed", "only the follower has torque control")
        if enabled:
            if self.state == "estopped":
                raise StationError("estopped", "reset the e-stop before enabling torque")
            self._torque_on()
        else:
            if not confirm and not (self.profile and self.profile.follower.rest_pose):
                raise StationError(
                    "validation_failed",
                    "torque off without a rest pose drops the arm: confirm=true is required",
                    params={"confirm_required": True},
                )
            self._torque_off()
        self.emit("state", self.status())
        return self.status()

    def _cmd_set_rest_pose(self) -> dict[str, Any]:
        self._require("idle")
        if not self.follower_calibrated or not self.last_obs:
            raise StationError("not_calibrated", "calibrate the follower first", params={"arm": "follower"})
        if self.profile is None:
            raise StationError("not_connected", "no robot profile")
        self.profile.follower.rest_pose = {k: round(v, 2) for k, v in self.last_obs.items()}
        self.profiles.put(self.profile)
        return {"rest_pose": self.profile.follower.rest_pose}

    def _cmd_update_profile(self, profile: RobotProfile) -> None:
        """Profile edited while connected (not in motion): cameras reopen, safety recomputed."""
        if self.profile is None or self.profile.id != profile.id:
            return
        if self.session is not None or self.state == "calibrating":
            raise StationError("busy", "profile is in use", params={"state": self.state})
        self.profile = profile
        self._setup_safety()
        if self.state in ("idle", "estopped"):
            errors = self.hub.configure(profile.cameras)
            for name, err in errors.items():
                self.raise_alert(
                    "camera", "warn", "camera.open_failed", {"camera": name, "error": err}, camera=name
                )
        self.emit("state", self.status())

    def _cmd_set_thresholds(self, thresholds: Thresholds) -> None:
        lim = self.telemetry.arms["follower"].limits.max_temp_c if "follower" in self.telemetry.arms else None
        problems = threshold_problems(thresholds, lim)
        if problems:
            raise StationError("validation_failed", "; ".join(problems))
        self.guard.set_thresholds(thresholds)

    # ---- calibration
    def _device(self, arm: str) -> Any:
        dev = self.follower if arm == "follower" else self.leader if arm == "leader" else None
        if dev is None:
            raise StationError("not_connected", f"no {arm} connected", params={"arm": arm})
        return dev

    def _cmd_calibration_start(self, arm: str, keep_existing: bool = False) -> dict[str, Any]:
        self._require("idle")
        dev = self._device(arm)
        if keep_existing:
            if not dev.calibration:
                raise StationError("not_found", f"no calibration file for {arm}")
            calib.apply_existing(dev)
            dev.configure()
            self._after_calibration(arm, dev)
            return self.status()
        proc = calib.CalibrationProcess(arm, dev)
        if self.mock and hasattr(dev, "world"):
            dev.world.auto_sweep = True  # the demo "hand" moves the limp arm...
            dev.world.sweep_hold_mid = True  # ...after holding it mid-range for Home
        proc.start()
        if arm == "follower":
            self.follower_torque = False
            self.follower_calibrated = False
        else:
            self.leader_calibrated = False
        self.calibration = proc
        self._set_state("calibrating", sub="home")
        self.emit("calibration", proc.view())
        return self.status()

    def _after_calibration(self, arm: str, dev: Any) -> None:
        if hasattr(dev, "world"):
            dev.world.sweep_hold_mid = False
            if arm == "follower":
                dev.world.auto_sweep = False
                if self.mock and dev.world.hand is None:
                    dev.world.place_all(2048.0)  # the demo hand lets go of the follower mid-range
        ok = bool(dev.bus.is_calibrated)
        if arm == "follower":
            self.follower_calibrated = ok
            self.follower_torque = True
            self._setup_safety()
        else:
            self.leader_calibrated = ok

    def _cmd_calibration_step(self, action: str) -> dict[str, Any]:
        proc = self.calibration
        if self.state != "calibrating" or proc is None:
            raise StationError("busy", "no calibration in progress", params={"state": self.state})
        if action == "set_home":
            proc.set_home()
            if self.mock and hasattr(proc.device, "world"):
                proc.device.world.sweep_hold_mid = False  # the demo hand now sweeps the ranges
            self.sub = "ranges"
            self.emit("calibration", proc.view())
            self.emit("state", self.status())
            return self.status()
        if action == "finish_ranges":
            try:
                _cal, warnings = proc.finish()
            except calib.CalibrationError as exc:
                raise StationError("validation_failed", str(exc)) from exc
            dev = proc.device
            dev.configure()
            self._after_calibration(proc.arm, dev)
            view = proc.view()
            view["warnings"] = warnings
            view["path"] = str(dev.calibration_fpath)
            self.emit("calibration", view)
            self.calibration = None
            self._set_state("idle")
            return {**self.status(), "calibration": view}
        if action == "cancel":
            dev = proc.device
            proc.cancel()
            self.calibration = None
            if dev.calibration:
                calib.apply_existing(dev)
            dev.configure()
            self._after_calibration(proc.arm, dev)
            self._set_state("idle")
            return self.status()
        raise StationError("validation_failed", f"unknown calibration action {action!r}")

    # ---- sessions
    def _start_checks(self, kind: str, needs_leader: bool) -> None:
        self._require("idle")
        if self.estop.is_set:
            raise StationError("estopped", "reset the e-stop first")
        hot = self.guard.hot_motors()
        if hot:
            raise StationError("motor_hot", "let the motors cool down first", params={"motors": hot})
        if not self.follower_calibrated:
            raise StationError("not_calibrated", "calibrate the follower first", params={"arm": "follower"})
        if needs_leader:
            if self.leader is None:
                raise StationError(
                    "not_connected", "this session needs a leader arm", params={"arm": "leader"}
                )
            if not self.leader_calibrated:
                raise StationError("not_calibrated", "calibrate the leader first", params={"arm": "leader"})
        if self.profile is not None:
            cams = {c["name"]: c for c in self.hub.status()}
            missing = [n for n in self.profile.cameras if n not in cams or not cams[n]["streaming"]]
            if missing:
                raise StationError(
                    "camera_unavailable", "a configured camera is not streaming", params={"cameras": missing}
                )

    def _cmd_start_session(
        self,
        kind: str,
        build: Callable[[HardwareOwner], MotionSession],
        needs_leader: bool,
        max_relative_target: float | dict[str, float] | None = None,
        leader_check_deg: float | None = None,
    ) -> dict[str, Any]:
        self._start_checks(kind, needs_leader)
        obs = self._read_follower()
        if obs is None:
            raise StationError("not_connected", "cannot read the follower")
        if needs_leader and leader_check_deg is not None:
            from hibiscus_station.sessions.teleop import check_leader_close

            leader = self._read_leader()
            if leader is None:
                raise StationError("not_connected", "cannot read the leader")
            check_leader_close(obs, leader, leader_check_deg)
        session = build(self)
        if not self.follower_torque:
            self._torque_on()
        self._setup_safety(max_relative_target)
        self.stats = LoopStats()
        self.telemetry.reads = 0
        self.telemetry.forced = 0
        self.tick = 0
        self.session = session
        self.session_log = SessionLog(
            self.paths.sessions,
            session.id,
            {
                "kind": session.kind,
                "robot": self.profile.id if self.profile else None,
                "profile": self.profile.model_dump(mode="json") if self.profile else None,
                "thresholds": self.guard.t.model_dump(),
                "fps": session.fps,
                "dataset": session.dataset,
                "model": session.model,
                "task": session.task,
            },
        )
        self.hub.loop_active = True
        self.watchdog.arm()
        session.t0 = time.monotonic()
        session.begin(self, obs)
        self._set_state(MOTION_STATES[kind], sub=session.episode.phase)
        self.emit("session", session.view())
        return session.view()

    def _cmd_control(self, action: str) -> dict[str, Any]:
        s = self.session
        if s is None:
            raise StationError("busy", "no session running", params={"state": self.state})
        s.control(self, action)
        s.phase_changed = True
        view = s.view()
        if s.finished:
            self._stop_session(s.outcome)
        return view

    def _cmd_estop_reset(self) -> dict[str, Any]:
        if self.state != "estopped":
            raise StationError("busy", "the e-stop is not latched", params={"state": self.state})
        if self.guard.any_motor_at_or_above_hot():
            raise StationError(
                "motor_hot",
                "a motor is still hot; let it cool down",
                params={"motors": self.guard.hot_motors()},
            )
        self.estop.clear()
        self.relaxed_in_estop = False
        for aid in [
            a
            for a, al in self.alerts.items()
            if al.level == "critical" and al.message_key == "motor.critical.stopped"
        ]:
            self.alerts.pop(aid, None)
        self._set_state("idle")
        return self.status()

    def _cmd_read_positions(self) -> dict[str, float]:
        return dict(self.last_obs)

    def _cmd_run(self, fn: Callable[[HardwareOwner], Any]) -> Any:
        """Run arbitrary code in the owner thread (tests and the camera probe)."""
        return fn(self)


def deadline_for(fps: int) -> Deadline:
    return Deadline(1.0 / fps)
