import qc, hammer, json, time
qc.setup()
name = "stress12"
with hammer.Hammer(name, 0.0) as h1, hammer.Hammer(name, 0.0) as h2:
    s, b = hammer.record(name, 12, ep=3.0)
    assert s == 200, (s, b)
    qc.wait_idle(); time.sleep(1)
print(json.dumps(h1.report())[:2000]); print(json.dumps(h2.report())[:2000])
s, d = qc.call("GET", f"/datasets/{name}"); print(s, d["episodes"], d["finalized"], [e["state"] for e in d["episode_list"]], d["size_bytes"])
