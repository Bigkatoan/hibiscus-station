"""MockFollower / MockLeader: real lerobot ``SOFollower`` / ``SOLeader`` subclasses on a mock bus.

Registered as ``hibiscus_mock_follower`` / ``hibiscus_mock_leader`` (``RobotConfig.register_subclass``),
with SO-101 motor names and norm modes. Their ``name`` stays ``so_follower`` / ``so_leader`` so the
calibration layout and dataset ``robot_type`` are those of the real arms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lerobot.robots.config import RobotConfig
from lerobot.robots.so_follower import SOFollower, SOFollowerRobotConfig
from lerobot.teleoperators.config import TeleoperatorConfig
from lerobot.teleoperators.so_leader import SOLeader, SOLeaderTeleopConfig

from hibiscus_station.mock.fakebus import MockMotorsBus, get_world


@RobotConfig.register_subclass("hibiscus_mock_follower")
@dataclass
class MockFollowerConfig(SOFollowerRobotConfig):  # type: ignore[misc]
    read_latency_s: float = 0.0015


@TeleoperatorConfig.register_subclass("hibiscus_mock_leader")
@dataclass
class MockLeaderConfig(SOLeaderTeleopConfig):  # type: ignore[misc]
    read_latency_s: float = 0.0015


class MockFollower(SOFollower):  # type: ignore[misc]
    config_class = MockFollowerConfig
    name = "so_follower"

    def __init__(self, config: MockFollowerConfig) -> None:
        super().__init__(config)
        world = get_world(config.port, read_latency_s=config.read_latency_s)
        self.world = world
        motors = dict(self.bus.motors)  # type: ignore[has-type]
        self.bus = MockMotorsBus(config.port, motors, self.calibration, world=world)


class MockLeader(SOLeader):  # type: ignore[misc]
    config_class = MockLeaderConfig
    name = "so_leader"

    def __init__(self, config: MockLeaderConfig) -> None:
        super().__init__(config)
        world = get_world(config.port, read_latency_s=config.read_latency_s)
        self.world = world
        motors = dict(self.bus.motors)  # type: ignore[has-type]
        self.bus = MockMotorsBus(config.port, motors, self.calibration, world=world)


def make_mock_follower(port: str, robot_id: str, calibration_dir: Any, **kw: Any) -> MockFollower:
    return MockFollower(MockFollowerConfig(port=port, id=robot_id, calibration_dir=calibration_dir, **kw))


def make_mock_leader(port: str, teleop_id: str, calibration_dir: Any) -> MockLeader:
    return MockLeader(MockLeaderConfig(port=port, id=teleop_id, calibration_dir=calibration_dir))
