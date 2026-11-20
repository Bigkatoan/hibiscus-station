import json
from lib import *
R = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in [("en", 1280, False), ("vi", 390, True)]:
        p = P(b, lang, w, dark); pg = p.page
        for ds in ("cnt3", "crasha"):
            p.go("/record", 1500)
            pg.get_by_label(p.t("record.mode"), exact=True).select_option("append"); pg.wait_for_timeout(300)
            pg.get_by_label(p.t("record.dataset")).select_option(ds); pg.wait_for_timeout(300)
            pg.get_by_label(p.t("record.task")).fill("pick the cube")
            for _ in range(60):
                pg.get_by_role("button", name=p.t("record.start")).click(); pg.wait_for_timeout(700)
                if pg.get_by_test_id("record-unfinalized").count() or pg.locator("[role=alert]").count(): break
            card = pg.get_by_test_id("record-unfinalized")
            r = {"card": card.count(), "text": card.inner_text()[:400] if card.count() else p.main()[-400:]}
            p.shot(f"r3-incompatible-{ds}")
            if card.count():
                card.get_by_role("button", name=p.t("record.new_instead")).click(); pg.wait_for_timeout(500)
                r["mode"] = pg.get_by_label(p.t("record.mode"), exact=True).input_value(); r["name"] = pg.get_by_label(p.t("record.dataset")).input_value()
            R[f"{p.tag}-{ds}"] = r
        R[f"{p.tag}-5xx"] = p.bad
        p.ctx.close()
    b.close()
print(json.dumps(R, indent=1, ensure_ascii=False))
