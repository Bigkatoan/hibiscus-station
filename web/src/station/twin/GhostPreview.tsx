/**
 * Ghost preview of a trajectory (Programs → Quỹ đạo): a translucent arm plays the take's stored
 * series (≤ 600 points, the kept part after the trim, at 100 % speed) over the live arm, with a
 * play / pause button and a scrub slider, so the operator sees the motion before running it.
 * Playback is local to the page: nothing is sent to the robot.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Button } from "@/components/ui/button";
import type { TrajectoryDetail } from "../api/types";
import { sampleSeries, toUrdfPose, type JointSeries } from "./mapping";
import { RobotTwin } from "./RobotTwin";
import { useMediaQuery } from "./registry";

/** The kept window [start, end] of a take in series seconds (drafts use the suggested trim). */
export function keptWindow(
  tr: Pick<TrajectoryDetail, "raw_duration_s" | "trim" | "suggested_trim" | "status">,
): {
  start: number;
  end: number;
} {
  const trim = tr.status === "draft" ? tr.suggested_trim : tr.trim;
  const start = Math.max(0, trim.start_s);
  const end = Math.max(start, tr.raw_duration_s - trim.end_s);
  return { start, end };
}

export function GhostPreview({ tr, className }: { tr: TrajectoryDetail; className?: string }) {
  const { t } = useTranslation("station");
  const { start, end } = keptWindow(tr);
  const length = Math.max(0, end - start);
  const [time, setTime] = useState(0);
  // Plays on its own unless the viewer asked for reduced motion (then it waits for Play).
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [playing, setPlaying] = useState(!reduced);
  const series: JointSeries = useMemo(() => ({ t: tr.series.t, joints: tr.series.joints }), [tr.series]);
  const last = useRef<number | null>(null);

  useEffect(() => {
    setTime(0);
    setPlaying(!reduced);
  }, [tr.id, reduced]);

  useEffect(() => {
    if (!playing || length <= 0) return undefined;
    let frame = 0;
    last.current = null;
    const step = (now: number) => {
      const prev = last.current ?? now;
      last.current = now;
      // Loop: the preview restarts after a short hold at the end.
      setTime((x) => {
        const next = x + (now - prev) / 1000;
        return next > length + 0.6 ? 0 : next;
      });
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [playing, length]);

  const shown = Math.min(time, length);
  const ghost = useMemo(() => toUrdfPose(sampleSeries(series, start + shown)), [series, start, shown]);

  return (
    <RobotTwin
      ghost={ghost}
      title={t("twin.ghost_of", { name: tr.name })}
      className={className}
      legend={false}
    >
      <div className="flex items-center gap-2" data-testid="ghost-player">
        <Button
          size="icon"
          variant="outline"
          aria-label={playing ? t("twin.pause") : t("twin.play")}
          onClick={() => {
            if (!playing && time >= length) setTime(0);
            setPlaying(!playing);
          }}
        >
          <PxIcon name={playing ? "pause" : "play"} />
        </Button>
        <input
          type="range"
          min={0}
          max={Math.max(0.01, length)}
          step={0.01}
          value={shown}
          aria-label={t("twin.scrub")}
          className="min-w-0 flex-1 accent-[rgb(var(--primary))]"
          data-testid="ghost-scrub"
          onChange={(e) => {
            setPlaying(false);
            setTime(Number(e.target.value));
          }}
        />
        <span className="shrink-0 text-xs tabular-nums" data-testid="ghost-time">
          {t("twin.time", { t: shown.toFixed(1), total: length.toFixed(1) })}
        </span>
      </div>
    </RobotTwin>
  );
}
