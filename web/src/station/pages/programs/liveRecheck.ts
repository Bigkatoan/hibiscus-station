/**
 * Keeps the program's check up to date while the arm moves (field report 0.2.9, D-24).
 *
 * "The arm will first move slowly to the start of this motion (X° away)" depends on where the
 * follower is, so a check made earlier goes stale as soon as the arm moves or a run ends. Once
 * the shown issues come from a check, the check runs again when the follower has moved more than
 * {@link RECHECK_MOVE_DEG} on some joint since the last one (at most once every
 * {@link RECHECK_MIN_MS}), and when a run ends. The joint stream is read from the store without
 * re-rendering the editor on every joint message.
 */
import { useCallback, useEffect, useRef } from "react";
import { useRuntime } from "../../ws/StationProvider";
import type { StationStore } from "../../ws/store";

/** A joint has to move this much (degrees) since the last check before checking again. */
export const RECHECK_MOVE_DEG = 2;
/** At most one automatic check this often while the arm keeps moving. */
export const RECHECK_MIN_MS = 1500;

export type Pose = Record<string, number | null | undefined>;

/** Largest joint difference in degrees between two follower poses (the gripper, in %, is left out). */
export function poseDelta(a: Pose | null, b: Pose | null): number {
  if (!a || !b) return a === b ? 0 : Infinity;
  let max = 0;
  for (const [k, v] of Object.entries(b)) {
    if (k.startsWith("gripper") || typeof v !== "number") continue;
    const w = a[k];
    if (typeof w !== "number") return Infinity;
    max = Math.max(max, Math.abs(v - w));
  }
  return max;
}

function followerOf(store: StationStore): Pose | null {
  return store.getSnapshot().joints?.arms.follower ?? null;
}

export function useLiveRecheck({
  enabled,
  running,
  recheck,
}: {
  /** The shown issues come from a check of the saved version (no unsaved edit, not running). */
  enabled: boolean;
  /** A run of this program is live (a run end re-checks). */
  running: boolean;
  /** Runs the check; resolves when the new issues are shown. */
  recheck: () => Promise<unknown>;
}): { markChecked: () => void } {
  const { store } = useRuntime();
  const basis = useRef<Pose | null>(null);
  const last = useRef(0);
  const inflight = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const live = useRef({ enabled, recheck });
  live.current = { enabled, recheck };

  const fire = useRef(() => {
    if (inflight.current || !live.current.enabled) return;
    inflight.current = true;
    basis.current = followerOf(store);
    last.current = Date.now();
    live.current
      .recheck()
      .catch(() => undefined)
      .finally(() => {
        inflight.current = false;
      });
  });

  useEffect(() => {
    if (!enabled) return undefined;
    const evaluate = () => {
      if (inflight.current || timer.current) return;
      if (poseDelta(basis.current, followerOf(store)) <= RECHECK_MOVE_DEG) return;
      const wait = last.current + RECHECK_MIN_MS - Date.now();
      if (wait <= 0) fire.current();
      else
        timer.current = setTimeout(() => {
          timer.current = null;
          if (poseDelta(basis.current, followerOf(store)) > RECHECK_MOVE_DEG) fire.current();
        }, wait);
    };
    const unsubscribe = store.subscribe(evaluate);
    return () => {
      unsubscribe();
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
  }, [enabled, store]);

  // A run that ends leaves the arm somewhere else: check again.
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running) fire.current();
    wasRunning.current = running;
  }, [running]);

  /** Call when a check (button, run start) produced the shown issues: the pose now is the basis. */
  const markChecked = useCallback(() => {
    basis.current = followerOf(store);
    last.current = Date.now();
  }, [store]);
  return { markChecked };
}
