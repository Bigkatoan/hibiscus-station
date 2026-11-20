"""QC timing driver (client side). Talks to a Station over REST + WS with the QC bearer token."""
from __future__ import annotations
import json, os, signal, statistics, threading, time, asyncio
from pathlib import Path
import httpx

TOK = "<QC_TOKEN>"
Q = Path("/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-timing")

def client(port):
    return httpx.Client(base_url=f"http://127.0.0.1:{port}/api/v1",
                        headers={"Authorization": f"Bearer {TOK}", "X-Station": "1"}, timeout=120)

def api(c, m, p, data=None, ok=True):
    r = c.request(m, p, json=data)
    if ok:
        assert r.is_success, f"{m} {p}: {r.status_code} {r.text[:400]}"
    try:
        return r.json()
    except Exception:
        return r

def status(c): return api(c, "GET", "/status")

def wait(pred, timeout=60, what="cond", every=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v: return v
        time.sleep(every)
    raise AssertionError("timeout: " + what)

def connect_cal(c):
    st = status(c)
    rid = None
    if not (st.get("robot") or {}).get("connected"):
        robots = api(c, "GET", "/robots")
        rid = robots.get("active") or robots["robots"][0]["id"]
        api(c, "POST", f"/robots/{rid}/connect")
        st = wait(lambda: (s := status(c))["state"] == "idle" and s, 60, "idle")
    for arm in ("follower", "leader"):
        if st["robot"]["arms"][arm]["calibrated"]:
            continue
        cid = st["robot"]["arms"][arm].get("calibration_id") or f"demo_{arm}"
        api(c, "POST", "/calibration/start", {"arm": arm, "id": cid, "keep_existing": False})
        api(c, "POST", "/calibration/step", {"action": "set_home"})
        time.sleep(2.5)
        wait(lambda: api(c, "POST", "/calibration/step", {"action": "finish_ranges"}, ok=False)
             and status(c)["state"] == "idle", 30, "cal", every=0.5)
        st = wait(lambda: (s := status(c))["state"] == "idle" and s, 30, "idle")
    return st

def leader_follow(c, on=True):
    api(c, "POST", "/mock/inject", {"port": "mock://leader", "hand": "follow" if on else "default"})

def start(c, path, body):
    for _ in range(60):
        r = c.post(path, json=body)
        if r.is_success: return r.json()
        assert r.json().get("code") == "leader_far", r.text
        time.sleep(0.5)
    raise AssertionError("leader far")

def stall(pid, dur):
    t0 = time.perf_counter(); os.kill(pid, signal.SIGSTOP); time.sleep(dur)
    os.kill(pid, signal.SIGCONT); t1 = time.perf_counter()
    return (t0, t1)

class WS:
    """Collect ws events; optional heartbeat every hb_s (None = never)."""
    def __init__(self, port, hb_s=None):
        self.port, self.hb_s, self.events, self.stop_ev = port, hb_s, [], threading.Event()
        self.hb_on = threading.Event()
        if hb_s: self.hb_on.set()
        self.th = threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True); self.th.start()
        time.sleep(1.0)
    async def _run(self):
        import websockets
        async with websockets.connect(f"ws://127.0.0.1:{self.port}/api/v1/ws",
                                      additional_headers={"Authorization": f"Bearer {TOK}"}, max_size=None) as ws:
            await ws.recv()
            await ws.send(json.dumps({"type": "hello", "heartbeat": bool(self.hb_s)}))
            async def hb():
                while not self.stop_ev.is_set():
                    if self.hb_on.is_set():
                        await ws.send(json.dumps({"type": "heartbeat"}))
                    await asyncio.sleep(self.hb_s or 0.25)
            t = asyncio.create_task(hb())
            while not self.stop_ev.is_set():
                try:
                    m = await asyncio.wait_for(ws.recv(), 0.5)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(m)
                self.events.append((time.perf_counter(), d.get("type"), d))
            t.cancel()
    def close(self): self.stop_ev.set(); self.th.join(5)

def probe(home):
    out = {"T": [], "W": [], "P": [], "E": [], "H": []}
    for ln in (Path(home) / "probe.log").read_text().splitlines():
        p = ln.split()
        if p[0] in out:
            out[p[0]].append((float(p[1]),) + tuple(p[2:]))
    return out

def pct(xs, q):
    xs = sorted(xs); 
    if not xs: return None
    k = (len(xs) - 1) * q / 100; f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def gapstats(ts, period, stalls=()):
    """ts: sorted times. Gap stats in ms; 'burst' = gaps < 0.5 period; catch-up after each stall."""
    g = [(b - a) for a, b in zip(ts, ts[1:])]
    if not g: return {}
    span = ts[-1] - ts[0]
    out = {
        "n": len(ts), "span_s": round(span, 3), "mean_hz": round((len(ts) - 1) / span, 3),
        "median_gap_ms": round(statistics.median(g) * 1e3, 3),
        "sd_gap_ms": round(statistics.pstdev(g) * 1e3, 3),
        "p1_gap_ms": round(pct(g, 1) * 1e3, 3), "p5_gap_ms": round(pct(g, 5) * 1e3, 3),
        "p95_gap_ms": round(pct(g, 95) * 1e3, 3), "p99_gap_ms": round(pct(g, 99) * 1e3, 3),
        "max_gap_ms": round(max(g) * 1e3, 1), "min_gap_ms": round(min(g) * 1e3, 3),
        "gaps_lt_half_period": sum(1 for x in g if x < 0.5 * period),
        "gaps_lt_0.2_period": sum(1 for x in g if x < 0.2 * period),
        "gaps_gt_1.5_period": sum(1 for x in g if x > 1.5 * period),
    }
    # drift vs ideal grid: mean rate excluding gaps > 1.5 period (stalls)
    gg = [x for x in g if x <= 1.5 * period]
    out["mean_gap_ms_excl_stalls"] = round(statistics.fmean(gg) * 1e3, 3) if gg else None
    out["rate_hz_excl_stalls"] = round(1 / statistics.fmean(gg), 3) if gg else None
    st = []
    for (a, b) in stalls:
        after = [t for t in ts if t >= b - 0.001][:8]
        before = [t for t in ts if t < a][-1:] 
        seq = before + after
        gaps = [round((y - x) * 1e3, 2) for x, y in zip(seq, seq[1:])]
        st.append({"stall_s": round(b - a, 3), "gaps_ms_around": gaps,
                   "ticks_within_1_period_after_resume": sum(1 for t in ts if b <= t < b + period),
                   "ticks_within_3_periods_after_resume": sum(1 for t in ts if b <= t < b + 3 * period)})
    out["stalls"] = st
    return out

def phase(c):
    s = status(c).get("session") or {}
    return (s.get("episode") or {}).get("phase")
