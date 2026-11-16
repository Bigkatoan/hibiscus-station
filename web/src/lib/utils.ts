import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Per-viewer convenience storage (theme, language). Never used for tokens or shared state. */
export const prefs = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(`hibiscus.${key}`);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(`hibiscus.${key}`, value);
    } catch {
      /* storage unavailable (private mode): ignore */
    }
  },
};

/** Which sides of a horizontally scrollable element have hidden content (tab strip affordance). */
export function overflowState(el: Pick<HTMLElement, "scrollLeft" | "scrollWidth" | "clientWidth">): {
  left: boolean;
  right: boolean;
} {
  const max = el.scrollWidth - el.clientWidth;
  return { left: el.scrollLeft > 1, right: max > 1 && el.scrollLeft < max - 1 };
}
