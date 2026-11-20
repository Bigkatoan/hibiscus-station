"""QC API fuzz: mutate x/meta/info.json, then list, detail(x), detail(healthy), telemetry, append, replay
through the running installed Station. Every 5xx, timeout or file change on a refused call is a failure."""
import json, shutil, sys, os, copy, hashlib, glob, time, collections
import qc, hammer
H = os.environ["QCHOME"]; D = f"{H}/datasets"; SRC = sys.argv[1]
def th(n):
    h = hashlib.sha256()
    for f in sorted(glob.glob(f"{D}/{n}/**", recursive=True) + glob.glob(f"{D}/{n}.hibiscus/**", recursive=True)):
        if os.path.isfile(f): h.update(f.encode()); h.update(open(f, "rb").read())
    return h.hexdigest()
def fresh(dst):
    for s in ("", ".hibiscus"):
        shutil.rmtree(f"{D}/{dst}{s}", ignore_errors=True); shutil.copytree(f"{SRC}{s}", f"{D}/{dst}{s}")
fresh("healthy"); healthy_h = th("healthy")
base = json.load(open(f"{SRC}/meta/info.json"))
V = [None, True, False, 0, -1, 1.5, 10**30, float("inf"), float("-inf"), float("nan"), "x", "", [], [1], {}, {"a": 1}]
muts = [([k], v) for k in base for v in V]
for f in base["features"]:
    muts += [(["features", f], v) for v in V]
    for sub in base["features"][f]: muts += [(["features", f, sub], v) for v in V]
muts += [(["features", "action", "names"], ["a"]), (["features", "action", "names"], [1, 2, 3, 4, 5, 6]), (["robot_type"], 5), (["robot_type"], {"a": 1})]
muts += [([], v) for v in (None, [], "x", 1, True)]
fails = []; stats = collections.Counter(); qc.setup()
for i, (path, v) in enumerate(muts):
    fresh("x")
    d = copy.deepcopy(base)
    if path:
        t = d
        for k in path[:-1]: t = t[k]
        t[path[-1]] = v
    else: d = v
    open(f"{D}/x/meta/info.json", "w").write(json.dumps(d))
    tag = f"{'.'.join(path) or '<root>'}={json.dumps(v) if v == v else 'NaN'}"
    before = th("x")
    calls = [("list", "GET", "/datasets", None), ("detail", "GET", "/datasets/x", None), ("healthy", "GET", "/datasets/healthy", None),
             ("tel", "GET", "/datasets/x/episodes/0/telemetry", None)]
    for name, m, p, body in calls:
        t0 = time.time(); s, b = qc.call(m, p, body); dt = time.time() - t0
        stats[(name, s)] += 1
        if s >= 500 or dt > 5: fails.append((tag, name, s, round(dt, 1), str(b)[:120]))
        if name == "list" and s == 200 and "x" not in [z["name"] for z in b["datasets"]]: fails.append((tag, "list-missing-x", s))
        if name == "detail" and s == 200: finalized = b["finalized"]
    s, b = hammer.record("x", 1, mode="append"); stats[("append", s, b.get("code") if isinstance(b, dict) else None)] += 1
    if s >= 500: fails.append((tag, "append", s, str(b)[:160]))
    appended = s == 200
    if appended:
        qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.wait_idle(60)
        if not finalized: fails.append((tag, "append accepted on a not-finalized dataset", s))
    elif th("x") != before: fails.append((tag, "files changed after refused append", s))
    if appended: fresh("x"); open(f"{D}/x/meta/info.json", "w").write(json.dumps(d)); before = th("x")
    s, b = qc.call("POST", "/sessions/replay", {"dataset": "x", "episode": 0}); stats[("replay", s, b.get("code") if isinstance(b, dict) else None)] += 1
    if s >= 500: fails.append((tag, "replay", s, str(b)[:160]))
    if s == 200:
        if not finalized: fails.append((tag, "replay accepted on a not-finalized/unreadable dataset", s))
        time.sleep(0.3); qc.call("POST", "/sessions/current/control", {"action": "stop"}); time.sleep(0.3)
        if qc.status()["state"] == "estopped": qc.call("POST", "/estop/reset")
        qc.wait_idle(60)
    if not appended and th("x") != before: fails.append((tag, "files changed after replay", s))
print("mutations", len(muts)); print("stats", dict(stats))
print("healthy identical", th("healthy") == healthy_h)
print("FAILS", len(fails)); [print("  ", f) for f in fails[:60]]
