/**
 * Sizes, durations and measured numbers in the current language: the one place the Station UI
 * turns a number into text (QC 0.2.9 QD-21 sweep; units.test.ts keeps every screen on it). Decimal
 * kB / MB / GB for sizes, a locale decimal separator ("1.5" en, "1,5" vi), never "0.00 GiB".
 */
import { formatFixed, formatSize } from "@/lib/format";
import { i18n } from "@/lib/i18n";

/** A size in bytes: "3.4 MB", "250 GB". */
export function fmtSize(bytes: number | null | undefined): string {
  return formatSize(bytes, i18n.language);
}

/** A measured value with fixed decimals: seconds on a clock, volts, fps, degrees, percent. */
export function fmtFixed(value: number | null | undefined, digits = 1): string {
  return formatFixed(value, i18n.language, digits);
}

/** A short duration: "4.5 s" under 10 s, "42 s" above. */
export function fmtSeconds(s: number): string {
  return `${fmtFixed(s, s < 10 ? 1 : 0)} s`;
}

/** An SVG coordinate (never shown as text): one decimal, always a dot. */
export function svgNum(v: number): string {
  return String(Math.round(v * 10) / 10);
}
