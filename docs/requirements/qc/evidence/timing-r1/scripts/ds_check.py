"""Offline dataset check of one run dir: parquet rows / timestamps / episodes vs mp4 frames, and the
LeRobotDataset (training reader) frame of every row == the mp4 frame decoded directly (mock counters).
usage: ds_check.py RUN_DIR"""
import json, sys
from pathlib import Path
import av, numpy as np, pyarrow.parquet as pq
from hibiscus_station.mock.camera import decode_counter
run = Path(sys.argv[1]); out = {}
for d in sorted(p for p in (run / "datasets").iterdir() if p.is_dir() and not p.name.endswith(".hibiscus")):
    info = json.loads((d / "meta/info.json").read_text()); fps = info["fps"]
    t = pq.read_table(sorted((d / "data").rglob("*.parquet"))[0]).to_pandas()
    ts = t["timestamp"].to_numpy(); fi = t["frame_index"].to_numpy()
    r = {"rows": len(t), "total_frames": info["total_frames"], "episodes": info["total_episodes"],
         "ts_monotonic": bool(np.all(np.diff(ts) > 0)), "ts_eq_index_over_fps": bool(np.allclose(ts, fi / fps, atol=1e-4)),
         "frame_index_contiguous": bool(np.array_equal(fi, np.arange(len(fi))))}
    cams = [k for k in info["features"] if k.startswith("observation.images.")]
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    ds = LeRobotDataset(f"local/{d.name}", root=d)
    for k in cams:
        mp4 = sorted((d / "videos" / k).rglob("*.mp4"))
        direct = []
        for f in mp4:
            with av.open(str(f)) as c:
                direct += [decode_counter(fr.to_ndarray(format="rgb24")) for fr in c.decode(video=0)]
        via = []
        for i in range(len(ds)):
            img = (ds[i][k].numpy().transpose(1, 2, 0) * 255).round().astype(np.uint8)
            via.append(decode_counter(img))
        dif = np.diff(np.array(direct, dtype=float))
        r[k] = {"mp4_frames": len(direct), "reader_eq_mp4": via == direct,
                "counter_steps": {str(int(x)): int((dif == x).sum()) for x in sorted(set(dif.tolist()))} if len(dif) else {}}
    out[d.name] = r
    print(d.name, json.dumps(r), flush=True)
(run / "ds_check.json").write_text(json.dumps(out, indent=1))
