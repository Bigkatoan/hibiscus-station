/**
 * Safety banners (§6.0): critical (red, full width, not dismissable while it holds), hot
 * (orange, sticky), reconnecting, other active alerts, and Hibi's speech bubble for warnings.
 */
import type { TFunction } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Mascot } from "@/components/Mascot";
import { PxIcon, Sprite } from "@/hibiscus/PixelAnim";
import type { AlertMsg, Status } from "../api/types";
import { DEFAULT_THRESHOLDS, coolingEtaS, levelCss } from "../health";
import { useStation } from "../ws/StationProvider";
import { DeviceLostBanner } from "./DeviceLost";
import { RestBanner } from "./RestBanner";
import type { StationSnapshot } from "../ws/store";

const THERMAL_REASONS = ["thermal", "electrical"];

export interface CriticalInfo {
  motor: string | null;
  arm: string | null;
  value: number | null;
  reason: string;
}

/** The critical condition to show, if any: a critical alert, or a thermal/electrical latch. */
export function criticalInfo(status: Status | null, alerts: readonly AlertMsg[]): CriticalInfo | null {
  const a = alerts.find((x) => x.level === "critical");
  if (a) return { motor: a.motor ?? null, arm: a.arm ?? null, value: a.value ?? null, reason: a.kind };
  if (status?.state === "estopped" && THERMAL_REASONS.includes(status.reason ?? "")) {
    const h = status.health.hottest;
    return {
      motor: h?.motor ?? null,
      arm: h?.arm ?? null,
      value: h?.temp_c ?? null,
      reason: status.reason ?? "",
    };
  }
  return null;
}

function alertText(t: TFunction<"station">, a: AlertMsg): string {
  return t(`alerts.${a.message_key}`, {
    ...a.params,
    motor: a.motor ?? a.params.motor,
    camera: a.camera ?? a.params.camera,
    value: a.value ?? a.params.value,
    defaultValue: t(`alerts.kind_${a.kind}`, { defaultValue: a.message_key }),
  });
}

const selAlerts = (s: StationSnapshot) => s.alerts;
const selConn = (s: StationSnapshot) => s.conn;
const selStatus = (s: StationSnapshot) => s.status;
const selTempHist = (s: StationSnapshot) => s.tempHist;

export function SafetyBanners() {
  const { t } = useTranslation("station");
  const alerts = useStation(selAlerts);
  const conn = useStation(selConn);
  const status = useStation(selStatus);
  const tempHist = useStation(selTempHist);
  const [dismissed, setDismissed] = useState<string[]>([]);

  const critical = criticalInfo(status, alerts);
  // A hot leader (moved by hand, torque off) never blocks a start: no "cannot start" banner for it.
  const hot = alerts.find((a) => a.level === "hot" && a.arm !== "leader");
  const warns = alerts.filter(
    (a) => a.level === "warn" && a.kind === "temperature" && !dismissed.includes(a.id),
  );
  const others = alerts.filter(
    (a) =>
      !(a.kind === "temperature" && a.level !== "info") &&
      a.level !== "critical" &&
      !dismissed.includes(a.id),
  );

  let eta: number | null = null;
  if (critical?.motor && critical.arm) {
    const h = tempHist[critical.arm as "follower" | "leader"]?.[critical.motor];
    if (h) eta = coolingEtaS(h.t, h.v, DEFAULT_THRESHOLDS.temp_hot_c);
  }

  return (
    <div className="flex flex-col gap-2">
      {conn !== "open" ? (
        <div
          role="status"
          className="flex items-center gap-2 border-2 border-frame bg-muted px-3 py-2 text-sm"
        >
          <PxIcon name="wifi_off" />
          {t(conn === "connecting" ? "banner.connecting" : "banner.reconnecting")}
        </div>
      ) : null}
      {critical ? (
        <div
          role="alert"
          data-testid="critical-banner"
          className="flex items-start gap-3 border-4 px-3 py-3"
          style={levelCss("critical")}
        >
          <Sprite name="icon_thermo_critical" className="mt-0.5" />
          <div className="min-w-0">
            <p className="font-extrabold">
              {critical.motor
                ? t("banner.critical", { motor: critical.motor, value: critical.value ?? "?" })
                : t("banner.critical_generic", {
                    reason: t(`reasons.${critical.reason}`, { defaultValue: critical.reason }),
                  })}
            </p>
            <p className="mt-1 text-sm">
              {status?.robot?.follower_torque === true ? t("banner.stopped_hold") : t("banner.support_arm")}
            </p>
            {eta !== null ? <p className="mt-1 text-sm">{t("banner.cooling_eta", { s: eta })}</p> : null}
          </div>
        </div>
      ) : null}
      {status?.state === "error" && status.reason === "device_lost" ? (
        <DeviceLostBanner status={status} />
      ) : null}
      {!critical &&
      status &&
      status.reason !== "device_lost" &&
      (status.state === "error" || (status.state === "estopped" && status.detail)) ? (
        <div
          role="alert"
          data-testid="state-banner"
          className="flex items-start gap-3 border-4 px-3 py-3"
          style={levelCss(status.state === "error" ? "critical" : "hot")}
        >
          <PxIcon name="warning" className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="font-extrabold">
              {t(status.state === "error" ? "banner.error" : "banner.estopped", {
                reason: t(`reasons.${status.reason ?? "internal"}`, { defaultValue: status.reason ?? "" }),
              })}
            </p>
            {status.detail ? <p className="mt-1 break-words font-mono text-xs">{status.detail}</p> : null}
          </div>
        </div>
      ) : null}
      {status ? <RestBanner status={status} /> : null}
      {!critical && hot ? (
        <div
          role="alert"
          data-testid="hot-banner"
          className="flex items-center gap-3 border-4 px-3 py-2"
          style={levelCss("hot")}
        >
          <Sprite name="icon_thermo_hot" />
          <p className="text-sm font-bold">
            {t("banner.hot", { motor: hot.motor ?? "?", value: hot.value ?? "?" })}
          </p>
        </div>
      ) : null}
      {others.map((a) => (
        <div
          key={a.id}
          role="status"
          className="flex items-center gap-2 border-2 border-l-8 border-frame bg-card px-3 py-2 text-sm"
          style={{ borderLeftColor: levelCss(a.level === "info" ? "ok" : a.level).backgroundColor }}
        >
          <span className="min-w-0 flex-1">{alertText(t, a)}</span>
          <button
            type="button"
            className="p-1"
            aria-label={t("common.dismiss")}
            onClick={() => {
              setDismissed((d) => [...d, a.id]);
            }}
          >
            <PxIcon name="close" />
          </button>
        </div>
      ))}
      {warns.length > 0 && !critical ? (
        <HibiSpeech
          text={t("banner.warm", { motor: warns[0]?.motor ?? "?", value: warns[0]?.value ?? "?" })}
          onDismiss={() => {
            setDismissed((d) => [...d, ...warns.map((w) => w.id)]);
          }}
        />
      ) : null}
    </div>
  );
}

/** Hibi with a speech bubble (HibiAlert). A warm robot wilts: "hot" shows the sad (drooping) Hibi. */
export function HibiSpeech({
  text,
  onDismiss,
  mood = "hot",
}: {
  text: string;
  onDismiss?: () => void;
  mood?: "hot" | "idle";
}) {
  const { t } = useTranslation("station");
  return (
    <div role="status" data-testid="hibi-alert" className="flex items-end justify-end gap-2">
      <div className="px-panel-sm relative max-w-xs bg-card px-3 py-2 text-sm">
        {text}
        {onDismiss ? (
          <button
            type="button"
            className="ml-2 align-middle"
            aria-label={t("common.dismiss")}
            onClick={onDismiss}
          >
            <PxIcon name="close" className="inline" />
          </button>
        ) : null}
      </div>
      <Mascot mood={mood === "hot" ? "sad" : "idle"} size="mini" />
    </div>
  );
}
