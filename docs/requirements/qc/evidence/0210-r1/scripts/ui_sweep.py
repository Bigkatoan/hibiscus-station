import json, sys
from lib import *
paths = ["/", "/robot", "/calibrate", "/cameras", "/teleop", "/record", "/upload", "/train", "/run", "/programs", "/datasets", "/models", "/sessions", "/settings"]
out = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in [("en", 1280, False), ("vi", 390, True)]:
        p = P(b, lang, w, dark)
        for path in paths:
            p.go(path, 1200); s = p.shell_ok()
            out[f"{p.tag}{path}"] = s if (not s["nav"] or s["unexpected"] or s["blank"]) else "ok"
        out[f"{p.tag}-errors"] = [e[:120] for e in p.errors][:6]; out[f"{p.tag}-5xx"] = p.bad
        p.ctx.close()
    b.close()
print(json.dumps(out, indent=0, ensure_ascii=False))
