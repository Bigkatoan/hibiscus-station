import qc, hammer, json, time, sys, subprocess, os
name, after, at_phase = sys.argv[1], int(sys.argv[2]), sys.argv[3]
qc.setup()
s, b = hammer.record(name, 40, ep=1.5); assert s == 200, (s, b)
def ep():
    se = qc.status()["session"]; return se and se["episode"]
while True:
    e = ep()
    if e and e["saved"] >= after and e["phase"] == at_phase: break
    time.sleep(0.005)
subprocess.run(["kill", "-9", open(os.environ["QCHOME"] + "/pid").read().strip()])
print("killed at", e)
