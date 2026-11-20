"""0.2.9 regression on the merged build: Stop prompt + hold (CR-1), Home (CR-2), relax / go-home blocks,
leader table, camera frames. Station D (desk profile, 640x480 + 320x240 mock cameras)."""
import json, sys, time, re, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright
from blocks_dsl import program, relax, go_home
D = Path(__file__).parent; PORT = 18641; BASE = f"http://127.0.0.1:{PORT}"
TOK = "<QC_TOKEN>"
SRC = Path("/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int/src/web/src/station/i18n")
def flat(d, p=""):
    o = {}
    for k, v in d.items():
        if isinstance(v, dict): o.update(flat(v, f"{p}{k}."))
        else: o[f"{p}{k}"] = v
    return o
I18N = {l: flat(json.loads((SRC / f"{l}.json").read_text())) for l in ("en", "vi")}
lang = sys.argv[1] if len(sys.argv) > 1 else "en"; width = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
dark = len(sys.argv) > 3 and sys.argv[3] == "dark"; tag = f"{lang}-{width}-{'dark' if dark else 'light'}"
def T(k, **kw):
    s = I18N[lang][k]
    for a, b in kw.items(): s = s.replace("{{" + a + "}}", str(b))
    return s
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
def st(): return api("GET", "/status")[1]
def wait(pred, t=60, every=0.05):
    end = time.time() + t
    while time.time() < end:
        v = pred()
        if v: return v
        time.sleep(every)
    return None
def pose(n):
    s, b = api("POST", "/poses/capture", {"name": n}); assert s < 300, (s, b)
    return b
def joints(p):  # find the follower joint dict in the pose answer
    if isinstance(p, dict):
        for k in ("joints", "positions", "pose", "follower"):
            if k in p and isinstance(p[k], dict): return joints(p[k]) if not all(isinstance(v, (int, float)) for v in p[k].values()) else p[k]
        if p and all(isinstance(v, (int, float)) for v in p.values()): return p
    return p
def maxdiff(a, b):
    a, b = joints(a), joints(b)
    try: return round(max(abs(a[k] - b[k]) for k in a), 3)
    except Exception: return f"? {str(a)[:80]} {str(b)[:80]}"
R = {"tag": tag}; DSN = f"stop_{lang}_{width}_{int(time.time()) % 100000}"
# --- setup
if st()["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
s0 = st()
if not s0["robot"] or not s0["robot"]["connected"]:
    api("POST", "/robots/desk/connect"); wait(lambda: st()["state"] == "idle", 60, 0.3)
for arm in ("follower", "leader"):
    if st()["robot"]["arms"][arm]["calibrated"]: continue
    api("POST", "/calibration/start", {"arm": arm, "id": f"desk_{arm}", "keep_existing": False})
    api("POST", "/calibration/step", {"action": "set_home"}); time.sleep(2.5)
    wait(lambda: api("POST", "/calibration/step", {"action": "finish_ranges"})[0] < 300 and st()["state"] == "idle", 30, 0.5)
    wait(lambda: st()["state"] == "idle", 30, 0.3)
R["calibrated"] = {a: st()["robot"]["arms"][a]["calibrated"] for a in ("follower", "leader")}
rb = api("GET", "/robots")[1]; desk = next(r for r in rb["robots"] if r["id"] == "desk")
first = desk["follower"].get("rest_pose") is None
R["rest_pose_initially"] = desk["follower"].get("rest_pose")
api("DELETE", "/programs/rh")
s, b = api("PUT", "/programs/rh", {"name": "relax and home", "editor": program(relax(id_="rx"), go_home(id_="gh")), "buttons": []})
R["put_issues"] = [(i["code"], i["severity"]) for i in b.get("issues", [])]
import atexit
atexit.register(lambda: print("PARTIAL", json.dumps(R, ensure_ascii=False)[:3000]))
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(locale="vi-VN" if lang == "vi" else "en-US", viewport={"width": width, "height": 900},
                         color_scheme="dark" if dark else "light", reduced_motion="reduce")
    pg = ctx.new_page(); errors = []; bad = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append("console:" + m.text))
    pg.on("response", lambda r: r.status >= 500 and bad.append((r.status, r.url)))
    HB = []
    pg.on("websocket", lambda ws: ws.url.endswith("/ws") and ws.on("framesent", lambda f: HB.append(time.monotonic()) if "heartbeat" in str(f) else None))
    def gaps(t0):
        ts = [x for x in HB if x >= t0]; g = [round(b - a, 2) for a, b in zip(ts, ts[1:])]
        return {"n": len(ts), "max_gap": max(g) if g else None, "last_hb_age": round(time.monotonic() - ts[-1], 2) if ts else None}
    pg.goto(f"{BASE}/auth?t={TOK}"); pg.wait_for_timeout(800)
    pg.evaluate(f"localStorage.setItem('i18nextLng','{lang}')")
    shot = lambda n: pg.screenshot(path=str(D / "shots" / f"{n}-{tag}.png"), full_page=True)
    main = lambda: pg.locator("main").inner_text()
    # --- relax / go-home blocks without Home (QD-2: problems shown on open, Set Home now in place)
    if first:
        pg.goto(f"{BASE}/programs?tab=programs"); pg.wait_for_timeout(3000)
        m = main(); R["blocks_no_home_on_open"] = {"issue_text": m.count(T("programs.issues.no_rest_pose")), "no_problems_text": T("programs.editor.no_issues") in m if "programs.editor.no_issues" in I18N[lang] else None,
                                                  "set_now_buttons": pg.get_by_role("button", name=T("home.set_now")).count()}
        shot("blocks-no-home")
        pg.get_by_role("button", name=T("home.set_now")).first.click(); pg.wait_for_timeout(500)
        dlg = pg.get_by_role("alertdialog").or_(pg.get_by_role("dialog"))
        if dlg.count(): dlg.get_by_role("button", name=re.compile(T("home.replace_ok") + "|" + T("home.set_short"))).first.click()
        pg.wait_for_timeout(2500); m = main()
        R["blocks_after_set_now"] = {"issue_text": m.count(T("programs.issues.no_rest_pose")),
                                     "rest_pose_set": api("GET", "/robots")[1]["robots"][0]["follower"].get("rest_pose") is not None}
        shot("blocks-after-set-now")
    s, b = api("POST", "/programs/rh/check"); R["check_after_home"] = (s, [(i["code"], i["severity"]) for i in (b.get("issues") or [])] if isinstance(b, dict) else b)
    home = next(r for r in api("GET", "/robots")[1]["robots"] if r["id"] == "desk")["follower"]["rest_pose"]
    # --- move the arm away from Home: teleop 2 s with the default (sweeping) leader hand
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "follow"})
    for _ in range(50):
        s, b = api("POST", "/sessions/teleop", {})
        if s == 200: break
        time.sleep(0.2)
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "default"})
    time.sleep(3); api("POST", "/sessions/current/control", {"action": "stop"}); wait(lambda: st()["state"] == "idle", 30)
    away = pose("qc_away")
    # --- CR-2 Return Home from the Robot page
    pg.goto(f"{BASE}/robot"); pg.wait_for_timeout(2500)
    gh = pg.locator("[data-testid=go-home]:visible").first
    R["go_home_enabled"] = gh.is_enabled(); t0 = time.time(); m0 = time.monotonic(); gh.click()
    seen = wait(lambda: (x := st())["state"] != "idle" and x, 10, 0.02); R["go_home_session"] = seen and (seen["state"], (seen.get("session") or {}).get("kind"))
    end = wait(lambda: (x := st())["state"] in ("idle", "estopped") and not x["session"] and x, 60, 0.2)
    R["go_home_end"] = end and (end["state"], end["reason"], round(time.time() - t0, 1), (end.get("last_session") or {}).get("outcome"))
    R["go_home_hb"] = gaps(m0 - 3)
    if end and end["state"] == "estopped": api("POST", "/estop/reset"); time.sleep(1)
    at_home = pose("qc_home_check")
    R["away_vs_home_maxdiff"] = maxdiff(away, {"joints": home} if isinstance(home, dict) and "joints" not in home else home)
    R["after_go_home_vs_home_maxdiff"] = maxdiff(at_home, {"joints": home} if isinstance(home, dict) and "joints" not in home else home)
    # --- leader table on the Robot page (0.2.9 field 3, QD-6)
    m = main()
    R["leader_table"] = {"connected_text": T("health.leader_connected", n=6, total=6) in m, "not_measured": m.count(T("health.not_measured")),
                         "tables_overflowing": pg.evaluate("[...document.querySelectorAll('main table')].filter(t => { const p = t.parentElement; return t.scrollWidth > p.clientWidth + 1 }).length"),
                         "tables": pg.locator("main table").count()}
    shot("robot-page")
    # --- relax asks first; Cancel keeps torque
    rel = pg.locator("[data-testid=relax]:visible").first; rel.click(); pg.wait_for_timeout(500)
    dlg = pg.get_by_role("alertdialog").or_(pg.get_by_role("dialog")).first
    R["relax_dialog"] = {"title": T("relax.confirm_title") in dlg.inner_text(), "ok": T("relax.confirm_ok") in dlg.inner_text()}
    shot("relax-dialog")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(800); R["torque_after_cancel"] = st()["robot"]["follower_torque"]
    rel.click(); pg.wait_for_timeout(500); pg.get_by_role("button", name=T("relax.confirm_ok")).click(); pg.wait_for_timeout(1200)
    R["torque_after_confirm"] = st()["robot"]["follower_torque"]
    # --- CR-1 / Stop during recording is prompt and the arm holds
    api("POST", "/robots/torque", {"arm": "follower", "enabled": True, "confirm": True}); time.sleep(0.5)
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "follow"})
    for _ in range(50):
        s, b = api("POST", "/sessions/record", {"dataset": DSN, "task": "t", "num_episodes": 1, "episode_time_s": 20, "reset_time_s": 0, "countdown_s": 0, "mode": "new"})
        if s == 200: break
        time.sleep(0.3)
    R["record_start"] = (s, b.get("code") if isinstance(b, dict) else None, str(b)[:200] if s != 200 else "")
    api("POST", "/mock/inject", {"port": "mock://leader", "hand": "default"})
    pg.goto(f"{BASE}/record"); pg.wait_for_timeout(1500)
    wait(lambda: ((x := st()).get("session") or {}).get("episode") and x["session"]["episode"]["phase"] == "episode" and x["session"]["episode"]["elapsed_s"] > 5, 40)
    btn = pg.locator("main button[aria-keyshortcuts='Escape']").first
    btn.wait_for(state="visible"); pg.wait_for_timeout(1000)
    R["elapsed_before_click"] = st()["session"]["episode"]["elapsed_s"]
    t0 = time.time(); btn.click(); t_click = time.time() - t0
    sv = wait(lambda: ((x := st()).get("session") or {}).get("episode", {}) and x["session"]["episode"]["phase"] != "episode" and x, 30, 0.01)
    R["click_call_s"] = round(t_click, 2)
    R["stop_to_saving_s"] = round(time.time() - t0, 2); R["phase_after_stop"] = sv and sv["session"]["episode"]["phase"]
    R["elapsed_at_saving"] = sv and sv["session"]["episode"]["elapsed_s"]
    shot("record-stop-saving")
    idle = wait(lambda: st()["state"] == "idle", 120, 0.05); R["stop_to_idle_s"] = round(time.time() - t0, 2)
    p1 = pose("qc_hold1"); time.sleep(3); p2 = pose("qc_hold2")
    R["hold_maxdiff_3s"] = maxdiff(p1, p2); R["torque_after_stop"] = st()["robot"]["follower_torque"]
    ls = st()["last_session"]; R["record_summary"] = {k: ls.get("summary", {}).get(k) for k in ("saved", "discarded", "cameras", "frames")}
    d = api("GET", f"/datasets/{DSN}")[1]; R["stop_dataset"] = {"episodes": d["episodes"], "frames": d["frames"], "finalized": d["finalized"]}
    # --- run the relax + go Home program on the robot (dry run first)
    pg.goto(f"{BASE}/programs?tab=programs"); pg.wait_for_timeout(2500)
    s, b = api("POST", "/programs/rh/run", {"dry_run": True}); R["dry_run"] = s
    wait(lambda: (api("GET", "/programs/rh/state")[1] or {}).get("status") in ("completed", "failed", "stopped"), 60, 0.3)
    R["dry_state"] = (api("GET", "/programs/rh/state")[1] or {}).get("status")
    s, b = api("POST", "/programs/rh/run", {"dry_run": False, "confirm": ["rx"]}); R["robot_run"] = (s, b.get("code") if isinstance(b, dict) else None)
    if s >= 400 and isinstance(b, dict):
        R["robot_run_detail"] = str(b)[:300]
    end = wait(lambda: (api("GET", "/programs/rh/state")[1] or {}).get("status") in ("completed", "failed", "stopped", "error"), 90, 0.3)
    stt = api("GET", "/programs/rh/state")[1] or {}
    R["robot_run_state"] = {k: stt.get(k) for k in ("status", "reason", "error")}
    R["robot_run_log_tail"] = [str(x)[:120] for x in (stt.get("log") or [])[-4:]]
    shot("program-run")
    R["page_errors"] = errors[:10]; R["5xx"] = bad[:10]
    br.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
json.dump(R, open(D / f"cr-{tag}.json", "w"), indent=1, ensure_ascii=False)
