/**
 * The WebGL part of the twin (lazy chunk with three.js + urdf-loader). The live pose is pushed to
 * the scene straight from the store subscription (no React render per joint message); the scene
 * draws a frame only when something changed and nothing while the canvas is off screen.
 */
import { useEffect, useRef } from "react";
import type { Level } from "../api/types";
import { useRuntime } from "../ws/StationProvider";
import { REST_POSE, toUrdfPose, type TwinJoint, type UrdfPose } from "./mapping";
import { TwinScene, type TwinTheme } from "./scene";

export interface TwinCanvasProps {
  ghost: UrdfPose | null;
  levels: Partial<Record<TwinJoint, Level | null>>;
  theme: TwinTheme;
  /** Changing it puts the camera back to the default view. */
  resetKey: number;
  label: string;
  onState: (state: "ready" | "error") => void;
}

export default function TwinCanvas({ ghost, levels, theme, resetKey, label, onState }: TwinCanvasProps) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<TwinScene | null>(null);
  const { store } = useRuntime();
  const onStateRef = useRef(onState);
  onStateRef.current = onState;

  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    let s: TwinScene;
    try {
      s = new TwinScene(el);
    } catch {
      onStateRef.current("error");
      return undefined;
    }
    scene.current = s;
    s.setPose(REST_POSE);
    let last = store.getSnapshot().joints;
    if (last) s.setPose(toUrdfPose(last.arms.follower));
    const unsub = store.subscribe(() => {
      const j = store.getSnapshot().joints;
      if (j === last) return;
      last = j;
      if (j) s.setPose(toUrdfPose(j.arms.follower));
    });
    const io =
      typeof IntersectionObserver === "function"
        ? new IntersectionObserver((entries) => {
            s.setVisible(entries.some((e) => e.isIntersecting));
          })
        : null;
    io?.observe(el);
    s.load().then(
      () => {
        onStateRef.current("ready");
      },
      () => {
        onStateRef.current("error");
      },
    );
    return () => {
      unsub();
      io?.disconnect();
      s.dispose();
      scene.current = null;
    };
  }, [store]);

  useEffect(() => {
    scene.current?.setTheme(theme);
  }, [theme]);
  useEffect(() => {
    scene.current?.setLevels(levels);
  }, [levels]);
  useEffect(() => {
    scene.current?.setGhostPose(ghost);
  }, [ghost]);
  useEffect(() => {
    if (resetKey > 0) scene.current?.resetView();
  }, [resetKey]);

  return (
    <div
      ref={host}
      role="img"
      aria-label={label}
      className="h-full w-full touch-none"
      data-testid="twin-canvas"
    />
  );
}
