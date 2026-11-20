import qc, threading, time, json, collections, sys
class Hammer:
    """Polls list/detail/telemetry continuously; records every status and every >=500 / anomaly."""
    def __init__(self, name, period=0.1):
        self.name, self.period = name, period
        self.codes = collections.Counter(); self.bad = []; self.snap = []; self.stop_ev = threading.Event()
        self.t = threading.Thread(target=self.run, daemon=True)
    def run(self):
        while not self.stop_ev.is_set():
            ts = time.time()
            s, b = qc.call("GET", "/datasets"); self.codes[("list", s)] += 1
            if s >= 500: self.bad.append((ts, "list", s, b))
            s, d = qc.call("GET", f"/datasets/{self.name}"); self.codes[("detail", s)] += 1
            if s >= 500: self.bad.append((ts, "detail", s, d))
            if s == 200:
                el = d["episode_list"]
                self.snap.append((ts, d["episodes"], d["finalized"], [(e["index"], e["state"]) for e in el]))
                idxs = [e["index"] for e in el]
                if len(idxs) != len(set(idxs)) or idxs != sorted(idxs): self.bad.append((ts, "dup/order", idxs))
                for e in el[-3:]:
                    s2, t = qc.call("GET", f"/datasets/{self.name}/episodes/{e['index']}/telemetry"); self.codes[("tel", e["state"], s2)] += 1
                    if s2 >= 500: self.bad.append((ts, "tel", e["index"], s2, t))
            elif s != 404:
                self.bad.append((ts, "detail-non200", s, d))
            time.sleep(self.period)
    def __enter__(self): self.t.start(); return self
    def __exit__(self, *a): self.stop_ev.set(); self.t.join()
    def report(self):
        return {"codes": {"|".join(map(str, k)): v for k, v in self.codes.items()}, "bad": self.bad[:20], "nbad": len(self.bad)}
def record(name, n, ep=1.0, mode="new", reset=0.0, extra=None):
    body = {"dataset": name, "task": "pick the cube", "num_episodes": n, "episode_time_s": ep, "reset_time_s": reset, "countdown_s": 0, "mode": mode}
    body.update(extra or {})
    for _ in range(300):
        s, b = qc.call("POST", "/sessions/record", body)
        if not (s == 409 and isinstance(b, dict) and b.get("code") == "leader_far"): return s, b
        time.sleep(0.2)
    return s, b
