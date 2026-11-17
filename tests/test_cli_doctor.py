"""``hibiscus-station doctor`` names the zip to send exactly once (F-63)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hibiscus_station import doctor as doc
from hibiscus_station.cli import app


def _run_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, summary: str) -> tuple[str, Path]:
    target = tmp_path / "hibiscus-station-doctor-20261117-120000.zip"
    target.write_bytes(b"zip")

    def fake_run(*_args: Any, **_kwargs: Any) -> tuple[str, Path]:
        return summary.format(path=target.resolve()), target

    monkeypatch.setattr(doc, "run", fake_run)
    r = CliRunner().invoke(app, ["doctor", "--home", str(tmp_path / "home"), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    return r.stdout, target


def test_doctor_names_the_zip_once_when_the_report_already_says_what_to_send(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out, target = _run_with(
        monkeypatch,
        tmp_path,
        "WHAT TO SEND / CẦN GỬI GÌ\n  EN: Send us this one file: {path}\n"
        "  VI: Bạn chỉ cần gửi cho chúng tôi một tệp: {path}",
    )
    assert "Report saved to" not in out
    assert out.count(str(target.resolve())) == 2  # once in English, once in Vietnamese


def test_doctor_still_names_the_zip_when_the_report_does_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out, target = _run_with(monkeypatch, tmp_path, "PORTS\n  none")
    assert out.count(str(target.resolve())) == 1
    assert "Report saved to" in out


def test_doctor_verbose_prints_station_bus_errors_but_no_library_debug_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """QD-12: --verbose is for bus errors (motor id, register); libraries' DEBUG lines stay out."""
    import logging

    target = tmp_path / "hibiscus-station-doctor-20261117-120000.zip"
    target.write_bytes(b"zip")

    def fake_run(*_args: Any, **_kwargs: Any) -> tuple[str, Path]:
        logging.getLogger().debug("Detected pyserial version: 3.5")  # lerobot's import check, root
        logging.getLogger("datasets").debug("PyTorch version 2.5 available.")
        logging.getLogger("hibiscus_station.hw.bus").debug("read Present_Current id 3 failed, retrying")
        return "report", target

    monkeypatch.setattr(doc, "run", fake_run)
    r = CliRunner().invoke(
        app, ["doctor", "--verbose", "--home", str(tmp_path / "home"), "--out", str(tmp_path)]
    )
    assert r.exit_code == 0, r.output
    assert "read Present_Current id 3 failed" in r.output
    assert "Detected pyserial version" not in r.output and "PyTorch version" not in r.output
    logging.getLogger("hibiscus_station").setLevel(logging.NOTSET)
    logging.getLogger().handlers.clear()
