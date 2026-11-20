import qc, hammer, json, time
qc.setup()
def phase(): 
    se = qc.status()["session"]; return se and se["episode"] and (se["episode"]["index"], se["episode"]["phase"])
# re-record: ep 0 recorded, during ep1 press rerecord, then next etc
name = "rerec"
with hammer.Hammer(name) as h:
    s, b = hammer.record(name, 3, ep=4.0); assert s == 200, b
    while phase() != (1, "episode"): time.sleep(0.05)
    time.sleep(1.5); print("rerecord", qc.call("POST", "/sessions/current/control", {"action": "rerecord"})[0], phase())
    time.sleep(0.5); print("after rerecord", phase())
    while phase() and phase()[0] < 2: time.sleep(0.05)
    print("ep2", phase())
    time.sleep(1); print("next", qc.call("POST", "/sessions/current/control", {"action": "next"})[0])
    qc.wait_idle(); time.sleep(1)
print(json.dumps(h.report())[:800])
s, d = qc.call("GET", f"/datasets/{name}"); print("rerec", d["episodes"], [(e["index"], e["state"], e["frames"]) for e in d["episode_list"]])
# Stop during recording: time to idle
name = "stopper"
with hammer.Hammer(name) as h:
    s, b = hammer.record(name, 50, ep=5.0); assert s == 200, b
    while phase() != (2, "episode"): time.sleep(0.05)
    time.sleep(2.0)
    t0 = time.time(); s, b = qc.call("POST", "/sessions/current/control", {"action": "stop"}); t1 = time.time()
    st = qc.status(); print("stop http", s, round(t1 - t0, 2), st["state"], st["sub"])
    qc.wait_idle(); print("idle after", round(time.time() - t0, 2))
    time.sleep(1)
print(json.dumps(h.report())[:800])
s, d = qc.call("GET", f"/datasets/{name}"); print("stopper", d["episodes"], d["finalized"], [(e["index"], e["state"], e["frames"]) for e in d["episode_list"]])
# Stop during the saving phase
name = "stopsave"
s, b = hammer.record(name, 5, ep=2.0); assert s == 200, b
while phase() != (1, "saving"): time.sleep(0.01)
t0 = time.time(); s, b = qc.call("POST", "/sessions/current/control", {"action": "stop"}); print("stop@saving", s, round(time.time()-t0,2))
qc.wait_idle(); print("idle after", round(time.time() - t0, 2))
s, d = qc.call("GET", f"/datasets/{name}"); print("stopsave", d["episodes"], d["finalized"], [(e["index"], e["state"], e["frames"]) for e in d["episode_list"]])
