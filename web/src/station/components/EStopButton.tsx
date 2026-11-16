/**
 * The big e-stop (§4.7, §6.0). Space triggers it from anywhere (never scrolls the page); inside a
 * text field Space types and Esc stops instead. The first press freezes the arm with torque on;
 * a second press within 2 s (or "Relax") turns torque off. In `estopped` it becomes "Reset".
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "../api/client";
import { useStationMutation } from "../api/hooks";
import { MOVING_STATES, type Status } from "../api/types";
import { useRuntime, useStation, useStatus } from "../ws/StationProvider";
import { PROGRAM_DONE } from "../ws/store";
import { StationError } from "./StationError";
import { Sprite } from "@/hibiscus/PixelAnim";

export const RELAX_WINDOW_MS = 2000;

export function isTextInput(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    return !["checkbox", "radio", "button", "submit", "range", "file", "reset"].includes(target.type);
  }
  return false;
}

export function EStopButton({ size = 96 }: { size?: 96 | 128 }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const { control } = useRuntime();
  const state = status?.state ?? null;
  // A dry run (programs §11) leaves the state idle but still stops on an e-stop press.
  const dryRun = useStation((s) => s.program?.dry_run === true && !PROGRAM_DONE.includes(s.program.status));
  const moving = (state !== null && MOVING_STATES.includes(state)) || dryRun;
  const estopped = state === "estopped";
  const [pressedAt, setPressedAt] = useState<number | null>(null);
  const pressedRef = useRef<number | null>(null);
  const reset = useStationMutation(() => api.post<Status>("/estop/reset"));
  const relax = useStationMutation(() =>
    api.post<Status>("/robots/torque", { arm: "follower", enabled: false, confirm: true }),
  );

  const press = useCallback(() => {
    // The WS path takes effect without a queue; REST is the fallback when the socket is down.
    if (!control.estop()) void api.post("/estop").catch(() => undefined);
    const now = Date.now();
    pressedRef.current = now;
    setPressedAt(now);
  }, [control]);

  useEffect(() => {
    if (!moving && !estopped) return undefined;
    const onKey = (e: KeyboardEvent) => {
      const inText = isTextInput(e.target);
      if ((e.code === "Space" || e.key === " ") && !inText) {
        e.preventDefault();
        if (!e.repeat) press();
      } else if (e.key === "Escape" && inText && moving) {
        e.preventDefault();
        press();
      }
    };
    // keyup too: a focused button would otherwise "click" on Space release.
    const onKeyUp = (e: KeyboardEvent) => {
      if ((e.code === "Space" || e.key === " ") && !isTextInput(e.target)) e.preventDefault();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onKeyUp, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("keyup", onKeyUp, true);
    };
  }, [moving, estopped, press]);

  useEffect(() => {
    if (pressedAt === null) return undefined;
    const id = setTimeout(() => {
      setPressedAt(null);
    }, RELAX_WINDOW_MS);
    return () => {
      clearTimeout(id);
    };
  }, [pressedAt]);

  if (!moving && !estopped) return null;
  const torqueOn = status?.robot?.follower_torque ?? false;
  const showRelax = torqueOn && (estopped || pressedAt !== null);

  return (
    <div
      className="fixed bottom-3 right-3 z-50 flex flex-col items-end gap-2 sm:bottom-4 sm:right-4"
      data-testid="estop-dock"
    >
      {estopped ? (
        <div className="px-panel-sm flex max-w-[16rem] flex-col items-end gap-2 bg-card p-2 text-right">
          <p className="text-sm font-bold">
            {t("estop.latched", {
              reason: t(`reasons.${status?.reason ?? "user"}`, { defaultValue: status?.reason ?? "" }),
            })}
          </p>
          <StationError error={reset.error} />
          <Button
            onClick={() => {
              reset.mutate(undefined);
            }}
            disabled={reset.isPending}
          >
            {t("estop.reset")}
          </Button>
        </div>
      ) : null}
      {showRelax ? (
        <Button
          variant="outline"
          onClick={() => {
            relax.mutate(undefined);
          }}
          disabled={relax.isPending}
        >
          {t("estop.relax")}
        </Button>
      ) : null}
      {!estopped ? (
        <button
          type="button"
          onClick={press}
          aria-keyshortcuts="Space"
          aria-label={t("estop.label")}
          className={cn(
            "px-btn-estop flex flex-col items-center justify-center gap-1 font-extrabold text-base text-[rgb(255_246_220)] shadow-[4px_4px_0_0_rgb(59_32_39/0.35)] hover:brightness-110 active:translate-y-[2px]",
          )}
          style={{ width: size, height: size }}
        >
          <Sprite name={pressedAt !== null ? "icon_estop_pressed" : "icon_estop"} />
          <span>{t("estop.short")}</span>
          <span className="text-[10px] leading-none opacity-90">{t("estop.key")}</span>
        </button>
      ) : null}
    </div>
  );
}
