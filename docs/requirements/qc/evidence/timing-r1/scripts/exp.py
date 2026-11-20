"""usage: exp.py BUILD LOADTAG PORT  -> runs/<BUILD>-<LOADTAG>/results.json
Teleop 30 Hz (clean window, 1.5 s + 1.0 s SIGSTOP, 3 x 20 ms SIGSTOP), record 20 s @30 fps clean and
with a 1.5 s SIGSTOP, e-stop x5 in teleop, Stop during record x2, dead-man x3 in replay."""
import json, subprocess, sys, time
from pathlib import Path
import qct
from qct import api, status, wait, gapstats, probe, stall

b, tag, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
home = qct.Q / "runs" / f"{b}-{tag}"
subprocess.run(["rm", "-rf", str(home)])
ST = str(qct.Q / "scripts/st.sh")
print(subprocess.run([ST, "start", b, str(home), str(port)], capture_output=True, text=True).stdout)
pid = int((home / "pid").read_text())
c = qct.client(port)
qct.connect_cal(c)
R = {"build": b, "load": tag}
def save(): (home / "results.json").write_text(json.dumps(R, indent=1))
def win(a, z, kind="T"):
    return [x[0] for x in probe(home)[kind] if a <= x[0] <= z]
P = 1 / 30

# ---------------- teleop
ws = qct.WS(port)
qct.leader_follow(c, True)
qct.start(c, "/sessions/teleop", {"fps": 30})
wait(lambda: qct.phase(c) == "teleop", 30, "teleop phase")
t0 = time.perf_counter(); time.sleep(12); t1 = time.perf_counter()
s1 = stall(pid, 1.5); time.sleep(3)
s2 = stall(pid, 1.0); time.sleep(3)
s3 = []
for _ in range(3):
    s3.append(stall(pid, 0.020)); time.sleep(1)
t2 = time.perf_counter()
api(c, "POST", "/sessions/current/control", {"action": "stop"})
wait(lambda: status(c)["state"] == "idle", 30, "idle")
ws.close()
R["teleop_clean_ticks"] = gapstats(win(t0, t1), P)
R["teleop_clean_writes"] = gapstats(win(t0, t1, "W"), P)
R["teleop_all_ticks"] = gapstats(win(t0, t2), P, [s1, s2] + s3)
R["teleop_all_writes"] = gapstats(win(t0, t2, "W"), P, [s1, s2] + s3)
j = [(e[0], e[2]["tick"]) for e in ws.events if e[1] == "joints" and t0 <= e[0] <= t1]
R["teleop_ws_rate_hz"] = round((j[-1][1] - j[0][1]) / (j[-1][0] - j[0][0]), 3) if len(j) > 2 else None
save(); print("teleop", R["teleop_clean_ticks"]["mean_hz"], R["teleop_all_writes"]["stalls"])

# ---------------- record (clean, then with a stall)
for name, st_at in (("rec_clean", None), ("rec_stall", 8.0)):
    qct.leader_follow(c, True)
    qct.start(c, "/sessions/record", {"dataset": name, "task": "pick the cube", "num_episodes": 1,
              "episode_time_s": 20, "reset_time_s": 0, "fps": 30, "countdown_s": 0})
    wait(lambda: qct.phase(c) == "episode", 30, "episode")
    a = time.perf_counter()
    stalls = []
    if st_at:
        time.sleep(st_at); stalls.append(stall(pid, 1.5))
    wait(lambda: qct.phase(c) in ("saving", None) or status(c)["state"] == "idle", 90, "ep end", 0.05)
    z = time.perf_counter()
    wait(lambda: status(c)["state"] == "idle", 120, "idle")
    R[name] = {"ticks": gapstats(win(a, z), P, stalls), "writes": gapstats(win(a, z, "W"), P, stalls),
               "wall_s": round(z - a, 3), "last": status(c).get("last_session")}
    save(); print(name, R[name]["ticks"]["mean_hz"], R[name]["wall_s"])

# ---------------- e-stop x5 during teleop
es = []
for i in range(5):
    qct.leader_follow(c, True)
    qct.start(c, "/sessions/teleop", {"fps": 30})
    wait(lambda: qct.phase(c) == "teleop", 30, "teleop")
    time.sleep(1.5 + 0.37 * i)
    tp = time.perf_counter()
    api(c, "POST", "/estop")
    wait(lambda: status(c)["state"] == "estopped", 10, "estopped", 0.02)
    time.sleep(0.5)
    pr = probe(home)
    P_ = [x[0] for x in pr["P"] if x[0] >= tp - 0.001][0]
    E_ = [x[0] for x in pr["E"] if x[0] >= P_][0]
    wr = [x[0] for x in pr["W"] if x[0] > P_]
    tk = [x[0] for x in pr["T"] if x[0] > P_ and x[0] < E_]
    last_tick_before = [x[0] for x in pr["T"] if x[0] <= P_][-1]
    es.append({"press_to_estopped_ms": round((E_ - P_) * 1e3, 2), "writes_after_press": len(wr),
               "ticks_completed_between": len(tk), "press_minus_last_tick_start_ms": round((P_ - last_tick_before) * 1e3, 2)})
    api(c, "POST", "/estop/reset")
    wait(lambda: status(c)["state"] == "idle", 20, "idle")
R["estop"] = es; save(); print("estop", es)

# ---------------- Stop during recording x2
stops = []
for i in range(2):
    qct.leader_follow(c, True)
    qct.start(c, "/sessions/record", {"dataset": f"stop{i}", "task": "pick the cube", "num_episodes": 1,
              "episode_time_s": 60, "reset_time_s": 0, "fps": 30, "countdown_s": 0})
    wait(lambda: qct.phase(c) == "episode", 30, "episode")
    time.sleep(5 + i)
    t = time.perf_counter(); v = api(c, "POST", "/sessions/current/control", {"action": "stop"}); ans = time.perf_counter() - t
    ph = qct.phase(c)
    wait(lambda: status(c)["state"] == "idle", 120, "idle", 0.05); idle = time.perf_counter() - t
    stops.append({"answer_s": round(ans, 3), "phase_after": ph, "view_phase": v.get("phase"), "idle_after_s": round(idle, 2),
                  "elapsed_before_stop_s": 5 + i})
R["stop_record"] = stops; save(); print("stops", stops)

# ---------------- dead-man x3 during replay of rec_clean
dm = []
for i in range(3):
    ws = qct.WS(port, hb_s=0.25)
    qct.leader_follow(c, False)
    r = c.post("/sessions/replay", json={"dataset": "rec_clean", "episode": 0})
    assert r.is_success, r.text
    wait(lambda: status(c)["state"] not in ("idle",), 30, "replay", 0.05); time.sleep(0.5); R.setdefault("replay_states", []).append([status(c)["state"], qct.phase(c)])
    time.sleep(2 + 0.3 * i)
    ws.hb_on.clear(); tcut = time.perf_counter()
    wait(lambda: status(c)["state"] == "estopped", 10, "estopped", 0.02)
    time.sleep(0.3)
    pr = probe(home)
    lastH = [x[0] for x in pr["H"] if x[0] <= tcut + 0.3][-1]
    E_ = [x for x in pr["E"] if x[0] > tcut][0]
    tks = [x[0] for x in pr["T"] if lastH + 1.0 <= x[0] <= E_[0]]
    dm.append({"last_heartbeat_to_estop_s": round(E_[0] - lastH, 4), "reason": E_[1],
               "ticks_started_after_timeout_before_estop": len(tks), "state": status(c)["state"]})
    ws.close()
    api(c, "POST", "/estop/reset"); wait(lambda: status(c)["state"] == "idle", 20, "idle")
R["deadman"] = dm; save(); print("deadman", dm)
print(subprocess.run([ST, "stop", str(home), str(port)], capture_output=True, text=True).stdout)
