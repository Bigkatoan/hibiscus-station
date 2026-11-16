"""Motor health telemetry (R1, spec §4.5.2-§4.5.3): scheduler, decode, thresholds, ThermalGuard.

The scheduler and the guard are plain objects driven by the hardware-owner thread: nothing here
starts a thread or touches a bus outside :meth:`TelemetryScheduler.maybe_read` / ``read_all``.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hibiscus_station.hw import feetech
from hibiscus_station.settings import TelemetrySettings, Thresholds

log = logging.getLogger(__name__)

LEVELS = ("ok", "warn", "hot", "critical")
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}
DEGRADED_AFTER = 3


@dataclass
class ArmLimits:
    max_temp_c: float = feetech.DEFAULT_MAX_TEMPERATURE_C
    min_voltage_v: float | None = None
    max_voltage_v: float | None = None
    protection_current_a: dict[str, float] = field(default_factory=dict)
    nominal_voltage_v: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_temp_c": self.max_temp_c,
            "min_voltage_v": self.min_voltage_v,
            "max_voltage_v": self.max_voltage_v,
            "nominal_voltage_v": self.nominal_voltage_v,
            "protection_current_a": dict(self.protection_current_a),
        }


@dataclass
class TelemetryRead:
    """The result of one group read on one arm (one ``sync_read``)."""

    arm: str
    group: str
    t: float
    ok: bool
    values: dict[str, Any]
    forced: bool = False
    degraded: bool = False  # edge: third consecutive failure of this group
    error: str | None = None


class ArmTelemetry:
    """Latest decoded values of one arm, with per-group freshness."""

    def __init__(self, arm: str, bus: Any, motors: list[str]) -> None:
        self.arm = arm
        self.bus = bus
        self.motors = motors
        self.values: dict[str, dict[str, Any]] = {g.name: {} for g in feetech.GROUPS}
        self.last_ok: dict[str, float] = dict.fromkeys(self.values, -math.inf)
        self.last_attempt: dict[str, float] = dict.fromkeys(self.values, -math.inf)
        self.fails: dict[str, int] = dict.fromkeys(self.values, 0)
        self.limits = ArmLimits()

    def stale_groups(self) -> list[str]:
        return [g for g, n in self.fails.items() if n > 0]

    def motor_view(self, motor: str, level: str) -> dict[str, Any]:
        return {
            "temp_c": self.values["temp_c"].get(motor),
            "voltage_v": self.values["voltage_v"].get(motor),
            "current_a": self.values["current_a"].get(motor),
            "load_pct": self.values["load_pct"].get(motor),
            "status": list(self.values["status"].get(motor, [])),
            "level": level,
            "stale": bool(self.stale_groups()),
        }


class TelemetryScheduler:
    """Round-robin, slack-aware register reads (§4.5.2). At most one read per call."""

    def __init__(
        self,
        settings: TelemetrySettings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.arms: dict[str, ArmTelemetry] = {}
        self.reads = 0
        self.forced = 0
        self.skipped_no_slack = 0

    def add_arm(self, arm: str, bus: Any) -> ArmTelemetry:
        at = ArmTelemetry(arm, bus, list(bus.motors))
        self.arms[arm] = at
        return at

    def remove_arm(self, arm: str) -> None:
        self.arms.pop(arm, None)

    def period(self, group: str) -> float:
        g = feetech.GROUP_BY_NAME[group]
        return 1.0 / (self.settings.hot_hz if g.hot else self.settings.cool_hz)

    # ------------------------------------------------------------------ limits
    def read_limits(self, arm: str) -> ArmLimits:
        """Read EEPROM limits once at connect (best effort: missing values keep defaults)."""
        at = self.arms[arm]
        lim = ArmLimits()
        try:
            temps = at.bus.sync_read(feetech.REG_MAX_TEMPERATURE, normalize=False, num_retry=2)
            if temps:
                lim.max_temp_c = float(min(temps.values()))
        except Exception as exc:
            log.warning("%s: cannot read Max_Temperature_Limit (%s); assuming %s C", arm, exc, lim.max_temp_c)
        try:
            vmin = at.bus.sync_read(feetech.REG_MIN_VOLTAGE, normalize=False, num_retry=2)
            vmax = at.bus.sync_read(feetech.REG_MAX_VOLTAGE, normalize=False, num_retry=2)
            lim.min_voltage_v = feetech.decode_voltage(max(vmin.values())) if vmin else None
            lim.max_voltage_v = feetech.decode_voltage(min(vmax.values())) if vmax else None
        except Exception as exc:
            log.warning("%s: cannot read voltage limits (%s)", arm, exc)
        try:
            prot = at.bus.sync_read(feetech.REG_PROTECTION_CURRENT, normalize=False, num_retry=2)
            lim.protection_current_a = {m: feetech.decode_current(v) for m, v in prot.items() if v}
        except Exception as exc:
            log.warning("%s: cannot read Protection_Current (%s)", arm, exc)
        at.limits = lim
        return lim

    # ------------------------------------------------------------------ reads
    def _read(self, at: ArmTelemetry, group: str, *, forced: bool) -> TelemetryRead:
        reg = feetech.GROUP_BY_NAME[group].register
        now = self.clock()
        at.last_attempt[group] = now
        self.reads += 1
        if forced:
            self.forced += 1
        try:
            raw = at.bus.sync_read(reg, normalize=False, num_retry=0)
        except Exception as exc:  # never fatal (§4.5.2)
            at.fails[group] += 1
            return TelemetryRead(
                at.arm,
                group,
                now,
                False,
                {},
                forced=forced,
                degraded=at.fails[group] == DEGRADED_AFTER,
                error=str(exc)[:200],
            )
        decoded = {m: feetech.decode(group, int(v)) for m, v in raw.items()}
        at.values[group] = decoded
        at.last_ok[group] = now
        at.fails[group] = 0
        if group == "voltage_v" and at.limits.nominal_voltage_v is None and decoded:
            vals = [float(v) for v in decoded.values() if isinstance(v, float)]
            if vals:
                at.limits.nominal_voltage_v = round(sorted(vals)[len(vals) // 2], 2)
        return TelemetryRead(at.arm, group, now, True, decoded, forced=forced)

    def due(self, now: float | None = None) -> list[tuple[float, str, str]]:
        """(overdue seconds, arm, group), most overdue first."""
        now = self.clock() if now is None else now
        out: list[tuple[float, str, str]] = []
        for arm, at in self.arms.items():
            for g in feetech.GROUPS:
                overdue = now - at.last_attempt[g.name] - self.period(g.name)
                if overdue >= 0:
                    out.append((overdue, arm, g.name))
        out.sort(key=lambda x: -x[0] if math.isfinite(x[0]) else -math.inf)
        return out

    def maybe_read(self, slack_s: float) -> TelemetryRead | None:
        """Read the most overdue group when the tick has ``min_slack_ms`` to spare.

        Anti-starvation: a temperature sample older than ``max_age_s`` is read even without slack.
        """
        now = self.clock()
        no_slack = slack_s * 1000.0 < self.settings.min_slack_ms
        for _arm, at in self.arms.items():
            age = now - at.last_ok["temp_c"]
            since_attempt = now - at.last_attempt["temp_c"]
            if age > self.settings.max_age_s and since_attempt >= self.period("temp_c"):
                return self._read(at, "temp_c", forced=no_slack)
        due = self.due(now)
        if not due:
            return None
        if no_slack:
            self.skipped_no_slack += 1
            return None
        _, arm, group = due[0]
        return self._read(self.arms[arm], group, forced=False)

    def read_all(self) -> list[TelemetryRead]:
        """Monitor mode (idle / estopped / calibrating): every group of every arm, no slack rule."""
        out: list[TelemetryRead] = []
        for at in self.arms.values():
            for g in feetech.GROUPS:
                out.append(self._read(at, g.name, forced=False))
        return out

    def read_due(self) -> list[TelemetryRead]:
        """Monitor mode at monitor_hz: every group that is due."""
        now = self.clock()
        return [self._read(self.arms[arm], group, forced=False) for _, arm, group in self.due(now)]


# ---------------------------------------------------------------------------------------- guard
@dataclass
class Alert:
    id: str
    t: float
    level: str
    kind: str
    arm: str | None = None
    motor: str | None = None
    camera: str | None = None
    value: float | None = None
    message_key: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "t": self.t,
            "level": self.level,
            "kind": self.kind,
            "arm": self.arm,
            "motor": self.motor,
            "camera": self.camera,
            "value": self.value,
            "message_key": self.message_key,
            "params": self.params,
            "active": self.active,
        }


@dataclass
class CriticalEvent:
    arm: str
    motor: str
    reason: str  # thermal | electrical
    kind: str  # temperature | status | voltage
    value: float | None
    immediate_torque_off: bool
    detail: str


class ThermalGuard:
    """Turns decoded telemetry into levels, alerts (edges) and critical events (§4.5.3)."""

    def __init__(self, thresholds: Thresholds) -> None:
        self.t = thresholds
        self.temp_level: dict[tuple[str, str], str] = {}
        self.consecutive_critical: dict[tuple[str, str], int] = {}
        self.status_level: dict[tuple[str, str], str] = {}
        self.voltage_level: dict[tuple[str, str], str] = {}
        self.current_level: dict[tuple[str, str], str] = {}
        self.load_level: dict[tuple[str, str], str] = {}
        self.stall_since: dict[tuple[str, str], float] = {}
        self.status_streak: dict[tuple[str, str], int] = {}
        self.voltage_streak: dict[tuple[str, str], int] = {}
        self.temps: dict[tuple[str, str], float] = {}
        self._critical: list[CriticalEvent] = []

    def set_thresholds(self, thresholds: Thresholds) -> None:
        self.t = thresholds

    # ------------------------------------------------------------------ helpers
    def _thr(self, level: str) -> float:
        return {"warn": self.t.temp_warn_c, "hot": self.t.temp_hot_c, "critical": self.t.temp_critical_c}[
            level
        ]

    def _temp_level(self, key: tuple[str, str], temp: float) -> str:
        cur = self.temp_level.get(key, "ok")
        if temp >= self.t.temp_critical_c:
            self.consecutive_critical[key] = self.consecutive_critical.get(key, 0) + 1
        else:
            self.consecutive_critical[key] = 0
        up = "ok"
        if temp >= self.t.temp_warn_c:
            up = "warn"
        if temp >= self.t.temp_hot_c:
            up = "hot"
        if temp >= self.t.temp_critical_c and self.consecutive_critical[key] >= self.t.critical_consecutive:
            up = "critical"
        if LEVEL_RANK[up] >= LEVEL_RANK[cur]:
            return up
        # hysteresis: step down only once the temperature is hysteresis_c below the level threshold
        level = cur
        while LEVEL_RANK[level] > LEVEL_RANK[up] and temp < self._thr(level) - self.t.hysteresis_c:
            level = LEVELS[LEVEL_RANK[level] - 1]
        return level

    @staticmethod
    def _edge(store: dict[tuple[str, str], str], key: tuple[str, str], new: str) -> tuple[bool, str]:
        old = store.get(key, "ok")
        store[key] = new
        return old != new, old

    # ------------------------------------------------------------------ public
    def update(self, read: TelemetryRead, limits: ArmLimits, now: float | None = None) -> list[Alert]:
        if not read.ok:
            return []
        now = read.t if now is None else now
        alerts: list[Alert] = []
        arm = read.arm
        for motor, value in read.values.items():
            key = (arm, motor)
            if read.group == "temp_c":
                temp = float(value)
                self.temps[key] = temp
                lvl = self._temp_level(key, temp)
                changed, old = self._edge(self.temp_level, key, lvl)
                if changed:
                    alerts.append(
                        Alert(
                            f"temperature:{arm}:{motor}",
                            now,
                            lvl if lvl != "ok" else "info",
                            "temperature",
                            arm=arm,
                            motor=motor,
                            value=temp,
                            message_key=f"motor.temp.{lvl}",
                            params={"motor": motor, "arm": arm, "temp_c": temp, "from": old},
                            active=lvl != "ok",
                        )
                    )
                    if lvl == "critical":
                        self._critical.append(
                            CriticalEvent(
                                arm,
                                motor,
                                "thermal",
                                "temperature",
                                temp,
                                immediate_torque_off=temp >= self.t.temp_critical_c + 5,
                                detail=f"{arm} {motor} {temp:.0f} C",
                            )
                        )
            elif read.group == "status":
                bits = list(value) if isinstance(value, list) else []
                crit_bits = feetech.STATUS_CRITICAL | feetech.STATUS_ELECTRICAL
                if motor in feetech.GRASP_MOTORS:
                    # lerobot sets the gripper's own overload protection (Overload_Torque 25 %):
                    # squeezing an object trips it by design, it is not a fault.
                    crit_bits = crit_bits - {"overload"}
                crit = sorted(set(bits) & crit_bits)
                # One status byte can be a glitch: a fault must be seen on consecutive reads,
                # except overheat (the servo has already cut its own torque).
                n = self.status_streak[key] = self.status_streak.get(key, 0) + 1 if crit else 0
                confirmed = "overheat" in crit or n >= self.t.critical_consecutive
                lvl = "critical" if crit and confirmed else ("warn" if bits else "ok")
                changed, _ = self._edge(self.status_level, key, lvl)
                if changed:
                    alerts.append(
                        Alert(
                            f"status:{arm}:{motor}",
                            now,
                            lvl if lvl != "ok" else "info",
                            "status",
                            arm=arm,
                            motor=motor,
                            message_key=f"motor.status.{lvl}",
                            params={"motor": motor, "arm": arm, "bits": bits},
                            active=lvl != "ok",
                        )
                    )
                    if lvl == "critical":
                        thermal = bool(set(bits) & feetech.STATUS_CRITICAL)
                        self._critical.append(
                            CriticalEvent(
                                arm,
                                motor,
                                "thermal" if thermal else "electrical",
                                "status",
                                None,
                                immediate_torque_off="overheat" in bits,
                                detail=f"{arm} {motor} status {','.join(bits)}",
                            )
                        )
            elif read.group == "voltage_v":
                v = float(value)
                lvl = "ok"
                low = limits.min_voltage_v is not None and v < limits.min_voltage_v
                n = self.voltage_streak[key] = self.voltage_streak.get(key, 0) + 1 if low else 0
                if low and n >= self.t.critical_consecutive:
                    lvl = "critical"
                elif low:
                    lvl = "warn"
                elif (
                    limits.min_voltage_v is not None and v < limits.min_voltage_v + self.t.voltage_margin_v
                ) or (
                    limits.nominal_voltage_v and v < limits.nominal_voltage_v * self.t.voltage_nominal_ratio
                ):
                    lvl = "warn"
                changed, _ = self._edge(self.voltage_level, key, lvl)
                if changed:
                    alerts.append(
                        Alert(
                            f"voltage:{arm}:{motor}",
                            now,
                            lvl if lvl != "ok" else "info",
                            "voltage",
                            arm=arm,
                            motor=motor,
                            value=v,
                            message_key=f"motor.voltage.{lvl}",
                            params={"motor": motor, "arm": arm, "voltage_v": v},
                            active=lvl != "ok",
                        )
                    )
                    if lvl == "critical":
                        self._critical.append(
                            CriticalEvent(
                                arm, motor, "electrical", "voltage", v, False, f"{arm} {motor} {v:.1f} V"
                            )
                        )
            elif read.group == "current_a":
                a = float(value)
                prot = limits.protection_current_a.get(motor)
                lvl = "warn" if prot and a > prot * self.t.current_ratio else "ok"
                changed, _ = self._edge(self.current_level, key, lvl)
                if changed:
                    alerts.append(
                        Alert(
                            f"current:{arm}:{motor}",
                            now,
                            lvl if lvl != "ok" else "info",
                            "current",
                            arm=arm,
                            motor=motor,
                            value=a,
                            message_key=f"motor.current.{lvl}",
                            params={"motor": motor, "arm": arm, "current_a": a},
                            active=lvl != "ok",
                        )
                    )
            elif read.group == "load_pct":
                load = float(value)
                if abs(load) >= self.t.load_stall_pct:
                    self.stall_since.setdefault(key, now)
                else:
                    self.stall_since.pop(key, None)
                since = self.stall_since.get(key)
                lvl = "warn" if since is not None and now - since > self.t.load_stall_s else "ok"
                changed, _ = self._edge(self.load_level, key, lvl)
                if changed:
                    alerts.append(
                        Alert(
                            f"load:{arm}:{motor}",
                            now,
                            lvl if lvl != "ok" else "info",
                            "load",
                            arm=arm,
                            motor=motor,
                            value=load,
                            message_key=f"motor.load.{lvl}",
                            params={"motor": motor, "arm": arm, "load_pct": load},
                            active=lvl != "ok",
                        )
                    )
        return alerts

    def take_critical(self) -> list[CriticalEvent]:
        out, self._critical = self._critical, []
        return out

    def level(self, arm: str, motor: str) -> str:
        key = (arm, motor)
        levels = [
            self.temp_level.get(key, "ok"),
            self.status_level.get(key, "ok"),
            self.voltage_level.get(key, "ok"),
            self.current_level.get(key, "ok"),
            self.load_level.get(key, "ok"),
        ]
        return max(levels, key=lambda x: LEVEL_RANK[x])

    def hot_motors(self) -> list[dict[str, Any]]:
        """Motors at or above ``hot`` (start refused, estop reset refused)."""
        return [
            {"arm": a, "motor": m, "temp_c": self.temps.get((a, m))}
            for (a, m), lvl in self.temp_level.items()
            if LEVEL_RANK[lvl] >= LEVEL_RANK["hot"]
        ] + [
            {"arm": a, "motor": m, "status": True}
            for (a, m), lvl in self.status_level.items()
            if lvl == "critical"
        ]

    def any_motor_at_or_above_hot(self) -> bool:
        """For estop reset: every motor must be below ``hot`` (raw value, no hysteresis)."""
        return any(t >= self.t.temp_hot_c for t in self.temps.values()) or any(
            lvl == "critical" for lvl in self.status_level.values()
        )

    def overall(self) -> dict[str, Any]:
        worst = "ok"
        for a, m in set(self.temp_level) | set(self.status_level) | set(self.voltage_level):
            lvl = self.level(a, m)
            if LEVEL_RANK[lvl] > LEVEL_RANK[worst]:
                worst = lvl
        hottest: dict[str, Any] | None = None
        if self.temps:
            (arm, motor), temp = max(self.temps.items(), key=lambda kv: kv[1])
            hottest = {"arm": arm, "motor": motor, "temp_c": temp}
        return {"level": worst, "hottest": hottest}

    def reset_arm(self, arm: str) -> None:
        for store in (
            self.temp_level,
            self.consecutive_critical,
            self.status_level,
            self.voltage_level,
            self.current_level,
            self.load_level,
            self.stall_since,
            self.status_streak,
            self.voltage_streak,
            self.temps,
        ):
            for key in [k for k in store if k[0] == arm]:
                del store[key]
