"""Episode video for the dataset viewer (F-72, FR-77, ADR-14).

A LeRobot v3 dataset concatenates many episodes into one ``videos/<camera>/chunk-NNN/file-NNN.mp4``;
``meta/episodes`` gives each episode's ``from_timestamp`` / ``to_timestamp`` in that file. Station
records with LeRobot's default encoder (AV1, ``libsvtav1``), which a stock Windows Edge does not
decode without the Store's "AV1 Video Extension". So the viewer asks for one of three formats:

* ``source``: the episode's own packets, stream-copied (no re-encode) into a small mp4 whose time
  0 is the episode start. Cheap; plays where the browser decodes the recorded codec.
* ``vp9``: re-encoded to VP9 in WebM. Edge, Chrome and Firefox decode VP9 with their own built-in
  decoder (no OS codec, no Store extension, also on Windows "N" editions).
* ``h264``: re-encoded to H.264 in mp4 (last resort).

Every cut is cached in the sidecar (``<name>.hibiscus/video-cache/``, never inside the LeRobot root)
under a key of the source file's size / mtime and the episode's span, so a re-recorded or appended
dataset never serves a stale cut. The dataset stays byte-for-byte what LeRobot wrote.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from hibiscus_station.data.sidecar import sidecar_dir
from hibiscus_station.errors import StationError
from hibiscus_station.oscompat import replace_file
from hibiscus_station.sessions.recorder import check_name

log = logging.getLogger(__name__)

VideoFormat = Literal["source", "vp9", "h264"]
FORMATS: tuple[VideoFormat, ...] = ("source", "vp9", "h264")
#: camera keys come from ``meta/info.json``; this is a second fence before they touch a path
CAMERA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
#: RFC 6381 codec strings for ``HTMLMediaElement.canPlayType`` (main profile, 8 bit)
_SOURCE_MIME = {
    "av1": 'video/mp4; codecs="av01.0.05M.08"',
    "h264": 'video/mp4; codecs="avc1.42E01E"',
    "hevc": 'video/mp4; codecs="hvc1.1.6.L93.B0"',
    "vp9": 'video/mp4; codecs="vp09.00.10.08"',
}
_MEDIA_TYPE = {"source": "video/mp4", "vp9": "video/webm", "h264": "video/mp4"}
_SUFFIX = {"source": "mp4", "vp9": "webm", "h264": "mp4"}
_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


@dataclass(frozen=True)
class EpisodeClip:
    camera: str
    codec: str | None
    path: Path | None  # the LeRobot file holding the episode (None: missing)
    from_s: float
    to_s: float
    error: str | None  # station error code when the clip cannot be served

    @property
    def mime(self) -> str | None:
        return _SOURCE_MIME.get(self.codec or "")


def _info(root: Path) -> dict[str, Any]:
    path = root / "meta" / "info.json"
    if not path.is_file():
        raise StationError("not_found", f"no dataset {root.name}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _episode_row(root: Path, index: int) -> dict[str, Any] | None:
    import pyarrow.parquet as pq

    for f in sorted((root / "meta" / "episodes").rglob("*.parquet")):
        cols = pq.read_schema(f).names
        want = ["episode_index", *[c for c in cols if c.startswith("videos/")]]
        if "length" in cols:
            want.append("length")
        t = pq.read_table(f, columns=want).to_pydict()
        for i, idx in enumerate(t.get("episode_index", [])):
            if int(idx) == index:
                return {k: v[i] for k, v in t.items()}
    return None


def _inside(root: Path, path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def episode_clips(datasets_root: Path, name: str, index: int) -> dict[str, Any]:
    """Every camera of episode ``index``: where its frames are and whether they can be served."""
    check_name(name)
    if index < 0:
        raise StationError("validation_failed", "episode index must be >= 0")
    root = datasets_root / name
    info = _info(root)
    row = _episode_row(root, index)
    if row is None:
        raise StationError("not_found", f"no episode {index} in {name}", params={"episode": index})
    fps = info.get("fps")
    template = str(info.get("video_path") or "")
    clips: list[EpisodeClip] = []
    for key, ft in info.get("features", {}).items():
        if not key.startswith("observation.images.") or not isinstance(ft, dict):
            continue
        cam = key.removeprefix("observation.images.")
        if ft.get("dtype") != "video":
            clips.append(EpisodeClip(cam, None, None, 0.0, 0.0, "video_unavailable"))
            continue
        codec = (ft.get("info") or {}).get("video.codec")
        prefix = f"videos/{key}/"
        try:
            chunk = int(row[prefix + "chunk_index"])
            file = int(row[prefix + "file_index"])
            start = float(row[prefix + "from_timestamp"])
            end = float(row[prefix + "to_timestamp"])
        except (KeyError, TypeError, ValueError):
            clips.append(EpisodeClip(cam, codec, None, 0.0, 0.0, "video_missing"))
            continue
        path = root / template.format(video_key=key, chunk_index=chunk, file_index=file)
        error = None
        if not CAMERA_RE.match(cam) or not _inside(root, path):
            error = "video_unavailable"
        elif not path.is_file():
            error = "video_missing"
        clips.append(EpisodeClip(cam, codec, path if error is None else None, start, end, error))
    length = row.get("length")
    return {
        "fps": int(fps) if isinstance(fps, (int, float)) else None,
        "length_s": round(int(length) / fps, 3) if isinstance(length, int) and fps else None,
        "clips": clips,
    }


def describe(datasets_root: Path, name: str, index: int) -> dict[str, Any]:
    """``EpisodeVideos`` (wire): the viewer's list of cameras for one episode."""
    found = episode_clips(datasets_root, name, index)
    return {
        "dataset": name,
        "episode": index,
        "fps": found["fps"],
        "length_s": found["length_s"],
        "cameras": [
            {
                "camera": c.camera,
                "codec": c.codec,
                "mime": c.mime,
                "duration_s": round(max(0.0, c.to_s - c.from_s), 3),
                "error": c.error,
                "formats": list(FORMATS) if c.error is None else [],
            }
            for c in found["clips"]
        ],
    }


def _lock(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(path, threading.Lock())


def cache_dir(datasets_root: Path, name: str) -> Path:
    return sidecar_dir(datasets_root, name) / "video-cache"


def clip_file(datasets_root: Path, name: str, index: int, camera: str, fmt: VideoFormat) -> tuple[Path, str]:
    """The cached cut of one camera of one episode in ``fmt`` (made on first request)."""
    if fmt not in FORMATS:
        raise StationError("validation_failed", f"format must be one of {', '.join(FORMATS)}")
    if not CAMERA_RE.match(camera):
        raise StationError("validation_failed", "bad camera name")
    found = episode_clips(datasets_root, name, index)
    clip = next((c for c in found["clips"] if c.camera == camera), None)
    if clip is None:
        raise StationError(
            "not_found", f"no camera {camera} in {name}", params={"camera": camera, "episode": index}
        )
    if clip.error is not None or clip.path is None:
        code = clip.error or "video_missing"
        raise StationError(code, f"no video of camera {camera}", params={"camera": camera, "episode": index})
    st = clip.path.stat()
    key = hashlib.sha256(
        f"{clip.path.name}|{st.st_size}|{st.st_mtime_ns}|{clip.from_s:.6f}|{clip.to_s:.6f}".encode()
    ).hexdigest()[:16]
    folder = cache_dir(datasets_root, name) / camera
    out = folder / f"episode_{index:06d}.{fmt}.{key}.{_SUFFIX[fmt]}"
    with _lock(out):
        if not out.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob(f"episode_{index:06d}.{fmt}.*"):
                with contextlib.suppress(OSError):  # Windows: still open by an earlier response
                    old.unlink()  # an earlier cut of a file that changed since
            fd, tmp_name = tempfile.mkstemp(prefix=f".{out.name}.", suffix=f".{_SUFFIX[fmt]}", dir=folder)
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                fps = found["fps"] or 30
                if fmt == "source":
                    _remux(clip.path, tmp, clip.from_s, clip.to_s, fps)
                else:
                    _transcode(clip.path, tmp, clip.from_s, clip.to_s, fps, fmt)
                replace_file(tmp, out)
            except StationError:
                raise
            except Exception as exc:
                log.warning("video cut of %s/%s episode %d (%s) failed: %s", name, camera, index, fmt, exc)
                raise StationError(
                    "video_unavailable",
                    f"could not read the video of camera {camera}: {type(exc).__name__}",
                    params={"camera": camera, "episode": index},
                ) from exc
            finally:
                tmp.unlink(missing_ok=True)
    return out, _MEDIA_TYPE[fmt]


def _remux(src: Path, dst: Path, start: float, end: float, fps: int) -> None:
    """Copy the packets of [start, end) into ``dst``, time 0 = ``start`` (no re-encode)."""
    import av

    half = 0.5 / fps
    with av.open(str(src)) as inp:
        ist = inp.streams.video[0]
        tb = ist.time_base
        if tb is None:
            raise ValueError("video stream without a time base")
        with av.open(str(dst), "w", format="mp4", options={"movflags": "+faststart"}) as out:
            ost = out.add_stream_from_template(ist, opaque=True)
            base: int | None = None
            inp.seek(int(max(0.0, start - 1.0) / tb), stream=ist, backward=True, any_frame=False)
            for pkt in inp.demux(ist):
                if pkt.pts is None or pkt.dts is None:
                    continue
                t = float(pkt.pts * tb)
                if t >= end - half:
                    break
                if base is None:
                    # first packet of the episode: a keyframe (LeRobot encodes each episode on its own)
                    if t < start - half or not pkt.is_keyframe:
                        continue
                    base = pkt.dts
                pkt.pts -= base
                pkt.dts -= base
                pkt.stream = ost
                out.mux(pkt)
            if base is None:
                raise ValueError(f"no keyframe at {start:.3f} s")


def _encoder(fmt: VideoFormat) -> str:
    import av

    names = ("libvpx-vp9",) if fmt == "vp9" else ("libx264", "libopenh264", "h264")
    for n in names:
        try:
            av.codec.Codec(n, "w")
            return n
        except Exception:  # noqa: S112 - try the next encoder this FFmpeg build has
            continue
    raise StationError("video_unavailable", f"this Station has no {fmt} encoder")


def _transcode(src: Path, dst: Path, start: float, end: float, fps: int, fmt: VideoFormat) -> None:
    """Decode [start, end) and encode it to ``fmt`` (VP9 / WebM or H.264 / mp4), time 0 = ``start``."""
    import av

    half = 0.5 / fps
    enc = _encoder(fmt)
    with av.open(str(src)) as inp:
        ist = inp.streams.video[0]
        tb = ist.time_base
        if tb is None:
            raise ValueError("video stream without a time base")
        container = "webm" if fmt == "vp9" else "mp4"
        opts = {"movflags": "+faststart"} if container == "mp4" else {}
        if enc == "libvpx-vp9":
            enc_opts = {"deadline": "realtime", "cpu-used": "8", "crf": "32", "b": "0", "row-mt": "1"}
        elif enc == "libx264":
            enc_opts = {"preset": "veryfast", "tune": "zerolatency", "crf": "23"}
        else:
            enc_opts = {}
        with av.open(str(dst), "w", format=container, options=opts) as out:
            ost: Any = out.add_stream(enc, rate=Fraction(fps), options=enc_opts)
            ctx = ist.codec_context
            ost.width = max(2, (ctx.width // 2) * 2)
            ost.height = max(2, (ctx.height // 2) * 2)
            ost.pix_fmt = "yuv420p"
            ost.time_base = Fraction(1, fps)
            ost.gop_size = max(1, fps)  # a keyframe a second: the scrubber seeks fast
            ost.codec_context.max_b_frames = 0
            n = 0
            written = 0
            out.start_encoding()  # the muxer picks the stream's real time base (mp4: 1/15360, WebM: 1/1000)
            stb = ost.time_base
            if stb is None:
                raise ValueError("output stream without a time base")
            step = 1 / (fps * stb)

            def mux(packets: Any) -> None:
                # No B-frames (zerolatency / VP9 superframes): packets come in frame order, so
                # frame k is shown at k / fps. Stamping them here keeps every encoder and muxer honest.
                nonlocal written
                for pkt in packets:
                    if pkt.size == 0:
                        continue
                    pkt.pts = pkt.dts = round(written * step)
                    pkt.duration = max(1, round(step))
                    pkt.time_base = stb
                    written += 1
                    out.mux(pkt)

            inp.seek(int(max(0.0, start - 1.0) / tb), stream=ist, backward=True, any_frame=False)
            for frame in inp.decode(ist):
                if frame.pts is None:
                    continue
                t = float(frame.pts * tb)
                if t < start - half:
                    continue
                if t >= end - half:
                    break
                img = frame.reformat(width=ost.width, height=ost.height, format="yuv420p")
                img.pts = n
                img.time_base = ost.time_base
                n += 1
                mux(ost.encode(img))
            mux(ost.encode(None))
            if n == 0:
                raise ValueError(f"no frame in [{start:.3f}, {end:.3f}) s")
