import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
root = Path(sys.argv[1]); scen = json.loads(Path("qc/" + (sys.argv[2] if len(sys.argv) > 2 else "qd34.json") + "").read_text())
def tags(t, arm):
    lp = " ".join(l for l in t.split("\n\n")[0].splitlines()[1:] if f"desk {arm}" in l and "no calibration" not in l)
    out = []
    for k, rx in [("slow", r"slow bus"), ("CABLES", r"reads failed"), ("3pin", r"3-pin cables"), ("unreliable", r"unreliable bus"),
                  ("late", r"answers came late"), ("dead", r"do not answer"), ("flaky", r"now and then"), ("corrupt", r"corrupted"),
                  ("stalled", r"stalled")]:
        if re.search(rx, lp): out.append(k)
    m = re.search(r"motor id\(s\) ([\d, ]+) do not answer", lp); 
    if m: out.append("dead=" + m.group(1).replace(" ", ""))
    m = re.search(r"motor id\(s\) ([\d, ]+) answer only now and then", lp)
    if m: out.append("flaky=" + m.group(1).replace(" ", ""))
    m = re.search(r"(\d+) of (\d+) reads failed", lp)
    if m: out.append(f"failed{m.group(1)}/{m.group(2)}")
    return out or ["clean"]
groups = defaultdict(Counter)
for n, cfg in scen.items():
    t = (root / n / "stdout.txt").read_text() if (root / n / "stdout.txt").exists() else ""
    arm = "follower" if "follower" in cfg else "leader"
    g = re.sub(r"-s\d$", "", n)
    if g.startswith(("qd34-","real-ad0")) and "-" not in g[8:]: g = re.sub(r"[\d.]+$", "", g)  # group steady sweep by kind
    groups[g][" ".join(x for x in tags(t, arm) if not x.startswith("failed"))] += 1
    if "CABLES" in tags(t, arm) or "3pin" in tags(t, arm):
        groups[g + " [cable-advice list]"][n] += 1
for g, c in groups.items():
    print(f"{g:34s} {dict(c)}")
