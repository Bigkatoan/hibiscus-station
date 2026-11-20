import json, sys
from lib import *
out = {}
CF = [("en", 1280, False), ("vi", 390, True), ("en", 390, True), ("vi", 1280, False)]
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in CF:
        p = P(b, lang, w, dark); r = out.setdefault(p.tag, {})
        for path in ("/datasets", "/datasets/cnt15", "/datasets/crasha", "/datasets/crashb", "/datasets/dmgi1", "/datasets/dmgsc", "/datasets/dmgp", "/datasets/nonexist"):
            p.go(path, 1500)
            m = p.main(); s = p.shell_ok()
            info = {"shell": s, "rows": p.page.locator("li[data-state]").count(),
                    "unreadable_msgs": m.count(p.t("datasets.unreadable")), "saving": m.count(p.t("datasets.saving")),
                    "disabled_btns": p.page.locator("li[data-state] button:disabled").count()}
            if path == "/datasets/nonexist": info["missing_msg"] = p.t("datasets.missing", name="nonexist") in m
            r[path] = info
            p.shot("static" + path.replace("/", "_"))
        # open telemetry of episode 1 on cnt15
        p.go("/datasets/cnt15", 1500)
        p.page.locator("li[data-state='saved'] button[aria-pressed]").first.click(); p.page.wait_for_timeout(1500)
        r["tel_open"] = {"svg_or_canvas": p.page.locator("main svg, main canvas").count()}
        p.shot("telemetry_cnt15")
        r["errors"] = p.errors[:10]; r["5xx"] = p.bad[:10]
        p.ctx.close()
    b.close()
print(json.dumps(out, indent=1, ensure_ascii=False))
json.dump(out, open(f"{Q}/ui_static.json", "w"), indent=1, ensure_ascii=False)
