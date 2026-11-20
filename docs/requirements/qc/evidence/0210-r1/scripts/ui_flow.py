import json, sys, time
from lib import *
lang, w, dark = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "dark"
R = {}
def wait_state(pred, t=60):
    end = time.time() + t
    while time.time() < end:
        st = api("GET", "/status")[1]
        if pred(st): return st
        time.sleep(0.05)
    return None
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = P(b, lang, w, dark); pg = p.page
    # 1. replay from the UI
    p.go("/datasets/cnt3", 1500)
    btn = pg.locator("li[data-state='saved']").first.get_by_role("button", name=p.t("datasets.replay"))
    for _ in range(100):
        if btn.is_enabled(): break
        pg.wait_for_timeout(200)
    btn.click()
    st = wait_state(lambda s: s["state"] != "idle", 10); R["replay_started"] = st and st["state"]
    st = wait_state(lambda s: s["state"] in ("idle", "estopped") and not s["session"], 120); R["replay_end"] = st and (st["state"], st["reason"])
    p.shot("replay-ui")
    # 2. route error element: malformed detail
    pg.route("**/api/v1/datasets/cnt3", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"name": "cnt3"})))
    p.go("/datasets/cnt3", 2000)
    R["error_el"] = {"testid": pg.get_by_test_id("page-error").count(), "text": p.t("datasets.page_error") in p.main(), "shell": p.shell_ok()}
    p.shot("error-element")
    pg.unroute("**/api/v1/datasets/cnt3")
    pg.get_by_test_id("page-error").get_by_role("link", name=p.t("datasets.to_list")).click(); pg.wait_for_timeout(1500)
    R["error_el_to_list"] = {"url": pg.url, "shell": p.shell_ok()}
    # reload button
    pg.route("**/api/v1/datasets/cnt3", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"name": "cnt3"})))
    p.go("/datasets/cnt3", 1500); pg.unroute("**/api/v1/datasets/cnt3")
    pg.get_by_test_id("page-error").get_by_role("button", name=p.t("datasets.reload")).click(); pg.wait_for_timeout(2500)
    R["error_el_reload"] = {"rows": pg.locator("li[data-state]").count(), "shell": p.shell_ok()}
    # 3. append 409 card
    for ds, expect in (("crashb", "crashb_3"), ("crasha", "crasha_5")):
        p.go("/record", 1500)
        pg.get_by_label(p.t("record.mode"), exact=True).select_option("append"); pg.wait_for_timeout(300)
        pg.get_by_label(p.t("record.dataset")).select_option(ds); pg.wait_for_timeout(300)
        pg.get_by_label(p.t("record.task")).fill("pick the cube")
        for _ in range(60):
            pg.get_by_role("button", name=p.t("record.start")).click(); pg.wait_for_timeout(700)
            if pg.get_by_test_id("record-unfinalized").count(): break
        card = pg.get_by_test_id("record-unfinalized")
        r = {"card": card.count(), "text_ok": card.count() and card.inner_text().find(p.t("record.unfinalized", dataset=ds)) >= 0}
        p.shot(f"append409-{ds}")
        card.get_by_role("button", name=p.t("record.new_instead")).click(); pg.wait_for_timeout(500)
        r["mode"] = pg.get_by_label(p.t("record.mode"), exact=True).input_value(); r["name"] = pg.get_by_label(p.t("record.dataset")).input_value()
        r["task_kept"] = pg.get_by_label(p.t("record.task")).input_value(); r["expected"] = expect; r["card_after"] = pg.get_by_test_id("record-unfinalized").count()
        p.shot(f"append409-new-{ds}")
        R[f"append_{ds}"] = r
    # 4. record into the proposed new dataset from the UI and Stop with the UI button during episode 2
    pg.get_by_label(p.t("record.episodes")).fill("20"); pg.get_by_label(p.t("record.episode_time")).fill("5")
    for _ in range(60):
        pg.get_by_role("button", name=p.t("record.start")).click(); pg.wait_for_timeout(700)
        if api("GET", "/status")[1]["state"] == "recording": break
    st = wait_state(lambda s: s["session"] and s["session"]["episode"] and s["session"]["episode"]["index"] == 1 and s["session"]["episode"]["phase"] == "episode", 60)
    pg.wait_for_timeout(1500)
    t0 = time.time(); pg.locator("button[aria-keyshortcuts=Escape]").click()
    st = wait_state(lambda s: s["state"] == "idle", 30); R["ui_stop_to_idle_s"] = round(time.time() - t0, 2)
    pg.wait_for_timeout(2500); p.shot("ui-stop-done")
    R["after_stop_main"] = p.main()[:300]
    s, d = api("GET", "/datasets/crasha_5"); R["crasha_3"] = (s, d.get("episodes"), d.get("finalized"), [e["state"] for e in d.get("episode_list", [])])
    R["errors"] = p.errors[:8]; R["5xx"] = p.bad
    b.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
