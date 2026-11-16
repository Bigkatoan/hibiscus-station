/**
 * A serial device that went away while connected (state `error`, reason `device_lost`; field
 * report 0.2.5: "Access is denied" on COM8). Says what happened in plain words, what to check, and
 * offers "Reconnect", which waits for the USB adapter to come back (maybe under a new COM number)
 * and connects again, writing the calibration back to the motors.
 */
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { api } from "../api/client";
import { qk, useStationMutation } from "../api/hooks";
import type { ReconnectResult, Status } from "../api/types";
import { levelCss } from "../health";
import { StationError } from "./StationError";

export function DeviceLostBanner({ status }: { status: Status }) {
  const { t } = useTranslation("station");
  const lost = status.lost;
  const reconnect = useStationMutation(
    () => api.post<ReconnectResult>("/robots/reconnect", { timeout_s: 30 }),
    [qk.robots, qk.calibrations],
  );
  const arm = lost ? t(`arm.${lost.arm}`) : t("arm.follower");
  const port = lost?.port ?? "";
  const windows = /^COM\d+$/i.test(port);
  const changed = reconnect.data ? Object.entries(reconnect.data.port_changes) : [];
  return (
    <div
      role="alert"
      data-testid="device-lost"
      className="flex flex-col gap-3 border-4 px-3 py-3"
      style={levelCss("critical")}
    >
      <div className="flex items-start gap-3">
        <PxIcon name="plug" className="mt-1 shrink-0" />
        <div className="min-w-0">
          <p className="font-extrabold">{t("lost.title", { arm, port })}</p>
          <p className="mt-1 text-sm">{t("lost.what")}</p>
        </div>
      </div>
      {lost?.after_torque_on ? (
        <p className="border-2 border-current px-2 py-1 text-sm font-bold" data-testid="lost-jump-hint">
          {t("lost.jump_hint")}
        </p>
      ) : null}
      <ul className="list-disc pl-6 text-sm">
        <li>{t("lost.check_cable", { arm })}</li>
        <li>{t("lost.check_power")}</li>
        <li>{t("lost.check_other")}</li>
        {windows ? <li>{t("lost.check_suspend")}</li> : null}
        <li>{t("lost.check_replug")}</li>
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          disabled={reconnect.isPending}
          onClick={() => {
            reconnect.mutate(undefined);
          }}
        >
          <PxIcon name={reconnect.isPending ? "spinner" : "refresh"} /> {t("lost.reconnect")}
        </Button>
        {reconnect.isPending ? <span className="text-sm">{t("lost.waiting")}</span> : null}
      </div>
      {changed.length ? (
        <p className="text-sm">
          {changed.map(([a, dev]) => t("lost.new_port", { arm: t(`arm.${a}`), port: dev })).join(" ")}
        </p>
      ) : null}
      <StationError error={reconnect.error} />
      {lost?.error ? (
        <p className="break-words font-mono text-xs opacity-80">
          {t("lost.os_said")} {lost.error}
        </p>
      ) : null}
    </div>
  );
}
