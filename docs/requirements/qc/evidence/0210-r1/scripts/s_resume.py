import qc, hammer, json, time
qc.setup()
for name, n in (("cnt3", 2), ("cnt11", 12), ("cnt3", 1)):
    before = qc.ok("GET", f"/datasets/{name}")["episodes"]
    with hammer.Hammer(name) as h:
        s, b = hammer.record(name, n, ep=1.0, mode="append"); assert s == 200, (s, b)
        qc.wait_idle(); time.sleep(1)
    live_rows = [(round(ts,1), tot, len(el), [x for _, x in el].count("unreadable")) for ts, tot, fin, el in h.snap if not fin]
    bad_live = [x for x in live_rows if x[2] != x[1] and x[1] > 0 or x[3]]
    d = qc.ok("GET", f"/datasets/{name}")
    print(name, "before", before, "after", d["episodes"], d["finalized"], "rows", len(d["episode_list"]), sorted({e["state"] for e in d["episode_list"]}),
          "idx ok", [e["index"] for e in d["episode_list"]] == list(range(d["episodes"])), "live snaps", len(live_rows), "bad live", bad_live[:5], h.report()["nbad"])
