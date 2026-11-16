/** Teleop (§6.5) and Replay: the shared running view with start/stop, timer and loop stats. */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { api, StationApiError } from "../api/client";
import { useStationMutation } from "../api/hooks";
import type { Session } from "../api/types";
import { LiveLayout } from "../components/LiveLayout";
import { LatencyReadout, LoopStats, SessionTimer } from "../components/SessionWidgets";
import { StationError } from "../components/StationError";
import { AUTO_MOVE_SPEED_DEG_S, useCritical, useSessionControl } from "../components/controls";
import { useStatus } from "../ws/StationProvider";

function LiveHeader({ session, extra }: { session: Session | null; extra?: ReactNode }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const control = useSessionControl();
  const critical = useCritical();
  return (
    <Card>
      <CardContent className="grid gap-4 pt-3 sm:pt-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,14rem)]">
        <div className="min-w-0">
          {session ? <SessionTimer session={session} /> : extra}
          {session?.kind === "teleop" ? <LatencyReadout /> : null}
          {session && status?.sub === "align" ? (
            <p
              role="status"
              data-testid="teleop-aligning"
              className="mt-2 border-2 border-frame bg-warning px-2 py-1 text-sm text-warning-foreground"
            >
              {t("teleop.aligning")}
            </p>
          ) : null}
          {session && status?.sub === "approach" ? (
            <p
              role="status"
              className="mt-2 border-2 border-frame bg-warning px-2 py-1 text-sm text-warning-foreground"
            >
              {t("teleop.approach")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          {session ? (
            <Button
              size="lg"
              variant="destructive"
              disabled={critical || !session.controls.stop}
              aria-keyshortcuts="Escape"
              onClick={() => {
                control("stop");
              }}
            >
              <PxIcon name="stop" /> {t("controls.stop")}
            </Button>
          ) : null}
        </div>
        <LoopStats targetFps={session?.fps ?? 30} />
      </CardContent>
    </Card>
  );
}

/** Teleop sends the leader pose every tick (LeLab runs free at ~250 Hz); a slow bus just runs slower. */
export const TELEOP_FPS = 250;

/** A refused start because the leader is far from the follower, and the session can align instead. */
export function canAlign(error: unknown): boolean {
  return error instanceof StationApiError && error.code === "leader_far" && error.params.can_align === true;
}
const TELEOP_FPS_OPTIONS = [30, 60, 120, TELEOP_FPS];

export function TeleopPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const [fps, setFps] = useState(TELEOP_FPS);
  const start = useStationMutation((req: { fps: number; align?: boolean }) =>
    api.post<Session>("/sessions/teleop", req),
  );
  const session = status?.session?.kind === "teleop" ? status.session : null;
  const canStart = status?.state === "idle";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("teleop.title")} description={t("teleop.desc")} />
      {!session ? (
        <Card>
          <CardContent className="flex flex-wrap items-end gap-3 pt-3 sm:pt-4">
            <Field label={t("record.fps")}>
              <NativeSelect
                value={fps}
                onChange={(e) => {
                  setFps(Number(e.target.value));
                }}
              >
                {TELEOP_FPS_OPTIONS.map((f) => (
                  <option key={f} value={f}>
                    {f === TELEOP_FPS ? t("teleop.fps_max", { fps: f }) : f}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Button
              size="lg"
              disabled={!canStart || start.isPending}
              onClick={() => {
                start.mutate({ fps });
              }}
            >
              <PxIcon name="play" /> {t("teleop.start")}
            </Button>
            {!canStart ? <p className="text-sm text-muted-foreground">{t("teleop.not_idle")}</p> : null}
            <StationError error={start.error} className="w-full" />
            {canAlign(start.error) ? (
              <div
                className="flex w-full flex-col gap-2 border-2 border-frame bg-card p-3"
                data-testid="align-offer"
              >
                <p className="font-extrabold">{t("teleop.align_title")}</p>
                <p className="text-sm">{t("teleop.align_hint", { speed: AUTO_MOVE_SPEED_DEG_S })}</p>
                <Button
                  className="self-start"
                  disabled={!canStart || start.isPending}
                  onClick={() => {
                    start.mutate({ fps, align: true });
                  }}
                >
                  <PxIcon name="play" /> {t("teleop.align")}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      <LiveLayout header={<LiveHeader session={session} />} />
    </div>
  );
}

export function ReplayPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const session = status?.session?.kind === "replay" ? status.session : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("replay.title")} description={t("replay.desc")} />
      {session ? (
        <LiveLayout arms={["follower"]} header={<LiveHeader session={session} extra={null} />} />
      ) : (
        <p className="text-sm">
          {t("replay.idle")}{" "}
          <Link to="/datasets" className="underline">
            {t("nav.datasets")}
          </Link>
        </p>
      )}
    </div>
  );
}
