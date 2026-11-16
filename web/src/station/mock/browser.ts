/**
 * Station mock mode (`vite --mode mock` / `pnpm dev:mock`): MSW serves the REST
 * API from a MockStation and the WebSockets are replaced by in-page MockSockets, so every screen is
 * clickable without a backend or a robot. Never part of the production bundle.
 *
 * Query switches (remembered for the tab): ?mock_connected=1, ?mock_paired=1, ?mock_heat=2
 * (°C/s on follower elbow_flex while the arm moves: shows warn → hot → critical safe stop),
 * ?mock_calib=ok|lelab|fresh (calibration scenario), ?mock_pose_off=1 (the pose check finds a
 * wrong file), ?mock_lost=1 (the follower's USB adapter went away: device_lost).
 */
import { setupWorker } from "msw/browser";
import type { SocketFactory } from "../ws/control";
import { stationHandlers } from "./handlers";
import { MockStation } from "./sim";

function flag(name: string, fallback: string): string {
  const q = new URLSearchParams(window.location.search).get(name);
  try {
    if (q !== null) window.sessionStorage.setItem(name, q);
    return window.sessionStorage.getItem(name) ?? fallback;
  } catch {
    return q ?? fallback;
  }
}

const SKY: Record<string, string> = { wrist: "#2c3150", front: "#2f6b3a" };

/** Draws a small pixel scene (arm + cube) per camera, stamped with the tick, as a JPEG. */
function canvasFrames(): (cam: string, tick: number, w: number, h: number) => Promise<Uint8Array> {
  const canvas = document.createElement("canvas");
  return async (cam, tick, w, h) => {
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return new Uint8Array();
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = SKY[cam] ?? "#4a5368";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#c99a62";
    ctx.fillRect(0, Math.round(h * 0.7), w, h);
    const x = Math.round(w / 2 + Math.sin(tick / 40) * w * 0.25);
    ctx.fillStyle = "#6fb7e8";
    ctx.fillRect(x - 8, Math.round(h * 0.25), 16, Math.round(h * 0.45));
    ctx.fillStyle = "#d7263d";
    ctx.fillRect(Math.round(w * 0.7), Math.round(h * 0.62), 16, 16);
    ctx.fillStyle = "#fff6dc";
    ctx.font = "12px monospace";
    ctx.fillText(`${cam} · tick ${tick}`, 6, 16);
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", 0.7);
    });
    return blob ? new Uint8Array(await blob.arrayBuffer()) : new Uint8Array();
  };
}

export async function startStationMock(): Promise<SocketFactory> {
  const sim = new MockStation({
    connected: flag("mock_connected", "1") === "1",
    paired: flag("mock_paired", "1") === "1",
    heatRate: Number(flag("mock_heat", "0.6")),
    deadman: true,
    calib: flag("mock_calib", "ok") as "ok" | "lelab" | "fresh",
    poseOff: flag("mock_pose_off", "0") === "1",
    lost: flag("mock_lost", "0") === "1",
    frameSource: canvasFrames(),
  });
  const worker = setupWorker(...stationHandlers(sim));
  await worker.start({ onUnhandledRequest: "bypass", quiet: true });
  sim.start();
  (window as unknown as { __station?: MockStation }).__station = sim;
  return sim.socketFactory;
}
