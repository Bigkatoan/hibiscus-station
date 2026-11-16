"""Decimate the SO-101 follower meshes for the Station 3D twin (web/src/station/twin/so101).

Source: TheRobotStudio/SO-ARM100 (Apache-2.0), Simulation/SO101 at commit a758567c39.
The CAD tessellation (long slivers) resists quadric decimation, so the meshes are first
vertex-clustered on a ``cell`` m grid, then reduced to <= 1500 faces with fast-simplification.

    uv run --no-project --with trimesh --with fast_simplification \\
        python tools/so101_meshes.py <SO-ARM100>/Simulation/SO101 <out dir> 0.001
"""

from __future__ import annotations

import os
import re
import sys

import fast_simplification  # type: ignore[import-not-found]
import numpy as np
import trimesh  # type: ignore[import-not-found]

MAX_FACES = 1500


def main(src: str, out: str, cell: float) -> None:
    with open(f"{src}/so101_new_calib.urdf", encoding="utf-8") as fh:
        urdf = fh.read()
    names = sorted(set(re.findall(r'filename="assets/([^"]+)"', urdf)))
    os.makedirs(f"{out}/assets", exist_ok=True)
    total = 0
    for name in names:
        mesh = trimesh.load(f"{src}/assets/{name}", force="mesh")
        faces_before = len(mesh.faces)
        grid = np.round(mesh.vertices / cell).astype(np.int64)
        cells, inverse = np.unique(grid, axis=0, return_inverse=True)
        inverse = inverse.ravel()
        centres = np.zeros((len(cells), 3))
        np.add.at(centres, inverse, mesh.vertices)
        centres /= np.bincount(inverse)[:, None]
        faces = inverse[mesh.faces]
        keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
        faces = faces[keep]
        _, idx = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
        faces = faces[np.sort(idx)]
        if len(faces) > MAX_FACES:
            centres, faces = fast_simplification.simplify(
                centres, faces, target_reduction=1 - MAX_FACES / len(faces), agg=7
            )
        reduced = trimesh.Trimesh(centres, faces, process=True)
        reduced.export(f"{out}/assets/{name}")
        size = os.path.getsize(f"{out}/assets/{name}")
        total += size
        print(
            f"{name}: {faces_before} -> {len(reduced.faces)} faces, {size / 1024:.0f} KiB, "
            f"extents {mesh.extents.round(3)} -> {reduced.extents.round(3)}"
        )
    print("total", round(total / 1024), "KiB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]))
