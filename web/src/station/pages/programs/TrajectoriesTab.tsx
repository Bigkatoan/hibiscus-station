/**
 * Tab "Quỹ đạo / Trajectories" (station-programs.md §3, §8): record a take with the leader arm
 * (countdown, live progress, stop), review it (joint plot, auto-suggested idle trim, name, save or
 * discard), list takes with a thumbnail plot, replay at a chosen speed (needs_check → 25 % check
 * replay + confirm), rename, trim, delete, and the named poses used by `move to pose`.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmButton } from "@/components/common";
import { Field } from "@/components/Field";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Progress } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { api } from "../../api/client";
import {
  qk,
  usePoses,
  useRobots,
  useSettings,
  useStationMutation,
  useTrajectories,
  useTrajectory,
} from "../../api/hooks";
import type {
  Pose,
  PoseInput,
  RecordTrajectoryRequest,
  Session,
  Trajectory,
  TrajectoryDetail,
  TrajectorySummary,
  TrajectoryUpdate,
} from "../../api/types";
import { StationError } from "../../components/StationError";
import { useSessionControl } from "../../components/controls";
import { useStation, useStatus } from "../../ws/StationProvider";
import { formatSeconds, JointLegend, JointPlot } from "./shared";
import { GhostPreview } from "../../twin/GhostPreview";

const enc = encodeURIComponent;
export const SPEEDS = [10, 25, 50, 75, 100, 125, 150];

function useProfile() {
  const status = useStatus();
  const robots = useRobots();
  return robots.data?.robots.find((r) => r.id === status?.robot?.id);
}

// ------------------------------------------------------------------ record
function RecordCard({ onDraft }: { onDraft: (id: string) => void }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const settings = useSettings();
  const qc = useQueryClient();
  const rec = useStation((s) => s.trajRecord);
  const [name, setName] = useState("");
  const [fps, setFps] = useState(30);
  const [limit, setLimit] = useState(60);
  const maxS = settings.data?.programs.traj_max_s ?? 600;
  const start = useStationMutation((body: RecordTrajectoryRequest) =>
    api.post<Session>("/trajectories/record", body),
  );
  const stop = useStationMutation(
    () => api.post<TrajectoryDetail>("/trajectories/record/stop"),
    [qk.trajectories],
  );
  const recording = status?.state === "recording_traj";
  const hasLeader = Boolean(status?.robot?.arms.leader);
  const canStart = status?.state === "idle" && hasLeader;

  // The take ended on its time limit: the final message carries the new draft. A draft that was
  // already there when this card mounted (another tab visit) is not reopened.
  const seen = useRef(rec?.trajectory_id ?? null);
  useEffect(() => {
    const id = rec?.ended ? rec.trajectory_id : null;
    if (!id || seen.current === id) return;
    seen.current = id;
    void qc.invalidateQueries({ queryKey: qk.trajectories });
    onDraft(id);
  }, [rec?.ended, rec?.trajectory_id, qc, onDraft]);

  const phase = recording
    ? rec && !rec.ended
      ? rec.phase
      : status.sub === "capture"
        ? "capture"
        : "countdown"
    : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("programs.traj.record_title")}</CardTitle>
        <CardDescription>{t("programs.traj.record_desc")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!recording ? (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate({
                ...(name.trim() ? { name: name.trim() } : {}),
                fps,
                limit_s: Math.min(maxS, Math.max(1, limit)),
                countdown_s: 3,
                keyframe_hz: 1,
              });
            }}
          >
            <Field label={t("programs.traj.name")} className="min-w-[12rem] flex-1">
              <Input
                value={name}
                maxLength={80}
                placeholder={t("programs.traj.name_hint")}
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
            </Field>
            <Field label={t("record.fps")}>
              <NativeSelect
                value={fps}
                onChange={(e) => {
                  setFps(Number(e.target.value));
                }}
              >
                <option value={15}>15</option>
                <option value={30}>30</option>
              </NativeSelect>
            </Field>
            <Field label={t("programs.traj.limit")}>
              <Input
                type="number"
                min={1}
                max={maxS}
                value={limit}
                className="w-24"
                onChange={(e) => {
                  setLimit(Number(e.target.value));
                }}
              />
            </Field>
            <Button type="submit" size="lg" disabled={!canStart || start.isPending}>
              <PxIcon name="play" /> {t("programs.traj.record")}
            </Button>
            {!hasLeader ? (
              <p className="w-full text-sm text-muted-foreground">{t("programs.traj.needs_leader")}</p>
            ) : null}
            {hasLeader && status?.state !== "idle" ? (
              <p className="w-full text-sm text-muted-foreground">{t("teleop.not_idle")}</p>
            ) : null}
          </form>
        ) : (
          <div className="flex flex-col gap-2" role="status" aria-live="polite" data-testid="traj-recording">
            {phase === "countdown" ? (
              <p className="font-extrabold text-2xl">
                {t("programs.traj.countdown", {
                  n: Math.max(1, Math.ceil(3 - (rec?.elapsed_s ?? 0))),
                })}
              </p>
            ) : (
              <>
                <p className="font-extrabold text-xl tabular-nums">
                  {t("programs.traj.capturing", {
                    s: (rec?.elapsed_s ?? 0).toFixed(1),
                    limit: rec?.limit_s ?? limit,
                    n: rec?.samples ?? 0,
                  })}
                </p>
                <Progress
                  value={rec ? Math.min(100, (rec.elapsed_s / Math.max(1, rec.limit_s)) * 100) : 0}
                  aria-label={t("programs.traj.progress")}
                />
              </>
            )}
            <Button
              size="lg"
              variant="destructive"
              className="self-start"
              disabled={stop.isPending}
              onClick={() => {
                stop.mutate(undefined, {
                  onSuccess: (d) => {
                    onDraft(d.id);
                  },
                });
              }}
            >
              <PxIcon name="stop" /> {t("programs.traj.stop")}
            </Button>
          </div>
        )}
        <StationError error={start.error ?? stop.error} />
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ playing
function PlayingCard() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const control = useSessionControl();
  if (status?.state !== "playing" || status.session?.kind !== "traj_play") return null;
  const ep = status.session.episode;
  return (
    <Card data-testid="traj-playing">
      <CardContent
        className="flex flex-wrap items-center gap-3 pt-3 sm:pt-4"
        role="status"
        aria-live="polite"
      >
        <div className="min-w-0 flex-1">
          <p className="font-extrabold text-lg">
            {status.sub === "approach" ? t("programs.traj.moving_to_start") : t("programs.traj.replaying")}
          </p>
          {status.sub === "replay" && ep.limit_s ? (
            <Progress
              value={Math.min(100, (ep.elapsed_s / ep.limit_s) * 100)}
              aria-label={t("programs.traj.progress")}
            />
          ) : null}
        </div>
        <Button
          size="lg"
          variant="destructive"
          onClick={() => {
            control("stop");
          }}
        >
          <PxIcon name="stop" /> {t("controls.stop")}
        </Button>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ review / edit one take
function TrajectoryEditor({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation("station");
  const q = useTrajectory(id);
  const poses = usePoses();
  const status = useStatus();
  const [name, setName] = useState("");
  const [trim, setTrim] = useState({ start_s: 0, end_s: 0 });
  const [poseName, setPoseName] = useState("");
  const tr = q.data;
  useEffect(() => {
    if (!tr) return;
    setName(tr.name);
    setTrim(tr.status === "draft" ? tr.suggested_trim : tr.trim);
  }, [tr]);
  const save = useStationMutation(
    (upd: TrajectoryUpdate) => api.put<Trajectory>(`/trajectories/${enc(id)}`, upd),
    [qk.trajectories, qk.trajectory(id)],
  );
  const discard = useStationMutation(() => api.del(`/trajectories/${enc(id)}`), [qk.trajectories]);
  const addPose = useStationMutation(
    (p: PoseInput) =>
      api.put<{ poses: Pose[] }>("/poses", {
        poses: [
          ...(poses.data?.poses ?? [])
            .filter((x) => x.name !== p.name)
            .map(({ name: n, positions, source, trajectory }) => ({
              name: n,
              positions,
              source,
              trajectory,
            })),
          p,
        ],
      }),
    [qk.poses],
  );
  if (!tr) return <StationError error={q.error} />;
  const raw = tr.raw_duration_s;
  const kept = Math.max(0, raw - trim.start_s - trim.end_s);
  const validTrim = trim.start_s >= 0 && trim.end_s >= 0 && kept > 0.1;
  const busy = status?.state === "playing";
  const draft = tr.status === "draft";
  const poseOk = /^[a-z0-9][a-z0-9_-]{0,63}$/.test(poseName);
  return (
    <Card data-testid="traj-editor">
      <CardHeader>
        <CardTitle>
          {draft ? t("programs.traj.review_title") : t("programs.traj.edit_title", { name: tr.name })}
        </CardTitle>
        <CardDescription>{t("programs.traj.review_desc")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <JointPlot
          t={tr.series.t}
          joints={tr.series.joints}
          trim={trim}
          width={600}
          height={160}
          className="h-40 w-full border-2 border-frame bg-card"
          label={t("programs.traj.plot_label", { name: tr.name, s: raw.toFixed(1) })}
        />
        <JointLegend names={tr.joints} />
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("programs.traj.name")} className="min-w-[12rem] flex-1">
            <Input
              value={name}
              maxLength={80}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          </Field>
          <Field label={t("programs.traj.trim_start")}>
            <Input
              type="number"
              step={0.1}
              min={0}
              max={raw}
              value={trim.start_s}
              className="w-24"
              onChange={(e) => {
                setTrim({ ...trim, start_s: Number(e.target.value) });
              }}
            />
          </Field>
          <Field label={t("programs.traj.trim_end")}>
            <Input
              type="number"
              step={0.1}
              min={0}
              max={raw}
              value={trim.end_s}
              className="w-24"
              onChange={(e) => {
                setTrim({ ...trim, end_s: Number(e.target.value) });
              }}
            />
          </Field>
          <Button
            variant="outline"
            onClick={() => {
              setTrim(tr.suggested_trim);
            }}
          >
            {t("programs.traj.use_suggested", {
              a: tr.suggested_trim.start_s.toFixed(1),
              b: tr.suggested_trim.end_s.toFixed(1),
            })}
          </Button>
        </div>
        <p className="text-sm tabular-nums text-muted-foreground">
          {t("programs.traj.kept", { kept: kept.toFixed(1), raw: raw.toFixed(1) })}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!validTrim || !name.trim() || save.isPending || busy}
            onClick={() => {
              save.mutate(
                { name: name.trim(), trim, save: draft },
                {
                  onSuccess: () => {
                    if (draft) onClose();
                  },
                },
              );
            }}
          >
            <PxIcon name="check" /> {draft ? t("programs.traj.save_take") : t("common.save")}
          </Button>
          {draft ? (
            <Button
              variant="outline"
              disabled={discard.isPending}
              onClick={() => {
                discard.mutate(undefined, { onSuccess: onClose });
              }}
            >
              <PxIcon name="trash" /> {t("programs.traj.discard")}
            </Button>
          ) : (
            <Button variant="outline" onClick={onClose}>
              {t("common.close")}
            </Button>
          )}
        </div>
        {!draft ? (
          <form
            className="flex flex-wrap items-end gap-2 border-t-2 border-frame/30 pt-3"
            onSubmit={(e) => {
              e.preventDefault();
            }}
          >
            <Field label={t("programs.poses.name")} description={t("programs.poses.name_hint")}>
              <Input
                value={poseName}
                onChange={(e) => {
                  setPoseName(e.target.value.toLowerCase());
                }}
                className="w-40"
              />
            </Field>
            <Button
              variant="outline"
              disabled={!poseOk || addPose.isPending}
              onClick={() => {
                addPose.mutate({
                  name: poseName,
                  positions: tr.start_pose,
                  source: "trajectory_start",
                  trajectory: tr.id,
                });
              }}
            >
              {t("programs.poses.from_start")}
            </Button>
            <Button
              variant="outline"
              disabled={!poseOk || addPose.isPending}
              onClick={() => {
                addPose.mutate({
                  name: poseName,
                  positions: tr.end_pose,
                  source: "trajectory_end",
                  trajectory: tr.id,
                });
              }}
            >
              {t("programs.poses.from_end")}
            </Button>
          </form>
        ) : null}
        <StationError error={save.error ?? discard.error ?? addPose.error} />
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ list
function TrajectoryCard({
  tr,
  fastOk,
  onEdit,
  previewing,
  onPreview,
}: {
  tr: TrajectorySummary;
  fastOk: boolean;
  onEdit: (id: string) => void;
  previewing: boolean;
  onPreview: (id: string) => void;
}) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const [speed, setSpeed] = useState(100);
  const play = useStationMutation((body: { speed_pct?: number; check?: boolean }) =>
    api.post<Session>(`/trajectories/${enc(tr.id)}/play`, body),
  );
  const confirm = useStationMutation(
    () => api.post<Trajectory>(`/trajectories/${enc(tr.id)}/confirm`),
    [qk.trajectories],
  );
  const del = useStationMutation(() => api.del(`/trajectories/${enc(tr.id)}`), [qk.trajectories]);
  const idle = status?.state === "idle";
  const needsCheck = tr.status === "needs_check";
  return (
    <li
      className={cn(
        "flex flex-col gap-2 border-2 border-frame bg-card p-3",
        previewing && "outline outline-4 outline-offset-0 outline-[#6fb7e8]",
      )}
      data-testid={`traj-${tr.id}`}
      data-previewing={previewing ? "true" : "false"}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-extrabold">{tr.name}</span>
        <Badge variant={tr.status === "ready" ? "success" : tr.status === "draft" ? "outline" : "warning"}>
          {t(`programs.traj.status_${tr.status}`)}
        </Badge>
      </div>
      <JointPlot
        joints={tr.preview}
        className="h-16 w-full border-2 border-frame/40 bg-background"
        label={t("programs.traj.thumb_label", { name: tr.name })}
      />
      <p className="text-xs tabular-nums text-muted-foreground">
        {t("programs.traj.meta", {
          s: formatSeconds(tr.duration_s),
          fps: tr.fps,
          speed: tr.max_speed_deg_s.toFixed(0),
        })}
      </p>
      {needsCheck ? (
        <p className="text-xs text-warning-foreground">{t("programs.traj.needs_check_hint")}</p>
      ) : null}
      <div className="flex flex-wrap items-end gap-2">
        {!needsCheck ? (
          <>
            <Field label={t("programs.traj.speed")}>
              <NativeSelect
                value={speed}
                onChange={(e) => {
                  setSpeed(Number(e.target.value));
                }}
              >
                {SPEEDS.map((s) => (
                  <option key={s} value={s} disabled={s > 100 && !fastOk}>
                    {s} %
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Button
              disabled={!idle || play.isPending || tr.status !== "ready"}
              onClick={() => {
                play.mutate({ speed_pct: speed });
              }}
            >
              <PxIcon name="play" /> {t("programs.traj.play")}
            </Button>
          </>
        ) : (
          <>
            <Button
              disabled={!idle || play.isPending}
              onClick={() => {
                play.mutate({ check: true });
              }}
            >
              <PxIcon name="play" /> {t("programs.traj.check_play")}
            </Button>
            <Button
              variant="outline"
              disabled={confirm.isPending}
              onClick={() => {
                confirm.mutate(undefined);
              }}
            >
              <PxIcon name="check" /> {t("programs.traj.confirm")}
            </Button>
          </>
        )}
        <Button
          variant="outline"
          aria-pressed={previewing}
          onClick={() => {
            onPreview(tr.id);
          }}
        >
          <PxIcon name="eye" /> {t("twin.preview")}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            onEdit(tr.id);
          }}
        >
          <PxIcon name="edit" /> {t("programs.traj.edit")}
        </Button>
        <ConfirmButton
          variant="ghost"
          destructive
          title={t("programs.traj.delete_title", { name: tr.name })}
          confirmLabel={t("common.remove")}
          aria-label={t("programs.traj.delete_title", { name: tr.name })}
          onConfirm={() => del.mutateAsync(undefined)}
        >
          <PxIcon name="trash" />
        </ConfirmButton>
      </div>
      <StationError error={play.error ?? confirm.error} />
    </li>
  );
}

// ------------------------------------------------------------------ 3D ghost preview
function PreviewCard({ id }: { id: string | null }) {
  const { t } = useTranslation("station");
  const q = useTrajectory(id);
  const tr = id ? q.data : undefined;
  return (
    <Card data-testid="traj-preview">
      <CardHeader>
        <CardTitle>{t("twin.ghost_title")}</CardTitle>
        <CardDescription>{t("twin.ghost_desc")}</CardDescription>
      </CardHeader>
      <CardContent>
        {!id ? <p className="text-sm text-muted-foreground">{t("twin.ghost_none")}</p> : null}
        {id && !tr ? <StationError error={q.error} /> : null}
        {tr ? (
          <div className="grid gap-4 md:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
            <GhostPreview tr={tr} />
            <div className="flex min-w-0 flex-col gap-2">
              <JointPlot
                t={tr.series.t}
                joints={tr.series.joints}
                trim={tr.status === "draft" ? tr.suggested_trim : tr.trim}
                width={600}
                height={160}
                className="h-40 w-full border-2 border-frame bg-card"
                label={t("programs.traj.plot_label", { name: tr.name, s: tr.raw_duration_s.toFixed(1) })}
              />
              <JointLegend names={tr.joints} />
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ poses
function PosesCard() {
  const { t } = useTranslation("station");
  const poses = usePoses();
  const status = useStatus();
  const [name, setName] = useState("");
  const capture = useStationMutation(
    (n: string) => api.post<Pose>("/poses/capture", { name: n }),
    [qk.poses],
  );
  const replace = useStationMutation(
    (list: Pose[]) =>
      api.put<{ poses: Pose[] }>("/poses", {
        poses: list.map(({ name: n, positions, source, trajectory }) => ({
          name: n,
          positions,
          source,
          trajectory,
        })),
      }),
    [qk.poses],
  );
  const list = poses.data?.poses ?? [];
  const ok = /^[a-z0-9][a-z0-9_-]{0,63}$/.test(name);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("programs.poses.title")}</CardTitle>
        <CardDescription>{t("programs.poses.desc")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {list.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("programs.poses.empty")}</p>
        ) : null}
        <ul className="flex flex-col gap-1" aria-label={t("programs.poses.title")}>
          {list.map((p) => (
            <li
              key={p.name}
              className="flex flex-wrap items-center gap-2 border-b border-frame/30 py-1 text-sm"
            >
              <span className="font-bold">{p.name}</span>
              <span className="text-xs text-muted-foreground">{t(`programs.poses.source_${p.source}`)}</span>
              {p.needs_check ? (
                <Badge variant="warning">{t("programs.traj.status_needs_check")}</Badge>
              ) : null}
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto"
                aria-label={t("programs.poses.remove", { name: p.name })}
                onClick={() => {
                  replace.mutate(list.filter((x) => x.name !== p.name));
                }}
              >
                <PxIcon name="trash" />
              </Button>
            </li>
          ))}
        </ul>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (ok) capture.mutate(name, { onSuccess: () => setName("") });
          }}
        >
          <Field label={t("programs.poses.name")} description={t("programs.poses.name_hint")}>
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value.toLowerCase());
              }}
              className="w-40"
            />
          </Field>
          <Button
            type="submit"
            variant="outline"
            disabled={!ok || status?.state !== "idle" || capture.isPending}
          >
            <PxIcon name="pin" /> {t("programs.poses.capture")}
          </Button>
        </form>
        <StationError error={capture.error ?? replace.error} />
      </CardContent>
    </Card>
  );
}

export function TrajectoriesTab() {
  const { t } = useTranslation("station");
  const list = useTrajectories();
  const profile = useProfile();
  const [editing, setEditing] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const takes = list.data?.trajectories ?? [];
  // The ghost shows the picked take, else the first one in the list.
  const previewId = takes.find((x) => x.id === picked)?.id ?? takes[0]?.id ?? null;
  const fastOk = Boolean(profile?.follower.allow_fast_replay);
  return (
    <div className="flex flex-col gap-4">
      <RecordCard onDraft={setEditing} />
      <PlayingCard />
      {editing ? (
        <TrajectoryEditor
          key={editing}
          id={editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
      {takes.length > 0 ? <PreviewCard id={previewId} /> : null}
      <section aria-labelledby="traj-list-title" className="flex flex-col gap-2">
        <h2 id="traj-list-title" className="font-extrabold text-lg">
          {t("programs.traj.list_title")}
        </h2>
        <StationError error={list.error} />
        {takes.length === 0 && !list.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("programs.traj.empty")}</p>
        ) : null}
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {takes.map((tr) => (
            <TrajectoryCard
              key={tr.id}
              tr={tr}
              fastOk={fastOk}
              onEdit={setEditing}
              previewing={tr.id === previewId}
              onPreview={setPicked}
            />
          ))}
        </ul>
      </section>
      <PosesCard />
    </div>
  );
}
