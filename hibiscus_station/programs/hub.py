"""``Station.programs``: one entry point to the feature's stores and runtimes.

Architect skeleton: ``robot_paths`` is implemented; each store accessor is filled in by the team that
owns the store (see the "Implementation map" of station-programs.md) and keeps this signature.
Stores are per robot profile: the hub caches one per robot id and builds it on first use.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.programs.detectors import DetectorStore as FileDetectorStore
from hibiscus_station.programs.operator import RunRegistry
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.signals import MqttBridge, MqttClient
from hibiscus_station.programs.signals import SignalBus as MemorySignalBus

if TYPE_CHECKING:
    from hibiscus_station.programs.interfaces import (
        DetectorStore,
        PoseStore,
        ProgramStore,
        SignalBus,
        TrajectoryStore,
    )
    from hibiscus_station.station import Station

log = logging.getLogger(__name__)


class ProgramsHub:
    def __init__(self, station: Station) -> None:
        self.station = station
        self._lock = threading.Lock()
        self._stores: dict[tuple[str, str], Any] = {}  # (kind, robot id) -> store
        self._detectors: dict[str, FileDetectorStore] = {}
        self._signals = MemorySignalBus(emit=station.owner.emit)
        self.mqtt: MqttBridge | None = None
        self.mqtt_client_factory: Callable[[], MqttClient] | None = None  # tests: a fake broker client
        self.runs = RunRegistry()  # team B: program runs of this launch (operator input routing)
        self.run_lock = threading.Lock()  # one program run at a time (dry or real)

    # ------------------------------------------------------------------ lifecycle (team B)
    def start(self) -> None:
        """Start the optional MQTT client (``settings.programs.mqtt_url``)."""
        self.apply_settings()

    def shutdown(self) -> None:
        for rt in self.runs.unfinished():  # dry runs have no owner session to end them
            try:
                rt.abort("stopped")
            except Exception:  # pragma: no cover - shutdown must go on
                log.exception("program abort at shutdown failed")
        if self.mqtt is not None:
            self.mqtt.stop()
            self.mqtt = None
        with self._lock:
            for store in self._detectors.values():
                store.close()
            self._detectors.clear()

    def apply_settings(self) -> None:
        """(Re)connect MQTT after a settings change; a bad URL is logged, never fatal."""
        cfg = self.station.settings.programs
        old = self.mqtt
        topics = [t for t in cfg.mqtt_topics if t]
        if old is not None and cfg.mqtt_url == old.url and topics == old.topics:
            return
        if old is not None:
            old.stop()
            self.mqtt = None
        if not cfg.mqtt_url:
            return
        try:
            bridge = MqttBridge(cfg.mqtt_url, topics, self._signals, client_factory=self.mqtt_client_factory)
            bridge.start()
        except Exception as exc:
            log.warning("mqtt client not started: %s", getattr(exc, "detail", exc))
            return
        self.mqtt = bridge

    def robot_id(self) -> str:
        """The connected profile, else the active one in ``robots.yaml``."""
        owner = self.station.owner
        if owner.profile is not None:
            return owner.profile.id
        active = self.station.profiles.active
        if active is None:
            raise StationError("not_connected", "add a robot profile first")
        return active

    def robot_paths(self, robot_id: str | None = None) -> RobotDataPaths:
        paths = RobotDataPaths(self.station.paths.home, robot_id or self.robot_id())
        paths.ensure()
        return paths

    # ------------------------------------------------------------------ team A
    def trajectories(self, robot_id: str | None = None) -> TrajectoryStore:
        from hibiscus_station.programs.trajectories import TrajectoryStore as Store

        rid = robot_id or self.robot_id()
        with self._lock:
            store = self._stores.get(("trajectories", rid))
            if store is None:

                def trim_rule() -> tuple[float, float]:
                    p = self.station.settings.programs
                    return p.idle_trim_deg, p.idle_trim_s

                store = Store(self.robot_paths(rid), lambda: self.calibration_hash(rid), trim_rule=trim_rule)
                self._stores[("trajectories", rid)] = store
            return store

    def poses(self, robot_id: str | None = None) -> PoseStore:
        from hibiscus_station.programs.poses import PoseStore as Store

        rid = robot_id or self.robot_id()
        with self._lock:
            store = self._stores.get(("poses", rid))
            if store is None:
                store = Store(self.robot_paths(rid), lambda: self.calibration_hash(rid))
                self._stores[("poses", rid)] = store
            return store

    def calibration_hash(self, robot_id: str | None = None) -> str:
        from hibiscus_station.programs.calibration_ref import calibration_hash

        rid = robot_id or self.robot_id()
        profile = self.station.profiles.get(rid)
        if profile is None:
            raise StationError("not_found", f"no robot profile {rid!r}", params={"robot": rid})
        return calibration_hash(self.station.cal_root, profile)

    # ------------------------------------------------------------------ team B
    def detectors(self, robot_id: str | None = None) -> DetectorStore:
        paths = self.robot_paths(robot_id)
        with self._lock:
            store = self._detectors.get(paths.robot_id)
            if store is None:
                store = self._detectors[paths.robot_id] = FileDetectorStore(paths)
            return store

    def programs(self, robot_id: str | None = None) -> ProgramStore:
        from hibiscus_station.programs.store import ProgramStore as Store

        paths = self.robot_paths(robot_id)
        with self._lock:
            store = self._stores.get(("programs", paths.robot_id))
            if store is None:
                store = Store(
                    paths, lambda: self.station.settings.programs, runs_home=self.station.paths.home
                )
                self._stores[("programs", paths.robot_id)] = store
            return store

    def current_program(self) -> dict[str, Any] | None:
        """``Status.program``: the state of the unfinished run (dry or real), for reconnects."""
        try:
            rt = self.runs.running()
        except StationError:
            return None
        return rt.state().model_dump(mode="json")

    @property
    def signals(self) -> SignalBus:
        return self._signals
