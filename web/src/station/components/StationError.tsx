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

/** Localised Station error from its Problem `code`, with the server `detail` underneath: the exact
 * reason (motor id, register, port, calibration file) is what lets a user or a bug report act on it. */
export function StationError({ error, className }: { error: unknown; className?: string }) {
  const { t } = useTranslation("station");
  if (!error) return null;
  const detail = errorDetail(error);
  return (
    <Alert variant="destructive" className={className}>
      <div className="flex gap-2">
        <PxIcon name="warning" className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <AlertTitle>{errorText(t, error)}</AlertTitle>
          {detail ? (
            <p className="mt-1 break-words font-mono text-xs" data-testid="error-detail">
              {detail}
            </p>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}
