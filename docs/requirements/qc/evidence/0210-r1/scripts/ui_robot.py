import json, sys, time
from lib import *
phase = sys.argv[1]
R = {}
CF = [("en", 1280, False), ("vi", 390, True)]
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in CF:
        p = P(b, lang, w, dark); pg = p.page; r = R.setdefault(p.tag, {})
        p.go("/robot", 2000)
        cards = pg.locator("main li")
        r["cards"] = []
        for i in range(cards.count()):
            c = cards.nth(i); btn = c.get_by_role("button", name=p.t("robot.delete"), exact=False)
            btn = c.locator("button", has_text=p.t("robot.delete")).last
            r["cards"].append({"text": c.inner_text()[:60].replace("\n", " | "), "delete_btns": c.locator("button", has_text=p.t("robot.delete")).count(),
                               "enabled": btn.is_enabled() if btn.count() else None, "hint": p.t("robot.delete_disconnect_first") in c.inner_text()})
        r["empty_msg"] = p.t("robot.empty") in p.main(); r["shell"] = p.shell_ok()
        p.shot(f"robot-{phase}")
        if phase == "dialog":
            # open the dialog on the first enabled card and cancel; check texts
            for i in range(cards.count()):
                btn = cards.nth(i).locator("button", has_text=p.t("robot.delete")).last
                if btn.count() and btn.is_enabled():
                    name = cards.nth(i).locator("h3, [class*=CardTitle], .font-extrabold").first.inner_text()
                    btn.click(); pg.wait_for_timeout(600)
                    dlg = pg.get_by_test_id("delete-robot-dialog")
                    r["dialog"] = {"visible": dlg.is_visible(), "text": dlg.inner_text(), "desc_ok": p.t("robot.delete_desc") in dlg.inner_text()}
                    p.shot("robot-dialog", full=False)
                    dlg.get_by_role("button", name=p.t("common.cancel")).click(); pg.wait_for_timeout(500)
                    r["after_cancel_dialog"] = dlg.count()
                    break
        if phase.startswith("delete:") and lang == "en":
            target = phase.split(":", 1)[1]
            for i in range(cards.count()):
                if target in cards.nth(i).inner_text():
                    cards.nth(i).locator("button", has_text=p.t("robot.delete")).last.click(); pg.wait_for_timeout(500)
                    dlg = pg.get_by_test_id("delete-robot-dialog"); r["dialog_title"] = dlg.inner_text().split("\n")[0]
                    dlg.get_by_role("button", name=p.t("robot.delete_confirm")).click(); pg.wait_for_timeout(1500)
                    r["after"] = [cards.nth(j).inner_text()[:40].replace("\n", " | ") for j in range(cards.count())]
                    r["empty_after"] = p.t("robot.empty") in p.main(); r["shell_after"] = p.shell_ok()
                    p.shot(f"robot-after-delete-{target}")
                    break
        r["errors"] = p.errors[:5]; r["5xx"] = p.bad
        p.ctx.close()
    b.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
