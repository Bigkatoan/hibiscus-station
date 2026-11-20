import json, sys
from lib import *
R = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in [("en", 1280, False), ("vi", 390, True)]:
        p = P(b, lang, w, dark); pg = p.page; r = R.setdefault(p.tag, {})
        for n in ("crasha", "crashb", "mixd", "cnt15", "e_huge"):
            p.go(f"/datasets/{n}", 1800); m = p.main()
            rows = pg.locator("li[data-state]")
            r[n] = {"notice": pg.get_by_test_id("dataset-unreadable").count(), "notice_text_ok": p.t("datasets.unreadable_all") in m,
                    "long_row_text": m.count(p.t("datasets.unreadable")), "short_row_text": sum(1 for i in range(rows.count()) if p.t("datasets.unreadable_short") in rows.nth(i).inner_text()),
                    "rows": rows.count(), "states": [rows.nth(i).get_attribute("data-state") for i in range(rows.count())], "shell": p.shell_ok()}
            # open the telemetry of the first unreadable row
            u = pg.locator("li[data-state='unreadable'] button[aria-pressed]").first
            if u.count():
                r[n]["unreadable_btn_enabled"] = u.is_enabled()
                if u.is_enabled():
                    u.click(); pg.wait_for_timeout(1500)
                    r[n]["tel_charts"] = pg.locator("main svg, main canvas").count(); r[n]["pick_msg_gone"] = p.t("datasets.pick_episode") not in p.main() if "datasets.pick_episode" in I18N[lang] else None
                r[n]["replay_disabled"] = pg.locator("li[data-state='unreadable']").first.get_by_role("button", name=p.t("datasets.replay")).is_disabled()
            p.shot(f"r2-{n}")
        # QH-2 card on the Record page
        for ds, key in (("dmgi1", "record.unreadable"), ("crasha", "record.unfinalized")):
            p.go("/record", 1500)
            pg.get_by_label(p.t("record.mode"), exact=True).select_option("append"); pg.wait_for_timeout(300)
            pg.get_by_label(p.t("record.dataset")).select_option(ds); pg.wait_for_timeout(300)
            pg.get_by_label(p.t("record.task")).fill("pick the cube")
            for _ in range(60):
                pg.get_by_role("button", name=p.t("record.start")).click(); pg.wait_for_timeout(700)
                if pg.get_by_test_id("record-unfinalized").count(): break
            card = pg.get_by_test_id("record-unfinalized")
            rr = {"card": card.count(), "text_ok": bool(card.count()) and p.t(key, dataset=ds) in card.inner_text()}
            p.shot(f"r2-append-{ds}")
            if card.count():
                card.get_by_role("button", name=p.t("record.new_instead")).click(); pg.wait_for_timeout(500)
                rr["mode"] = pg.get_by_label(p.t("record.mode"), exact=True).input_value(); rr["name"] = pg.get_by_label(p.t("record.dataset")).input_value()
            R[p.tag][f"append_{ds}"] = rr
        r["errors"] = [e[:120] for e in p.errors][:6]; r["5xx"] = p.bad
        p.ctx.close()
    b.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
