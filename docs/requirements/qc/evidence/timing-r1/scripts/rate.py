"""usage: rate.py BUILD TAG PORT MODE(shim|plain) FPS -> runs/<BUILD>-<TAG>/rate.json
teleop 15 s at 30 Hz + record one 15 s episode at FPS; rate, lag behind the nominal grid, jitter."""
import json, subprocess, sys, time, statistics
import qct
from qct import api, status, wait, gapstats, probe
b, tag, port, mode, fps = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
home = qct.Q / "runs" / f"{b}-{tag}"; subprocess.run(["rm", "-rf", str(home)])
ST = str(qct.Q / "scripts/st.sh")
subprocess.run([ST, "start", b, str(home), str(port), mode], capture_output=True)
c = qct.client(port); qct.connect_cal(c)
R = {"build": b, "tag": tag, "mode": mode}
def win(a, z, kind="T"):
    return [x[0] for x in probe(home)[kind] if a <= x[0] <= z] if mode == "shim" else []
def lag(ts, P):
    return round(((ts[-1] - ts[0]) - (len(ts) - 1) * P) * 1e3, 1) if len(ts) > 1 else None
ws = qct.WS(port); qct.leader_follow(c, True)
qct.start(c, "/sessions/teleop", {"fps": 30})
wait(lambda: qct.phase(c) == "teleop", 30, "teleop")
a = time.perf_counter(); time.sleep(15); z = time.perf_counter()
api(c, "POST", "/sessions/current/control", {"action": "stop"}); wait(lambda: status(c)["state"] == "idle", 60, "idle")
j = [(e[0], e[2]["tick"]) for e in ws.events if e[1] == "joints" and a <= e[0] <= z]
R["teleop_ws_hz"] = round((j[-1][1] - j[0][1]) / (j[-1][0] - j[0][0]), 3)
if mode == "shim":
    t = win(a, z); R["teleop"] = gapstats(t, 1 / 30); R["teleop"]["lag_ms"] = lag(t, 1 / 30)
    R["teleop_writes"] = gapstats(win(a, z, "W"), 1 / 30)
qct.leader_follow(c, True)
qct.start(c, "/sessions/record", {"dataset": "r", "task": "t", "num_episodes": 1, "episode_time_s": 15,
          "reset_time_s": 0, "fps": fps, "countdown_s": 0})
wait(lambda: qct.phase(c) == "episode", 30, "episode", 0.02); a = time.perf_counter()
wait(lambda: qct.phase(c) != "episode", 120, "end", 0.02); z = time.perf_counter()
wait(lambda: status(c)["state"] == "idle", 120, "idle")
R["record_wall_s"] = round(z - a, 3)
R["record_ws_hz"] = None
if mode == "shim":
    t = win(a, z); R["record"] = gapstats(t, 1 / fps); R["record"]["lag_ms"] = lag(t, 1 / fps)
    R["record_writes"] = gapstats(win(a, z, "W"), 1 / fps)
ws.close()
subprocess.run([ST, "stop", str(home), str(port)], capture_output=True)
(home / "rate.json").write_text(json.dumps(R, indent=1))
T = R.get("teleop", {}); Rr = R.get("record", {})
print(b, tag, mode, "teleop ws", R["teleop_ws_hz"], "tick", T.get("mean_hz"), "lag", T.get("lag_ms"), "sd", T.get("sd_gap_ms"), "p99", T.get("p99_gap_ms"), "minW", R.get("teleop_writes", {}).get("min_gap_ms"),
      "| record wall", R["record_wall_s"], "tick", Rr.get("mean_hz"), "lag", Rr.get("lag_ms"), "sd", Rr.get("sd_gap_ms"), "p99", Rr.get("p99_gap_ms"), "minW", R.get("record_writes", {}).get("min_gap_ms"), flush=True)
