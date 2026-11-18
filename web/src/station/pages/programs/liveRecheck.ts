/**
 * Keeps the program's check up to date while the arm moves (field report 0.2.9, D-24).
 *
 * "The arm will first move slowly to the start of this motion (X° away)" depends on where the
 * follower is, so a check made earlier goes stale as soon as the arm moves or a run ends. Once
 * the shown issues come from a check, the check runs again when the follower has moved more than
 * {@link RECHECK_MOVE_DEG} on some joint since the last one (at most once every
 * {@link RECHECK_MIN_MS}), and when a run ends. The joint stream is read from the store without
 * re-rendering the editor on every joint message.
 *
 * When the pose becomes unknown (robot disconnected, joints older than {@link POSE_STALE_MS}), the
 * pose-dependent lines go at once and the check runs again (QC F029 r1, QD-36).
 */
import { useCallback, useEffect, useRef } from "react";
import { useRuntime } from "../../ws/StationProvider";

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

/** No joint message for this long: the pose is unknown (stream stopped, robot gone). */
export const POSE_STALE_MS = 2500;

export function useLiveRecheck({
  enabled,
  running,
  recheck,
  onPoseLost,
}: {
  /** The shown issues come from a check of the saved version (no unsaved edit, not running). */
  enabled: boolean;
  /** A run of this program is live (a run end re-checks). */
  running: boolean;
  /**
   * Runs the check; resolves when the new issues are shown. `poseKnown` is false when the robot
   * is not connected or its joints went stale: then nothing about the arm's pose may be shown.
   */
  recheck: (poseKnown: boolean) => Promise<unknown>;
  /** The robot disconnected or its pose went stale (QD-36): drop what depends on the pose now. */
  onPoseLost: () => void;
}): { markChecked: () => void } {
  const { store } = useRuntime();
  const basis = useRef<Pose | null>(null);
  const last = useRef(0);
  const inflight = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const live = useRef({ enabled, recheck, onPoseLost });
  live.current = { enabled, recheck, onPoseLost };
  // When the last joint message arrived (the store keeps the last one after the stream stops).
  const seen = useRef<{ msg: unknown; at: number }>({
    msg: store.getSnapshot().joints,
    at: Date.now(),
  });

  /** The follower pose, or null when it is not known now (not connected, stale joints). */
  const knownPose = useRef((): Pose | null => {
    const snap = store.getSnapshot();
    if (snap.joints !== seen.current.msg) seen.current = { msg: snap.joints, at: Date.now() };
    if (!snap.status?.robot?.connected || !snap.joints) return null;
    if (Date.now() - seen.current.at > POSE_STALE_MS) return null;
    return snap.joints.arms.follower;
  });
  const known = useRef(knownPose.current() !== null);

  // The pose became known or unknown since the last check: check again whatever the movement
  // (a reconnect within a second leaves the arm where it was: QC F029 QD-38).
  const force = useRef(false);

  const fire = useRef(() => {
    if (inflight.current || !live.current.enabled) return;
    inflight.current = true;
    force.current = false;
    basis.current = knownPose.current();
    last.current = Date.now();
    live.current
      .recheck(basis.current !== null)
      .catch(() => undefined)
      .finally(() => {
        inflight.current = false;
      });
  });

  useEffect(() => {
    if (!enabled) return undefined;
    const due = () => force.current || poseDelta(basis.current, knownPose.current()) > RECHECK_MOVE_DEG;
    const evaluate = () => {
      const pose = knownPose.current();
      if (known.current !== (pose !== null)) {
        if (pose === null) live.current.onPoseLost();
        force.current = true;
      }
      known.current = pose !== null;
      if (inflight.current || timer.current || !due()) return;
      const wait = last.current + RECHECK_MIN_MS - Date.now();
      if (wait <= 0) fire.current();
      else
        timer.current = setTimeout(() => {
          timer.current = null;
          if (due()) fire.current();
        }, wait);
    };
    const unsubscribe = store.subscribe(evaluate);
    // A stream that stops sends nothing: look at the pose's age regularly too. This also picks up
    // a forced check that had to wait for one in flight.
    const tick = setInterval(evaluate, 1000);
    return () => {
      unsubscribe();
      clearInterval(tick);
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
    basis.current = knownPose.current();
    known.current = basis.current !== null;
    last.current = Date.now();
  }, []);
  return { markChecked };
}
