import qc, hammer, json, time, sys
qc.setup()
out = {}
for n in [int(x) for x in sys.argv[1:]] or [1, 3, 10, 11, 15]:
    name = f"cnt{n}"
    with hammer.Hammer(name) as h:
        s, b = hammer.record(name, n)
        assert s == 200, (s, b)
        t0 = time.time(); st = qc.wait_idle(); dur = time.time() - t0
        time.sleep(1.5)
    s, d = qc.call("GET", f"/datasets/{name}")
    states = [e["state"] for e in d["episode_list"]]
    # max number of saved rows seen during session vs. counter
    lag = [(round(ts - t0, 1), tot, fin, len(el), sum(1 for _, x in el if x == "saved")) for ts, tot, fin, el in h.snap]
    mism = [x for x in lag if not x[2] and x[3] < x[1]]  # rows fewer than total while not finalized
    out[n] = {"dur": round(dur, 1), "final_status": s, "episodes": d["episodes"], "finalized": d["finalized"], "rows": len(states),
              "states": sorted(set(states)), "frames": sorted({e["frames"] for e in d["episode_list"]}), "hammer": h.report(),
              "rows_lt_total_while_live": mism[:5], "snaps": len(h.snap)}
    print(n, json.dumps(out[n])[:1500], flush=True)
json.dump(out, open("s_counts.json", "w"), indent=1)
