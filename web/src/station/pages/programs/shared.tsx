/** Pieces shared by the three tabs of the programs screen (station-programs.md §8). */
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { HibiMood } from "@/lib/hibi";
import { PALETTE } from "@/hibiscus/sprites.gen";
import { api } from "../../api/client";
import type { TFunction } from "i18next";
import type { OperatorInput, ProgramLogLine, ProgramState } from "../../api/types";
import type { EditorRefs } from "../../programs/blockly/refs";
import { jointName, PROGRAM_DONE } from "../../ws/store";
import { useRuntime } from "../../ws/StationProvider";

/** One colour per joint, in the order of the SO-101 motors (palette colours, both themes). */
export const JOINT_COLOURS = [PALETTE.b, PALETTE.r, PALETTE.g, PALETTE.Y, PALETTE.u, PALETTE.k];

export function jointColour(i: number): string {
  return JOINT_COLOURS[i % JOINT_COLOURS.length] ?? PALETTE.k;
}

export interface JointPlotProps {
  /** Time axis (seconds). When omitted the samples are evenly spaced. */
  t?: number[];
  joints: Record<string, number[]>;
  width?: number;
  height?: number;
  /** Seconds cut at the start / end, drawn as hatched bands (raw time axis). */
  trim?: { start_s: number; end_s: number } | null;
  label: string;
  className?: string;
}

/**
 * Joint positions over time as one SVG polyline per joint (crisp, no canvas). Each joint is
 * scaled on its own range, so small motions stay visible; the gripper (0–100) is drawn the same way.
 */
export function JointPlot({
  t,
  joints,
  width = 240,
  height = 64,
  trim = null,
  label,
  className,
}: JointPlotProps) {
  const names = Object.keys(joints);
  const n = Math.max(0, ...names.map((k) => joints[k]?.length ?? 0));
  const t0 = t?.[0] ?? 0;
  const t1 = t?.[t.length - 1] ?? Math.max(1, n - 1);
  const span = Math.max(1e-6, t1 - t0);
  const x = (k: number) => (((t ? (t[k] ?? t0) : k) - t0) / span) * width;
  const pad = 2;
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      shapeRendering="crispEdges"
    >
      {trim && trim.start_s > 0 ? (
        <rect
          x={0}
          y={0}
          width={(trim.start_s / span) * width}
          height={height}
          className="fill-muted"
          opacity={0.7}
        />
      ) : null}
      {trim && trim.end_s > 0 ? (
        <rect
          x={width - (trim.end_s / span) * width}
          y={0}
          width={(trim.end_s / span) * width}
          height={height}
          className="fill-muted"
          opacity={0.7}
        />
      ) : null}
      {names.map((name, i) => {
        const v = joints[name] ?? [];
        if (v.length === 0) return null;
        const lo = Math.min(...v);
        const hi = Math.max(...v);
        const r = Math.max(1, hi - lo);
        const pts = v
          .map((y, k) => `${x(k).toFixed(1)},${(pad + (1 - (y - lo) / r) * (height - 2 * pad)).toFixed(1)}`)
          .join(" ");
        return (
          <polyline
            key={name}
            data-joint={jointName(name)}
            points={pts}
            fill="none"
            stroke={jointColour(i)}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
    </svg>
  );
}

export function JointLegend({ names }: { names: string[] }) {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
      {names.map((n, i) => (
        <li key={n} className="flex items-center gap-1">
          <span aria-hidden className="inline-block h-2 w-4" style={{ background: jointColour(i) }} />
          {jointName(n)}
        </li>
      ))}
    </ul>
  );
}

/** Hibi on the program run panel: working while it runs, asleep while it waits, sad on a fault/e-stop. */
export function programMood(p: ProgramState | null): HibiMood {
  if (!p) return "idle";
  switch (p.status) {
    case "waiting":
    case "paused":
    case "pausing":
      return "sleep";
    case "failed":
    case "estopped":
    case "timeout":
      return "sad";
    case "completed":
      return "happy";
    case "stopped":
      return "idle";
    default:
      return "working";
  }
}

export function isLive(p: ProgramState | null): boolean {
  return p !== null && !PROGRAM_DONE.includes(p.status);
}

/** Operator input (button / key / answer): WS `program_input` first, REST as the fallback. */
export function useProgramInput(programId: string | null): (ev: OperatorInput) => void {
  const { control } = useRuntime();
  return useCallback(
    (ev) => {
      if (!control.send({ type: "program_input", ...ev }) && programId) {
        void api.post(`/programs/${encodeURIComponent(programId)}/input`, ev).catch(() => undefined);
      }
    },
    [control, programId],
  );
}

export function formatSeconds(s: number): string {
  return `${s.toFixed(s < 10 ? 1 : 0)} s`;
}

/** Program status label key (`programs.status.<status>`). */
export function useStatusLabel(): (s: ProgramState["status"]) => string {
  const { t } = useTranslation("station");
  return (s) => t(`programs.status.${s}`);
}

/**
 * What a block works on, for the run panel (current block, condition values, log): the trajectory,
 * pose or button name, the detector label or the key, so three "camera sees" rows tell red from blue.
 */
export function blockDetail(fields: Record<string, unknown>, refs: EditorRefs): string | null {
  const str = (k: string): string | null => {
    const v = fields[k];
    return typeof v === "string" && v !== "" ? v : null;
  };
  const name = (list: { value: string; label: string }[], v: string | null) =>
    v === null ? null : (list.find((o) => o.value === v)?.label ?? v);
  return (
    name(refs.trajectories, str("TRAJECTORY")) ??
    str("POSE") ??
    name(refs.buttons, str("BUTTON")) ??
    str("LABEL") ??
    str("KEY")?.toUpperCase() ??
    null
  );
}

const OUTCOMES = new Set(["completed", "cancelled", "timeout", "aborted", "failed"]);

/**
 * One run-log line in the operator's language. The Station writes machine text (block ids, kinds,
 * `True`); the line's `kind`, `block_id` and `data` say the same thing in words the screen can
 * translate. User text (log, notify, variables, signals) and fault details are shown as written.
 */
export function logLineText(
  l: Pick<ProgramLogLine, "kind" | "block_id" | "message" | "data">,
  t: TFunction<"station">,
  blockLabel: (id: string) => string,
): string {
  const kind = t(`programs.log_kind.${l.kind}`, { defaultValue: l.kind });
  const block = l.block_id ? blockLabel(l.block_id) : null;
  const d = l.data;
  let body: string;
  switch (l.kind) {
    case "start":
      body = [
        typeof d.version === "number" ? `v${d.version}` : null,
        d.dry_run === true ? t("programs.run.dry") : null,
      ]
        .filter(Boolean)
        .join(" · ");
      break;
    case "block":
      body = block ?? l.message;
      break;
    case "condition": {
      const v = d.value;
      const shown =
        typeof v === "boolean"
          ? t(v ? "programs.run.value_true" : "programs.run.value_false")
          : typeof v === "number" || typeof v === "string"
            ? String(v)
            : typeof d.message === "string"
              ? d.message
              : "?";
      body = `${block ?? "?"} = ${shown}`;
      break;
    }
    case "motion": {
      const o = typeof d.outcome === "string" && OUTCOMES.has(d.outcome) ? d.outcome : "start";
      body = `${block ?? l.message} · ${t(`programs.motion.${o}`)}`;
      break;
    }
    case "timeout":
      body = block ?? l.message;
      break;
    case "input":
      body =
        d.kind === "key" && typeof d.value === "string"
          ? t("programs.run.key", { key: d.value.toUpperCase() })
          : l.message;
      break;
    case "end": {
      const o = typeof d.outcome === "string" ? d.outcome : null;
      body = o ? t(`programs.status.${o}`, { defaultValue: o }) : l.message;
      if ((o === "failed" || o === "timeout") && l.message && l.message !== o) body += ` · ${l.message}`;
      break;
    }
    default:
      body = l.message;
  }
  return body ? `${kind} · ${body}` : kind;
}
