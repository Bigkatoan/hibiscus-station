import qc, hammer, json, os, hashlib, glob, subprocess, sys
H = os.environ["QCHOME"]; D = H + "/datasets"
def th(n):
    h = hashlib.sha256()
    for f in sorted(glob.glob(f"{D}/{n}/**", recursive=True) + glob.glob(f"{D}/{n}.hibiscus/**", recursive=True)):
        if os.path.isfile(f):
            h.update(f.encode()); st = os.stat(f); h.update(str(st.st_mode).encode())
            try: h.update(open(f, "rb").read())
            except PermissionError: h.update(b"<noperm>")
    return h.hexdigest()[:16]
qc.setup()
names = sys.argv[1:]
for n in names:
    before = th(n)
    s, b = hammer.record(n, 1, mode="append")
    code = b.get("code") if isinstance(b, dict) else b
    if s == 200:
        qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.wait_idle()
    s2, r = qc.call("POST", "/sessions/replay", {"dataset": n, "episode": 0})
    if s2 == 200:
        import time; time.sleep(1); qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.call("POST", "/estop/reset"); qc.wait_idle()
    print(f"{n:10s} append {s} {str(code):24s} identical={th(n) == before} | reasons={(b.get('params') or {}).get('reasons') if isinstance(b, dict) else ''} | replay {s2} {r.get('code') if isinstance(r, dict) else r}", flush=True)
