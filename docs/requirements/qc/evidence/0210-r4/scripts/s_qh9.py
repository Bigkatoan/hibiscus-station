import qc, hammer, os, glob, hashlib, time, sys
D = os.environ["QCHOME"] + "/datasets"
def th(n):
    h = hashlib.sha256()
    for f in sorted(glob.glob(f"{D}/{n}/**", recursive=True) + glob.glob(f"{D}/{n}.hibiscus/**", recursive=True)):
        if os.path.isfile(f): h.update(f.encode()); h.update(open(f, "rb").read())
    return h.hexdigest()
qc.setup()
s, b = qc.call("GET", "/datasets"); L = {d["name"]: d for d in b["datasets"]}
for n in sys.argv[1:]:
    s, d = qc.call("GET", f"/datasets/{n}")
    before = th(n)
    s2, r = hammer.record(n, 1, ep=1.0, mode="append")
    if s2 == 200: qc.wait_idle(); time.sleep(1)
    after = qc.call("GET", f"/datasets/{n}")[1]
    print(f"{n:8s} list fin={L[n]['finalized']} detail fin={d['finalized']} reasons={[x[:80] for x in d['finalize_reasons']][:2]}\n         append {s2} {r.get('code') if isinstance(r, dict) else ''} identical={th(n) == before} | after: eps={after['episodes']} fin={after['finalized']} rows={''.join(e['state'][0] for e in after['episode_list'])}", flush=True)
