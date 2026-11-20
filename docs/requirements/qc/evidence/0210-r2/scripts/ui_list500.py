import json
from lib import *
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang, w, dark in [("en", 1280, False), ("vi", 390, True)]:
        p = P(b, lang, w, dark); p.go("/datasets", 2000)
        print(p.tag, p.shell_ok(), p.main()[:300].replace("\n", " | "), p.bad[:2]); p.shot("r2-list500")
        p.go("/datasets/cnt15", 2000); print("  detail of a good dataset:", p.page.locator("li[data-state]").count(), "rows")
        p.go("/record", 1500); print("  record page append options:", p.page.locator("option").count(), p.shell_ok())
    b.close()
