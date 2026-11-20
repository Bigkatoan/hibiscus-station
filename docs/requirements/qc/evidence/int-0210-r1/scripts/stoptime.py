import sys, time, json, os
os.environ["QCPORT"] = sys.argv[1]
sys.path.insert(0, "/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int/w")
import qc, hammer
qc.setup(); res = []
for i in range(int(sys.argv[2])):
    s, b = hammer.record(f"st{int(time.time())}_{i}", 5, ep=4.0); assert s == 200, b
    while True:
        se = qc.status()["session"]
        if se and se["episode"] and se["episode"]["index"] == 1 and se["episode"]["phase"] == "episode" and se["episode"]["elapsed_s"] > 2: break
        time.sleep(0.05)
    t0 = time.time(); qc.call("POST", "/sessions/current/control", {"action": "stop"}); qc.wait_idle(); res.append(round(time.time() - t0, 2)); time.sleep(1)
print(sys.argv[1], qc.status()["station"]["version"], "stop->idle s", res)
