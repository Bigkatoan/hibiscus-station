"""Hardware mocks shipped with Station (tests and ``--mock`` demo mode), spec §9.1."""

from hibiscus_station.mock.camera import MockCamera, MockCameraConfig, decode_counter, encode_counter
from hibiscus_station.mock.fakebus import MockArmWorld, MockMotorsBus, get_world, reset_worlds
from hibiscus_station.mock.robots import MockFollower, MockFollowerConfig, MockLeader, MockLeaderConfig

__all__ = [
    "MockArmWorld",
    "MockCamera",
    "MockCameraConfig",
    "MockFollower",
    "MockFollowerConfig",
    "MockLeader",
    "MockLeaderConfig",
    "MockMotorsBus",
    "decode_counter",
    "encode_counter",
    "get_world",
    "reset_worlds",
]
