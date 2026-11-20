import json, sys, time, threading
from lib import *
lang, w, dark, name, n = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "dark", sys.argv[4], int(sys.argv[5])
res = {"samples": []}
def start():
    for _ in range(300):
        s, b = api("POST", "/sessions/record", {"dataset": name, "task": "pick the cube", "num_episodes": n, "episode_time_s": 1.5, "reset_time_s": 0, "countdown_s": 0})
        if not (s == 409 and b.get("code") == "leader_far"): return s, b
        time.sleep(0.2)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    p = P(b, lang, w, dark)       # dataset detail page
    p2 = P(b, lang, w, dark)      # record page (strip)
    p2.go("/record", 1000)
    p.go(f"/datasets/{name}", 500)
    s, r = start(); res["start"] = s
    t0 = time.time(); shots = 0; saw_saving_shot = False
    p.go(f"/datasets/{name}", 300)
    while True:
        st = api("GET", "/status")[1]
        m = p.main(); sh = p.shell_ok()
        rows = p.page.locator("li[data-state]")
        states = [rows.nth(i).get_attribute("data-state") for i in range(rows.count())]
        strip = p2.main().count(p2.t("datasets.saving"))
        res["samples"].append({"t": round(time.time() - t0, 1), "st": st["state"], "saved": (st["session"] or {}).get("episode", {}).get("saved") if st["session"] else None,
                               "rows": len(states), "saving_rows": states.count("saving"), "saving_badge": m.count(p.t("datasets.saving")), "shell": sh, "strip_saving": strip})
        if states.count("saving") and not saw_saving_shot:
            p.shot(f"live-saving-{name}"); p2.shot(f"live-recordstrip-{name}"); saw_saving_shot = True
        if st["state"] == "idle" and time.time() - t0 > 2: break
        p.page.wait_for_timeout(250)
    p.page.wait_for_timeout(3000)  # no reload: auto refresh
    rows = p.page.locator("li[data-state]")
    res["after_stop_no_reload"] = [rows.nth(i).get_attribute("data-state") for i in range(rows.count())]
    p.shot(f"live-after-{name}"); p2.shot(f"live-record-after-{name}")
    res["errors"] = p.errors + p2.errors; res["5xx"] = p.bad + p2.bad
    b.close()
S = res["samples"]
print(json.dumps({"start": res["start"], "nsamples": len(S), "max_rows": max(x["rows"] for x in S), "saw_saving_badge": sum(1 for x in S if x["saving_badge"]),
  "saw_strip_saving": sum(1 for x in S if x["strip_saving"]), "rows_lag": [ (x["t"], x["saved"], x["rows"]) for x in S if x["saved"] is not None and x["rows"] < x["saved"]][:8],
  "shell_bad": [x for x in S if not x["shell"]["nav"] or x["shell"]["unexpected"] or x["shell"]["blank"]][:3],
  "after": res["after_stop_no_reload"], "errors": res["errors"][:5], "5xx": res["5xx"][:5]}, ensure_ascii=False))
json.dump(res, open(f"{Q}/ui_live_{name}.json", "w"), indent=1, ensure_ascii=False)
