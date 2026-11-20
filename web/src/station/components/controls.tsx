import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Progress } from "@/components/ui/misc";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { useRuntime, useStation } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";
import { fmtFixed, fmtSize } from "../units";

/** Peak joint speed of "Align follower to leader" and "Return to rest pose" (the Station's cap). */
export const AUTO_MOVE_SPEED_DEG_S = 30;

/** Session control (next / rerecord / stop): WS first (no HTTP round trip), REST fallback. */
export function useSessionControl(): (action: "next" | "rerecord" | "stop") => void {
  const { control } = useRuntime();
  return useCallback(
    (action) => {
      if (!control.send({ type: "control", action })) {
        void api.post("/sessions/current/control", { action }).catch(() => undefined);
      }
    },
    [control],
  );
}

/** True while a critical condition holds (critical alert active or thermal/electrical latch). */
export function useCritical(): boolean {
  return useStation(
    (s: StationSnapshot) =>
      s.alerts.some((a) => a.level === "critical") ||
      (s.status?.state === "estopped" && ["thermal", "electrical"].includes(s.status.reason ?? "")),
  );
}

/** Display a loosely typed job result value. */
export function scalar(v: unknown): string {
  return typeof v === "string" || typeof v === "number" || typeof v === "boolean" ? String(v) : "?";
}

/** Sizes read the same everywhere (QC 0.2.9 QD-21): see units.ts. */
export const formatBytes = fmtSize;

/** Progress of one job (upload / pull / import / load) with its phase. */
export function JobProgress({ job }: { job: Job }) {
  const { t } = useTranslation("station");
  const p = job.progress;
  const pct = p.total > 0 ? (p.done / p.total) * 100 : job.status === "succeeded" ? 100 : 0;
  return (
    <div className="flex flex-col gap-1" data-testid={`job-${job.id}`} data-status={job.status}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          {t(`jobs.kind_${job.kind}`)} · {t(`jobs.status_${job.status}`)}
          {` · ${t(`jobs.phase_${p.phase}`, { defaultValue: p.phase })}`}
        </span>
        <span className="tabular-nums text-xs">
          {p.unit === "bytes" ? `${formatBytes(p.done)} / ${formatBytes(p.total)}` : `${p.done} / ${p.total}`}{" "}
          · {fmtFixed(pct, 0)}%
        </span>
      </div>
      <Progress value={pct} aria-label={t(`jobs.kind_${job.kind}`)} />
      {job.error ? (
        <p className="text-sm text-destructive">
          {t(`errors.${job.error.code}`, { defaultValue: t("errors.unknown_error") })}
        </p>
      ) : null}
    </div>
  );
}

/** Latest job of a kind for a subject (dataset name / model key), from the live store. */
export function useLatestJob(kind: Job["kind"], subject?: string | null): Job | null {
  const jobs = useStation((s: StationSnapshot) => s.jobs);
  const list = Object.values(jobs).filter(
    (j) => j.kind === kind && (subject === undefined || j.subject === subject || subject === null),
  );
  return list[list.length - 1] ?? null;
}
