import qc, json, time, copy, os, hashlib, glob
H = os.environ["QCHOME"]
def tree_hash(p):
    h = hashlib.sha256()
    for f in sorted(glob.glob(p + "/**", recursive=True)):
        if os.path.isfile(f): h.update(f.encode()); h.update(open(f, "rb").read())
    return h.hexdigest()[:16]
R = {}
rb = qc.ok("GET", "/robots"); R["initial"] = [r["id"] for r in rb["robots"]], rb["active"]
demo = rb["robots"][0]
for pid, name in (("so-101-1", "so-101-1"), ("SO_101", "SO_101")):
    p = copy.deepcopy(demo); p["id"] = pid; p["name"] = name
    R[f"put_{pid}"] = qc.call("PUT", f"/robots/{pid}", p)[0]
rb = qc.ok("GET", "/robots"); R["after_put"] = [r["id"] for r in rb["robots"]], rb["active"]
qc.setup()  # connects demo + calibrates
cal = sorted(glob.glob(H + "/hf/lerobot/calibration/**/*.json", recursive=True)); R["cal_files"] = [os.path.basename(c) for c in cal]
cal_h = {c: hashlib.sha256(open(c, "rb").read()).hexdigest() for c in cal}
ds_h = tree_hash(H + "/datasets")
def d(pid):
    s, b = qc.call("DELETE", f"/robots/{pid}"); return s, (b.get("code"), b.get("params")) if isinstance(b, dict) else b
R["del_connected"] = d("demo_so101")
# session
for _ in range(100):
    s, b = qc.call("POST", "/sessions/teleop", {});
    if s == 200: break
    time.sleep(0.2)
time.sleep(1); R["state_teleop"] = qc.status()["state"]; R["del_in_session"] = d("demo_so101")
qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.wait_idle()
# calibrating
s, b = qc.call("POST", "/calibration/start", {"arm": "follower", "keep_existing": True}); time.sleep(0.5)
R["state_cal"] = (s, qc.status()["state"]); R["del_calibrating"] = d("demo_so101")
qc.call("POST", "/calibration/step", {"action": "cancel"}); time.sleep(1)
# delete another (not connected) profile while demo connected
R["del_other_while_connected"] = d("so-101-1")
qc.ok("POST", "/robots/disconnect", {}); time.sleep(1)
R["state_disc"] = qc.status()["state"]
R["del_SO_101"] = d("SO_101")
R["del_missing"] = d("nope")
rb = qc.ok("GET", "/robots"); R["after_del"] = [r["id"] for r in rb["robots"]], rb["active"]
R["cal_kept"] = all(os.path.isfile(c) and hashlib.sha256(open(c, "rb").read()).hexdigest() == h for c, h in cal_h.items())
R["datasets_kept"] = tree_hash(H + "/datasets") == ds_h
# new profile with the same calibration ids -> connects calibrated
p = copy.deepcopy(demo); p["id"] = "so101-new"; p["name"] = "SO-101 new"
R["put_new"] = qc.call("PUT", "/robots/so101-new", p)[0]
R["connect_new"] = qc.call("POST", "/robots/so101-new/connect", {})[0]; time.sleep(1)
st = qc.status(); R["new_calibrated"] = {a: st["robot"]["arms"][a]["calibrated"] for a in ("follower", "leader")}
qc.ok("POST", "/robots/disconnect", {}); time.sleep(1)
print(json.dumps(R, indent=1))
