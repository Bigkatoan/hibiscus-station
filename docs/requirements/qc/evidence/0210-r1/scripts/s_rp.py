import qc, hammer, json, time, collections
qc.setup()
for name in ("rp2", "rp3"):
    s, b = hammer.record(name, 3, ep=1.0); assert s == 200
    seen = collections.Counter(); t_idle = None
    while True:
        st = qc.status()
        if st["state"] == "idle" and t_idle is None: t_idle = time.time()
        s, r = qc.call("POST", "/sessions/replay", {"dataset": name, "episode": 2})
        seen[(st["state"], s, r.get("code") if isinstance(r, dict) else None)] += 1
        if s == 200 or s >= 500: break
        time.sleep(0.01)
    print(name, dict(seen), "replay accepted", round(time.time() - t_idle, 2), "s after idle", flush=True)
    time.sleep(2); st = qc.status(); print("  state", st["state"], st["reason"])
    if st["state"] == "estopped": qc.call("POST", "/estop/reset")
    qc.call("POST", "/sessions/current/control", {"action": "stop"}); time.sleep(1)
    if qc.status()["state"] == "estopped": qc.call("POST", "/estop/reset")
s, b = hammer.record("delme", 2, ep=1.0); assert s == 200
while qc.status()["state"] != "idle": time.sleep(0.01)
s, r = qc.call("DELETE", "/datasets/delme"); print("delete during finalize", s, r)
time.sleep(3); s, r = qc.call("GET", "/datasets/delme"); print("after", s, r.get("code") if isinstance(r, dict) else r)
