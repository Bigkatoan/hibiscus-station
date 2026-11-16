import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { initI18n } from "@/lib/i18n";
import { server } from "./server";

initI18n("en");

// uPlot draws on <canvas>, which jsdom does not implement. Replace the renderer with a recorder;
// the data shaping it receives (alignSeries etc.) is real and unit-tested separately.
vi.mock("uplot", () => {
  class FakeUPlot {
    static instances: FakeUPlot[] = [];
    data: unknown;
    ctx = {
      save: () => undefined,
      restore: () => undefined,
      beginPath: () => undefined,
      moveTo: () => undefined,
      lineTo: () => undefined,
      stroke: () => undefined,
    };
    bbox = { top: 0, left: 0, width: 100, height: 100 };
    cursor = { idx: null };
    constructor(
      readonly opts: { series: { label?: string }[] },
      data: unknown,
      readonly el: HTMLElement,
    ) {
      this.data = data;
      FakeUPlot.instances.push(this);
      el.setAttribute("data-uplot-series", opts.series.map((s) => s.label ?? "").join("|"));
    }
    setData(d: unknown): void {
      this.data = d;
    }
    setSize(): void {
      /* no-op */
    }
    redraw(): void {
      /* no-op */
    }
    valToPos(): number {
      return 0;
    }
    destroy(): void {
      /* no-op */
    }
  }
  return { default: FakeUPlot };
});

// jsdom lacks these browser APIs used by Radix / charts.
class ResizeObserverStub {
  observe(): void {
    /* no-op */
  }
  unobserve(): void {
    /* no-op */
  }
  disconnect(): void {
    /* no-op */
  }
}
globalThis.ResizeObserver = ResizeObserverStub;
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      // Legacy MediaQueryList API, still called by some libraries.
      // eslint-disable-next-line @typescript-eslint/no-deprecated
      addListener: () => undefined,
      // eslint-disable-next-line @typescript-eslint/no-deprecated
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
Object.assign(Element.prototype, {
  scrollIntoView: vi.fn(),
  hasPointerCapture: () => false,
  releasePointerCapture: () => undefined,
});
window.HTMLMediaElement.prototype.pause = () => undefined;
window.HTMLMediaElement.prototype.load = () => undefined;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  document.cookie.split(";").forEach((c) => {
    const name = c.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
  window.localStorage.clear();
  window.sessionStorage.clear();
});
afterAll(() => {
  server.close();
});
