/**
 * Live camera previews (R2, §4.6 / §5.4). Frames arrive on the video WebSocket and are drawn to a
 * <canvas> through createImageBitmap (never <img> object URLs). Each tile shows the tick of the
 * frames it came from and, while a policy runs, "policy input · 640×480 → 320×240".
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { CameraStatus, FrameHeader } from "../api/types";
import { useRuntime, useStation } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";
import { Sprite } from "@/hibiscus/PixelAnim";

export const STALE_AFTER_MS = 1500;

/**
 * Draws one JPEG onto the canvas. Returns false when the browser cannot decode (no
 * createImageBitmap / no 2D context), so the caller keeps its placeholder.
 */
export async function drawJpeg(canvas: HTMLCanvasElement, jpeg: Uint8Array): Promise<boolean> {
  if (typeof globalThis.createImageBitmap !== "function") return false;
  const bmp = await globalThis.createImageBitmap(new Blob([jpeg], { type: "image/jpeg" }));
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bmp.close();
    return false;
  }
  if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
    canvas.width = bmp.width;
    canvas.height = bmp.height;
  }
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return true;
}

export function CameraTile({
  name,
  cam,
  overlay,
}: {
  name: string;
  cam: CameraStatus | undefined;
  /** Drawn over the frame, in the frame's box (e.g. the detector ROI editor). */
  overlay?: ReactNode;
}) {
  const { t } = useTranslation("station");
  const { video } = useRuntime();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [header, setHeader] = useState<FrameHeader | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [late, setLate] = useState(false);
  const lastAt = useRef(0);

  useEffect(() => {
    let busy = false;
    let pending: { header: FrameHeader; jpeg: Uint8Array } | null = null;
    const draw = (f: { header: FrameHeader; jpeg: Uint8Array }) => {
      const el = canvas.current;
      if (!el) return;
      busy = true;
      void drawJpeg(el, f.jpeg)
        .catch(() => false)
        .finally(() => {
          busy = false;
          const next = pending;
          pending = null;
          if (next) draw(next);
        });
    };
    const off = video.watch(
      name,
      (f) => {
        lastAt.current = Date.now();
        setHeader(f.header);
        setError(null);
        setLate(false);
        // Latest frame wins: while one decode runs, only the newest frame waits.
        if (busy) pending = f;
        else draw(f);
      },
      (code) => {
        setError(code);
      },
    );
    const timer = setInterval(() => {
      setLate(lastAt.current > 0 && Date.now() - lastAt.current > STALE_AFTER_MS);
    }, 500);
    return () => {
      off();
      clearInterval(timer);
    };
  }, [name, video]);

  const stale = Boolean(header?.stale) || Boolean(cam?.stale) || error !== null || late;
  const srcW = header?.src_w ?? cam?.width ?? 640;
  const srcH = header?.src_h ?? cam?.height ?? 480;
  return (
    <figure
      className="relative min-w-0 border-4 border-frame bg-[#1f2340]"
      data-testid={`camera-${name}`}
      data-tick={header?.tick ?? ""}
      data-stale={stale ? "true" : "false"}
    >
      <div className="relative w-full" style={{ aspectRatio: `${srcW} / ${srcH}` }}>
        <canvas
          ref={canvas}
          className="pixelated absolute inset-0 h-full w-full object-contain"
          aria-hidden
        />
        {!header ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-[#c7d3e3]">
            <Sprite name="icon_camera" />
            <span className="text-sm">{t("camera.waiting")}</span>
          </div>
        ) : null}
        {stale ? (
          <div className="station-stale absolute inset-0 flex items-center justify-center" role="status">
            <span className="bg-[#3b2027] px-2 py-1 font-extrabold text-base text-[#fff6dc]">
              {t(error ? `camera.err_${error}` : "camera.stale", { defaultValue: t("camera.stale") })}
            </span>
          </div>
        ) : null}
        {overlay}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-x-2 bg-[#3b2027] px-2 py-1 text-xs text-[#fff6dc]">
        <span className="font-extrabold text-base">{name}</span>
        <span className={cn("tabular-nums", header?.policy_input && "text-[#9bd35a]")}>
          {header?.policy_input
            ? t("camera.policy_input", { sw: srcW, sh: srcH, w: header.w, h: header.h })
            : header
              ? `${srcW}×${srcH} → ${header.w}×${header.h}`
              : `${srcW}×${srcH}`}
        </span>
        {/* Outside a session the frames have no control-loop tick (-1): show nothing then. */}
        <span className="tabular-nums">
          {header && header.tick >= 0 ? t("camera.tick", { tick: header.tick }) : ""}
        </span>
      </figcaption>
    </figure>
  );
}

const selCameras = (s: StationSnapshot) => s.status?.cameras;
const selTick = (s: StationSnapshot) => s.joints?.tick;

/** Every configured camera, live. `names` defaults to all cameras in the status. */
export function CameraGrid({ names, className }: { names?: string[]; className?: string }) {
  const { t } = useTranslation("station");
  const cameras = useStation(selCameras);
  const tick = useStation(selTick);
  const list = names ?? (cameras ?? []).map((c) => c.name);
  if (list.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 border-2 border-dashed border-frame/50 p-4 text-sm",
          className,
        )}
      >
        <Sprite name="icon_camera" />
        {t("camera.none")}
      </div>
    );
  }
  return (
    <section
      aria-label={t("camera.title")}
      className={cn("flex flex-col gap-1", className)}
      data-testid="camera-grid"
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {list.map((n) => (
          <CameraTile key={n} name={n} cam={cameras?.find((c) => c.name === n)} />
        ))}
      </div>
      {tick !== undefined ? (
        <p className="text-right tabular-nums text-xs text-muted-foreground">
          {t("camera.state_tick", { tick })}
        </p>
      ) : null}
    </section>
  );
}
