"""WebGL fallback (QD-18) on the installed build: Teleop, Record, Run model, Programs run panel, trajectory ghost."""
import json, sys, time, re
from pathlib import Path
from playwright.sync_api import sync_playwright
D = Path(__file__).parent; BASE = "http://127.0.0.1:18641"; TOK = "<QC_TOKEN>"
SRC = Path("/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int/src/web/src/station/i18n")
def flat(d, p=""):
    o = {}
    for k, v in d.items():
        if isinstance(v, dict): o.update(flat(v, f"{p}{k}."))
        else: o[f"{p}{k}"] = v
    return o
I18N = {l: flat(json.loads((SRC / f"{l}.json").read_text())) for l in ("en", "vi")}
mode, lang, width = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1280
T = lambda k: I18N[lang][k]
import urllib.request, urllib.error
def api(m, path, data=None):
    req = urllib.request.Request(f"{BASE}/api/v1{path}", method=m, data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {TOK}", "X-Station": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read(); return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b)
        except Exception: return e.code, b.decode(errors="replace")
st = lambda: api("GET", "/status")[1]
if st()["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
# a saved trajectory for the ghost preview
if not api("GET", "/trajectories")[1]:
    pass
trs = api("GET", "/trajectories")[1]; trs = trs.get("trajectories", trs) if isinstance(trs, dict) else trs
if not trs:
    for _ in range(50):
        s, b = api("POST", "/trajectories/record", {"name": "wave", "countdown_s": 0, "limit_s": 10})
        if s == 200: break
        time.sleep(0.3)
    time.sleep(2.5); s, b = api("POST", "/trajectories/record/stop"); tid = (b or {}).get("id")
    for _ in range(50):
        if st()["state"] == "idle": break
        time.sleep(0.2)
    print("traj", s, tid, api("PUT", f"/trajectories/{tid}", {"save": True})[0])
R = {"mode": mode, "lang": lang, "width": width}
with sync_playwright() as pw:
    if mode == "chromium-nowebgl": b = pw.chromium.launch(args=["--disable-webgl", "--disable-3d-apis"])
    elif mode == "chromium": b = pw.chromium.launch()
    else: b = pw.firefox.launch()
    ctx = b.new_context(locale="vi-VN" if lang == "vi" else "en-US", viewport={"width": width, "height": 900})
    pg = ctx.new_page(); errs = []; bad = []
    pg.on("pageerror", lambda e: errs.append("pageerror:" + str(e)[:200]))
    pg.on("console", lambda m: m.type in ("error", "warning") and errs.append(f"console.{m.type}:" + m.text[:200]))
    pg.on("response", lambda r: r.status >= 500 and bad.append((r.status, r.url)))
    pg.goto(f"{BASE}/auth?t={TOK}"); pg.wait_for_timeout(800); pg.evaluate(f"localStorage.setItem('i18nextLng','{lang}')")
    R["webgl2_probe"] = pg.evaluate("(() => { try { return !!document.createElement('canvas').getContext('webgl2') } catch (e) { return 'throws' } })()")
    def twins():
        loc = pg.locator("[data-testid=robot-twin]:visible")
        return [{"state": loc.nth(i).get_attribute("data-state"), "note": (loc.nth(i).locator("[data-testid=twin-no-webgl]").inner_text() if loc.nth(i).locator("[data-testid=twin-no-webgl]").count() else None)} for i in range(loc.count())]
    def open_twin():
        if pg.locator("[data-testid=robot-twin]:visible").count(): return "inline"
        btn = pg.locator(f"button[aria-label='{T('twin.show')}']:visible")
        if btn.count(): btn.first.click(); pg.wait_for_timeout(1500); return "dock"
        sec = pg.locator("[data-testid=twin-section] button[aria-expanded=false]")
        if sec.count(): sec.first.click(); pg.wait_for_timeout(1500); return "section"
        return "none"
    pages = [("/teleop", None), ("/record", None), ("/run", None), ("/programs?tab=programs", None), ("/programs?tab=trajectories", "ghost")]
    for path, extra in pages:
        n0 = len(errs); pg.goto(f"{BASE}{path}"); pg.wait_for_timeout(3000)
        how = open_twin()
        tw = twins()
        R[path] = {"how": how, "twins": tw, "fallback_ok": bool(tw) and all((x["state"] == "no-webgl" and x["note"] == T("twin.no_webgl")) if mode != "chromium" else x["state"] != "no-webgl" for x in tw),
                   "nav": pg.locator("nav").count() > 0, "errors": errs[n0:][:5],
                   "ghost_card": pg.get_by_test_id("traj-preview").count() if extra else None,
                   "ghost_player": pg.get_by_test_id("ghost-player").count() if extra else None}
        pg.screenshot(path=str(D / "shots" / f"webgl-{mode}-{lang}-{width}{path.replace('/', '_').replace('?', '_')}.png"), full_page=True)
    # everything else works: teleop from the page with the fallback showing
    pg.goto(f"{BASE}/teleop"); pg.wait_for_timeout(2500)
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "follow"})
    start = pg.locator("main button").filter(has_text=re.compile(re.escape(T("teleop.start")) if "teleop.start" in I18N[lang] else "Start")).first
    clicked = False
    for _ in range(20):
        if start.count() and start.is_enabled(): start.click(); clicked = True; break
        pg.wait_for_timeout(500)
    ok = None
    for _ in range(60):
        s = st()
        if s["state"] == "teleop" or (s.get("session") or {}).get("kind") == "teleop": ok = True; break
        time.sleep(0.2)
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "default"})
    time.sleep(1.5)
    R["teleop_ui"] = {"clicked": clicked, "running": ok, "twins_live": twins()}
    stop = pg.locator("main button").filter(has_text=T("controls.stop")).first
    if stop.count(): stop.click()
    for _ in range(60):
        if st()["state"] == "idle": break
        time.sleep(0.2)
    R["teleop_ui"]["idle_after_stop"] = st()["state"]
    R["errors_total"] = errs[:20]; R["5xx"] = bad
    b.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
json.dump(R, open(D / f"webgl-{mode}-{lang}-{width}.json", "w"), indent=1, ensure_ascii=False)
