import { PxIcon } from "@/hibiscus/PixelAnim";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Alert, AlertTitle } from "@/components/ui/misc";
import { StationApiError } from "../api/client";

/** One Problem param as words. A motor ({arm, motor, temp_c}, as in `motor_hot`) reads
 * "follower elbow_flex 66 °C" (QC 0.2.9 QD-3: a list of them showed "[object Object]"). */
function paramText(v: unknown): string {
  if (Array.isArray(v)) return v.map(paramText).join(", ");
  if (typeof v !== "object" || v === null) return String(v);
  const o = v as Record<string, unknown>;
  if (typeof o.motor === "string") {
    const temp = typeof o.temp_c === "number" ? `${Math.round(o.temp_c)} °C` : null;
    return [o.arm, o.motor, temp].filter((x) => typeof x === "string" && x).join(" ");
  }
  return Object.entries(o)
    .map(([name, x]) => `${name} ${paramText(x)}`)
    .join(", ");
}

export function errorText(t: TFunction<"station">, error: unknown): string {
  if (error instanceof StationApiError) {
    const params: Record<string, unknown> = { ...error.params };
    for (const [k, v] of Object.entries(params)) {
      if (typeof v === "object" && v !== null) params[k] = paramText(v);
    }
    return t(`errors.${error.code}`, { ...params, defaultValue: t("errors.unknown_error") });
  }
  return t("errors.unknown_error");
}

/** Codes whose localised text already says everything the server detail says (in English). */
const SELF_EXPLAINED = new Set(["motor_hot"]);

/** The server's own explanation (which motor, which port, which file), when it says more than the code. */
export function errorDetail(error: unknown): string | null {
  if (!(error instanceof StationApiError))
    return error instanceof Error && error.message ? error.message : null;
  const problem = error.problem;
  if (SELF_EXPLAINED.has(error.code) && Object.keys(error.params).length > 0) return null;
  if (!problem && error.status > 0) return `HTTP ${error.status}${error.raw ? `: ${error.raw}` : ""}`;
  const raw: unknown = problem?.detail; // a hand-written Problem may lack it
  const detail = typeof raw === "string" ? raw.trim() : "";
  if (!detail || detail === problem?.title || detail === error.code) return null;
  return detail;
}

/**
 * Codes whose own sentence fully explains the error: their Station `detail` (English, machine
 * words) goes into the closed "Technical details" (FR-73, P-5; QC F029 QD-39). Every other code,
 * the generic `validation_failed` first (52 places, each with its own reason), keeps the detail in
 * sight: hiding it hid the reason (QD-44). The dataset codes of 0.2.10 (D-2) say what happened and
 * that the files are kept; their detail is the file or OS error (QC 0.2.10). `dataset_not_finalized`
 * keeps its detail in sight: its sentence alone does not say which files are open.
 */
export const SELF_EXPLAINING = new Set([
  "server_url_invalid",
  "server_url_file_share",
  "server_url_insecure",
  "server_not_hibiscus",
  "server_unauthorized",
  "token_format_invalid",
  "token_missing_scope",
  "workspace_required",
  "dataset_unreadable",
  "dataset_io_error",
  // F-72 (QV-6): the episode viewer's sentences say all there is
  "episode_saving",
  "video_missing",
  "video_unavailable",
  "no_video",
]);

/** True when the UI's sentence for this error says all there is to say. */
export function selfExplaining(error: unknown): boolean {
  return error instanceof StationApiError && SELF_EXPLAINING.has(error.code);
}

/**
 * Localised Station error from its Problem `code`, with the server's own `detail` (motor id,
 * register, port, calibration file) that lets a user or a bug report act on it: in sight, or in a
 * closed "Technical details" when the sentence already says everything.
 */
export function StationError({ error, className }: { error: unknown; className?: string }) {
  const { t } = useTranslation("station");
  if (!error) return null;
  const detail = errorDetail(error);
  const known = selfExplaining(error);
  return (
    <Alert variant="destructive" className={className}>
      <div className="flex gap-2">
        <PxIcon name="warning" className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <AlertTitle>{errorText(t, error)}</AlertTitle>
          {detail && known ? (
            <details className="mt-1 text-xs" data-testid="error-details">
              <summary className="cursor-pointer select-none">{t("common.technical_details")}</summary>
              <p className="mt-1 break-words font-mono" data-testid="error-detail">
                {detail}
              </p>
            </details>
          ) : detail ? (
            <p className="mt-1 break-words font-mono text-xs" data-testid="error-detail">
              {detail}
            </p>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}
