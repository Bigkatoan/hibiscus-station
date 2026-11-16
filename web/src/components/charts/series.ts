/** Pure helpers that shape API series into uPlot's aligned-columns format. */

export interface XYSeries {
  label: string;
  x: readonly number[];
  y: readonly (number | null)[];
}

export type AlignedData = [number[], ...(number | null)[][]];

/** Union of all x values (sorted, unique) with each series' y placed on it (null where absent). */
export function alignSeries(series: readonly XYSeries[]): AlignedData {
  const xsSet = new Set<number>();
  for (const s of series) for (const x of s.x) xsSet.add(x);
  const xs = [...xsSet].sort((a, b) => a - b);
  const index = new Map(xs.map((x, i) => [x, i]));
  const cols = series.map((s) => {
    const col: (number | null)[] = new Array<number | null>(xs.length).fill(null);
    s.x.forEach((x, i) => {
      const at = index.get(x);
      const v = s.y[i];
      if (at !== undefined) col[at] = v !== undefined && v !== null && Number.isFinite(v) ? v : null;
    });
    return col;
  });
  return [xs, ...cols];
}

/** Append (step, value) points to a growing series without duplicating steps (SSE replay safe). */
export function appendPoint(
  s: { steps: number[]; values: (number | null)[] },
  step: number,
  value: number | null,
): void {
  const last = s.steps.at(-1);
  if (last === undefined || step > last) {
    s.steps.push(step);
    s.values.push(value);
    return;
  }
  // Out-of-order / replayed point: overwrite or insert in order.
  let i = s.steps.length - 1;
  while (i >= 0 && (s.steps[i] ?? 0) > step) i -= 1;
  if (i >= 0 && s.steps[i] === step) {
    s.values[i] = value;
  } else {
    s.steps.splice(i + 1, 0, step);
    s.values.splice(i + 1, 0, value);
  }
}

/** Exponential moving average smoothing (TensorBoard-style), nulls preserved. */
export function smooth(values: readonly (number | null)[], weight: number): (number | null)[] {
  if (weight <= 0) return [...values];
  let last: number | null = null;
  return values.map((v) => {
    if (v === null || !Number.isFinite(v)) return null;
    last = last === null ? v : last * weight + (1 - weight) * v;
    return last;
  });
}

export function lastFinite(values: readonly (number | null)[]): number | null {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    const v = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) return v;
  }
  return null;
}
