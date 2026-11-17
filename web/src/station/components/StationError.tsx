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
