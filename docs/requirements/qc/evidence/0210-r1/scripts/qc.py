import json, sys, time, urllib.request, urllib.error
TOK = "<QC_TOKEN>"
import os
PORT = int(os.environ.get("QCPORT", "18501"))
def call(m, path, data=None, port=None):
    port = port or PORT
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", method=m,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {TOK}", "X-Station": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read(); return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b)
        except Exception: return e.code, b.decode(errors="replace")
def ok(m, path, data=None):
    s, b = call(m, path, data); assert s < 300, (m, path, s, b); return b
def status(): return ok("GET", "/status")
def connect():
    st = status()
    if st["state"] != "disconnected": return st
    rid = ok("GET", "/robots")
    return rid
def setup():
    st = status()
    if st["state"] == "disconnected":
        ok("POST", "/robots/demo_so101/connect", {})
    for arm in ("follower", "leader"):
        st = status()
        if st["robot"]["arms"][arm]["calibrated"]: continue
        ok("POST", "/calibration/start", {"arm": arm})
        time.sleep(0.5); ok("POST", "/calibration/step", {"action": "set_home"})
        time.sleep(1.0); ok("POST", "/calibration/step", {"action": "finish_ranges"})
        time.sleep(0.5)
    return status()
def wait_idle(t=600):
    end = time.time() + t
    while time.time() < end:
        st = status()
        if st["state"] == "idle" and not st.get("session"): return st
        time.sleep(0.3)
    raise AssertionError("not idle")
