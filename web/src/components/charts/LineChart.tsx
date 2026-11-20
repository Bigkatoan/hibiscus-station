import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useTranslation } from "react-i18next";
import { formatNumber, formatTick } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { alignSeries, lastFinite, type XYSeries } from "./series";

export interface LineChartProps {
  title: string;
  series: readonly XYSeries[];
  height?: number;
  xLabel?: string;
  logY?: boolean;
  /** Optional vertical cursor sync key across charts (e.g. episode viewer). */
  syncKey?: string;
  /** Called with the x value under the pointer, anywhere on the x scale, not only at a data
   * point (for video sync: a click reaches the first and the last frame). */
  onCursorX?: (x: number | null) => void;
  /** Fixed x scale (e.g. 0 to the episode's duration) instead of the data's extent. */
  xRange?: readonly [number, number];
  /** Draw a vertical marker at this x (e.g. current video time). */
  markerX?: number | null;
}

const PALETTE_VARS = [
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--chart-6",
  "--chart-7",
  "--chart-8",
];

/** Tick label formatter for uPlot axes (CX-05: lr ~1e-5 must not render as "0, 0, 0"). */
export function axisValues(locale: string): (u: unknown, splits: number[]) => string[] {
  return (_u, splits) => splits.map((v) => formatTick(v, locale));
}

/**
 * Show point markers when a series has few points (QC-e2e-11: a 200-step run logged once has a
 * single point, and a line needs two). Dense series keep plain lines.
 */
export const SPARSE_POINTS = 30;
export function showPoints(u: { data: ArrayLike<ArrayLike<unknown>> }, seriesIdx: number): boolean {
  const ys = Array.from(u.data[seriesIdx] ?? []);
  let n = 0;
  for (const y of ys) if (typeof y === "number" && Number.isFinite(y)) n += 1;
  return n > 0 && n <= SPARSE_POINTS;
}

/** x scale: the data's extent, or a fixed range (QV-9: 0 to the episode's duration). */
export function xScale(xRange?: readonly [number, number]): uPlot.Scale {
  return xRange ? { time: false, range: [xRange[0], xRange[1]] } : { time: false };
}

/** The x value under the pointer, anywhere on the scale (not snapped to a data point). */
export function pointerX(left: number | undefined | null, posToVal: (pos: number) => number): number | null {
  return left !== undefined && left !== null && left >= 0 ? posToVal(left) : null;
}

function cssColor(name: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `rgb(${v})` : "#2f6f9f";
}

/** Canvas line chart (uPlot: thousands of points, cheap appends). */
export function LineChart({
  title,
  series,
  height = 240,
  xLabel,
  logY = false,
  syncKey,
  onCursorX,
  markerX,
  xRange,
}: LineChartProps) {
  const { t, i18n } = useTranslation();
  const { resolved } = useTheme();
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const markerRef = useRef<number | null>(markerX ?? null);
  const cursorCb = useRef(onCursorX);
  cursorCb.current = onCursorX;
  const data = useMemo(() => alignSeries(series), [series]);
  const labels = series.map((s) => s.label).join("|");

  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    const fg = cssColor("--muted-foreground");
    const grid = cssColor("--border");
    // Nunito on the axes too (canvas text): readable numbers, no pixel fonts.
    const axisFont = "13px Nunito, ui-sans-serif, sans-serif";
    const labelFont = "bold 14px Nunito, ui-sans-serif, sans-serif";
    const opts: uPlot.Options = {
      width: Math.max(200, el.clientWidth),
      height,
      legend: { show: true, live: true },
      cursor: {
        ...(syncKey ? { sync: { key: syncKey } } : {}),
        drag: { x: true, y: false },
      },
      scales: {
        x: xScale(xRange),
        // distr 3 = logarithmic (uPlot.Scale.Distr is a const enum, not importable as a value here).
        // eslint-disable-next-line @typescript-eslint/no-unsafe-enum-assignment
        y: logY ? { distr: 3 } : { auto: true },
      },
      axes: [
        {
          stroke: fg,
          font: axisFont,
          labelFont,
          grid: { stroke: grid, width: 2, dash: [4, 4] },
          ticks: { stroke: grid, width: 2 },
          values: axisValues(i18n.language),
          ...(xLabel ? { label: xLabel } : {}),
        },
        {
          stroke: fg,
          font: axisFont,
          grid: { stroke: grid, width: 2, dash: [4, 4] },
          ticks: { stroke: grid, width: 2 },
          values: axisValues(i18n.language),
          // Wide enough for the longest tick label ("1,5e-5" in Nunito 13px ~ 7px per char).
          size: (_u: uPlot, values: string[] | null) =>
            Math.max(48, 20 + 9 * Math.max(0, ...(values ?? []).map((v) => v.length))),
        },
      ],
      series: [
        { label: xLabel ?? "x" },
        ...series.map((s, i) => ({
          label: s.label,
          stroke: cssColor(PALETTE_VARS[i % PALETTE_VARS.length] ?? "--chart-1"),
          width: 2,
          spanGaps: false,
          points: { show: showPoints, size: 7, width: 2 },
        })),
      ],
      hooks: {
        setCursor: [
          (u) => {
            cursorCb.current?.(pointerX(u.cursor.left, (pos) => u.posToVal(pos, "x")));
          },
        ],
        draw: [
          (u) => {
            const mx = markerRef.current;
            if (mx === null) return;
            const left = u.valToPos(mx, "x", true);
            const ctx = u.ctx;
            ctx.save();
            ctx.strokeStyle = cssColor("--destructive");
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(left, u.bbox.top);
            ctx.lineTo(left, u.bbox.top + u.bbox.height);
            ctx.stroke();
            ctx.restore();
          },
        ],
      },
    };
    let u: uPlot;
    try {
      u = new uPlot(opts, data, el);
    } catch {
      return undefined; // canvas unavailable (non-browser env)
    }
    plot.current = u;
    const ro = new ResizeObserver(() => {
      u.setSize({ width: Math.max(200, el.clientWidth), height });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      u.destroy();
      plot.current = null;
    };
    // Recreate only when the series set, size, scale or theme changes; data updates use setData.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labels, height, logY, resolved, syncKey, xLabel, i18n.language, xRange?.[0], xRange?.[1]]);

  useEffect(() => {
    plot.current?.setData(data);
  }, [data]);

  useEffect(() => {
    markerRef.current = markerX ?? null;
    plot.current?.redraw(false, false);
  }, [markerX]);

  const summary = series.map((s) => `${s.label}: ${formatNumber(lastFinite(s.y), i18n.language)}`).join(", ");

  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 font-extrabold text-base">{title}</figcaption>
      <div ref={host} role="img" aria-label={t("chart.summary", { title, summary })} className="w-full" />
      {series.every((s) => s.x.length === 0) ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t("chart.no_data")}</p>
      ) : null}
    </figure>
  );
}
