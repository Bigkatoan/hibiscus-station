import json, shutil, sys, os, copy, traceback
from pathlib import Path
from hibiscus_station.data import datasets as cat
from hibiscus_station.errors import StationError
from hibiscus_station.sessions.replay import load_episode_actions
src = Path(sys.argv[1]); work = Path(sys.argv[2])
base = json.loads((src / "meta/info.json").read_text())
V = [None, True, 0, -1, 1.5, 10**30, float("inf"), float("nan"), "x", "", [], [1], {}, {"a": 1}]
muts = []
for key in base:
    for v in V: muts.append(([key], v))
for f in base["features"]:
    for v in V: muts.append((["features", f], v))
    for sub in base["features"][f]:
        for v in V: muts.append((["features", f, sub], v))
muts += [([], v) for v in (None, [], "x", 1)]
res = {}
for path, v in muts:
    d = copy.deepcopy(base)
    if path:
        t = d
        for k in path[:-1]: t = t[k]
        t[path[-1]] = v
    else: d = v
    root = work / "datasets"; shutil.rmtree(root, ignore_errors=True); root.mkdir(parents=True)
    shutil.copytree(src, root / "x"); shutil.copytree(str(src) + ".hibiscus", root / "x.hibiscus")
    (root / "x/meta/info.json").write_text(json.dumps(d))
    for name, fn in (("list", lambda: cat.list_datasets(root)), ("detail", lambda: cat.detail(root, "x")),
                     ("tel", lambda: cat.episode_series(root, "x", 0)), ("replay", lambda: load_episode_actions(root / "x", 0))):
        try: fn()
        except StationError: pass
        except Exception as e:
            res.setdefault(f"{name}: {type(e).__name__}", []).append(f"{'.'.join(path) or '<root>'}={json.dumps(v) if v == v else 'NaN'}")
for k, v in sorted(res.items()): print(k, len(v), v[:12])
