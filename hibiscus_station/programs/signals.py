"""External signals (station-programs.md §4 "External"): the process-wide :class:`SignalBus` and the
optional MQTT client that feeds it.

* ``POST /api/v1/signals/{name}`` (127.0.0.1, token, ``X-Station: 1``) sets a signal with source
  ``http``; the ``set signal`` block uses ``program``; the UI uses ``ui``.
* :class:`MqttBridge` (paho-mqtt, pinned) subscribes to ``settings.programs.mqtt_topics`` on
  ``settings.programs.mqtt_url`` and sets a signal per message, source ``mqtt``. It only exists when
  a broker URL is configured. The signal name is the topic with ``/`` replaced by ``.`` (signal names
  cannot contain ``/``); ``message_received(mqtt, <topic>)`` matches the raw topic.
* Every set bumps the bus-wide ``seq``, publishes a ``signal`` message on the control socket and
  calls the subscribers. ``message_received`` compares ``last_seq(name, source)`` with the value it
  saw at its previous evaluation.

Payloads: a number (JSON/MQTT text that parses as a finite float; ``true``/``false`` become 1/0) or a
text of at most :data:`MAX_TEXT` characters.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import re
import threading
from collections.abc import Callable, Iterable
from typing import Any, Literal, Protocol
from urllib.parse import unquote, urlsplit

from hibiscus_station.errors import StationError
from hibiscus_station.programs.schemas import SIGNAL_NAME_RE, Scalar, Signal, SignalSource

log = logging.getLogger(__name__)

MAX_TEXT = 500
MAX_SIGNALS = 1024
Emit = Callable[[str, dict[str, Any]], None]


def coerce_value(value: object) -> Scalar:
    """A signal value: finite number, bool as 1/0, or a text (≤ ``MAX_TEXT``)."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        f = float(value)
        if not math.isfinite(f):
            raise StationError("validation_failed", "signal value must be finite")
        return f
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            raise StationError("validation_failed", f"signal text is longer than {MAX_TEXT} characters")
        return value
    raise StationError("validation_failed", "signal value must be a number or a text")


def parse_payload(raw: bytes) -> Scalar:
    """An MQTT payload: UTF-8 text, a number when it parses as one (``true``/``false`` as 1/0)."""
    text = raw.decode("utf-8", errors="replace").strip()
    low = text.lower()
    if low in ("true", "false"):
        return 1.0 if low == "true" else 0.0
    try:
        f = float(text)
    except ValueError:
        return text[:MAX_TEXT]
    return f if math.isfinite(f) else text[:MAX_TEXT]


_BAD = re.compile(r"[^A-Za-z0-9_.-]")


def topic_signal_name(topic: str) -> str | None:
    """MQTT topic -> signal name (``a/b c`` -> ``a.b_c``); ``None`` when nothing usable is left."""
    name = _BAD.sub("_", topic.strip("/").replace("/", "."))[:64]
    return name if SIGNAL_NAME_RE.fullmatch(name) else None


def values_equal(a: Scalar, b: Scalar) -> bool:
    """``signal [name] = [value]``: numerically when both sides read as numbers, else as texts."""
    fa, fb = _num(a), _num(b)
    if fa is not None and fb is not None:
        return math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-9)
    return str(a) == str(b)


def _num(v: Scalar) -> float | None:
    if isinstance(v, float | int):
        return float(v)
    try:
        f = float(v)
    except ValueError:
        return None
    return f if math.isfinite(f) else None


class SignalBus:
    """Thread-safe store of the latest value of every signal (implements ``interfaces.SignalBus``)."""

    def __init__(self, emit: Emit | None = None) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._signals: dict[str, Signal] = {}
        self._seq = 0
        self._last: dict[tuple[str, str], int] = {}
        self._subs: list[Callable[[Signal], None]] = []

    def set(self, name: str, value: Scalar, source: SignalSource) -> Signal:
        if not SIGNAL_NAME_RE.fullmatch(name):
            raise StationError("validation_failed", "bad signal name", params={"name": name})
        return self._set(name, coerce_value(value), source, raw=name)

    def message(self, topic: str, value: Scalar, source: Literal["http", "mqtt"]) -> Signal | None:
        """A message on an MQTT topic (or any raw name): counted for ``message_received`` even when
        the name cannot become a signal."""
        name = topic_signal_name(topic) if source == "mqtt" else topic
        if name is None or not SIGNAL_NAME_RE.fullmatch(name):
            with self._lock:
                self._seq += 1
                self._last[(source, topic)] = self._seq
            return None
        return self._set(name, coerce_value(value), source, raw=topic)

    def _set(self, name: str, value: Scalar, source: SignalSource, *, raw: str) -> Signal:
        with self._lock:
            if name not in self._signals and len(self._signals) >= MAX_SIGNALS:
                raise StationError("validation_failed", f"more than {MAX_SIGNALS} signals")
            self._seq += 1
            sig = Signal(
                name=name, value=value, source=source, at=dt.datetime.now(dt.UTC).isoformat(), seq=self._seq
            )
            self._signals[name] = sig
            self._last[(source, name)] = self._seq
            if raw != name:
                self._last[(source, raw)] = self._seq
            subs = list(self._subs)
        if self._emit is not None:
            self._emit("signal", sig.model_dump(mode="json"))
        for fn in subs:
            try:
                fn(sig)
            except Exception:  # a subscriber never breaks a set
                log.exception("signal subscriber failed")
        return sig

    def get(self, name: str) -> Signal | None:
        with self._lock:
            return self._signals.get(name)

    def all(self) -> list[Signal]:
        with self._lock:
            return sorted(self._signals.values(), key=lambda s: s.name)

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def last_seq(self, name: str, source: Literal["http", "mqtt"]) -> int:
        with self._lock:
            return self._last.get((source, name), 0)

    def subscribe(self, fn: Callable[[Signal], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.append(fn)

        def unsubscribe() -> None:
            with self._lock:
                if fn in self._subs:
                    self._subs.remove(fn)

        return unsubscribe


# --------------------------------------------------------------------------- MQTT
class MqttClient(Protocol):
    """The part of ``paho.mqtt.client.Client`` the bridge uses (a fake in tests)."""

    on_connect: Any
    on_message: Any
    on_disconnect: Any

    def username_pw_set(self, username: str | None, password: str | None = None) -> None: ...

    def tls_set(self) -> Any: ...

    def connect_async(self, host: str, port: int = 1883, keepalive: int = 60) -> Any: ...

    def subscribe(self, topic: str, qos: int = 0) -> Any: ...

    def loop_start(self) -> Any: ...

    def loop_stop(self) -> Any: ...

    def disconnect(self) -> Any: ...


def _paho_client() -> MqttClient:
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    return mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="", clean_session=True)


class BrokerUrl:
    def __init__(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("mqtt", "mqtts") or not parts.hostname:
            raise StationError(
                "validation_failed", "mqtt_url must look like mqtt://host:1883", params={"url": url[:200]}
            )
        self.tls = parts.scheme == "mqtts"
        self.host = parts.hostname
        self.port = parts.port or (8883 if self.tls else 1883)
        self.username = unquote(parts.username) if parts.username else None
        self.password = unquote(parts.password) if parts.password else None

    def safe(self) -> str:
        """The URL without credentials (logs)."""
        return f"{'mqtts' if self.tls else 'mqtt'}://{self.host}:{self.port}"


class MqttBridge:
    """Feeds MQTT messages into the bus. Reconnects by itself (paho's network loop thread)."""

    def __init__(
        self,
        url: str,
        topics: Iterable[str],
        bus: SignalBus,
        *,
        client_factory: Callable[[], MqttClient] | None = None,
    ) -> None:
        self.url = url
        self.broker = BrokerUrl(url)
        self.topics = [t for t in topics if t]
        self.bus = bus
        self._factory = client_factory or _paho_client
        self._client: MqttClient | None = None
        self.connected = False

    def start(self) -> None:
        if self._client is not None:
            return
        client = self._factory()
        if self.broker.username is not None:
            client.username_pw_set(self.broker.username, self.broker.password)
        if self.broker.tls:
            client.tls_set()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.connect_async(self.broker.host, self.broker.port, keepalive=30)
        client.loop_start()
        self._client = client
        log.info("mqtt: connecting to %s (%d topics)", self.broker.safe(), len(self.topics))

    def stop(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:  # pragma: no cover - shutting down anyway
            log.exception("mqtt: stop failed")
        self.connected = False

    # paho VERSION2 callbacks (network thread)
    def _on_connect(
        self, client: MqttClient, userdata: Any, flags: Any, reason: Any, props: Any = None
    ) -> None:
        failed = bool(getattr(reason, "is_failure", False))
        self.connected = not failed
        if failed:
            log.warning("mqtt: connect to %s refused: %s", self.broker.safe(), reason)
            return
        for t in self.topics:
            client.subscribe(t, qos=0)

    def _on_disconnect(self, client: MqttClient, userdata: Any, *args: Any) -> None:
        self.connected = False

    def _on_message(self, client: MqttClient, userdata: Any, msg: Any) -> None:
        try:
            self.bus.message(str(msg.topic), parse_payload(bytes(msg.payload)), "mqtt")
        except StationError as exc:
            log.warning("mqtt: dropped a message on %s: %s", msg.topic, exc.detail)
