import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Mascot } from "@/components/Mascot";
import { Progress } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import type { Session } from "../api/types";
import { fmt } from "../health";
import { useStation } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";

const RUNNING_PHASES = ["countdown", "warmup", "episode", "reset"];

/** Elapsed seconds of the current phase, interpolated locally between 1 Hz session messages. */
export function useElapsed(session: Session | null | undefined): number {
  const ep = session?.episode;
  const [now, setNow] = useState(() => Date.now());
  const [base, setBase] = useState({ elapsed: ep?.elapsed_s ?? 0, at: Date.now() });
  useEffect(() => {
    setBase({ elapsed: ep?.elapsed_s ?? 0, at: Date.now() });
  }, [ep?.elapsed_s, ep?.phase, ep?.index]);
  const running = ep ? ep.phase !== null && RUNNING_PHASES.includes(ep.phase) : Boolean(session);
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => {
      setNow(Date.now());
    }, 200);
    return () => {
      clearInterval(id);
    };
  }, [running]);
  if (!session) return 0;
  if (!ep) return Math.max(0, (now - Date.parse(session.started_at)) / 1000);
  const extra = running ? Math.max(0, (now - base.at) / 1000) : 0;
  const v = base.elapsed + extra;
  return ep.limit_s !== null ? Math.min(v, ep.limit_s) : v;
}

export function formatClock(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

/** Phase header + episode timer with a pixel progress bar (§6.6, §6.9). */
export function SessionTimer({
  session,
  className,
}: {
  session: Session | null | undefined;
  className?: string;
}) {
  const { t } = useTranslation("station");
  const elapsed = useElapsed(session);
  if (!session) return null;
  const ep = session.episode;
  const limit = ep.limit_s ?? null;
  let headline: string;
  if (session.kind === "teleop") headline = t(`session.kind_${session.kind}`);
  else if (ep.phase === "countdown")
    headline = t("session.countdown", { s: Math.max(0, Math.ceil((limit ?? 3) - elapsed)) });
  else if (ep.phase === "reset") headline = t("session.reset", { e: fmt(elapsed, 0), l: limit ?? "∞" });
  else if (ep.phase === "saving") headline = t("session.saving", { n: ep.index + 1 });
  else if (ep.phase === "warmup") headline = t("session.warmup");
  else if (ep.phase === "done") headline = t("session.done");
  else
    headline = t(session.kind === "run" ? "session.episode_run" : "session.episode_rec", {
      n: ep.index + 1,
      of: ep.of,
      e: fmt(elapsed, 1),
      l: limit ?? "∞",
    });
  const pct = limit ? (elapsed / limit) * 100 : 0;
  return (
    <div className={cn("flex flex-col gap-2", className)} data-testid="session-timer">
      <div className="flex items-center gap-3">
        <Mascot
          mood={ep.phase === "saving" ? "working" : ep.phase === "reset" ? "idle" : "working"}
          size="mini"
        />
        <div className="min-w-0 flex-1">
          <p className="font-extrabold text-base" aria-live="polite">
            {headline}
          </p>
          <p className="tabular-nums text-2xl" aria-label={t("session.timer")}>
            {formatClock(elapsed)}
            {limit ? <span className="text-muted-foreground"> / {formatClock(limit)}</span> : null}
          </p>
        </div>
      </div>
      {limit ? <Progress value={pct} aria-label={t("session.timer")} /> : null}
    </div>
  );
}

const selLoop = (s: StationSnapshot) => s.joints?.loop;
const selTick = (s: StationSnapshot) => s.joints?.tick;

export function LoopStats({ targetFps, inference = false }: { targetFps: number; inference?: boolean }) {
  const { t } = useTranslation("station");
  const loop = useStation(selLoop);
  const tick = useStation(selTick);
  const items: [string, string][] = [
    [t("stats.step"), tick !== undefined ? String(tick) : "–"],
    [t("stats.fps"), `${fmt(loop?.fps, 1)} / ${targetFps}`],
    [t("stats.tick_p95"), `${fmt(loop?.tick_ms_p95, 1)} ms`],
  ];
  if (inference) {
    items.push([
      t("stats.inference"),
      `${fmt(loop?.inference_ms_p50, 0)} / ${fmt(loop?.inference_ms_p95, 0)} ms`,
    ]);
  }
  items.push([t("stats.overruns"), loop ? String(loop.overruns) : "–"]);
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm" data-testid="loop-stats">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="text-right tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
