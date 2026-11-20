import json, sys
from lib import *
paths = ["/", "/robot", "/calibrate", "/cameras", "/teleop", "/record", "/upload", "/train", "/run", "/programs?tab=trajectories", "/programs?tab=detection",
         "/programs?tab=programs", "/datasets", "/datasets/cnt15", "/datasets/crasha", "/datasets/dmgi1", "/models", "/sessions", "/settings"]
out = {}; summary = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang in ("en", "vi"):
        for dark in (False, True):
            for w in (1280, 390):
                p = P(b, lang, w, dark); bad_pages = {}; hs = []
                for path in paths:
                    p.go(path, 1500); s = p.shell_ok()
                    if not s["nav"] or s["unexpected"] or s["blank"]: bad_pages[path] = s
                    if p.page.evaluate("document.scrollingElement.scrollWidth > document.scrollingElement.clientWidth + 1"): hs.append(path)
                    if path == "/datasets/cnt15":
                        btn = p.page.locator("li[data-state='saved'] button[aria-pressed]").first
                        if btn.count(): btn.click(); p.page.wait_for_timeout(2500)
                        if p.page.evaluate("document.scrollingElement.scrollWidth > document.scrollingElement.clientWidth + 1"): hs.append(path + "#episode")
                        p.shot("episode_cnt15")
                    if path in ("/", "/datasets/cnt15", "/programs?tab=programs"): p.shot("sweep" + path.replace("/", "_").replace("?", "_"))
                errs = [e[:160] for e in p.errors]
                summary[p.tag] = {"pages": len(paths), "bad_pages": bad_pages, "hscroll": hs, "errors": errs[:8], "n_errors": len(errs), "5xx": p.bad[:5]}
                print(p.tag, json.dumps(summary[p.tag], ensure_ascii=False)[:600], flush=True)
                p.ctx.close()
    b.close()
json.dump(summary, open(f"{Q}/ui_sweep8.json", "w"), indent=1, ensure_ascii=False)
