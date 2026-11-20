"""Adversarial safety checks of block programs on the mock Station (station-programs.md §5.1, §6, §11;
station.md §4.7).

Every motion of a program goes through the owner's e-stop, dead-man, ThermalGuard and SafetyFilter
paths; these tests try to get around them: e-stop during the approach, a wait and a policy run,
heartbeat loss while the program only waits, a thermal cutoff mid-program, fast replay without the
profile flag, a trajectory of another calibration, busy loops the compiler cannot see, malformed and
deeply nested editor JSON, concurrent starts, signal spam, path traversal in ids, a detector on a
camera that does not exist.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from blocks_dsl import (
    blk,
    change,
    forever,
    if_,
    key,
    num,
    play,
    program,
    sees,
    var,
    wait,
    wait_until,
)
from conftest import (
    Heartbeat,
    ManualClock,
    connect_calibrated,
    deep_json,
    estop_ticks,
    mock_profile,
    press_estop_frozen_within_one_tick,
    ticks_pass,
    wait_for,
)

from hibiscus_station.mock import get_world
from hibiscus_station.mock.policy import make_dummy_act
from hibiscus_station.models.importer import import_dir
from hibiscus_station.programs import schemas as ps
from hibiscus_station.programs.interfaces import TrajectorySamples
from hibiscus_station.programs.interpreter import Interpreter
from hibiscus_station.station import Station

API = "/api/v1"
JOINTS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


def _traj(st: Station, *, start_offset: float = 0.0, seconds: float = 3.0, fps: int = 30) -> str:
    """A ready trajectory: shoulder_pan sweeps 10° from ``present + start_offset``."""
    here = dict(st.owner.last_obs)
    n = int(seconds * fps)
    base = [here.get(j, 0.0) for j in JOINTS]
    rows = []
    for i in range(n):
        r = list(base)
        r[0] = base[0] + start_offset + 10.0 * i / n
        rows.append(r)
    samples = TrajectorySamples(fps=fps, names=JOINTS, t=[i / fps for i in range(n)], rows=rows)
    store = st.programs.trajectories()
    tr = store.create_draft(name="T", fps=fps, samples=samples, keyframes={}, keyframe_times=[])
    store.update(tr.id, ps.TrajectoryUpdate(save=True, trim=ps.TrimRange(start_s=0, end_s=0)))
    return tr.id


def _put(client: Any, doc: dict[str, Any], pid: str = "p", **kw: Any) -> ps.Program:
    r = client.put(f"{API}/programs/{pid}", json={"name": "P", "editor": doc, **kw})
    assert r.status_code == 200, r.text
    return ps.Program.model_validate(r.json())


def _put_deep(client: Any, pid: str, body: dict[str, Any]) -> Any:
    """PUT a body too deep for the C ``json`` encoder on Windows (its recursion limit is 3000)."""
    return client.put(
        f"{API}/programs/{pid}", content=deep_json(body), headers={"content-type": "application/json"}
    )


def _refused_as_too_deep(r: Any) -> bool:
    """Windows: Python cannot even parse JSON nested past 3000 levels; Station must answer a clean
    400 ``validation_failed`` (never a 500 or a crash). Elsewhere the limit is 10000."""
    return sys.platform == "win32" and r.status_code == 400 and r.json()["code"] == "validation_failed"


def _run(client: Any, pid: str = "p", **body: Any) -> Any:
    return client.post(f"{API}/programs/{pid}/run", json=body)


def _rt(st: Station, pid: str = "p") -> Interpreter:
    rt = st.programs.runs.get(pid)
    assert isinstance(rt, Interpreter)
    return rt


def _phase(st: Station) -> str | None:
    s = st.owner.session
    return s.episode.phase if s is not None else None


@pytest.fixture
def real(connected: Station) -> Station:
    """Connected mock Station whose programs may run on the (mock) hardware without a dry run."""
    connected.settings.programs.require_dry_run = False
    return connected


# =========================================================================== e-stop
def test_estop_during_the_approach_aborts_the_program(real: Station, client: Any) -> None:
    st = real
    tid = _traj(st, start_offset=40.0)
    _put(client, program(play(tid, id_="pl")))
    world = get_world("mock://follower")
    with Heartbeat(st):
        assert _run(client).status_code == 200
        rt = _rt(st)
        wait_for(lambda: _phase(st) == "approach", 3)
        time.sleep(0.2)
        press_estop_frozen_within_one_tick(st, world)
        assert rt.join(2) and rt.outcome == "estopped"
    assert world.any_torque()
    assert client.post(f"{API}/estop/reset").status_code == 200
    time.sleep(0.3)
    assert st.owner.state == "idle" and rt.finished  # never resumes by itself


def test_estop_during_a_wait_ends_the_run_at_once(real: Station, client: Any) -> None:
    st = real
    _put(client, program(wait(30, id_="w")))
    with Heartbeat(st):
        assert _run(client).status_code == 200
        rt = _rt(st)
        wait_for(lambda: rt.state().status == "waiting", 3)
        t0 = time.monotonic()
        st.owner.press_estop("user")
        assert rt.join(1.0) and rt.outcome == "estopped"
        assert time.monotonic() - t0 < 0.5
        wait_for(lambda: st.owner.state == "estopped", 1)
    st.owner.call("estop_reset")


def test_estop_during_run_model(tmp_path: Path, station: Station, client: Any) -> None:
    st = station
    st.settings.programs.require_dry_run = False
    connect_calibrated(st, mock_profile())
    src = make_dummy_act(tmp_path / "act" / "pretrained_model", {"wrist": (96, 128)})
    entry = import_dir(st.registry, src, st.paths.staging, [tmp_path])
    st.jobs.wait(st.load_model(entry.key, "cpu").id)
    doc = program(blk("hb_run_model_for", "m", fields={"MODEL": entry.key, "TASK": "", "SECONDS": 20}))
    p = _put(client, doc)
    assert p.ast is not None, p.issues
    world = get_world("mock://follower")
    with Heartbeat(st):
        r = _run(client)
        assert r.status_code == 200, r.text
        rt = _rt(st)
        wait_for(lambda: _phase(st) == "episode", 5)
        time.sleep(0.5)
        press_estop_frozen_within_one_tick(st, world)
        assert rt.join(2) and rt.outcome == "estopped"
    st.owner.call("estop_reset")


def test_deadman_loss_while_the_program_waits(real: Station, client: Any) -> None:
    """NFR-4 (QH-6): no heartbeat while a program waits -> e-stop "ui_lost" after the dead-man
    timeout (1.0 s) + at most 1 tick. The watchdog runs on a clock the test steps, the bound is
    counted in loop ticks: this thread's wall clock measured 1.61 s on a loaded Windows runner (the
    test thread woke late), which says nothing about the loop."""
    st = real
    clock = ManualClock()
    st.owner.watchdog.clock = clock
    timeout = st.settings.safety.deadman_timeout_s
    estop_at = estop_ticks(st)
    _put(client, program(wait_until(key("1"), timeout=60, id_="wu")))
    assert _run(client).status_code == 200  # no heartbeat at all
    rt = _rt(st)
    armed = clock.t  # the session start armed the watchdog on this clock
    ticks_pass(st, 10)
    clock.t = armed + timeout - 0.001  # just inside the timeout: the program keeps waiting
    ticks_pass(st, 10)
    assert st.owner.state == "programming" and not estop_at, st.owner.state
    clock.t = armed + timeout + 0.001  # just past it
    tick = st.owner.tick  # the tick in flight when the timeout passed is at most this one
    wait_for(lambda: estop_at, 10)  # the owner thread sets the state, then tells its listeners
    assert estop_at[0] <= tick + 1, (estop_at, tick)
    assert st.owner.reason == "ui_lost"
    assert rt.join(2) and rt.outcome == "estopped"
    st.owner.call("estop_reset")


def test_thermal_critical_during_a_program(real: Station, client: Any) -> None:
    st = real
    tid = _traj(st, seconds=6.0)
    _put(client, program(play(tid, id_="pl")))
    world = get_world("mock://follower")
    with Heartbeat(st):
        assert _run(client).status_code == 200
        rt = _rt(st)
        wait_for(lambda: _phase(st) == "replay", 3)
        world.inject("elbow_flex", temp_c=66.0)
        wait_for(lambda: st.owner.state == "estopped", 4)
        assert st.owner.reason == "thermal"
        assert rt.join(2) and rt.outcome == "estopped"
    assert not world.any_torque()
    world.inject("elbow_flex", temp_c=61.0)  # hot: a new program cannot start
    wait_for(lambda: st.owner.guard.temp_level.get(("follower", "elbow_flex")) == "hot", 4)
    assert client.post(f"{API}/estop/reset").status_code == 409
    world.inject("elbow_flex", clear_temp=True, temp_c=30.0)


def test_hot_motor_refuses_a_program_start(real: Station, client: Any) -> None:
    st = real
    _put(client, program(wait(0.2)))
    get_world("mock://follower").inject("gripper", temp_c=61.0)
    wait_for(lambda: st.owner.guard.temp_level.get(("follower", "gripper")) == "hot", 4)
    r = _run(client)
    assert r.status_code == 409 and r.json()["code"] == "motor_hot", r.text
    assert st.programs.runs.get("p") is None or _rt(st).finished
    assert _run(client).json()["code"] == "motor_hot"  # a refused start does not block the next one


# =========================================================================== refusals
def test_fast_replay_needs_the_flag_in_programs(real: Station, client: Any) -> None:
    st = real
    tid = _traj(st)
    _put(client, program(play(tid, speed=150, id_="pl")))
    r = _run(client, confirm=["fast_replay:pl"])
    assert r.status_code == 422, r.text
    assert "fast_replay_not_allowed" in {e["code"] for e in r.json()["errors"]}
    assert _run(client, dry_run=True, confirm=["fast_replay:pl"]).status_code == 422
    assert st.owner.state == "idle"


def test_trajectory_from_another_calibration_is_refused(real: Station, client: Any) -> None:
    st = real
    tid = _traj(st)
    _put(client, program(play(tid, id_="pl")))
    from hibiscus_station.programs.calibration_ref import calibration_file

    f = calibration_file(st.cal_root, st.owner.profile)  # type: ignore[arg-type]
    f.write_text(f.read_text(encoding="utf-8") + " ")
    r = _run(client)
    assert r.status_code == 422 and "trajectory_needs_check" in {e["code"] for e in r.json()["errors"]}, (
        r.text
    )
    r = client.post(f"{API}/trajectories/{tid}/play", json={"speed_pct": 100})
    assert r.status_code == 409 and r.json()["code"] == "needs_check"


# =========================================================================== loops
def test_wait_zero_in_a_forever_loop_is_paced(station: Station, client: Any) -> None:
    """``repeat forever { wait 0 }`` passes the compiler's busy-loop rule; the runner must still pace it."""
    st = station
    connect_calibrated(st)
    doc = program(
        forever(wait(0, id_="w0"), change("n", num(1)), id_="loop"), variables=[("n", "n", "Number")]
    )
    _put(client, doc)
    assert _run(client, dry_run=True).status_code == 200
    rt = _rt(st)
    time.sleep(1.0)
    n = rt.state().variables["n"]
    assert client.post(f"{API}/programs/p/stop").status_code == 200
    assert isinstance(n, float) and n <= 15, n  # ≤ condition_hz iterations per second


def test_wait_with_a_zero_variable_is_paced(station: Station, client: Any) -> None:
    st = station
    connect_calibrated(st)
    doc = program(
        forever(blk("hb_wait", "w", inputs={"SECONDS": var("z")}), change("n", num(1)), id_="loop"),
        variables=[("n", "n", "Number"), ("z", "z", "Number")],
    )
    _put(client, doc)
    assert _run(client, dry_run=True).status_code == 200
    rt = _rt(st)
    time.sleep(1.0)
    n = rt.state().variables["n"]
    assert client.post(f"{API}/programs/p/stop").status_code == 200
    assert isinstance(n, float) and n <= 15, n


def test_run_log_is_bounded(station: Station, client: Any) -> None:
    """A fast loop that logs every iteration must not fill the disk."""
    from hibiscus_station.programs import runlog

    st = station
    connect_calibrated(st)
    doc = program(
        forever(
            wait(0.01),
            change("n", num(1)),
            blk("hb_log", inputs={"TEXT": var("n")}),
            id_="loop",
        ),
        variables=[("n", "n", "Number")],
    )
    _put(client, doc)
    old = runlog.MAX_FILE_LINES
    runlog.MAX_FILE_LINES = 50
    try:
        assert _run(client, dry_run=True).status_code == 200
        rt = _rt(st)
        wait_for(lambda: float(rt.state().variables["n"]) >= 60, 15)
        assert client.post(f"{API}/programs/p/stop").status_code == 200
    finally:
        runlog.MAX_FILE_LINES = old
    body = client.get(f"{API}/programs/p/runs/{rt.run_id}").json()
    lines = body["lines"]
    assert len(lines) == 50 + 2, len(lines)  # + the "log full" warning + end
    assert lines[-2]["message"].startswith("the run log is full") and lines[-1]["kind"] == "end"
    assert body["summary"]["outcome"] == "stopped"


# =========================================================================== editor JSON
def _nested_ifs(depth: int) -> dict[str, Any]:
    inner: dict[str, Any] = blk("hb_wait", inputs={"SECONDS": num(0.1)})
    for _ in range(depth):
        inner = if_([(blk("logic_boolean", fields={"BOOL": "TRUE"}), [inner])])
    return program(inner)


@pytest.mark.parametrize("depth", [10, 33, 300, 1500])
def test_deeply_nested_programs_never_crash(station: Station, client: Any, depth: int) -> None:
    from hibiscus_station.programs.compiler import MAX_NESTING

    connect_calibrated(station)
    r = _put_deep(client, "deep", {"name": "deep", "editor": _nested_ifs(depth)})
    if _refused_as_too_deep(r):
        return
    assert r.status_code == 200, r.text[:300]
    p = ps.Program.model_validate(r.json())
    if depth * 2 <= MAX_NESTING:
        assert p.ast is not None, p.issues
    else:
        assert p.ast is None and [i.code for i in p.issues] == ["too_many_blocks"]
    assert client.get(f"{API}/programs").json()["programs"][0]["id"] == "deep"
    assert client.get(f"{API}/programs/deep").json()["version"] == 1
    assert client.post(f"{API}/programs/deep/check").status_code == 200
    if p.ast is not None:
        assert _run(client, "deep", dry_run=True).status_code == 200
        assert _rt(station, "deep").join(10) and _rt(station, "deep").outcome == "completed"


@pytest.mark.parametrize("n", [100, 400, 990])  # 2 blocks each (wait + number), ≤ max_blocks
def test_long_programs_round_trip(station: Station, client: Any, n: int) -> None:
    """A Blockly chain nests two levels per statement: long programs must still save and load."""
    connect_calibrated(station)
    p = _put(client, program(*[wait(0.01) for _ in range(n)]), pid="long")
    assert p.ast is not None and len(p.ast.body) == n
    got = client.get(f"{API}/programs/long")
    assert got.status_code == 200 and got.json()["editor"] == p.editor
    assert [x["id"] for x in client.get(f"{API}/programs").json()["programs"]] == ["long"]
    assert _put(client, program(*[wait(0.01) for _ in range(n)]), pid="long").version == 2
    assert client.post(f"{API}/programs/long/check").json()["ok"]


MALFORMED: list[Any] = [
    {},
    {"blocks": []},
    {"blocks": {"blocks": {"x": 1}}},
    {"blocks": {"blocks": [1, "a", None, []]}},
    {"blocks": {"blocks": [{"type": "hb_start", "id": 5, "inputs": []}]}},
    {"blocks": {"blocks": [{"type": "hb_start", "inputs": {"DO": {"block": "x"}}}]}},
    {"blocks": {"blocks": [{"type": "hb_start", "inputs": {"DO": {"block": {"type": None}}}}]}},
    {"blocks": {"blocks": [{"type": "hb_start", "inputs": {"DO": {"block": {"type": "hb_wait"}}}}]}},
    {
        "blocks": {
            "blocks": [
                {
                    "type": "hb_start",
                    "inputs": {
                        "DO": {
                            "block": {
                                "type": "controls_if",
                                "extraState": {"elseIfCount": 10**9, "hasElse": "yes"},
                            }
                        }
                    },
                }
            ]
        }
    },
    {
        "blocks": {
            "blocks": [
                {
                    "type": "hb_start",
                    "inputs": {
                        "DO": {
                            "block": {
                                "type": "hb_log",
                                "inputs": {
                                    "TEXT": {"block": {"type": "text_join", "extraState": {"itemCount": -5}}}
                                },
                            }
                        }
                    },
                }
            ]
        }
    },
    {
        "blocks": {
            "blocks": [
                {
                    "type": "hb_start",
                    "inputs": {
                        "DO": {
                            "block": {
                                "type": "hb_play_trajectory",
                                "fields": {"TRAJECTORY": ["../../etc"], "SPEED": "1e999"},
                            }
                        }
                    },
                }
            ]
        }
    },
    {
        "variables": [{"id": 1}, "x", {"id": "v", "name": "v", "type": 5}],
        "blocks": {
            "blocks": [
                {
                    "type": "hb_start",
                    "inputs": {
                        "DO": {
                            "block": {
                                "type": "variables_set",
                                "fields": {"VAR": {"id": {"nested": 1}}},
                                "inputs": {
                                    "VALUE": {"block": {"type": "math_number", "fields": {"NUM": "nan"}}}
                                },
                            }
                        }
                    },
                }
            ]
        },
    },
    {
        "blocks": {
            "blocks": [
                {
                    "type": "hb_start",
                    "inputs": {
                        "DO": {
                            "block": {
                                "type": "hb_wait",
                                "inputs": {
                                    "SECONDS": {"block": {"type": "math_number", "fields": {"NUM": 1e308}}}
                                },
                            }
                        }
                    },
                }
            ]
        }
    },
]


@pytest.mark.parametrize("doc", MALFORMED)
def test_malformed_editor_json_is_saved_with_issues(station: Station, client: Any, doc: Any) -> None:
    connect_calibrated(station)
    r = client.put(f"{API}/programs/bad", json={"name": "bad", "editor": doc})
    assert r.status_code in (200, 422), r.text[:300]
    if r.status_code == 200:
        p = r.json()
        assert client.post(f"{API}/programs/bad/check").status_code == 200
        rr = _run(client, "bad", dry_run=True)
        assert rr.status_code in (200, 422), rr.text[:300]
        if rr.status_code == 200:
            rt = _rt(station, "bad")
            client.post(f"{API}/programs/bad/stop")
            assert rt.join(5)
        assert p["version"] == 1


def test_too_many_blocks(station: Station, client: Any) -> None:
    connect_calibrated(station)
    r = _put_deep(client, "p", {"name": "P", "editor": program(*[wait(0.1) for _ in range(2100)])})
    if _refused_as_too_deep(r):
        return
    assert r.status_code == 200, r.text[:300]
    p = ps.Program.model_validate(r.json())
    assert p.ast is None and [i.code for i in p.issues] == ["too_many_blocks"]


# =========================================================================== concurrency
def test_concurrent_starts_answer_409(real: Station, client: Any) -> None:
    st = real
    _put(client, program(wait(5)))
    _put(client, program(wait(5)), pid="q")
    codes: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def go(i: int) -> None:
        barrier.wait()
        r = _run(client, "p" if i % 2 else "q", dry_run=i % 4 == 0)
        with lock:
            codes.append(r.status_code)

    with Heartbeat(st):
        ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(15)
        assert sorted(codes).count(200) == 1, codes
        assert all(c in (200, 409) for c in codes), codes
        running = [
            rt for rt in (st.programs.runs.get("p"), st.programs.runs.get("q")) if rt and not rt.finished
        ]
        assert len(running) == 1
        running[0].stop()
        assert running[0].join(5)  # type: ignore[attr-defined]
        wait_for(lambda: st.owner.state == "idle", 5)


def test_trajectory_play_while_a_program_runs_is_busy(real: Station, client: Any) -> None:
    st = real
    tid = _traj(st)
    _put(client, program(wait(5)))
    with Heartbeat(st):
        assert _run(client).status_code == 200
        r = client.post(f"{API}/trajectories/{tid}/play", json={"speed_pct": 100})
        assert r.status_code == 409 and r.json()["code"] == "busy"
        client.post(f"{API}/programs/p/stop")
        wait_for(lambda: st.owner.state == "idle", 5)


# =========================================================================== signals, MQTT
def test_signal_spam_is_bounded(station: Station, client: Any) -> None:
    from hibiscus_station.programs.signals import MAX_SIGNALS

    for i in range(MAX_SIGNALS):
        assert client.post(f"{API}/signals/s{i}", json={"value": i}).status_code == 200
    r = client.post(f"{API}/signals/one_more", json={"value": 1})
    assert r.status_code == 422
    assert client.post(f"{API}/signals/s1", json={"value": "x" * 501}).status_code == 422
    assert client.post(f"{API}/signals/s1", json={"value": 2}).status_code == 200  # updates still work
    assert len(client.get(f"{API}/signals").json()["signals"]) == MAX_SIGNALS


def test_mqtt_is_off_by_default(station: Station) -> None:
    assert station.settings.programs.mqtt_url is None
    assert station.programs.mqtt is None
    names = [t.name.lower() for t in threading.enumerate() if not t.name.startswith("pytest_timeout")]
    assert not [n for n in names if "paho" in n or "mqtt" in n]


def test_signals_need_the_token(station: Station, client: Any) -> None:
    r = client.post(f"{API}/signals/x", json={"value": 1}, headers={"Authorization": ""})
    assert r.status_code in (401, 403)


# =========================================================================== ids
@pytest.mark.parametrize(
    "path",
    [
        "/programs/..%2F..%2Fetc",
        "/programs/%2e%2e",
        "/programs/..",
        "/programs/a%00b",
        "/programs/p/runs/..%2F..%2Fsettings",
        "/detectors/..%2Fx",
        "/trajectories/..%2F..%2F",
        "/trajectories/t_20261116_120000_aaaa/keyframes/..%2F..%2F/0",
        "/trajectories/t_20261116_120000_aaaa/keyframes/../0",
        "/signals/..%2Fx",
    ],
)
def test_path_traversal_in_ids(station: Station, client: Any, path: str) -> None:
    connect_calibrated(station)
    for method in ("GET", "PUT", "DELETE", "POST"):
        r = client.request(method, f"{API}{path}", json={"name": "x", "editor": {}, "value": 1})
        assert r.status_code in (404, 405, 422), (method, path, r.status_code, r.text[:200])


# =========================================================================== detectors
def test_detector_on_a_missing_camera(real: Station, client: Any) -> None:
    st = real
    det = {
        "name": "Ghost",
        "spec": {
            "kind": "color",
            "camera": "nope",
            "roi": {"x": 0, "y": 0, "w": 1, "h": 1},
            "rules": [{"label": "red", "h_min": 170, "h_max": 10}],
        },
    }
    r = client.put(f"{API}/detectors/ghost", json=det)
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        r = client.post(f"{API}/detectors/ghost/test", json={})
        assert r.status_code in (409, 422), r.text
    _put(client, program(wait_until(sees("ghost", "red", camera="nope", id_="s"), timeout=1, id_="wu")))
    rep = client.post(f"{API}/programs/p/check").json()
    assert not rep["ok"], rep
    assert _run(client).status_code == 422
    assert st.owner.state == "idle"


def test_detector_camera_goes_stale_during_a_run(real: Station, client: Any) -> None:
    st = real
    det = {
        "name": "Cubes",
        "spec": {
            "kind": "color",
            "camera": "wrist",
            "roi": {"x": 0, "y": 0, "w": 1, "h": 1},
            "rules": [{"label": "blue", "h_min": 100, "h_max": 130, "s_min": 120, "v_min": 80}],
        },
    }
    assert client.put(f"{API}/detectors/cubes", json=det).status_code == 200
    _put(client, program(wait_until(sees("cubes", "blue", id_="s"), timeout=1.5, id_="wu")))
    cam = st.hub.camera("wrist")
    cam.show_cube("green")
    with Heartbeat(st):
        assert _run(client).status_code == 200
        rt = _rt(st)
        assert rt.join(6) and rt.outcome == "timeout", rt.state()
        wait_for(lambda: st.owner.state == "idle", 3)
    cam.show_cube(None)


# =========================================================================== dry run pass rule
def test_a_dry_run_stopped_before_any_motion_does_not_count(station: Station, client: Any) -> None:
    """§5.2: a dry run stopped before a motion completed proves nothing about the motions."""
    st = station
    connect_calibrated(st)
    tid = _traj(st, seconds=0.5)
    doc = program(forever(if_([(key("1"), [play(tid, id_="pl")])]), wait(0.1), id_="loop"))
    p = _put(client, doc)
    assert _run(client, dry_run=True).status_code == 200
    rt = _rt(st)
    wait_for(lambda: rt.state().status == "waiting", 3)
    assert client.post(f"{API}/programs/p/stop").status_code == 200
    assert client.get(f"{API}/programs/p").json()["dry_run_version"] is None
    with Heartbeat(st):
        assert _run(client).json()["code"] == "dry_run_required"
    # the same program, once the motion has run in the simulation
    assert _run(client, dry_run=True).status_code == 200
    rt = _rt(st)
    wait_for(lambda: rt.state().status == "waiting", 3)
    assert client.post(f"{API}/programs/p/input", json={"kind": "key", "value": "1"}).status_code == 200
    log = lambda: client.get(f"{API}/programs/p/runs/{rt.run_id}").json()["lines"]  # noqa: E731
    wait_for(
        lambda: any(ln["kind"] == "motion" and ln["data"].get("outcome") == "completed" for ln in log()), 10
    )
    assert client.post(f"{API}/programs/p/stop").status_code == 200
    assert client.get(f"{API}/programs/p").json()["dry_run_version"] == p.version


def test_a_dry_run_without_motions_passes_when_stopped(station: Station, client: Any) -> None:
    connect_calibrated(station)
    p = _put(client, program(forever(wait(0.1), id_="loop")))
    assert _run(client, dry_run=True).status_code == 200
    rt = _rt(station)
    wait_for(lambda: rt.state().status == "waiting", 3)
    assert client.post(f"{API}/programs/p/stop").status_code == 200
    assert client.get(f"{API}/programs/p").json()["dry_run_version"] == p.version
