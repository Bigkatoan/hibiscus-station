/**
 * Calibrate (§6.3), as simple as LeLab (field report 0.2.5): one guided flow, follower → leader →
 * pose check → teleop.
 *
 * On entering, Station reads every arm's EEPROM (`GET /calibration/check`): an arm that is
 * calibrated says so in green ("use it"); an arm whose motors already carry a file on disk (LeLab's
 * `so_101_follower.json`…) offers exactly that file in one click; only the "Advanced" disclosure
 * lists every file, and never a file of the other arm. Otherwise the two-step wizard: Home (picture),
 * then Ranges with a live bar and a tick per joint, Save enabled only when every joint moved enough.
 * The last step compares both arms held in the same pose (`GET /calibration/compare`) and warns
 * about a wrong file or swapped roles before teleop.
 */
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Mascot } from "@/components/Mascot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PxIcon, Sprite } from "@/hibiscus/PixelAnim";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { api } from "../api/client";
import { qk, useCalibrationCheck, useRobots, useStationMutation } from "../api/hooks";
import type {
  Arm,
  ArmCalibrationCheck,
  CalibrationCandidate,
  CalibrationMotor,
  CalibrationMsg,
  PoseCompare,
  RobotProfile,
  Status,
} from "../api/types";
import { StationError } from "../components/StationError";
import { useStation, useStatus } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";

export const MIN_RANGE_STEPS = 100;
const STEPS = 4096;

type StepKey = Arm | "check";

const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

// ------------------------------------------------------------------ the wizard
function RangeRow({ motor, r: raw, min }: { motor: string; r: CalibrationMotor; min: number }) {
  const { t } = useTranslation("station");
  const r = { min: raw.min ?? 0, pos: raw.pos ?? 0, max: raw.max ?? raw.min ?? 0 };
  const full = raw.full_turn;
  const ok = full || (raw.ok ?? r.max - r.min >= min);
  const left = (r.min / STEPS) * 100;
  const width = (Math.max(0, r.max - r.min) / STEPS) * 100;
  return (
    <li
      className="grid grid-cols-[1.5rem_6.5rem_minmax(0,1fr)] items-center gap-2 text-sm sm:grid-cols-[1.5rem_9rem_minmax(0,1fr)_8rem]"
      data-testid={`range-${motor}`}
      data-ok={ok}
    >
      <span
        className={cn(
          "inline-flex size-6 items-center justify-center border-2 border-frame",
          ok ? "bg-success text-success-foreground" : "bg-card text-muted-foreground",
        )}
        aria-label={ok ? t("calibrate.joint_done") : t("calibrate.joint_todo")}
        role="img"
      >
        {ok ? <PxIcon name="check" /> : null}
      </span>
      <span className={cn("truncate", ok ? "font-bold" : "")}>{motor}</span>
      <span className="relative h-4 border-2 border-frame bg-muted" aria-hidden>
        {!full ? (
          <span
            className={cn("absolute inset-y-0", ok ? "bg-success" : "bg-warning")}
            style={{ left: `${left}%`, width: `${width}%` }}
          />
        ) : null}
        <span
          className="absolute inset-y-0 w-1 bg-foreground"
          style={{ left: `calc(${(r.pos / STEPS) * 100}% - 2px)` }}
        />
      </span>
      <span className="col-span-3 pl-8 tabular-nums text-xs text-muted-foreground sm:col-span-1 sm:pl-0">
        {full ? t("calibrate.full_turn") : `${r.min} | ${r.pos} | ${r.max}`}
      </span>
    </li>
  );
}

const selCal = (s: StationSnapshot) => s.calibration;

function Wizard({
  arm,
  cal,
  status,
  onDone,
}: {
  arm: Arm;
  cal: CalibrationMsg | null;
  status: Status | null;
  onDone: () => void;
}) {
  const { t } = useTranslation("station");
  const step = useStationMutation(
    (action: "set_home" | "finish_ranges" | "cancel") => api.post<Status>("/calibration/step", { action }),
    [qk.calibrations],
  );
  const sub = cal?.arm === arm ? cal.step : (status?.sub as CalibrationMsg["step"] | null);
  const motors = Object.entries(cal?.arm === arm ? cal.motors : {});
  const min = cal?.min_range ?? MIN_RANGE_STEPS;
  const done = motors.filter(([, r]) => r.full_turn || (r.ok ?? false)).length;
  const ready = Boolean(cal?.ready) && motors.length > 0;
  return (
    <div className="flex flex-col gap-4" data-testid={`wizard-${arm}`}>
      {arm === "follower" ? (
        <p
          role="alert"
          className="border-4 border-frame bg-warning px-3 py-2 text-sm font-bold text-warning-foreground"
        >
          {t("calibrate.limp")}
        </p>
      ) : null}
      <ol className="flex flex-wrap gap-2 text-sm">
        <li>
          <Badge variant={sub === "home" || !sub ? "default" : "outline"}>
            1 · {t("calibrate.step_home")}
          </Badge>
        </li>
        <li>
          <Badge variant={sub === "ranges" ? "default" : "outline"}>2 · {t("calibrate.step_ranges")}</Badge>
        </li>
      </ol>
      {sub === "home" || !sub ? (
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center" data-testid="cal-home">
          <div className="flex items-end gap-2">
            <Sprite name="arm_home" alt={t("calibrate.arm_alt")} />
            <Mascot mood="idle" size="mini" />
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <p className="font-extrabold">{t("calibrate.home_title")}</p>
            <p className="text-sm">{t("calibrate.home_text")}</p>
            <Button
              size="lg"
              className="self-start"
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
          <div className="flex items-start gap-3">
            <Mascot mood="working" size="mini" />
            <div className="min-w-0">
              <p className="font-extrabold">{t("calibrate.ranges_title")}</p>
              <p className="text-sm">{t("calibrate.ranges_text")}</p>
            </div>
          </div>
          <ul className="flex flex-col gap-2" aria-label={t("calibrate.checklist")}>
            {motors.map(([m, r]) => (
              <RangeRow key={m} motor={m} r={r} min={min} />
            ))}
          </ul>
          <p className="text-sm font-bold" data-testid="cal-progress">
            {t("calibrate.progress", { done, total: motors.length })}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="lg"
              onClick={() => {
                // The wizard unmounts as soon as the status says "idle": a promise, not a mutate callback.
                step.mutateAsync("finish_ranges").then(onDone, () => undefined);
              }}
              disabled={step.isPending || !ready}
            >
              <PxIcon name="check" /> {t("calibrate.finish")}
            </Button>
            {!ready ? (
              <span className="text-xs text-muted-foreground">{t("calibrate.finish_hint")}</span>
            ) : null}
          </div>
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

// ------------------------------------------------------------------ one arm
function Box({
  tone,
  mood,
  title,
  children,
  testid,
}: {
  tone: "success" | "info" | "warning";
  mood: "happy" | "idle" | "sad" | "working";
  title: string;
  children?: ReactNode;
  testid?: string;
}) {
  const border = { success: "border-l-success", info: "border-l-info", warning: "border-l-warning" }[tone];
  return (
    <div
      className={cn("flex items-start gap-3 border-2 border-l-8 border-frame bg-card p-3", border)}
      data-testid={testid}
    >
      <Mascot mood={mood} size="mini" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="text-base font-extrabold">{title}</p>
        {children}
      </div>
    </div>
  );
}

function FileRow({
  f,
  arm,
  disabled,
  onUse,
}: {
  f: CalibrationCandidate;
  arm: Arm;
  disabled: boolean;
  onUse: (path: string) => void;
}) {
  const { t, i18n } = useTranslation("station");
  const other = arm === "follower" ? "leader" : "follower";
  return (
    <li className="flex flex-wrap items-center gap-2 border-b-2 border-dashed border-frame/40 py-2 last:border-b-0">
      <span className="min-w-0 break-all font-mono text-sm">{fileName(f.path)}</span>
      <span className="text-xs text-muted-foreground">
        {f.dir} · {formatDateTime(f.modified_at, i18n.language)}
      </span>
      {f.own ? <Badge variant="outline">{t("calibrate.badge_own")}</Badge> : null}
      {f.matches_motors ? <Badge variant="success">{t("calibrate.badge_motors")}</Badge> : null}
      {f.matches_other_arm ? (
        <Badge variant="warning">{t("calibrate.badge_other_arm", { arm: t(`arm.${other}`) })}</Badge>
      ) : null}
      {!f.valid ? <Badge variant="destructive">{t("calibrate.badge_invalid")}</Badge> : null}
      {!f.own ? (
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={disabled || f.matches_other_arm || !f.valid}
          onClick={() => {
            onUse(f.path);
          }}
        >
          {t("calibrate.use_file")}
        </Button>
      ) : null}
    </li>
  );
}

function ArmStep({
  arm,
  profile,
  check,
  checkError,
  checking,
  arrived,
  next,
  onDone,
}: {
  arm: Arm;
  profile: RobotProfile;
  check: ArmCalibrationCheck | null;
  checkError: unknown;
  checking: boolean;
  arrived: boolean;
  next: { label: string; go: () => void } | { label: string; to: string };
  onDone: () => void;
}) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const cal = useStation(selCal);
  const calId = arm === "follower" ? profile.follower.calibration_id : (profile.leader?.calibration_id ?? "");
  const start = useStationMutation(
    () => api.post<Status>("/calibration/start", { arm, id: calId, keep_existing: false }),
    [qk.calibrations],
  );
  const adopt = useStationMutation(
    (source: string) => api.post<Status>("/calibration/start", { arm, id: calId, source }),
    [qk.calibrations],
  );
  const keep = useStationMutation(
    () => api.post<Status>("/calibration/start", { arm, id: calId, keep_existing: true }),
    [qk.calibrations],
  );
  const idle = status?.state === "idle";
  const calibrating = status?.state === "calibrating";
  const busyArm = calibrating && cal?.step !== "done" ? (cal?.arm ?? null) : null;
  const calibrated = Boolean(status?.robot?.arms[arm]?.calibrated);
  const armName = t(`arm.${arm}`);

  if (calibrating && (busyArm === arm || busyArm === null)) {
    return <Wizard arm={arm} cal={cal} status={status} onDone={onDone} />;
  }

  const recalibrate = (
    <Button
      variant="outline"
      disabled={!idle || start.isPending}
      onClick={() => {
        start.mutate(undefined);
      }}
    >
      <PxIcon name="refresh" /> {t("calibrate.recalibrate")}
    </Button>
  );
  const nextButton =
    "to" in next ? (
      <Button asChild>
        <Link to={next.to}>
          {next.label} <PxIcon name="arrow_right" />
        </Link>
      </Button>
    ) : (
      <Button onClick={next.go}>
        {next.label} <PxIcon name="arrow_right" />
      </Button>
    );

  const state = check?.state ?? (calibrated ? "ok" : null);
  let main: ReactNode;
  if (state === "ok") {
    main = (
      <Box
        tone="success"
        mood="happy"
        title={t("calibrate.ok_title", { arm: armName })}
        testid={`cal-ok-${arm}`}
      >
        <p className="text-sm">{t("calibrate.ok_text")}</p>
        {check ? (
          <p className="break-all font-mono text-xs text-muted-foreground">{fileName(check.file)}</p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {nextButton}
          {recalibrate}
        </div>
      </Box>
    );
  } else if (state === "adopt" && check?.suggestion) {
    const s = check.suggestion;
    main = (
      <Box
        tone="info"
        mood="idle"
        title={t("calibrate.adopt_title", { file: fileName(s.path) })}
        testid={`cal-adopt-${arm}`}
      >
        <p className="text-sm">{t("calibrate.adopt_text", { own: fileName(check.file) })}</p>
        <p className="break-all font-mono text-xs text-muted-foreground">{s.path}</p>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!idle || adopt.isPending}
            onClick={() => {
              adopt.mutateAsync(s.path).then(onDone, () => undefined);
            }}
          >
            <PxIcon name="check" /> {t("calibrate.adopt_use")}
          </Button>
          {recalibrate}
        </div>
      </Box>
    );
  } else if (state === "mismatch") {
    main = (
      <Box
        tone="warning"
        mood="sad"
        title={t("calibrate.mismatch_title", { arm: armName })}
        testid={`cal-mismatch-${arm}`}
      >
        <p className="text-sm">{t("calibrate.mismatch_text")}</p>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!idle || start.isPending}
            onClick={() => {
              start.mutate(undefined);
            }}
          >
            {t("calibrate.start")}
          </Button>
          <Button
            variant="outline"
            disabled={!idle || keep.isPending}
            onClick={() => {
              keep.mutateAsync(undefined).then(onDone, () => undefined);
            }}
          >
            {t("calibrate.retry_write")}
          </Button>
        </div>
      </Box>
    );
  } else if (state === "needs_calibration" || (!checking && !calibrated)) {
    main = (
      <Box
        tone="warning"
        mood="idle"
        title={t("calibrate.needs_title", { arm: armName })}
        testid={`cal-needs-${arm}`}
      >
        <p className="text-sm">{t("calibrate.needs_text")}</p>
        <Button
          size="lg"
          className="self-start"
          disabled={!idle || start.isPending}
          onClick={() => {
            start.mutate(undefined);
          }}
        >
          <Sprite name="icon_calibrate" /> {t("calibrate.start")}
        </Button>
      </Box>
    );
  } else {
    main = <Box tone="info" mood="working" title={t("calibrate.checking")} testid={`cal-checking-${arm}`} />;
  }

  const files = check?.files ?? [];
  const issue = check?.issue ?? status?.robot?.arms[arm]?.issue;
  return (
    <div className="flex flex-col gap-4">
      {arrived ? (
        <p className="flex items-center gap-2 text-sm font-bold" data-testid={`cal-now-${arm}`}>
          <PxIcon name="arrow_right" /> {t("calibrate.now_arm", { arm: armName })}
        </p>
      ) : null}
      {main}
      {busyArm && busyArm !== arm ? (
        <p className="text-sm text-muted-foreground">
          {t("calibrate.other_busy", { arm: t(`arm.${busyArm}`) })}
        </p>
      ) : null}
      <StationError error={start.error ?? adopt.error ?? keep.error} />
      {checkError ? <StationError error={checkError} /> : null}
      <details
        className="border-2 border-frame bg-card px-3 py-2 text-sm"
        data-testid={`cal-advanced-${arm}`}
      >
        <summary className="cursor-pointer font-bold">{t("calibrate.advanced")}</summary>
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs">
            {t("calibrate.own_file")}{" "}
            <span className="break-all font-mono">
              {check?.file ?? status?.robot?.arms[arm]?.calibration_file ?? calId}
            </span>
          </p>
          {issue ? (
            <p className="text-xs" data-testid={`cal-issue-${arm}`}>
              <span className="font-bold">{t("calibrate.issue")}</span>{" "}
              <span className="break-words font-mono">{issue}</span>
            </p>
          ) : null}
          {files.length > 0 ? (
            <>
              <p>{t("calibrate.other_files", { arm: armName })}</p>
              <ul className="flex flex-col" data-testid={`cal-files-${arm}`}>
                {files.map((f) => (
                  <FileRow
                    key={f.path}
                    f={f}
                    arm={arm}
                    disabled={!idle || adopt.isPending}
                    onUse={(p) => {
                      adopt.mutateAsync(p).then(onDone, () => undefined);
                    }}
                  />
                ))}
              </ul>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">{t("calibrate.no_files")}</p>
          )}
        </div>
      </details>
    </div>
  );
}

// ------------------------------------------------------------------ pose check
function PoseCheck({ onRecalibrate }: { onRecalibrate: (arm: Arm) => void }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const cmp = useMutation({ mutationFn: () => api.get<PoseCompare>("/calibration/compare") });
  const arms = status?.robot?.arms;
  const both = Boolean(arms?.follower.calibrated && arms.leader?.calibrated);
  const r = cmp.data;
  if (!both) {
    return (
      <Box tone="warning" mood="idle" title={t("calibrate.check_need_both")}>
        <div className="flex flex-wrap gap-2">
          {(["follower", "leader"] as const)
            .filter((a) => !arms?.[a]?.calibrated)
            .map((a) => (
              <Button
                key={a}
                variant="outline"
                onClick={() => {
                  onRecalibrate(a);
                }}
              >
                {t(`arm.${a}`)}
              </Button>
            ))}
        </div>
      </Box>
    );
  }
  const unit = (u: string) => (u === "%" ? " %" : "°");
  return (
    <div className="flex flex-col gap-4" data-testid="pose-check">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
        <div className="flex items-end gap-1" aria-hidden>
          <Sprite name="arm_home" />
          <Sprite name="arm_home" />
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <p className="font-extrabold">{t("calibrate.check_title")}</p>
          <p className="text-sm">{t("calibrate.check_text")}</p>
          <Button
            size="lg"
            className="self-start"
            disabled={cmp.isPending || status?.state !== "idle"}
            onClick={() => {
              cmp.mutate();
            }}
          >
            <PxIcon name="compare" /> {r ? t("calibrate.check_again") : t("calibrate.check_run")}
          </Button>
        </div>
      </div>
      <StationError error={cmp.error} />
      {r ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[18rem] border-collapse text-sm" data-testid="pose-table">
              <thead>
                <tr className="border-b-2 border-frame text-left">
                  <th className="py-1 pr-2">{t("calibrate.col_joint")}</th>
                  <th className="py-1 pr-2 text-right">{t("arm.follower")}</th>
                  <th className="py-1 pr-2 text-right">{t("arm.leader")}</th>
                  <th className="py-1 text-right">{t("calibrate.col_diff")}</th>
                </tr>
              </thead>
              <tbody>
                {r.joints.map((j) => (
                  <tr
                    key={j.joint}
                    className={cn("border-b border-frame/30", !j.ok && "bg-destructive/10 font-bold")}
                    data-testid={`pose-${j.joint}`}
                    data-ok={j.ok}
                  >
                    <td className="py-1 pr-2">
                      <span className="inline-flex items-center gap-1">
                        {j.ok ? <PxIcon name="check" /> : <PxIcon name="warning" />} {j.joint}
                      </span>
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">{j.follower.toFixed(1)}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">{j.leader.toFixed(1)}</td>
                    <td className="py-1 text-right tabular-nums">
                      {j.diff.toFixed(1)}
                      {unit(j.unit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.ok ? (
            <Box
              tone="success"
              mood="happy"
              title={t("calibrate.check_ok", { max: r.max_diff.toFixed(1) })}
              testid="pose-ok"
            >
              <Button asChild size="lg" className="self-start">
                <Link to="/teleop">
                  <Sprite name="icon_teleop" /> {t("calibrate.try_teleop")}
                </Link>
              </Button>
            </Box>
          ) : (
            <Box
              tone="warning"
              mood="sad"
              title={t("calibrate.check_bad", { joints: r.off.join(", "), threshold: r.threshold })}
              testid="pose-bad"
            >
              <ul className="list-disc pl-5 text-sm">
                <li>{t("calibrate.check_bad_pose")}</li>
                <li>{t("calibrate.check_bad_file")}</li>
                <li>{t("calibrate.check_bad_roles")}</li>
              </ul>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    onRecalibrate("follower");
                  }}
                >
                  {t("calibrate.redo_arm", { arm: t("arm.follower") })}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    onRecalibrate("leader");
                  }}
                >
                  {t("calibrate.redo_arm", { arm: t("arm.leader") })}
                </Button>
                <Button asChild variant="ghost">
                  <Link to="/teleop">{t("calibrate.teleop_anyway")}</Link>
                </Button>
              </div>
            </Box>
          )}
        </>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ the page
function Stepper({
  steps,
  active,
  done,
  onPick,
  locked,
}: {
  steps: StepKey[];
  active: StepKey;
  done: Record<StepKey, boolean>;
  onPick: (s: StepKey) => void;
  locked: boolean;
}) {
  const { t } = useTranslation("station");
  return (
    <ol className="grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
      {steps.map((s, i) => (
        <li key={s} className="min-w-0">
          <button
            type="button"
            disabled={locked}
            aria-current={s === active ? "step" : undefined}
            data-testid={`cal-step-${s}`}
            onClick={() => {
              onPick(s);
            }}
            className={cn(
              "flex w-full min-w-0 items-center gap-2 border-2 border-frame px-2 py-2 text-left text-sm disabled:cursor-not-allowed",
              s === active ? "bg-primary text-primary-foreground" : "bg-card hover:bg-accent",
            )}
          >
            <span
              className={cn(
                "inline-flex size-6 shrink-0 items-center justify-center border-2 border-frame font-extrabold",
                done[s] ? "bg-success text-success-foreground" : "bg-card text-foreground",
              )}
            >
              {done[s] ? <PxIcon name="check" /> : i + 1}
            </span>
            <span className="truncate font-bold">{t(`calibrate.step_${s}`)}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function CalibratePage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const cal = useStation(selCal);
  const robots = useRobots();
  const profile = robots.data?.robots.find((r) => r.id === status?.robot?.id);
  const connected = Boolean(profile && status?.robot?.connected);
  const canCheck = connected && (status?.state === "idle" || status?.state === "estopped");
  const check = useCalibrationCheck(canCheck);
  const fCal = Boolean(status?.robot?.arms.follower.calibrated);
  const lCal = Boolean(status?.robot?.arms.leader?.calibrated);
  const refetch = check.refetch;
  useEffect(() => {
    if (canCheck) void refetch();
  }, [fCal, lCal, canCheck, refetch]);
  const [picked, setPicked] = useState<StepKey | null>(null);
  const [arrived, setArrived] = useState<Arm | null>(null);

  const hasLeader = Boolean(profile?.leader);
  const steps: StepKey[] = hasLeader ? ["follower", "leader", "check"] : ["follower"];
  const arms = check.data?.arms;
  const isOk = (a: Arm) => {
    const c = arms?.[a];
    return c ? c.state === "ok" : a === "follower" ? fCal : lCal;
  };
  const calibrating = status?.state === "calibrating";
  const todo: Arm[] = hasLeader ? ["follower", "leader"] : ["follower"];
  const firstTodo = todo.find((a) => !isOk(a));
  const active: StepKey =
    calibrating && cal?.arm && cal.step !== "done"
      ? cal.arm
      : (picked ?? firstTodo ?? (hasLeader ? "check" : "follower"));
  const done: Record<StepKey, boolean> = { follower: fCal, leader: lCal, check: false };

  const after = (a: Arm) => () => {
    if (a === "follower" && hasLeader) {
      setArrived("leader");
      setPicked("leader");
    } else if (hasLeader) {
      setArrived(null);
      setPicked("check");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("calibrate.title")} description={t("calibrate.desc")} />
      {!profile || !connected ? (
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
          <CardContent className="flex flex-col gap-4">
            {steps.length > 1 ? (
              <Stepper
                steps={steps}
                active={active}
                done={done}
                locked={calibrating}
                onPick={(s) => {
                  setArrived(null);
                  setPicked(s);
                }}
              />
            ) : null}
            {active === "check" ? (
              <PoseCheck
                onRecalibrate={(a) => {
                  setPicked(a);
                }}
              />
            ) : (
              <ArmStep
                key={active}
                arm={active}
                profile={profile}
                check={arms?.[active] ?? null}
                checkError={check.error}
                checking={check.isFetching || (!check.data && !check.error)}
                arrived={arrived === active}
                next={
                  active === "follower" && hasLeader
                    ? { label: t("calibrate.next_leader"), go: after("follower") }
                    : hasLeader
                      ? { label: t("calibrate.next_check"), go: after("leader") }
                      : { label: t("calibrate.next"), to: "/cameras" }
                }
                onDone={after(active)}
              />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
