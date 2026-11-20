/**
 * Home (CR-2, 2026-11-17; formerly "rest pose") and the safe follow-ups of a Stop (CR-1).
 *
 * - "Set Home at current position" saves the follower's present pose as the robot's Home
 *   (stored as `follower.rest_pose`; replacing an existing Home asks first).
 * - "Return Home": one slow minimum-jerk move (dead-man on, Space / Stop halts it). From a user
 *   e-stop it resets the latch first; never after a thermal / electrical stop (those need Reset
 *   once cool).
 * - "Relax" always asks to support the arm first (D-6).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ConfirmButton } from "@/components/common";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "../api/client";
import { qk, useRobots, useStationMutation } from "../api/hooks";
import type { Session, Status } from "../api/types";
import { useStatus } from "../ws/StationProvider";
import { AUTO_MOVE_SPEED_DEG_S } from "./controls";
import { StationError } from "./StationError";

/** Stops whose cause is the hardware itself: Reset only once the condition cleared. */
export const DANGER_REASONS = ["thermal", "electrical", "thermal_blind", "device_lost", "bus_lost"];

export interface HomeState {
  connected: boolean;
  calibrated: boolean;
  hasHome: boolean;
  /** Why "Set Home" is not available now (null: available). */
  setBlocked: string | null;
  /** Why "Return Home" is not available now (null: available). */
  goBlocked: string | null;
  /** Return Home has to reset a user e-stop first. */
  fromEstop: boolean;
}

export function useHomeState(): HomeState {
  const { t } = useTranslation("station");
  const status = useStatus();
  const robots = useRobots();
  const robot = status?.robot ?? null;
  const connected = Boolean(robot?.connected);
  const calibrated = Boolean(robot?.arms.follower.calibrated);
  const profile = robots.data?.robots.find((r) => r.id === robot?.id) ?? null;
  const hasHome = Boolean(profile?.follower.rest_pose && Object.keys(profile.follower.rest_pose).length);
  const state = status?.state ?? "disconnected";
  const danger = state === "estopped" && DANGER_REASONS.includes(status?.reason ?? "");
  const fromEstop = state === "estopped" && !danger;
  let setBlocked: string | null = null;
  if (!connected) setBlocked = t("home.why_connect");
  else if (!calibrated) setBlocked = t("home.why_calibrate");
  else if (state !== "idle") setBlocked = t("home.why_busy");
  let goBlocked: string | null = setBlocked;
  if (connected && calibrated) {
    if (!hasHome) goBlocked = t("home.why_no_home");
    else if (danger) goBlocked = t("home.why_danger");
    else if (state === "idle" || fromEstop) goBlocked = null;
    else goBlocked = t("home.why_busy");
  }
  return { connected, calibrated, hasHome, setBlocked, goBlocked, fromEstop };
}

/** "Set Home at current position" (asks before replacing an existing Home). */
export function SetHomeButton({
  compact = false,
  label,
  className,
  onDone,
}: {
  compact?: boolean;
  label?: string;
  className?: string;
  /** After Home was saved (e.g. re-check a program that needed it). */
  onDone?: () => void;
}) {
  const { t } = useTranslation("station");
  const qc = useQueryClient();
  const home = useHomeState();
  const save = useStationMutation(() => api.post("/robots/rest-pose"), [qk.robots]);
  const text = label ?? (compact ? t("home.set_short") : t("home.set"));
  const blocked = home.setBlocked;
  const common = {
    variant: "outline" as const,
    size: compact ? ("sm" as const) : ("default" as const),
    disabled: blocked !== null || save.isPending,
    "aria-label": compact ? t("home.set") : undefined,
    className,
    "data-testid": "set-home",
  };
  const body = (
    <>
      <PxIcon name="pin" /> <span className={cn(compact && "hidden lg:inline")}>{text}</span>
    </>
  );
  return (
    <span className="inline-flex flex-col gap-1" title={blocked ?? t("home.set_title")}>
      {home.hasHome ? (
        <ConfirmButton
          {...common}
          title={t("home.replace_title")}
          description={t("home.replace_text")}
          confirmLabel={t("home.replace_ok")}
          onConfirm={async () => {
            await save.mutateAsync(undefined);
            await qc.invalidateQueries({ queryKey: qk.robots });
            onDone?.();
          }}
        >
          {body}
        </ConfirmButton>
      ) : (
        <Button
          {...common}
          onClick={() => {
            save.mutate(undefined, { onSuccess: () => onDone?.() });
          }}
        >
          {body}
        </Button>
      )}
      {!compact ? <StationError error={save.error} /> : null}
    </span>
  );
}

/** "Return Home": the slow rest move (from a user e-stop: reset the latch, then move). */
export function GoHomeButton({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t } = useTranslation("station");
  const home = useHomeState();
  const go = useStationMutation(async () => {
    if (home.fromEstop) await api.post<Status>("/estop/reset");
    return api.post<Session>("/robots/rest");
  });
  const blocked = home.goBlocked;
  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        size={compact ? "sm" : "default"}
        variant={compact ? "outline" : "default"}
        disabled={blocked !== null || go.isPending}
        title={blocked ?? t("home.go_title", { speed: AUTO_MOVE_SPEED_DEG_S })}
        aria-label={compact ? t("home.go") : undefined}
        className={className}
        data-testid="go-home"
        onClick={() => {
          go.mutate(undefined);
        }}
      >
        <PxIcon name="undo" /> <span className={cn(compact && "hidden lg:inline")}>{t("home.go")}</span>
      </Button>
      {!compact ? <StationError error={go.error} /> : null}
    </span>
  );
}

/** "Relax": torque off after the operator confirms they support the arm (D-6). */
export function RelaxButton({ className }: { className?: string }) {
  const { t } = useTranslation("station");
  const relax = useStationMutation(() =>
    api.post<Status>("/robots/torque", { arm: "follower", enabled: false, confirm: true }),
  );
  return (
    <ConfirmButton
      variant="outline"
      className={className}
      data-testid="relax"
      title={t("relax.confirm_title")}
      description={t("relax.confirm_text")}
      confirmLabel={t("relax.confirm_ok")}
      destructive
      onConfirm={async () => {
        await relax.mutateAsync(undefined);
      }}
    >
      {t("relax.button")}
    </ConfirmButton>
  );
}

/** Set Home + Return Home, for the top bar (compact) and the Robot 3D panel. */
export function HomeControls({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t } = useTranslation("station");
  const home = useHomeState();
  if (!home.connected) return null;
  return (
    <div
      className={cn("flex flex-wrap items-start gap-2", className)}
      role="group"
      aria-label={t("home.group")}
      data-testid={compact ? "home-bar" : "home-panel"}
    >
      <SetHomeButton compact={compact} />
      <GoHomeButton compact={compact} />
    </div>
  );
}
