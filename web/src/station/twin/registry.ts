/**
 * Which pages show a twin inline (Teleop / Record / Run / Programs): the shell dock hides while
 * one is mounted, so a page never draws two WebGL arms of the same robot.
 */
import { useEffect, useSyncExternalStore } from "react";

let inline = 0;
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useRegisterInlineTwin(active: boolean): void {
  useEffect(() => {
    if (!active) return undefined;
    inline += 1;
    emit();
    return () => {
      inline -= 1;
      emit();
    };
  }, [active]);
}

export function useInlineTwinCount(): number {
  return useSyncExternalStore(subscribe, () => inline);
}

/** `window.matchMedia` as React state (false where matchMedia is missing, e.g. jsdom). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (fn) => {
      if (typeof window.matchMedia !== "function") return () => undefined;
      const mq = window.matchMedia(query);
      mq.addEventListener("change", fn);
      return () => {
        mq.removeEventListener("change", fn);
      };
    },
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
  );
}

/** True when the browser exposes WebGL at all (jsdom and WebGL-off browsers do not). */
export function hasWebGL(): boolean {
  return typeof window !== "undefined" && typeof window.WebGLRenderingContext !== "undefined";
}
