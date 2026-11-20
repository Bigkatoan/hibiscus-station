import { PxIcon } from "@/hibiscus/PixelAnim";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Alert, AlertTitle } from "@/components/ui/misc";
import { StationApiError } from "../api/client";

export function errorText(t: TFunction<"station">, error: unknown): string {
  if (error instanceof StationApiError) {
    const params: Record<string, unknown> = { ...error.params };
    for (const [k, v] of Object.entries(params)) {
      if (Array.isArray(v)) params[k] = v.join(", ");
      else if (typeof v === "object" && v !== null)
        params[k] = Object.entries(v)
          .map(([name, x]) => `${name} ${String(x)}`)
          .join(", ");
    }
    return t(`errors.${error.code}`, { ...params, defaultValue: t("errors.unknown_error") });
  }
  return t("errors.unknown_error");
}

/** The server's own explanation (which motor, which port, which file), when it says more than the code. */
export function errorDetail(error: unknown): string | null {
  if (!(error instanceof StationApiError))
    return error instanceof Error && error.message ? error.message : null;
  const problem = error.problem;
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
 * sight: hiding it hid the reason (QD-44).
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
