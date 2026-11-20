/**
 * The Station's own lines (status `detail`, an arm's calibration `issue`, a Problem `detail`, an OS
 * error) are English, written for logs and bug reports. The screen never prints them under a
 * translated title (QC 0.2.9 QD-19: "no heartbeat from the UI for 1.0 s" under a Vietnamese
 * banner). The lines the Station is known to write are said in the user's language
 * ({@link serverText}); anything else stays behind a closed "Technical details" ({@link TechDetails}).
 */
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface ServerText {
  /** The line in the user's language, when the Station's wording is known. */
  text: string | null;
  /** What is left to show as technical detail (the whole line when it is not known). */
  raw: string | null;
}

type Rule = (m: RegExpExecArray, t: TFunction<"station">, lng: string) => ServerText;

const arm = (t: TFunction<"station">, a: string | undefined): string =>
  t(`arm.${a ?? "follower"}`, { defaultValue: a ?? "" });

/** Station wordings (hw/owner.py, hw/telemetry.py) and how each one reads on screen. */
const RULES: [RegExp, Rule][] = [
  [
    // hw/owner.py: the dead-man stop
    /^no heartbeat from the UI for ([\d.]+) s$/,
    (m, t, lng) => ({
      text: t("server_text.ui_lost", { s: formatNumber(Number(m[1]), lng, 2) }),
      raw: null,
    }),
  ],
  [
    // hw/telemetry.py: a motor too hot
    /^(follower|leader) (\S+) (-?[\d.]+) °C$/,
    (m, t, lng) => ({
      text: t("server_text.motor_temp", {
        arm: arm(t, m[1]),
        motor: m[2],
        temp: formatNumber(Number(m[3]), lng, 3),
      }),
      raw: null,
    }),
  ],
  [
    // hw/telemetry.py: status register bits
    /^(follower|leader) (\S+) status (.*)$/,
    (m, t) => ({
      text: t("server_text.motor_status", {
        arm: arm(t, m[1]),
        motor: m[2],
        bits: (m[3] ?? "")
          .split(",")
          .filter(Boolean)
          .map((b) => t(`health.bit_${b}`, { defaultValue: b }))
          .join(", "),
      }),
      raw: null,
    }),
  ],
  [
    // hw/telemetry.py: a low supply voltage
    /^(follower|leader) (\S+) (-?[\d.]+) V$/,
    (m, t, lng) => ({
      text: t("server_text.motor_voltage", {
        arm: arm(t, m[1]),
        motor: m[2],
        v: formatNumber(Number(m[3]), lng, 3),
      }),
      raw: null,
    }),
  ],
  [
    // hw/owner.py: an arm without its calibration file
    /^no calibration file (\S+?)(?:; calibration files found(?: for this arm)?: (.+))?$/,
    (m, t) => ({
      text: [t("server_text.no_cal_file"), m[2] ? t("server_text.cal_files_found", { files: m[2] }) : null]
        .filter(Boolean)
        .join(" "),
      raw: m[1] ?? null,
    }),
  ],
  [
    // hw/owner.py: the motors refused the calibration written to them
    /^the motors do not keep the calibration of (\S+) after it was written to them \((.*)\)$/,
    (m, t) => ({ text: t("server_text.cal_not_kept"), raw: `${m[1] ?? ""} (${m[2] ?? ""})` }),
  ],
];

/** One Station line in the user's language, or (unknown wording) only as technical detail. */
export function serverText(t: TFunction<"station">, line: string | null | undefined, lng = "en"): ServerText {
  const raw = (line ?? "").trim();
  if (!raw) return { text: null, raw: null };
  for (const [re, rule] of RULES) {
    const m = re.exec(raw);
    if (m) return rule(m, t, lng);
  }
  return { text: null, raw };
}

/** A closed "Technical details" holding the Station's own line, for a bug report. */
export function TechDetails({
  raw,
  className,
  testid,
}: {
  raw: string | null | undefined;
  className?: string;
  /** test id of the line itself */
  testid?: string;
}) {
  const { t } = useTranslation("station");
  if (!raw) return null;
  return (
    <details className={cn("text-xs", className)} data-testid="tech-details">
      <summary className="cursor-pointer select-none opacity-80">{t("server_text.technical")}</summary>
      <p className="mt-1 break-words font-mono" data-testid={testid}>
        {raw}
      </p>
    </details>
  );
}

/** A Station line: the known wording in words, anything else behind "Technical details". */
export function ServerDetail({
  line,
  className,
  textClassName,
  testid,
}: {
  line: string | null | undefined;
  className?: string;
  textClassName?: string;
  testid?: string;
}) {
  const { t, i18n } = useTranslation("station");
  const { text, raw } = serverText(t, line, i18n.language);
  if (!text && !raw) return null;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)} data-testid={testid}>
      {text ? <p className={cn("break-words text-sm", textClassName)}>{text}</p> : null}
      <TechDetails raw={raw} />
    </div>
  );
}
