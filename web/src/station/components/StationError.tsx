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

/** True when the UI has its own sentence for this error's `code`. */
export function knownError(exists: (key: string) => boolean, error: unknown): boolean {
  return error instanceof StationApiError && Boolean(error.code) && exists(`station:errors.${error.code}`);
}

/**
 * Localised Station error from its Problem `code`. The server's own `detail` (motor id, register,
 * port, calibration file: English, machine words) is what lets an engineer or a bug report act on
 * it: for a code the UI knows it sits in a closed "Technical details" (FR-73, P-5; QC F029 QD-39),
 * only an error the UI has no sentence for shows it right away.
 */
export function StationError({ error, className }: { error: unknown; className?: string }) {
  const { t, i18n } = useTranslation("station");
  if (!error) return null;
  const detail = errorDetail(error);
  const known = knownError((k) => i18n.exists(k), error);
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
