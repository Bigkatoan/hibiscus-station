/**
 * Calibrate (§6.3): per arm, reuse the existing lerobot calibration file or recalibrate in two
 * guided steps — Home (Hibi + pixel SO-101 at mid pose) and Ranges (live min | pos | max bars).
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Mascot } from "@/components/Mascot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { api } from "../api/client";
import { qk, useCalibrations, useRobots, useStationMutation } from "../api/hooks";
import type { Arm, CalibrationMotor, CalibrationMsg, RobotProfile, Status } from "../api/types";
import { StationError } from "../components/StationError";
import { Sprite } from "@/hibiscus/PixelAnim";
import { useStation, useStatus } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";

export const MIN_RANGE_STEPS = 100;
const FULL_TURN = ["wrist_roll"];
const STEPS = 4096;

function RangeRow({ motor, r: raw }: { motor: string; r: CalibrationMotor }) {
  const { t } = useTranslation("station");
  const r = { min: raw.min ?? 0, pos: raw.pos ?? 0, max: raw.max ?? raw.min ?? 0 };
  const full = FULL_TURN.includes(motor);
  const ok = full || r.max - r.min >= MIN_RANGE_STEPS;
  const left = (r.min / STEPS) * 100;
  const width = (Math.max(0, r.max - r.min) / STEPS) * 100;
  return (
    <li
      className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-2 text-sm sm:grid-cols-[9rem_minmax(0,1fr)_10rem]"
      data-testid={`range-${motor}`}
      data-ok={ok}
    >
      <span className="truncate">{motor}</span>
      <span className="relative h-4 border-2 border-frame bg-muted" aria-hidden>
        {!full ? (
          <span
            className="absolute inset-y-0"
            style={{ left: `${left}%`, width: `${width}%`, backgroundColor: ok ? "#5fa04e" : "#ffc531" }}
          />
        ) : null}
        <span
          className="absolute inset-y-0 w-1 bg-[#3b2027]"
          style={{ left: `calc(${(r.pos / STEPS) * 100}% - 2px)` }}
        />
      </span>
      <span className="col-span-2 tabular-nums text-xs sm:col-span-1">
        {full ? t("calibrate.full_turn") : `${r.min} | ${r.pos} | ${r.max}`}
        {!ok ? <span className="ml-1 text-destructive">{t("calibrate.too_small")}</span> : null}
      </span>
    </li>
  );
}

const selCal = (s: StationSnapshot) => s.calibration;

function Wizard({ arm, cal, status }: { arm: Arm; cal: CalibrationMsg | null; status: Status | null }) {
  const { t } = useTranslation("station");
  const step = useStationMutation(
    (action: "set_home" | "finish_ranges" | "cancel") => api.post<Status>("/calibration/step", { action }),
    [qk.calibrations],
  );
  const calibrating = status?.state === "calibrating";
  const sub =
    cal?.arm === arm ? cal.step : calibrating ? (status.sub as CalibrationMsg["step"] | null) : null;

  if (sub === "done" || (!calibrating && cal?.arm === arm && cal.step === "done")) {
    return (
      <div className="flex flex-wrap items-center gap-4" data-testid="cal-done">
        <Mascot mood="happy" />
        <div className="min-w-0 flex-1">
          <p className="font-extrabold text-base">{t("calibrate.done", { arm: t(`arm.${arm}`) })}</p>
          {cal?.path ? <p className="break-all font-mono text-xs">{cal.path}</p> : null}
        </div>
        <Button asChild>
          <Link to="/cameras">{t("calibrate.next")}</Link>
        </Button>
      </div>
    );
  }
  if (!calibrating) return null;
  return (
    <div className="flex flex-col gap-4">
      {arm === "follower" ? (
        <p
          role="alert"
          className="border-4 border-[#f08a24] bg-[#ffc531] px-3 py-2 text-sm font-bold text-[#3b2027]"
        >
          {t("calibrate.limp")}
        </p>
      ) : null}
      <ol className="flex gap-2 text-sm">
        <li>
          <Badge variant={sub === "home" ? "default" : "outline"}>1 · {t("calibrate.step_home")}</Badge>
        </li>
        <li>
          <Badge variant={sub === "ranges" ? "default" : "outline"}>2 · {t("calibrate.step_ranges")}</Badge>
        </li>
      </ol>
      {sub === "home" || sub === null ? (
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center" data-testid="cal-home">
          <div className="flex items-end gap-2">
            <Sprite name="arm_home" alt={t("calibrate.arm_alt")} />
            <Mascot mood="idle" />
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-sm">{t("calibrate.home_text")}</p>
            <Button
              size="lg"
              onClick={() => {
                step.mutate("set_home");
              }}
              disabled={step.isPending}
            >
              {t("calibrate.set_home")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3" data-testid="cal-ranges">
          <div className="flex items-center gap-3">
            <Mascot mood="working" size="mini" />
            <p className="text-sm">{t("calibrate.ranges_text")}</p>
          </div>
          <ul className="flex flex-col gap-2">
            {Object.entries(cal?.motors ?? {}).map(([m, r]) => (
              <RangeRow key={m} motor={m} r={r} />
            ))}
          </ul>
          {(cal?.warnings ?? []).map((w) => (
            <p key={w} className="text-sm text-destructive">
              {w}
            </p>
          ))}
          <Button
            size="lg"
            className="self-start"
            onClick={() => {
              step.mutate("finish_ranges");
            }}
            disabled={step.isPending}
          >
            {t("calibrate.finish")}
          </Button>
        </div>
      )}
      <StationError error={step.error} />
      <Button
        variant="ghost"
        className="self-start"
        onClick={() => {
          step.mutate("cancel");
        }}
      >
        {t("common.cancel")}
      </Button>
    </div>
  );
}

function ArmPanel({ arm, profile }: { arm: Arm; profile: RobotProfile }) {
  const { t, i18n } = useTranslation("station");
  const status = useStatus();
  const cal = useStation(selCal);
  const files = useCalibrations();
  const calId = arm === "follower" ? profile.follower.calibration_id : (profile.leader?.calibration_id ?? "");
  const existing = files.data?.files.find((f) => f.arm === arm && f.id === calId);
  const start = useStationMutation(
    (keep: boolean) => api.post<Status>("/calibration/start", { arm, id: calId, keep_existing: keep }),
    [qk.calibrations],
  );
  const calibrated = Boolean(status?.robot?.arms[arm]?.calibrated);
  const idle = status?.state === "idle";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Sprite name="icon_calibrate" />
        <span className="font-mono">{calId}</span>
        {calibrated ? (
          <Badge variant="success">{t("calibrate.calibrated")}</Badge>
        ) : (
          <Badge variant="warning">{t("calibrate.not_calibrated")}</Badge>
        )}
      </div>
      {existing ? (
        <p className="text-sm">
          {t("calibrate.existing", { date: formatDateTime(existing.modified_at, i18n.language) })}
          <br />
          <span className="break-all font-mono text-xs text-muted-foreground">{existing.path}</span>
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">{t("calibrate.no_file")}</p>
      )}
      {status?.state !== "calibrating" ? (
        <div className="flex flex-wrap gap-2">
          {existing ? (
            <Button
              variant="outline"
              disabled={!idle || start.isPending}
              onClick={() => {
                start.mutate(true);
              }}
            >
              {t("calibrate.use_existing")}
            </Button>
          ) : null}
          <Button
            disabled={!idle || start.isPending}
            onClick={() => {
              start.mutate(false);
            }}
          >
            {existing ? t("calibrate.recalibrate") : t("calibrate.start")}
          </Button>
        </div>
      ) : null}
      <StationError error={start.error} />
      <Wizard arm={arm} cal={cal} status={status} />
    </div>
  );
}

export function CalibratePage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const robots = useRobots();
  const profile = robots.data?.robots.find((r) => r.id === status?.robot?.id);
  const [tab, setTab] = useState<Arm>("follower");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("calibrate.title")} description={t("calibrate.desc")} />
      {!profile || !status?.robot?.connected ? (
        <p className="text-sm">
          {t("lock.connect_first")}{" "}
          <Link to="/robot" className="underline">
            {t("nav.robot")}
          </Link>
        </p>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{profile.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs
              value={tab}
              onValueChange={(v) => {
                setTab(v as Arm);
              }}
            >
              <TabsList>
                <TabsTrigger value="follower">{t("arm.follower")}</TabsTrigger>
                {profile.leader ? <TabsTrigger value="leader">{t("arm.leader")}</TabsTrigger> : null}
              </TabsList>
              <TabsContent value="follower" className="pt-4">
                <ArmPanel arm="follower" profile={profile} />
              </TabsContent>
              {profile.leader ? (
                <TabsContent value="leader" className="pt-4">
                  <ArmPanel arm="leader" profile={profile} />
                </TabsContent>
              ) : null}
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
