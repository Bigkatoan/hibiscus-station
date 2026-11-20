import json, os, re, time, urllib.request
from playwright.sync_api import sync_playwright
Q = os.environ["Q"]; PORT = int(os.environ.get("QCPORT", "18501")); BASE = f"http://127.0.0.1:{PORT}"
TOK = "<QC_TOKEN>"
WT = f"{Q}/src2/web/src/station/i18n"
def flat(d, p=""):
    o = {}
    for k, v in d.items():
        if isinstance(v, dict): o.update(flat(v, f"{p}{k}."))
        else: o[f"{p}{k}"] = v
    return o
I18N = {l: flat(json.load(open(f"{WT}/{l}.json"))) for l in ("en", "vi")}
def T(lang, k, **kw):
    s = I18N[lang][k]
    for a, b in kw.items(): s = s.replace("{{" + a + "}}", str(b))
    return s
def api(m, path, data=None):
    req = urllib.request.Request(f"{BASE}/api/v1{path}", method=m, data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {TOK}", "X-Station": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read(); return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b)
        except Exception: return e.code, b.decode(errors="replace")
class P:
    def __init__(self, browser, lang="en", w=1280, dark=False):
        self.lang, self.w, self.dark = lang, w, dark
        self.tag = f"{lang}-{w}-{'dark' if dark else 'light'}"
        self.ctx = browser.new_context(locale="vi-VN" if lang == "vi" else "en-US", viewport={"width": w, "height": 900},
            color_scheme="dark" if dark else "light", reduced_motion="reduce")
        self.page = self.ctx.new_page(); self.errors = []; self.bad = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: m.type == "error" and self.errors.append("console:" + m.text))
        self.page.on("response", lambda r: r.status >= 500 and self.bad.append((r.status, r.url)))
        self.page.goto(f"{BASE}/auth?t={TOK}"); self.page.wait_for_url(re.compile(rf"{BASE}/.*"))
        self.page.wait_for_timeout(500)
        # force the language if the station does not follow the browser locale
        self.page.evaluate(f"localStorage.setItem('i18nextLng','{lang}')")
    def t(self, k, **kw): return T(self.lang, k, **kw)
    def go(self, path, wait=1200):
        self.page.goto(f"{BASE}{path}"); self.page.wait_for_timeout(wait)
    def shell_ok(self):
        txt = self.page.locator("body").inner_text()
        return {"nav": self.page.locator("nav").count() > 0 and self.page.locator("header").count() > 0,
                "unexpected": "Unexpected Application Error" in txt, "blank": len(txt.strip()) < 40}
    def main(self): return self.page.locator("main").inner_text() if self.page.locator("main").count() else self.page.locator("body").inner_text()
    def shot(self, name, full=True):
        os.makedirs(f"{Q}/shots", exist_ok=True); self.page.screenshot(path=f"{Q}/shots/{name}-{self.tag}.png", full_page=full)
