"""``hibiscus-station`` entry point (spec §1.1, §8).

uvx hibiscus-station                 # start on 127.0.0.1:18210 and open the browser
hibiscus-station --mock --no-browser # demo mode with mock arms and cameras
hibiscus-station url                 # print a fresh login URL for the running instance
hibiscus-station health              # exit 0 when the running instance answers (Docker, systemd)
hibiscus-station openapi PATH        # write the OpenAPI document
hibiscus-station doctor              # check ports, calibration and motors; write a zip to send

Robot ports are picked in the UI: ``/dev/ttyACM0`` (or ``/dev/serial/by-id/...``) on Linux,
``/dev/tty.usbmodem...`` on macOS, ``COM3`` on Windows. Close LeLab / lerobot first: a serial port has
one owner.

LAN mode (spec §8.1, opt-in): ``--host 0.0.0.0`` (or a LAN address) is accepted only with a fixed
token in ``$HIBISCUS_STATION_TOKEN`` and at least one ``--allow-host`` name the browser will use.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import webbrowser
from pathlib import Path

import typer

from hibiscus_station import __version__
from hibiscus_station.settings import DEFAULT_PORT, StationPaths, station_home

app = typer.Typer(
    add_completion=False,
    help=(
        "Hibiscus Station: the local robot agent. Opens the UI in the browser; pick the arm's serial "
        "port there (Linux /dev/ttyACM0, macOS /dev/tty.usbmodem..., Windows COM3). Close LeLab or "
        "any lerobot script first: a serial port or camera has one owner."
    ),
    no_args_is_help=False,
)
LOOPBACK_HOSTS = ("127.0.0.1", "::1")
TOKEN_ENV = "HIBISCUS_STATION_TOKEN"  # noqa: S105 - the name of the variable
ALLOWED_HOSTS_ENV = "HIBISCUS_STATION_ALLOWED_HOSTS"
MIN_TOKEN_LEN = 32
TOKEN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def _setup_logging(paths: StationPaths, verbose: bool) -> None:
    from hibiscus_station.logs import RedactingFilter

    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        paths.logs / "station.log", maxBytes=10 * 1024**2, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.addFilter(RedactingFilter())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO, handlers=[handler, console], force=True
    )
    # Every failed bus call (motor id, register, error) always reaches the log file; the console
    # shows them with --verbose. lerobot's per-tick timing lines stay out even with --verbose.
    logging.getLogger("hibiscus_station.hw.bus").setLevel(logging.DEBUG)
    logging.getLogger("lerobot").setLevel(logging.INFO)


def _fixed_token() -> str | None:
    """``$HIBISCUS_STATION_TOKEN``: a fixed login token instead of a fresh one per launch."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return None
    if len(token) < MIN_TOKEN_LEN or not set(token) <= TOKEN_CHARS:
        typer.echo(
            f"${TOKEN_ENV} must be at least {MIN_TOKEN_LEN} characters of A-Z a-z 0-9 - _ "
            "(e.g. `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`).",
            err=True,
        )
        raise typer.Exit(2)
    return token


def _allowed_hosts(values: list[str], port: int) -> tuple[tuple[str, ...], str | None]:
    """``--allow-host`` / ``$HIBISCUS_STATION_ALLOWED_HOSTS`` entries for the Host/Origin checks.

    ``robot.local`` allows ``robot.local:<port>`` (direct) and ``robot.local`` (a TLS proxy on
    443); ``robot.local:8443`` is taken as given. Also returns ``host:port`` of the first entry,
    used for the printed login link (None when there is no entry).
    """
    raw = [*values, *os.environ.get(ALLOWED_HOSTS_ENV, "").split(",")]
    out: list[str] = []
    login: str | None = None
    for item in (v.strip().lower() for v in raw):
        if not item:
            continue
        if any(c in item for c in "/@ ") or item.startswith("*"):
            typer.echo(f"--allow-host {item!r}: give a host name or address, e.g. robot.local", err=True)
            raise typer.Exit(2)
        bare = item.rsplit("]", 1)[-1] if item.startswith("[") else item
        with_port = item if ":" in bare else f"{item}:{port}"
        login = login or with_port
        out.extend([item] if with_port == item else [item, with_port])
    return tuple(dict.fromkeys(out)), login


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Port on 127.0.0.1"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="127.0.0.1 or ::1. Any other address (LAN mode) needs $HIBISCUS_STATION_TOKEN and --allow-host",
    ),
    allow_host: list[str] = typer.Option(
        [],
        "--allow-host",
        help="LAN mode: a host name or address the browser uses (repeatable; also "
        "$HIBISCUS_STATION_ALLOWED_HOSTS, comma-separated)",
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the browser"),
    mock: bool = typer.Option(
        False, "--mock", help="Demo mode: simulated arms and cameras, data in ~/.hibiscus/station-demo"
    ),
    home: Path | None = typer.Option(None, "--home", help="Data dir (default ~/.hibiscus/station)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    version: bool = typer.Option(False, "--version"),
) -> None:
    if version:
        typer.echo(f"hibiscus-station {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is not None:
        return
    token = _fixed_token()
    extra_hosts, lan_login = _allowed_hosts(allow_host, port)
    lan = host not in LOOPBACK_HOSTS
    if lan and (token is None or not extra_hosts):
        typer.echo(
            f"--host {host}: Station binds 127.0.0.1 or ::1 only, unless LAN mode is set up: a fixed "
            f"login token in ${TOKEN_ENV} and the names the browser will use in --allow-host "
            f"(or ${ALLOWED_HOSTS_ENV}). See docs/deploy.md, 'Open Station on the LAN'.",
            err=True,
        )
        raise typer.Exit(2)
    import uvicorn

    from hibiscus_station.api.security import LocalAuth
    from hibiscus_station.app import create_app
    from hibiscus_station.hw.locks import DeviceBusyError, InstanceLock
    from hibiscus_station.station import Station

    paths = StationPaths(home or (demo_home() if mock else station_home()))
    paths.ensure()
    lock = InstanceLock(paths.lock, paths.pid)
    try:
        lock.acquire()
    except DeviceBusyError:
        token = paths.token.read_text(encoding="utf-8").strip() if paths.token.is_file() else ""
        running = _running_login(paths, _running_port(paths) or port)
        typer.echo(f"Hibiscus Station is already running: http://{running}/auth?t={token}")
        raise typer.Exit(0) from None
    login = lan_login if lan and lan_login else _host_port(host, port)
    pid_info = {"pid": os.getpid(), "port": port, "host": host, "login": login}
    paths.pid.write_text(json.dumps(pid_info), encoding="utf-8")
    _setup_logging(paths, verbose)
    auth = LocalAuth(token=token, port=port, extra_hosts=extra_hosts)
    auth.write_token(paths.token)
    station = Station(paths.home, mock=mock, port=port)
    application = create_app(station, auth)
    url = f"http://{login}/auth?t={auth.token}"
    if lan:
        logging.getLogger(__name__).warning(
            "LAN mode: listening on %s:%d for %s; anyone on this network with the token can move the robot",
            host,
            port,
            ", ".join(extra_hosts),
        )
    typer.echo(f"Hibiscus Station {__version__}{' (mock)' if mock else ''}: {url}")
    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: S110 - no browser on this machine: the URL is printed
            pass
    try:
        uvicorn.run(application, host=host, port=port, log_level="warning", access_log=False)
    finally:
        lock.release()


def _host_port(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _running_login(paths: StationPaths, port: int) -> str:
    """``host:port`` for the login link of the running instance (its pid file, else loopback)."""
    login = _pid_info(paths).get("login")
    return str(login) if login else _host_port("127.0.0.1", port)


def _pid_info(paths: StationPaths) -> dict[str, object]:
    try:
        data = json.loads(paths.pid.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _running_port(paths: StationPaths) -> int | None:
    try:
        return int(str(_pid_info(paths)["port"]))
    except (KeyError, ValueError):
        return None


@app.command()
def url(home: Path | None = typer.Option(None, "--home")) -> None:
    """Print a fresh login URL for the running Station."""
    paths = StationPaths(home or station_home())
    if not paths.token.is_file():
        typer.echo("Hibiscus Station is not running.", err=True)
        raise typer.Exit(1)
    login = _running_login(paths, _running_port(paths) or DEFAULT_PORT)
    typer.echo(f"http://{login}/auth?t={paths.token.read_text(encoding='utf-8').strip()}")


@app.command()
def health(
    home: Path | None = typer.Option(None, "--home"),
    timeout: float = typer.Option(5.0, "--timeout", help="Seconds to wait for the answer"),
) -> None:
    """Exit 0 when the running Station answers ``GET /api/v1/status`` (Docker / systemd health check)."""
    import httpx

    paths = StationPaths(home or station_home())
    info = _pid_info(paths)
    if not paths.token.is_file() or not info:
        typer.echo("unhealthy: Hibiscus Station is not running", err=True)
        raise typer.Exit(1)
    port = _running_port(paths) or DEFAULT_PORT
    bound = str(info.get("host") or "127.0.0.1")
    connect = "127.0.0.1" if bound in ("0.0.0.0", "::", "") else bound  # noqa: S104 - a bind address, not a bind
    target = f"[{connect}]" if ":" in connect else connect
    try:
        r = httpx.get(
            f"http://{target}:{port}/api/v1/status",
            headers={
                "Authorization": f"Bearer {paths.token.read_text(encoding='utf-8').strip()}",
                "Host": f"127.0.0.1:{port}",
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        typer.echo(f"unhealthy: {type(exc).__name__}", err=True)
        raise typer.Exit(1) from None
    if r.status_code != 200:
        typer.echo(f"unhealthy: HTTP {r.status_code}", err=True)
        raise typer.Exit(1)
    station = r.json().get("station", {})
    typer.echo(f"healthy: hibiscus-station {station.get('version', '?')} state={r.json().get('state', '?')}")


@app.command()
def doctor(
    home: Path | None = typer.Option(None, "--home"),
    out: Path = typer.Option(Path("."), "--out", help="Folder for the zip"),
    no_ping: bool = typer.Option(False, "--no-ping", help="Do not open the arms' serial ports"),
    no_cameras: bool = typer.Option(False, "--no-cameras", help="Do not probe cameras"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print every bus error (motor id, register)"),
) -> None:
    """Check ports, calibration, profiles and motors; write hibiscus-station-doctor-<time>.zip to send us.

    Read only: no motor register is written and no torque is switched on. Stop Station first to let
    the doctor ping the motors (a port has one owner); the zip holds no login token.
    """
    from hibiscus_station import doctor as doc

    # Libraries (lerobot's import checks, datasets, av...) log DEBUG lines on the root logger:
    # --verbose shows Station's own lines only, every bus error with its motor id and register.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s", force=True)
    logging.getLogger("hibiscus_station").setLevel(logging.DEBUG if verbose else logging.NOTSET)
    text, target = doc.run(
        home or station_home(),
        out,
        ping=not no_ping,
        probe_cameras=not no_cameras,
        echo=lambda s: typer.echo(f"... {s}", err=True),
    )
    typer.echo(text)
    if str(target.resolve()) not in text:  # the report's bilingual "what to send" names it already
        typer.echo(f"\nReport saved to {target.resolve()} - send this file with your bug report.")


@app.command()
def openapi(path: Path = typer.Argument(Path("openapi.json"))) -> None:
    """Write the OpenAPI document (committed as station/openapi.json)."""
    from hibiscus_station.openapi import export

    path.write_text(export(), encoding="utf-8")
    typer.echo(f"wrote {path}")


def demo_home() -> Path:
    """``--mock`` keeps its demo profile, datasets and sessions apart from the real arm's data."""
    home = station_home()
    return home.with_name(f"{home.name}-demo")


def main() -> None:
    from hibiscus_station.oscompat import utf8_console

    # OpenCV prints backend noise while cameras are probed (Windows: "VIDEOIO/FFMPEG: Failed list
    # devices for backend dshow"); real camera errors still reach Station's own log.
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

    utf8_console()  # Windows pipes / files default to cp1252
    app(prog_name="hibiscus-station")


if __name__ == "__main__":  # pragma: no cover
    main()
    sys.exit(0)
