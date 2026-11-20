import qc, json, sys
names = sys.argv[1:] or ["dmgsc","dmgsj","dmgi1","dmgi2","dmgi3","dmgi4","dmgv","dmgm","dmgp","dmgd","dmgx","dmgt"]
s, b = qc.call("GET", "/datasets"); print("LIST", s, [(d["name"], d["episodes"], d["finalized"]) for d in b["datasets"] if d["name"].startswith("dmg")] if s == 200 else b)
for n in names:
    s, d = qc.call("GET", f"/datasets/{n}")
    if s != 200: print(n, s, d if isinstance(d,str) else (d.get("code"), d.get("detail"))); continue
    el = d["episode_list"]
    tel = [qc.call("GET", f"/datasets/{n}/episodes/{i}/telemetry")[0] for i in range(min(len(el), 8))]
    print(n, s, "eps", d["episodes"], "fin", d["finalized"], "rows", len(el), sorted({e.get("state") for e in el}), "tel", tel)
    s3, r = qc.call("POST", f"/datasets/{n}/upload", {"new_dataset_name": n}); print("   upload", s3, r.get("code") if isinstance(r, dict) else r)
    s4, r = qc.call("POST", "/sessions/record", {"dataset": n, "mode": "append", "task": "x", "num_episodes": 1, "episode_time_s": 1, "reset_time_s": 0, "countdown_s": 0})
    print("   append", s4, r.get("code") if isinstance(r, dict) else r, (r.get("detail") or "")[:140] if isinstance(r, dict) else "")
    if s4 == 200:
        qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.wait_idle()
