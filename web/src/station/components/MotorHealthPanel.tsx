/**
 * MotorHealthPanel (R1, §6.0): per arm, motor × {temp, V, A, load, status}. Temperature cells are
 * coloured ok/warn/hot/critical with the thermometer sprite; the large variant adds 120 s
 * sparklines with the thresholds drawn as dashed lines, and the limits read from the motors.
 */
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useSettings } from "../api/hooks";
import type { Arm, MotorLimits, MotorSample } from "../api/types";
import { DEFAULT_THRESHOLDS, fmt, levelCss, motorLevel, type Thresholds } from "../health";
import { useStation } from "../ws/StationProvider";
import type { Series, StationSnapshot } from "../ws/store";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { svgNum } from "../units";

export function useThresholds(): Thresholds {
  const settings = useSettings();
  return settings.data?.thresholds ?? DEFAULT_THRESHOLDS;
}

const selTelemetry = (s: StationSnapshot) => s.telemetry;
const selLimits = (s: StationSnapshot) => s.limits;
const selTempHist = (s: StationSnapshot) => s.tempHist;

export function Sparkline({
  series,
  thresholds,
  width = 120,
  height = 28,
  maxTemp = 75,
}: {
  series: Series | undefined;
  thresholds: Thresholds;
  width?: number;
  height?: number;
  maxTemp?: number;
}) {
  const lo = 20;
  const hi = Math.max(maxTemp, thresholds.temp_critical_c + 5);
  const y = (v: number) => height - ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * height;
  const ts = series?.t ?? [];
  const t1 = ts[ts.length - 1] ?? 0;
  const t0 = t1 - 120;
  const x = (t: number) => ((t - t0) / 120) * width;
  const pts = ts
    .map((t, i) => {
      const v = series?.v[i];
      return v === null || v === undefined ? null : `${svgNum(x(t))},${svgNum(y(v))}`;
    })
    .filter((p): p is string => p !== null)
    .join(" ");
  const lines: [number, string][] = [
    [thresholds.temp_warn_c, "#ffc531"],
    [thresholds.temp_hot_c, "#f08a24"],
    [thresholds.temp_critical_c, "#d7263d"],
  ];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      className="block"
      shapeRendering="crispEdges"
    >
      {lines.map(([v, c]) => (
        <line
          key={v}
          x1={0}
          x2={width}
          y1={y(v)}
          y2={y(v)}
          stroke={c}
          strokeWidth={1}
          strokeDasharray="3 2"
        />
      ))}
      {pts ? <polyline points={pts} fill="none" stroke="currentColor" strokeWidth={2} /> : null}
    </svg>
  );
}

function LoadBar({ pct }: { pct: number | null }) {
  const v = pct === null ? 0 : Math.min(100, Math.abs(pct));
  const warn = v >= 90;
  return (
    <span className="inline-flex items-center gap-1">
      <span className="relative inline-block h-2 w-10 border-2 border-frame bg-muted" aria-hidden>
        <span
          className="absolute inset-y-0 left-0"
          style={{ width: `${v}%`, backgroundColor: warn ? "#f08a24" : "#2f6f9f" }}
        />
      </span>
      <span className="tabular-nums">{fmt(pct, 0)}</span>
    </span>
  );
}

/** A value the leader's servos never report: "not measured" with the reason as a tooltip. */
function NotMeasured() {
  const { t } = useTranslation("station");
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-muted-foreground"
      title={t("health.not_measured_title")}
      data-testid="not-measured"
    >
      <PxIcon name="info" />
      {t("health.not_measured")}
      <span className="sr-only">{t("health.not_measured_title")}</span>
    </span>
  );
}

function MotorRow({
  arm,
  motor,
  s,
  thresholds,
  large,
  series,
  maxTemp,
}: {
  arm: Arm;
  motor: string;
  s: MotorSample;
  thresholds: Thresholds;
  large: boolean;
  series: Series | undefined;
  maxTemp: number;
}) {
  const { t } = useTranslation("station");
  const level = motorLevel(s, thresholds, arm);
  // Field report 0.2.8: the leader's 5 V servos report no temperature / current. A bare "–" read
  // as "leader not recognised"; say what it is instead.
  const leaderUnmeasured = (v: number | null) => arm === "leader" && v === null && !s.stale;
  return (
    <tr
      data-testid={`motor-${arm}-${motor}`}
      data-level={level}
      className={cn("border-b border-frame/30", s.stale && "opacity-60")}
    >
      <th scope="row" className="max-w-[7rem] truncate py-1 pr-2 text-left font-normal">
        {motor}
      </th>
      <td className="py-1 pr-2">
        {leaderUnmeasured(s.temp_c) ? (
          <NotMeasured />
        ) : (
          <span
            className="inline-flex min-w-[4.5rem] items-center gap-1 border-2 px-1 tabular-nums"
            style={levelCss(level)}
            title={t(`level.${level}`)}
          >
            <PxIcon name="thermo" />
            {fmt(s.temp_c, 0)}°C
            <span className="sr-only">{t(`level.${level}`)}</span>
          </span>
        )}
      </td>
      <td
        className="py-1 pr-2 tabular-nums"
        title={s.voltage_v === null && arm !== "leader" ? t("health.unknown_title") : undefined}
      >
        {leaderUnmeasured(s.voltage_v) ? <NotMeasured /> : fmt(s.voltage_v, 1)}
      </td>
      <td
        className="hidden py-1 pr-2 tabular-nums sm:table-cell"
        title={s.current_a === null && arm !== "leader" ? t("health.unknown_title") : undefined}
      >
        {leaderUnmeasured(s.current_a) ? <NotMeasured /> : fmt(s.current_a, 2)}
      </td>
      <td className="py-1 pr-2">
        <LoadBar pct={s.load_pct} />
      </td>
      <td className="py-1 pr-2">
        {s.status.length === 0 ? (
          <span className="text-muted-foreground">{t("health.status_ok")}</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {s.status.map((b) => (
              <span key={b} className="px-notch bg-destructive px-1 text-xs text-destructive-foreground">
                {t(`health.bit_${b}`, { defaultValue: b })}
              </span>
            ))}
          </span>
        )}
        {s.stale ? (
          <span
            className="ml-1 text-xs text-muted-foreground"
            title={t("health.stale_title")}
            data-testid="stale"
          >
            {t("health.stale")}
          </span>
        ) : null}
      </td>
      {large ? (
        <td className="py-1 text-foreground">
          <Sparkline series={series} thresholds={thresholds} maxTemp={maxTemp} />
        </td>
      ) : null}
    </tr>
  );
}

function limitsText(t: TFunction<"station">, l: MotorLimits | undefined): string | null {
  if (!l) return null;
  const parts: string[] = [];
  if (l.max_temp_c !== null) parts.push(t("health.limit_temp", { v: l.max_temp_c }));
  if (l.min_voltage_v !== null) parts.push(t("health.limit_vmin", { v: l.min_voltage_v }));
  const currents = Object.values(l.protection_current_a);
  if (currents.length) parts.push(t("health.limit_current", { v: Math.min(...currents) }));
  return parts.join(" · ");
}

export function MotorHealthPanel({
  arms,
  variant = "compact",
  className,
}: {
  arms?: Arm[];
  variant?: "compact" | "large";
  className?: string;
}) {
  const { t } = useTranslation("station");
  const telemetry = useStation(selTelemetry);
  const limits = useStation(selLimits);
  const tempHist = useStation(selTempHist);
  const thresholds = useThresholds();
  const shown = (arms ?? (["follower", "leader"] as Arm[])).filter((a) => telemetry[a]);
  const large = variant === "large";

  return (
    <section
      aria-label={t("health.title")}
      className={cn("flex flex-col gap-3", className)}
      data-testid="motor-health"
    >
      {shown.length === 0 ? <p className="text-sm text-muted-foreground">{t("health.no_data")}</p> : null}
      {shown.map((arm) => {
        const motors = telemetry[arm] ?? {};
        const lim = limitsText(t, limits[arm]);
        return (
          <div key={arm} className="min-w-0">
            <h3 className="mb-1 flex flex-wrap items-center gap-2 font-extrabold text-base">
              {t(`arm.${arm}`)}
              {arm === "leader" ? (
                <span
                  className="border-2 px-1 text-xs font-bold"
                  style={levelCss("ok")}
                  data-testid="leader-connected"
                >
                  {t("health.leader_connected", {
                    n: Object.values(motors).filter((m) => !m.stale).length,
                    total: Object.keys(motors).length,
                  })}
                </span>
              ) : null}
            </h3>
            {arm === "leader" ? (
              <p className="mb-1 text-xs text-muted-foreground" data-testid="leader-note">
                {t("health.leader_note")}
              </p>
            ) : null}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b-2 border-frame text-left text-xs text-muted-foreground">
                    <th scope="col" className="pr-2 font-normal">
                      {t("health.motor")}
                    </th>
                    <th scope="col" className="pr-2 font-normal">
                      {t("health.temp")}
                    </th>
                    <th scope="col" className="pr-2 font-normal">
                      {t("health.voltage")}
                    </th>
                    <th scope="col" className="hidden pr-2 font-normal sm:table-cell">
                      {t("health.current")}
                    </th>
                    <th scope="col" className="pr-2 font-normal">
                      {t("health.load")}
                    </th>
                    <th scope="col" className="pr-2 font-normal">
                      {t("health.status")}
                    </th>
                    {large ? (
                      <th scope="col" className="font-normal">
                        {t("health.history")}
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(motors).map(([motor, s]) => (
                    <MotorRow
                      key={motor}
                      arm={arm}
                      motor={motor}
                      s={s}
                      thresholds={thresholds}
                      large={large}
                      series={tempHist[arm]?.[motor]}
                      maxTemp={limits[arm]?.max_temp_c ?? 70}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {large && lim ? <p className="mt-1 text-xs text-muted-foreground">{lim}</p> : null}
          </div>
        );
      })}
      {large ? (
        <p className="text-xs text-muted-foreground">
          {t("health.thresholds", {
            warn: thresholds.temp_warn_c,
            hot: thresholds.temp_hot_c,
            critical: thresholds.temp_critical_c,
          })}
        </p>
      ) : null}
    </section>
  );
}
