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

/** Localised Station error from its Problem `code` (never the server `detail`). */
export function StationError({ error, className }: { error: unknown; className?: string }) {
  const { t } = useTranslation("station");
  if (!error) return null;
  return (
    <Alert variant="destructive" className={className}>
      <div className="flex gap-2">
        <PxIcon name="warning" className="mt-0.5 shrink-0" />
        <AlertTitle>{errorText(t, error)}</AlertTitle>
      </div>
    </Alert>
  );
}
