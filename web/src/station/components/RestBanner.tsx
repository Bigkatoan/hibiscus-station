/**
 * "Return to rest pose" (field report 0.2.8). After an e-stop / safe stop ended a motion
 * (`Status.interrupted`) and the operator reset the latch, the arm stands where it froze: offer one
 * slow minimum-jerk move to the profile's rest pose (dead-man on, Space / Stop halts it). While that
 * move runs (session kind `rest`) the banner shows its progress and a Stop button.
 */
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Button } from "@/components/ui/button";
import { api } from "../api/client";
import { useRobots, useStationMutation } from "../api/hooks";
import type { Session, Status } from "../api/types";
import { levelCss } from "../health";
import { AUTO_MOVE_SPEED_DEG_S, useSessionControl } from "./controls";
import { StationError } from "./StationError";

export function RestBanner({ status }: { status: Status }) {
  const { t } = useTranslation("station");
  const robots = useRobots();
  const control = useSessionControl();
  const go = useStationMutation(() => api.post<Session>("/robots/rest"));
  const resting = status.session?.kind === "rest";
  const offer = status.state === "idle" && status.interrupted === true && Boolean(status.robot?.connected);
  if (!resting && !offer) return null;
  const profile = robots.data?.robots.find((r) => r.id === status.robot?.id) ?? null;
  const hasRest = Boolean(profile?.follower.rest_pose && Object.keys(profile.follower.rest_pose).length);
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
  return (
    <div
      role="status"
      data-testid="rest-banner"
      data-phase="offer"
      className="flex flex-col gap-2 border-4 border-frame bg-card px-3 py-3"
    >
      <p className="font-extrabold">{t("banner.interrupted")}</p>
      <p className="text-sm">{t("banner.interrupted_hint")}</p>
      {hasRest ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => {
              go.mutate(undefined);
            }}
            disabled={go.isPending}
          >
            <PxIcon name="undo" /> {t("banner.rest")}
          </Button>
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            {t("banner.rest_hint", { speed: AUTO_MOVE_SPEED_DEG_S })}
          </p>
        </div>
      ) : (
        <p className="text-sm">
          {t("banner.rest_need_pose")}{" "}
          <Link to="/robot" className="underline">
            {t("nav.robot")}
          </Link>
        </p>
      )}
      <StationError error={go.error} />
    </div>
  );
}
