/**
 * After a Stop (CR-1, 2026-11-17) or an e-stop / safe stop that ended a motion
 * (`Status.interrupted`): the arm holds where it stopped. Offer "Return Home" (one slow
 * minimum-jerk move, dead-man on, Space / Stop halts it) and "Relax" (support the arm first,
 * D-6); without a Home, "Set Home at current position". While the move runs (session kind
 * `rest`) the banner shows its progress and a Stop button.
 */
import { useTranslation } from "react-i18next";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Button } from "@/components/ui/button";
import type { Status } from "../api/types";
import { levelCss } from "../health";
import { AUTO_MOVE_SPEED_DEG_S, useSessionControl } from "./controls";
import { GoHomeButton, RelaxButton, SetHomeButton, useHomeState } from "./HomeControls";

export function RestBanner({ status }: { status: Status }) {
  const { t } = useTranslation("station");
  const control = useSessionControl();
  const home = useHomeState();
  const resting = status.session?.kind === "rest";
  const offer = status.state === "idle" && status.interrupted === true && Boolean(status.robot?.connected);
  if (!resting && !offer) return null;
  if (resting) {
    return (
      <div
        role="status"
        data-testid="rest-banner"
        data-phase="moving"
        className="flex flex-wrap items-center gap-3 border-4 px-3 py-2"
        style={levelCss("warn")}
      >
        <PxIcon name="robot" />
        <p className="min-w-0 flex-1 text-sm font-bold">{t("banner.resting")}</p>
        <Button
          variant="destructive"
          onClick={() => {
            control("stop");
          }}
        >
          <PxIcon name="stop" /> {t("banner.rest_stop")}
        </Button>
      </div>
    );
  }
  const torqueOn = status.robot?.follower_torque ?? false;
  return (
    <div
      role="status"
      data-testid="rest-banner"
      data-phase="offer"
      className="flex flex-col gap-2 border-4 border-frame bg-card px-3 py-3"
    >
      <p className="font-extrabold">{t("banner.interrupted")}</p>
      <p className="text-sm">{t("banner.interrupted_hint")}</p>
      <div className="flex flex-wrap items-start gap-2">
        {home.hasHome ? <GoHomeButton /> : <SetHomeButton />}
        {torqueOn ? <RelaxButton /> : null}
      </div>
      {home.hasHome ? (
        <p className="text-xs text-muted-foreground">
          {t("banner.rest_hint", { speed: AUTO_MOVE_SPEED_DEG_S })}
        </p>
      ) : (
        <p className="text-sm">{t("banner.rest_need_pose")}</p>
      )}
      {!torqueOn ? (
        <p className="text-sm font-bold" data-testid="support-arm">
          {t("banner.support_arm")}
        </p>
      ) : null}
    </div>
  );
}
