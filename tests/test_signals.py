"""External signals (station-programs.md §4 "External"): SignalBus, POST /signals/{name}, the
optional MQTT client (against a fake paho client: no broker needed)."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any

import pytest
from conftest import contract_errors, wait_for

from hibiscus_station.errors import StationError
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.signals import (
    MAX_TEXT,
    BrokerUrl,
    MqttBridge,
    SignalBus,
    coerce_value,
    parse_payload,
    topic_signal_name,
    values_equal,
)
from hibiscus_station.station import Station


class Emitted:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, kind: str, payload: dict[str, Any]) -> None:
        self.items.append((kind, payload))


def test_bus_set_get_seq_and_ws_message() -> None:
    emitted = Emitted()
    bus = SignalBus(emit=emitted)
    assert bus.seq == 0 and bus.all() == [] and bus.get("door") is None
    a = bus.set("door", 1, "http")
    assert a.value == 1.0 and a.seq == 1 and a.source == "http"
    b = bus.set("mode", "auto", "program")
    assert bus.seq == 2 and b.seq == 2
    assert [s.name for s in bus.all()] == ["door", "mode"]
    assert bus.get("door") == a
    assert bus.last_seq("door", "http") == 1 and bus.last_seq("door", "mqtt") == 0
    assert bus.last_seq("mode", "http") == 0  # set by the program, not received over HTTP
    assert [k for k, _ in emitted.items] == ["signal", "signal"]
    for kind, payload in emitted.items:
        assert contract_errors(kind, payload) == []
    bus.set("door", 0, "ui")
    assert bus.get("door").value == 0.0 and bus.get("door").source == "ui"  # type: ignore[union-attr]


def test_bus_validates_names_and_values() -> None:
    bus = SignalBus()
    for bad in ("bad name", "", "a/b", "-x", "x" * 65):
        with pytest.raises(StationError) as e:
            bus.set(bad, 1, "http")
        assert e.value.code == "validation_failed"
    with pytest.raises(StationError):
        bus.set("x", math.inf, "http")
    with pytest.raises(StationError):
        bus.set("x", "y" * (MAX_TEXT + 1), "http")
    assert bus.seq == 0


def test_coerce_and_compare_values() -> None:
    assert coerce_value(True) == 1.0 and coerce_value(False) == 0.0 and coerce_value(3) == 3.0
    assert coerce_value("on") == "on"
    with pytest.raises(StationError):
        coerce_value([1])
    assert values_equal(1.0, "1") and values_equal("1.0", 1.0) and values_equal(0.1 + 0.2, 0.3)
    assert not values_equal("on", "off") and values_equal("on", "on") and not values_equal(1.0, "on")


def test_subscribers_and_unsubscribe() -> None:
    bus = SignalBus()
    seen: list[str] = []

    def boom(sig: ps.Signal) -> None:
        raise RuntimeError("subscriber bug")

    bus.subscribe(boom)  # never breaks a set
    unsub = bus.subscribe(lambda s: seen.append(s.name))
    bus.set("a", 1, "http")
    unsub()
    unsub()
    bus.set("b", 1, "http")
    assert seen == ["a"]


def test_bus_is_thread_safe() -> None:
    bus = SignalBus()

    def work(i: int) -> None:
        for j in range(200):
            bus.set(f"s{i}", j, "http")

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert bus.seq == 1600 and len(bus.all()) == 8
    assert all(s.value == 199.0 for s in bus.all())


def test_mqtt_payloads_and_topic_names() -> None:
    assert parse_payload(b" 42 ") == 42.0 and parse_payload(b"true") == 1.0 and parse_payload(b"FALSE") == 0.0
    assert parse_payload(b"open") == "open" and parse_payload(b"nan") == "nan"
    assert parse_payload("é".encode()) == "é" and parse_payload(b"\xff") == "�"
    assert topic_signal_name("factory/door/1") == "factory.door.1"
    assert topic_signal_name("/a b/c+") == "a_b.c_"
    assert topic_signal_name("#") is None


def test_bus_message_counts_topics_that_are_not_signal_names() -> None:
    bus = SignalBus()
    sig = bus.message("factory/door", 1.0, "mqtt")
    assert sig is not None and sig.name == "factory.door" and sig.source == "mqtt"
    assert bus.last_seq("factory/door", "mqtt") == 1 == bus.last_seq("factory.door", "mqtt")
    assert bus.message("#", "x", "mqtt") is None
    assert bus.seq == 2 and bus.last_seq("#", "mqtt") == 2 and bus.get("#") is None


# --------------------------------------------------------------------------- MQTT bridge
@dataclass
class Msg:
    topic: str
    payload: bytes


@dataclass
class Reason:
    is_failure: bool


class FakeMqtt:
    """The part of paho's Client the bridge uses."""

    def __init__(self) -> None:
        self.on_connect: Any = None
        self.on_message: Any = None
        self.on_disconnect: Any = None
        self.auth: tuple[str | None, str | None] | None = None
        self.tls = False
        self.connected_to: tuple[str, int, int] | None = None
        self.subscribed: list[str] = []
        self.looping = False
        self.disconnected = False

    def username_pw_set(self, username: str | None, password: str | None = None) -> None:
        self.auth = (username, password)

    def tls_set(self) -> None:
        self.tls = True

    def connect_async(self, host: str, port: int = 1883, keepalive: int = 60) -> None:
        self.connected_to = (host, port, keepalive)

    def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscribed.append(topic)

    def loop_start(self) -> None:
        self.looping = True

    def loop_stop(self) -> None:
        self.looping = False

    def disconnect(self) -> None:
        self.disconnected = True

    # broker side
    def broker_connects(self, ok: bool = True) -> None:
        self.on_connect(self, None, {}, Reason(is_failure=not ok), None)

    def deliver(self, topic: str, payload: bytes) -> None:
        self.on_message(self, None, Msg(topic, payload))


def test_broker_url_parsing() -> None:
    b = BrokerUrl("mqtt://user:p%40ss@broker.local")
    assert (b.host, b.port, b.tls, b.username, b.password) == ("broker.local", 1883, False, "user", "p@ss")
    assert b.safe() == "mqtt://broker.local:1883"  # never logs the password
    t = BrokerUrl("mqtts://10.0.0.2:9000")
    assert (t.port, t.tls, t.username) == (9000, True, None)
    assert BrokerUrl("mqtts://h").port == 8883
    for bad in ("http://x", "mqtt://", "x"):
        with pytest.raises(StationError):
            BrokerUrl(bad)


def test_mqtt_bridge_feeds_the_bus() -> None:
    bus = SignalBus()
    fake = FakeMqtt()
    bridge = MqttBridge(
        "mqtts://u:pw@broker:8884", ["factory/#", "", "door"], bus, client_factory=lambda: fake
    )
    bridge.start()
    bridge.start()  # idempotent
    assert (
        fake.connected_to == ("broker", 8884, 30) and fake.looping and fake.tls and fake.auth == ("u", "pw")
    )
    fake.broker_connects(ok=False)
    assert not bridge.connected and fake.subscribed == []
    fake.broker_connects()
    assert bridge.connected and fake.subscribed == ["factory/#", "door"]
    fake.deliver("factory/belt/speed", b"1.5")
    fake.deliver("door", b"open")
    fake.deliver("door", b"x" * (MAX_TEXT + 10))  # long text is cut, never crashes the network thread
    assert bus.get("factory.belt.speed").value == 1.5  # type: ignore[union-attr]
    assert bus.get("door").value == "x" * MAX_TEXT  # type: ignore[union-attr]
    assert bus.last_seq("door", "mqtt") == 3 and bus.last_seq("factory/belt/speed", "mqtt") == 1
    fake.on_disconnect(fake, None, None, None, None)
    assert not bridge.connected
    bridge.stop()
    assert fake.disconnected and not fake.looping
    bridge.stop()


def test_paho_client_is_built_with_the_v2_callbacks() -> None:
    from hibiscus_station.programs.signals import _paho_client

    client = _paho_client()
    assert hasattr(client, "connect_async")


def test_hub_starts_mqtt_only_when_configured(station: Station) -> None:
    hub = station.programs
    assert hub.mqtt is None  # no broker URL by default: no client, no thread
    fakes: list[FakeMqtt] = []

    def factory() -> FakeMqtt:
        fakes.append(FakeMqtt())
        return fakes[-1]

    hub.mqtt_client_factory = factory
    new = station.settings.model_copy(deep=True)
    new.programs.mqtt_url = "mqtt://127.0.0.1:18230"
    new.programs.mqtt_topics = ["door"]
    station.update_settings(new)
    assert hub.mqtt is not None and len(fakes) == 1
    station.update_settings(new.model_copy(deep=True))  # same config: same client
    assert len(fakes) == 1
    fakes[0].broker_connects()
    fakes[0].deliver("door", b"1")
    assert hub.signals.get("door").source == "mqtt"  # type: ignore[union-attr]
    bad = new.model_copy(deep=True)
    bad.programs.mqtt_url = "http://nope"
    station.update_settings(bad)  # logged, never fatal
    assert hub.mqtt is None and fakes[0].disconnected
    off = new.model_copy(deep=True)
    off.programs.mqtt_url = None
    station.update_settings(off)
    assert hub.mqtt is None


# --------------------------------------------------------------------------- REST + WS
def test_signals_rest(client: Any, station: Station) -> None:
    assert client.get("/api/v1/signals").json() == {"signals": []}
    r = client.post("/api/v1/signals/door", json={"value": 1})
    assert r.status_code == 200, r.text
    sig = ps.Signal.model_validate(r.json())
    assert sig.name == "door" and sig.value == 1.0 and sig.source == "http" and sig.seq == 1
    r = client.post("/api/v1/signals/mode", json={"value": "auto"})
    assert r.json()["value"] == "auto"
    r = client.post("/api/v1/signals/flag", json={"value": True})
    assert r.json()["value"] == 1.0
    names = [s["name"] for s in client.get("/api/v1/signals").json()["signals"]]
    assert names == ["door", "flag", "mode"]
    assert client.post("/api/v1/signals/door", json={}).status_code == 422
    assert client.post("/api/v1/signals/door", json={"value": "x" * 600}).status_code == 422
    assert (
        client.post("/api/v1/signals/door", json={"value": 1}, headers={"X-Station": ""}).status_code == 403
    )
    assert station.programs.signals.last_seq("door", "http") == 1


def test_signal_reaches_the_control_socket(client: Any) -> None:
    with client.websocket_connect(
        "/api/v1/ws", headers={"authorization": client.headers["Authorization"]}
    ) as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "hello", "v": 1, "client": "test"})
        ws.send_json({"type": "ping"})
        assert wait_for(lambda: ws.receive_json()["type"] == "pong")
        client.post("/api/v1/signals/door", json={"value": 2})
        for _ in range(50):
            msg = ws.receive_json()
            if msg["type"] == "signal":
                break
        assert msg["type"] == "signal" and msg["name"] == "door" and msg["value"] == 2.0
        assert contract_errors("signal", {k: v for k, v in msg.items() if k != "type"}) == []
