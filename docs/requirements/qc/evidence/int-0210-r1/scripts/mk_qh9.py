"""Make the QH-9 copies of a consistent dataset SRC (6 episodes, several data files)."""
import json, os, shutil, sys, glob
import pyarrow.parquet as pq
D = os.environ["QCHOME"] + "/datasets"; SRC = sys.argv[1]
def mk(n):
    for s in ("", ".hibiscus"):
        shutil.rmtree(f"{D}/{n}{s}", ignore_errors=True)
        if os.path.exists(f"{D}/{SRC}{s}"): shutil.copytree(f"{D}/{SRC}{s}", f"{D}/{n}{s}")
    return f"{D}/{n}"
def info(n, **kw):
    p = f"{D}/{n}/meta/info.json"; d = json.load(open(p)); d.update(kw); json.dump(d, open(p, "w"), indent=4)
base = json.load(open(f"{D}/{SRC}/meta/info.json")); te, tf = base["total_episodes"], base["total_frames"]
print("src", te, tf)
for k in (0, 1, te // 2, te + 2): mk(f"te{k}"); info(f"te{k}", total_episodes=k)
mk("tfm1"); info("tfm1", total_frames=tf - 1)
mk("tfp1"); info("tfp1", total_frames=tf + 1)
r = mk("gap"); f = sorted(glob.glob(f"{r}/meta/episodes/**/*.parquet", recursive=True))[-1]
t = pq.read_table(f); col = t.column("episode_index").to_pylist(); col[-1] = col[-1] + 5
t = t.set_column(t.schema.get_field_index("episode_index"), "episode_index", __import__("pyarrow").array(col, t.schema.field("episode_index").type)); pq.write_table(t, f)
r = mk("nodata"); f = sorted(glob.glob(f"{r}/data/**/*.parquet", recursive=True))[-1]; os.remove(f); print("nodata removed", f[len(r):])
r = mk("novideo"); f = sorted(glob.glob(f"{r}/videos/**/*.mp4", recursive=True))[0]; os.remove(f); print("novideo removed", f[len(r):])
mk("ok")
