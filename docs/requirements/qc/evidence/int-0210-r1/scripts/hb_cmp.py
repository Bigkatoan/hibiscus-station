"""Dead-man trip rate of UI-started Replay and Return Home under the same machine load, for two builds."""
import json, sys, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright
port = int(sys.argv[1]); rounds = int(sys.argv[2]); BASE = f"http://127.0.0.1:{port}"; TOK = "<QC_TOKEN>"
def api(m, p, d=None):
    r = urllib.request.Request(BASE + "/api/v1" + p, method=m, data=json.dumps(d).encode() if d is not None else None, headers={"Authorization": "Bearer " + TOK, "X-Station": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120) as x: b = x.read(); return x.status, json.loads(b) if b else None
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b)
        except Exception: return e.code, b
st = lambda: api("GET", "/status")[1]
def wait(p, t=60):
    end = time.time() + t
    while time.time() < end:
        v = p()
        if v: return v
        time.sleep(0.2)
if st()["state"] == "disconnected": api("POST", "/robots/demo_so101/connect", {}); wait(lambda: st()["state"] == "idle")
for arm in ("follower", "leader"):
    if st()["robot"]["arms"][arm]["calibrated"]: continue
    api("POST", "/calibration/start", {"arm": arm}); time.sleep(0.5); api("POST", "/calibration/step", {"action": "set_home"}); time.sleep(1.0); api("POST", "/calibration/step", {"action": "finish_ranges"}); time.sleep(0.5)
wait(lambda: st()["state"] == "idle")
if api("GET", "/datasets/hbds")[0] != 200:
    for _ in range(100):
        s, b = api("POST", "/sessions/record", {"dataset": "hbds", "task": "t", "num_episodes": 1, "episode_time_s": 8, "reset_time_s": 0, "countdown_s": 0, "mode": "new"})
        if s == 200: break
        time.sleep(0.2)
    wait(lambda: st()["state"] == "idle", 120)
api("POST", "/robots/rest-pose", {})
out = {"port": port, "version": st()["station"]["version"], "replay": [], "home": []}
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(f"{BASE}/auth?t={TOK}"); pg.wait_for_timeout(800)
    for r in range(rounds):
        if st()["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
        wait(lambda: st()["state"] == "idle")
        pg.goto(f"{BASE}/datasets/hbds"); pg.wait_for_timeout(2500)
        pg.get_by_role("button", name="Replay", exact=True).first.click(); time.sleep(0.4)
        for name in ("Replay", "Start", "Confirm"):
            btn = pg.get_by_role("dialog").get_by_role("button", name=name)
            if btn.count(): btn.first.click(); break
        end = wait(lambda: (x := st())["state"] in ("idle", "estopped") and not x["session"] and x, 60)
        ls = end["last_session"] or {}
        out["replay"].append((ls.get("kind"), ls.get("outcome")))
        if end["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
        # Return Home from the Robot page after a short teleop away from Home
        api("POST", "/sessions/teleop", {}); time.sleep(1.5); api("POST", "/sessions/current/control", {"action": "stop"}); wait(lambda: st()["state"] == "idle")
        pg.goto(f"{BASE}/robot"); pg.wait_for_timeout(2500)
        pg.locator("[data-testid=go-home]:visible").first.click()
        end = wait(lambda: (x := st())["state"] in ("idle", "estopped") and not x["session"] and (x["last_session"] or {}).get("kind") == "rest" and x, 60)
        ls = (end or st())["last_session"] or {}
        out["home"].append((ls.get("kind"), ls.get("outcome")))
        print(r, out["replay"][-1], out["home"][-1], flush=True)
    b.close()
out["replay_trips"] = sum(1 for k, o in out["replay"] if o == "ui_lost"); out["home_trips"] = sum(1 for k, o in out["home"] if o == "ui_lost")
print(json.dumps(out))
