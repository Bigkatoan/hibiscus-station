/**
 * Episode viewer (F-72, FR-77, ADR-14): every camera of a recorded episode, played together, with
 * play / pause, a scrubber and the time cursor of the episode's telemetry chart.
 *
 * Station records AV1 (LeRobot's default). A stock Windows Edge cannot decode AV1 without the Store's
 * "AV1 Video Extension", so each tile asks the Station for the first format this browser says it
 * plays (`canPlayType`): the recorded packets cut to the episode (`source`), else H.264, else VP9
 * (Edge, Chrome and Firefox decode VP9 themselves). A format that still fails falls through to the
 * next one; the tile shows why when none plays. Every format starts at the episode's first frame.
 */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { stationBase } from "../api/client";
import type { EpisodeCamera, EpisodeVideos } from "../api/types";

export type VideoFormat = EpisodeCamera["formats"][number];

const H264 = 'video/mp4; codecs="avc1.42E01E"';
const VP9 = 'video/webm; codecs="vp9"';
/** Server answers that no other format can fix. */
const FINAL = new Set(["video_missing", "no_video", "episode_saving", "not_found", "unauthenticated"]);

/**
 * Formats to try, best first: those the browser says it plays (source, then H.264, then VP9), then
 * the rest (`canPlayType` can be wrong both ways; a failing format falls through to the next).
 */
export function formatOrder(cam: EpisodeCamera, canPlay: (mime: string) => string): VideoFormat[] {
  const mime: Record<VideoFormat, string | null> = { source: cam.mime, h264: H264, vp9: VP9 };
  const wanted: VideoFormat[] = ["source", "h264", "vp9"];
  const offered = wanted.filter((f) => cam.formats.includes(f));
  const yes = offered.filter((f) => {
    const m = mime[f];
    return m !== null && canPlay(m) !== "";
  });
  return [...yes, ...offered.filter((f) => !yes.includes(f))];
}

export function videoUrl(dataset: string, episode: number, camera: string, format: VideoFormat): string {
  const path = `/datasets/${encodeURIComponent(dataset)}/episodes/${String(episode)}/videos/${encodeURIComponent(camera)}`;
  return `${stationBase()}${path}?format=${format}`;
}

function browserCanPlay(mime: string): string {
  if (typeof document === "undefined") return "";
  try {
    return document.createElement("video").canPlayType(mime);
  } catch {
    return "";
  }
}

/** The Problem code behind a failed <video> load (the element itself only says "error"). */
async function problemCode(url: string): Promise<string | null> {
  try {
    const r = await fetch(url, { headers: { Range: "bytes=0-0" }, credentials: "same-origin" });
    if (r.ok) return null;
    const body = (await r.json()) as { code?: unknown };
    return typeof body.code === "string" ? body.code : `http_${String(r.status)}`;
  } catch {
    return null;
  }
}

type TileState = "loading" | "ready" | "error";

interface TileProps {
  dataset: string;
  episode: number;
  cam: EpisodeCamera;
  register: (camera: string, el: HTMLVideoElement | null) => void;
  onReady: (camera: string) => void;
}

function VideoTile({ dataset, episode, cam, register, onReady }: TileProps) {
  const { t } = useTranslation("station");
  const order = useMemo(() => formatOrder(cam, browserCanPlay), [cam]);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<TileState>(cam.error ? "error" : "loading");
  const [code, setCode] = useState<string | null>(cam.error);
  const format = order[attempt];
  const src = format !== undefined && !cam.error ? videoUrl(dataset, episode, cam.camera, format) : undefined;

  const failed = useCallback(() => {
    if (!src) return;
    void problemCode(src).then((c) => {
      if (c !== null && FINAL.has(c)) {
        setCode(c);
        setState("error");
        return;
      }
      if (attempt + 1 < order.length) {
        setAttempt(attempt + 1);
        setState("loading");
      } else {
        setCode(c ?? "unplayable");
        setState("error");
      }
    });
  }, [attempt, order.length, src]);

  const message =
    code === null
      ? ""
      : t(`datasets.video_err_${code}`, {
          defaultValue: t(`errors.${code}`, { defaultValue: t("datasets.video_err_unplayable") }),
        });
  return (
    <figure
      className="relative min-w-0 border-4 border-frame bg-[#1f2340]"
      data-testid={`episode-video-${cam.camera}`}
      data-state={state}
      data-format={state === "error" ? "" : (format ?? "")}
    >
      <div className="relative aspect-[4/3] w-full">
        {src && state !== "error" ? (
          <video
            key={src}
            ref={(el) => {
              register(cam.camera, el);
            }}
            src={src}
            className="absolute inset-0 h-full w-full object-contain"
            muted
            playsInline
            preload="auto"
            aria-label={t("datasets.video_of", { camera: cam.camera })}
            onLoadedData={() => {
              setState("ready");
              onReady(cam.camera);
            }}
            onError={failed}
          />
        ) : null}
        {state === "loading" ? (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-[#c7d3e3]"
            role="status"
          >
            <PxIcon name="spinner" />
            <span className="text-sm">{t("datasets.video_loading")}</span>
          </div>
        ) : null}
        {state === "error" ? (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-3 text-center"
            role="alert"
          >
            <PxIcon name="warning" className="text-[#ffd166]" />
            <span className="bg-[#3b2027] px-2 py-1 text-sm font-extrabold text-[#fff6dc]">{message}</span>
          </div>
        ) : null}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-x-2 bg-[#3b2027] px-2 py-1 text-xs text-[#fff6dc]">
        <span className="font-extrabold text-base">{cam.camera}</span>
        <span>
          {state === "ready" && format
            ? t(`datasets.video_fmt_${format}`, { codec: (cam.codec ?? "").toUpperCase() })
            : ""}
        </span>
      </figcaption>
    </figure>
  );
}

export interface EpisodeClock {
  time: number;
  duration: number;
  playing: boolean;
  seek: (t: number) => void;
}

/**
 * The shared clock: the first camera that plays is the master; the others follow it (re-seeked when
 * they drift more than 0.25 s). With no camera playing, a wall clock drives the chart cursor.
 */
export function EpisodePlayer({
  videos,
  onClock,
  seekRequest,
}: {
  videos: EpisodeVideos;
  onClock: (c: EpisodeClock) => void;
  /** A time to jump to (e.g. a click on the chart); the nonce makes the same time jump again. */
  seekRequest: { t: number; nonce: number } | null;
}) {
  const { t } = useTranslation("station");
  const fps = videos.fps ?? 30;
  const duration = Math.max(videos.length_s ?? 0, ...videos.cameras.map((c) => (c.error ? 0 : c.duration_s)));
  const els = useRef(new Map<string, HTMLVideoElement>());
  const order = useMemo(() => videos.cameras.map((c) => c.camera), [videos.cameras]);
  const ready = useRef(new Set<string>());
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const clock = useRef({ t: 0, at: 0 });
  const timeRef = useRef(0);

  const master = useCallback((): HTMLVideoElement | null => {
    for (const cam of order) {
      const el = els.current.get(cam);
      if (el && ready.current.has(cam)) return el;
    }
    return null;
  }, [order]);

  const show = useCallback((v: number) => {
    timeRef.current = v;
    setTime(v);
  }, []);

  const seek = useCallback(
    (v: number) => {
      const to = Math.min(Math.max(0, v), duration);
      clock.current = { t: to, at: performance.now() };
      for (const el of els.current.values()) {
        try {
          el.currentTime = to;
        } catch {
          /* not loaded yet: it is synced on loadeddata */
        }
      }
      show(to);
    },
    [duration, show],
  );

  const pauseAll = useCallback(() => {
    for (const el of els.current.values()) {
      try {
        el.pause();
      } catch {
        /* jsdom / not loaded */
      }
    }
  }, []);

  const playAll = useCallback(() => {
    for (const el of els.current.values()) {
      try {
        void Promise.resolve(el.play()).catch(() => undefined);
      } catch {
        /* jsdom / not loaded */
      }
    }
  }, []);

  const toggle = useCallback(() => {
    if (playing) {
      pauseAll();
      clock.current = { t: timeRef.current, at: performance.now() };
      setPlaying(false);
      return;
    }
    if (timeRef.current >= duration - 0.5 / fps) seek(0);
    clock.current = { t: timeRef.current, at: performance.now() };
    playAll();
    setPlaying(true);
  }, [duration, fps, pauseAll, playAll, playing, seek]);

  // The play loop: read the master, keep the others on it, stop at the end.
  useEffect(() => {
    if (!playing) return undefined;
    let raf = 0;
    let shownAt = 0;
    const step = (now: number) => {
      const m = master();
      let v = m ? m.currentTime : clock.current.t + (now - clock.current.at) / 1000;
      const end = v >= duration - 0.5 / fps || Boolean(m?.ended);
      if (end) v = duration;
      for (const el of els.current.values()) {
        if (el !== m && !end && Math.abs(el.currentTime - v) > 0.25) {
          try {
            el.currentTime = v;
          } catch {
            /* not seekable yet */
          }
        }
      }
      if (end) {
        pauseAll();
        show(v);
        setPlaying(false);
        return;
      }
      if (now - shownAt > 66) {
        shownAt = now;
        show(v);
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [duration, fps, master, pauseAll, playing, show]);

  useEffect(() => {
    if (seekRequest) seek(seekRequest.t);
  }, [seek, seekRequest]);

  useEffect(() => {
    onClock({ time, duration, playing, seek });
  }, [duration, onClock, playing, seek, time]);

  const register = useCallback((camera: string, el: HTMLVideoElement | null) => {
    if (el) els.current.set(camera, el);
    else {
      els.current.delete(camera);
      ready.current.delete(camera);
    }
  }, []);

  const onReady = useCallback(
    (camera: string) => {
      ready.current.add(camera);
      const el = els.current.get(camera);
      if (!el) return;
      try {
        el.currentTime = timeRef.current;
        if (playing) void Promise.resolve(el.play()).catch(() => undefined);
      } catch {
        /* jsdom */
      }
    },
    [playing],
  );

  if (videos.cameras.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("datasets.video_none")}</p>;
  }
  if (videos.cameras.every((c) => c.error === "no_video")) {
    // recorded with video encoding off (QV-5): one sentence, no empty tiles
    return (
      <p className="text-sm text-muted-foreground" data-testid="episode-no-video">
        {t("datasets.video_err_no_video")}
      </p>
    );
  }
  return (
    <section
      className="flex flex-col gap-2"
      aria-label={t("datasets.video_title", { n: videos.episode + 1 })}
      data-testid="episode-player"
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {videos.cameras.map((cam) => (
          <VideoTile
            key={`${videos.dataset}/${String(videos.episode)}/${cam.camera}`}
            dataset={videos.dataset}
            episode={videos.episode}
            cam={cam}
            register={register}
            onReady={onReady}
          />
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          aria-label={playing ? t("datasets.video_pause") : t("datasets.video_play")}
          data-testid="episode-play"
          onClick={toggle}
        >
          <PxIcon name={playing ? "pause" : "play"} />
        </Button>
        <input
          type="range"
          min={0}
          max={Math.max(0.01, duration)}
          step={1 / fps}
          value={Math.min(time, duration)}
          aria-label={t("datasets.video_scrub")}
          aria-valuetext={t("datasets.video_time", { t: time.toFixed(1), d: duration.toFixed(1) })}
          className="min-w-0 flex-1 accent-[rgb(var(--primary))]"
          data-testid="episode-scrub"
          onChange={(e) => {
            if (playing) {
              pauseAll();
              setPlaying(false);
            }
            seek(Number(e.target.value));
          }}
        />
        <span className="shrink-0 text-xs tabular-nums" data-testid="episode-time">
          {t("datasets.video_time", { t: time.toFixed(1), d: duration.toFixed(1) })}
        </span>
      </div>
    </section>
  );
}
