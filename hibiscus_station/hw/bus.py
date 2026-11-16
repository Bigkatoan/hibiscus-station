"""lerobot's ``SerialMotorsBus`` with retries and a record of every bus error (real arms and mocks).

A real Feetech bus drops or corrupts a status packet now and then (USB adapter, cable, power sag
when joints move). lerobot retries ``get_observation`` reads but none of the writes it sends while
connecting (``configure``), calibrating (``set_half_turn_homings``, ``write_calibration``) or
switching torque, so one bad packet failed a whole connect or calibration. Here every call that is
not given an explicit ``num_retry`` gets :attr:`StationMotorsBus.min_retry` retries. Register
writes and torque switches are idempotent, so a retry after a lost *answer* is harmless.

Each failed attempt is logged at DEBUG (``--verbose``) with the operation, register and motor ids,
and counted in :attr:`StationMotorsBus.errors` (shown by ``hibiscus-station doctor`` and the
status). Telemetry passes ``num_retry=0`` explicitly: a failed telemetry read is never retried.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from lerobot.motors import Motor, MotorCalibration, SerialMotorsBus
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

log = logging.getLogger(__name__)

T = TypeVar("T")
MIN_RETRY = 2
RETRY_PAUSE_S = 0.002  # let a half-sent answer drain before asking again


class StationMotorsBus(SerialMotorsBus):  # type: ignore[misc]
    min_retry: int = MIN_RETRY

    def __init__(
        self,
        port: str,
        motors: dict[str, Motor],
        calibration: dict[str, MotorCalibration] | None = None,
        *,
        arm: str = "",
    ) -> None:
        super().__init__(port, motors, calibration)
        self.arm = arm
        self.errors: Counter[str] = Counter()
        self.retried = 0  # calls that failed at least once and then went through
        self.last_error: str | None = None
        self.last_error_t: float | None = None

    # ------------------------------------------------------------------ bookkeeping
    def _names(self, motors: Any) -> str:
        try:
            names = self._get_motors_list(motors)
        except Exception:
            return str(motors)
        ids = [self.motors[m].id for m in names if m in self.motors]
        return ",".join(str(i) for i in ids) if ids else str(motors)

    def _attempt(self, op: str, register: str, motors: Any, num_retry: int | None, fn: Callable[[], T]) -> T:
        tries = (self.min_retry if num_retry is None else max(0, num_retry)) + 1
        for i in range(tries):
            try:
                out = fn()
            except (DeviceNotConnectedError, DeviceAlreadyConnectedError):
                raise
            except (ConnectionError, RuntimeError, OSError) as exc:
                ids = self._names(motors)
                key = f"{op} {register} [{ids}]"
                self.errors[key] += 1
                self.last_error = f"{self.arm or self.port}: {op} {register} motor id(s) {ids}: {exc}"
                self.last_error_t = time.time()
                log.debug(
                    "bus error %s (attempt %d/%d) on %s: %s %s motor id(s) %s: %s",
                    self.arm or "-",
                    i + 1,
                    tries,
                    self.port,
                    op,
                    register,
                    ids,
                    exc,
                )
                if i == tries - 1:
                    if tries > 1:
                        log.warning("bus error on %s after %d tries: %s", self.port, tries, self.last_error)
                    raise
                time.sleep(RETRY_PAUSE_S)
                continue
            if i:
                self.retried += 1
            return out
        raise AssertionError("unreachable")  # pragma: no cover

    def error_summary(self) -> dict[str, Any]:
        return {
            "errors": sum(self.errors.values()),
            "retried_ok": self.retried,
            "by_call": dict(self.errors.most_common(10)),
            "last_error": self.last_error,
        }

    # ------------------------------------------------------------------ lerobot API
    def read(
        self, data_name: str, motor: str, *, normalize: bool = True, num_retry: int | None = None
    ) -> Any:
        return self._attempt(
            "read",
            data_name,
            motor,
            num_retry,
            lambda: super(StationMotorsBus, self).read(data_name, motor, normalize=normalize, num_retry=0),
        )

    def write(
        self,
        data_name: str,
        motor: str,
        value: Any,
        *,
        normalize: bool = True,
        num_retry: int | None = None,
    ) -> None:
        self._attempt(
            "write",
            data_name,
            motor,
            num_retry,
            lambda: super(StationMotorsBus, self).write(
                data_name, motor, value, normalize=normalize, num_retry=0
            ),
        )

    def sync_read(
        self,
        data_name: str,
        motors: str | int | Sequence[str | int] | None = None,
        *,
        normalize: bool = True,
        num_retry: int | None = None,
    ) -> dict[str, Any]:
        return self._attempt(
            "sync_read",
            data_name,
            motors,
            num_retry,
            lambda: super(StationMotorsBus, self).sync_read(
                data_name, motors, normalize=normalize, num_retry=0
            ),
        )

    def ping(self, motor: str | int, num_retry: int | None = None) -> int | None:
        tries = (self.min_retry if num_retry is None else max(0, num_retry)) + 1
        for i in range(tries):
            found = super().ping(motor, num_retry=0)
            if found is not None:
                if i:
                    self.retried += 1
                return found  # type: ignore[no-any-return]
            ids = self._names(motor if isinstance(motor, str) else [motor])
            self.errors[f"ping Model_Number [{ids}]"] += 1
            self.last_error = f"{self.arm or self.port}: motor id {ids} does not answer a ping"
            self.last_error_t = time.time()
            log.debug(
                "bus error %s (attempt %d/%d) on %s: no answer from motor id %s",
                self.arm,
                i + 1,
                tries,
                self.port,
                ids,
            )
        return None

    def _set_torque(self, motors: Any, enabled: bool, num_retry: int) -> None:
        # rustypot retries each motor (torque + Feetech lock) on its own; the outer attempts redo
        # the motors that still failed (switching torque twice is harmless).
        self._attempt(
            "torque_on" if enabled else "torque_off",
            "Torque_Enable",
            motors,
            max(num_retry, self.min_retry),
            lambda: super(StationMotorsBus, self)._set_torque(motors, enabled, self.min_retry),
        )
