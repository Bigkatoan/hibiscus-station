import json, sys, time, urllib.request
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:18641"; TOK = "<QC_TOKEN>"
def api(m, p, d=None):
    r = urllib.request.Request(BASE + "/api/v1" + p, method=m, data=json.dumps(d).encode() if d is not None else None, headers={"Authorization": "Bearer " + TOK, "X-Station": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")
browser = sys.argv[1] if len(sys.argv) > 1 else "chromium"
if api("GET", "/status")[1]["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
sent = []; res = {}
with sync_playwright() as pw:
    b = getattr(pw, browser).launch(); pg = b.new_page()
    def onws(ws):
        if ws.url.endswith("/ws"): ws.on("framesent", lambda f: sent.append(time.monotonic()) if "heartbeat" in str(f) else None)
    pg.on("websocket", onws)
    pg.goto(BASE + "/auth?t=" + TOK); pg.wait_for_timeout(800); pg.goto(BASE + "/robot"); pg.wait_for_timeout(3000)
    for rnd in range(3):
        n0 = len(sent); t0 = time.monotonic()
        # move away first: relax + re-enable is enough? use API teleop 1.5 s
        s, _ = api("POST", "/sessions/teleop", {}); time.sleep(1.5); api("POST", "/sessions/current/control", {"action": "stop"}); time.sleep(1)
        pg.get_by_test_id("go-home").first.click()
        end = None
        for _ in range(400):
            st = api("GET", "/status")[1]
            if st["state"] in ("idle", "estopped") and not st["session"]: end = st; break
            time.sleep(0.05)
        ts = sent[n0:]; gaps = [round(b2 - a2, 3) for a2, b2 in zip(ts, ts[1:])]
        res[rnd] = {"end": (end["state"], end["reason"], (end["last_session"] or {}).get("kind"), (end["last_session"] or {}).get("outcome")), "hb": len(ts), "max_gap": max(gaps) if gaps else None, "gaps_over_0.5": [g for g in gaps if g > 0.5]}
        print(rnd, res[rnd], flush=True)
        if end["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
    b.close()
