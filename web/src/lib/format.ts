/** Locale-aware formatting helpers (pure; locale passed explicitly so they are testable). */
import { safeLocale } from "./locale";

const UNITS = ["B", "KiB", "MiB", "GiB", "TiB"] as const;

export function formatBytes(bytes: number | null | undefined, locale = "en"): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return "—";
  let value = bytes;
  let unit = 0;
  while (Math.abs(value) >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : value < 10 ? 2 : value < 100 ? 1 : 0;
  return `${new Intl.NumberFormat(safeLocale(locale), { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(value)} ${UNITS[unit] ?? "B"}`;
}

const SIZE_UNITS = ["B", "kB", "MB", "GB", "TB", "PB"] as const;

/**
 * A size people read: decimal kB / MB / GB (what a disk or a file manager says), one decimal under
 * 10 and none above, so it never reads "0.00 GiB" for a few megabytes (QC 0.2.9 QD-21).
 */
export function formatSize(bytes: number | null | undefined, locale = "en"): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "—";
  let unit = 0;
  let value = bytes;
  while (value >= 1000 && unit < SIZE_UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  let digits = unit === 0 || value >= 10 ? 0 : 1;
  // 999.7 kB rounds to "1,000 kB": say "1 MB" instead
  if (Number(value.toFixed(digits)) >= 1000 && unit < SIZE_UNITS.length - 1) {
    value /= 1000;
    unit += 1;
    digits = 1;
  }
  const n = new Intl.NumberFormat(safeLocale(locale), { maximumFractionDigits: digits }).format(value);
  return `${n} ${SIZE_UNITS[unit] ?? "B"}`;
}

/** A number of seconds (or any measured value) with fixed decimals in the user's locale: "1.5" / "1,5". */
export function formatFixed(value: number | null | undefined, locale = "en", digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(safeLocale(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

interface DurationUnits {
  d: string;
  h: string;
  m: string;
  s: string;
  sep: string;
}
const EN_UNITS: DurationUnits = { d: "d", h: "h", m: "m", s: "s", sep: "" };
const DURATION_UNITS: Record<string, DurationUnits> = {
  en: EN_UNITS,
  vi: { d: "ngày", h: "giờ", m: "phút", s: "giây", sep: " " },
};

/**
 * Duration in seconds, two largest units. en: "1h 02m", "3m 05s", "42s";
 * vi: "1 giờ 2 phút", "3 phút 5 giây", "42 giây" (CX-08).
 */
export function formatDuration(seconds: number | null | undefined, locale = "en"): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.round(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const lang = locale.slice(0, 2).toLowerCase();
  const u = DURATION_UNITS[lang] ?? EN_UNITS;
  // English keeps the compact zero-padded form; spelled-out units read better unpadded.
  const pad = (n: number) => (u.sep ? String(n) : String(n).padStart(2, "0"));
  const part = (n: number, unit: string) => `${n}${u.sep}${unit}`;
  const pair = (a: number, ua: string, b: number, ub: string) =>
    u.sep && b === 0 ? part(a, ua) : `${part(a, ua)} ${pad(b)}${u.sep}${ub}`;
  if (d > 0) return pair(d, u.d, h, u.h);
  if (h > 0) return pair(h, u.h, m, u.m);
  if (m > 0) return pair(m, u.m, sec, u.s);
  return part(sec, u.s);
}

/** Locale-aware scientific notation with a lower-case "e": en "2.5e-5", vi "2,5e-5". */
export function formatScientific(value: number, locale = "en", fractionDigits = 2): string {
  const parts = new Intl.NumberFormat(safeLocale(locale), {
    notation: "scientific",
    maximumFractionDigits: fractionDigits,
  }).formatToParts(value);
  return parts
    .map((p) =>
      p.type === "exponentSeparator"
        ? "e"
        : p.type === "exponentMinusSign" || p.type === "minusSign"
          ? "-"
          : p.value,
    )
    .join("");
}

export function formatNumber(value: number | null | undefined, locale = "en", maxDigits = 4): string {
  if (value === null || value === undefined) return "—";
  if (!Number.isFinite(value)) return String(value);
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e6)) return formatScientific(value, locale);
  return new Intl.NumberFormat(safeLocale(locale), { maximumSignificantDigits: maxDigits }).format(value);
}

/**
 * Chart axis tick labels (CX-05): tiny values (learning rate ~1e-5) in scientific notation so the
 * ticks stay distinct instead of all rounding to "0"; large values compact; thousands separators.
 */
export function formatTick(value: number | null | undefined, locale = "en"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs < 1e-3) return formatScientific(value, locale);
  if (abs >= 1e6)
    return new Intl.NumberFormat(safeLocale(locale), {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  return new Intl.NumberFormat(safeLocale(locale), { maximumSignificantDigits: 6 }).format(value);
}

export function formatInt(value: number | null | undefined, locale = "en"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(safeLocale(locale), { maximumFractionDigits: 0 }).format(value);
}

export function formatDateTime(iso: string | null | undefined, locale = "en"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(safeLocale(locale), { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function formatPercent(fraction: number | null | undefined, locale = "en"): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "—";
  return new Intl.NumberFormat(safeLocale(locale), { style: "percent", maximumFractionDigits: 1 }).format(
    fraction,
  );
}

/** "5 minutes ago" style relative time using Intl.RelativeTimeFormat. */
export function formatRelative(
  iso: string | null | undefined,
  locale = "en",
  now: Date = new Date(),
): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffS = Math.round((then - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(safeLocale(locale), { numeric: "auto" });
  const abs = Math.abs(diffS);
  if (abs < 60) return rtf.format(diffS, "second");
  if (abs < 3600) return rtf.format(Math.round(diffS / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffS / 3600), "hour");
  return rtf.format(Math.round(diffS / 86400), "day");
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "—";
}
