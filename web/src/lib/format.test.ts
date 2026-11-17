import { describe, expect, it } from "vitest";
import { alignSeries, appendPoint, lastFinite, smooth } from "@/components/charts/series";
import {
  formatBytes,
  formatSize,
  formatDuration,
  formatInt,
  formatNumber,
  formatPercent,
  formatTick,
  formatRelative,
  shortId,
} from "./format";

describe("formatSize: human sizes, never 0.00 (QC 0.2.9 QD-21)", () => {
  it("uses kB / MB / GB with one decimal under 10, none above", () => {
    expect(formatSize(0)).toBe("0 B");
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(3.04e6)).toBe("3 MB");
    expect(formatSize(3.4e6)).toBe("3.4 MB");
    expect(formatSize(12.4e6)).toBe("12 MB");
    expect(formatSize(999.7e3)).toBe("1 MB");
    expect(formatSize(1.5e9)).toBe("1.5 GB");
    expect(formatSize(250e9)).toBe("250 GB");
    expect(formatSize(3.4e6, "vi")).toBe("3,4 MB");
    expect(formatSize(null)).toBe("—");
    expect(formatSize(Number.NaN)).toBe("—");
  });
  it("never prints a zero for a size that is not zero", () => {
    for (const b of [1, 999, 1001, 4.9e6, 9.99e6, 1e12, 7e15])
      expect(formatSize(b)).not.toMatch(/^0[.,]?0*\s/);
  });
});

describe("format helpers", () => {
  it("formats bytes with binary units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KiB");
    expect(formatBytes(64 * 1024 * 1024)).toBe("64 MiB");
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(5 * 1024 ** 3, "vi")).toBe("5 GiB");
  });

  it("formats durations", () => {
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(185)).toBe("3m 05s");
    expect(formatDuration(3720)).toBe("1h 02m");
    expect(formatDuration(90000)).toBe("1d 01h");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(-1)).toBe("—");
  });

  it("formats durations in Vietnamese (CX-08)", () => {
    expect(formatDuration(42, "vi")).toBe("42 giây");
    expect(formatDuration(824, "vi")).toBe("13 phút 44 giây");
    expect(formatDuration(3900, "vi")).toBe("1 giờ 5 phút");
    expect(formatDuration(3600, "vi")).toBe("1 giờ");
    expect(formatDuration(90000, "vi")).toBe("1 ngày 1 giờ");
    expect(formatDuration(824, "en")).toBe("13m 44s");
  });

  it("formats chart ticks so tiny learning rates stay distinct (CX-05)", () => {
    const ticks = [1e-5, 2e-5, 3e-5].map((v) => formatTick(v, "en"));
    expect(new Set(ticks).size).toBe(3);
    expect(ticks).toEqual(["1e-5", "2e-5", "3e-5"]);
    expect(formatTick(2.5e-5, "vi")).toBe("2,5e-5");
    expect(formatTick(0, "vi")).toBe("0");
    expect(formatTick(10000, "vi")).toBe("10.000");
    expect(formatTick(0.25, "vi")).toBe("0,25");
    expect(formatTick(null)).toBe("");
  });

  it("formats numbers compactly", () => {
    expect(formatNumber(0.52)).toBe("0.52");
    expect(formatNumber(0.00001)).toBe("1e-5");
    expect(formatNumber(0.00002, "vi")).toBe("2e-5");
    expect(formatNumber(0.000025, "vi")).toBe("2,5e-5");
    expect(formatNumber(null)).toBe("—");
    expect(formatInt(11277)).toBe("11,277");
    expect(formatInt(11277, "vi")).toBe("11.277");
    expect(formatPercent(0.105)).toBe("10.5%");
    expect(shortId("66666666-6666")).toBe("66666666");
  });

  it("formats relative time", () => {
    const now = new Date("2026-11-15T10:00:00Z");
    expect(formatRelative("2026-11-15T09:55:00Z", "en", now)).toBe("5 minutes ago");
    expect(formatRelative("2026-11-14T10:00:00Z", "en", now)).toBe("yesterday");
  });
});

describe("chart series helpers", () => {
  it("aligns series with different x onto a shared axis", () => {
    const d = alignSeries([
      { label: "a", x: [1, 2, 3], y: [10, 20, 30] },
      { label: "b", x: [2, 4], y: [5, Number.NaN] },
    ]);
    expect(d).toEqual([
      [1, 2, 3, 4],
      [10, 20, 30, null],
      [null, 5, null, null],
    ]);
  });

  it("appendPoint dedups replayed steps and keeps order", () => {
    const s = { steps: [200, 400], values: [1, 0.5] as (number | null)[] };
    appendPoint(s, 600, 0.4);
    appendPoint(s, 400, 0.45); // replay overwrites
    appendPoint(s, 300, 0.7); // out of order inserts
    expect(s.steps).toEqual([200, 300, 400, 600]);
    expect(s.values).toEqual([1, 0.7, 0.45, 0.4]);
  });

  it("smooths with EMA and keeps gaps", () => {
    expect(smooth([1, null, 3], 0.5)).toEqual([1, null, 2]);
    expect(smooth([1, 2], 0)).toEqual([1, 2]);
    expect(lastFinite([1, 2, null])).toBe(2);
    expect(lastFinite([])).toBeNull();
  });
});
