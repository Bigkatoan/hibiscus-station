/**
 * Run model (R2, §6.9): model picker (import zip/path, pull from server), compat checklist with
 * one-click fixes, load, run setup, and the running view with ALL configured cameras (the policy
 * input frames), joints vs commanded action, motor health, stats, timer and the 128 px e-stop.
 */
import type { TFunction } from "i18next";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { api } from "../api/client";
import { qk, useCompat, useModels, useRobots, useServerModels, useStationMutation } from "../api/hooks";
import type { CompatCheck, Job, ModelEntry, RobotProfile, RunRequest, Session } from "../api/types";
import {
  JobProgress,
  formatBytes,
  scalar,
  useCritical,
  useLatestJob,
  useSessionControl,
} from "../components/controls";
import { LiveLayout } from "../components/LiveLayout";
import { LoopStats, SessionTimer, formatClock } from "../components/SessionWidgets";
import { StationError } from "../components/StationError";
import { useRuntime, useStatus } from "../ws/StationProvider";

function ModelPicker({ selected, onSelect }: { selected: string | null; onSelect: (k: string) => void }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const models = useModels();
  const [path, setPath] = useState("");
  const [showServer, setShowServer] = useState(false);
  const paired = Boolean(status?.server.paired);
  const server = useServerModels(showServer && paired);
  const importJob = useLatestJob("import");
  const pullJob = useLatestJob("pull");
  const importZip = useStationMutation((file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<Job>("/models/import", fd);
  });
  const importPath = useStationMutation((p: string) => api.post<Job>("/models/import", { path: p }));
  const pull = useStationMutation((id: string) => api.post<Job>("/models/pull", { server_model_id: id }));
  const loaded = models.data?.loaded ?? status?.loaded_model ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("run.models")}</CardTitle>
        <CardDescription>{t("run.models_desc")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {(models.data?.models ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("run.no_models")}</p>
        ) : null}
        <ul className="flex flex-col gap-2" aria-label={t("run.models")}>
          {(models.data?.models ?? []).map((m) => (
            <li key={m.key}>
              <button
                type="button"
                onClick={() => {
                  onSelect(m.key);
                }}
                aria-pressed={selected === m.key}
                className={`flex w-full flex-wrap items-center gap-2 border-2 px-2 py-2 text-left text-sm ${selected === m.key ? "border-frame bg-accent" : "border-frame/30 hover:border-frame"}`}
              >
                <span className="min-w-0 flex-1 truncate font-bold">{m.name}</span>
                <Badge variant="info">{m.policy_type}</Badge>
                <Badge variant="outline">{t(`run.source_${m.source}`)}</Badge>
                {m.verified ? (
                  <Badge variant="success">{t("run.verified")}</Badge>
                ) : (
                  <Badge variant="warning">{t("run.unverified")}</Badge>
                )}
                {loaded === m.key ? <Badge>{t("run.loaded")}</Badge> : null}
                <span className="tabular-nums text-xs text-muted-foreground">
                  {formatBytes(m.size_bytes)}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("run.import_zip")}>
            <Input
              type="file"
              accept=".zip,application/zip"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importZip.mutate(f);
              }}
            />
          </Field>
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (path.trim()) importPath.mutate(path.trim());
            }}
          >
            <Field label={t("run.import_path")} className="flex-1" description={t("run.import_path_hint")}>
              <Input
                value={path}
                onChange={(e) => {
                  setPath(e.target.value);
                }}
                placeholder="~/outputs/train/act/checkpoints/last/pretrained_model"
              />
            </Field>
            <Button type="submit" variant="outline" disabled={!path.trim() || importPath.isPending}>
              {t("run.import")}
            </Button>
          </form>
        </div>
        <StationError error={importZip.error ?? importPath.error ?? pull.error} />
        {importJob && importJob.status !== "succeeded" ? <JobProgress job={importJob} /> : null}
        {paired ? (
          <div className="flex flex-col gap-2">
            <Button
              variant="outline"
              className="self-start"
              onClick={() => {
                setShowServer((v) => !v);
              }}
              aria-expanded={showServer}
            >
              {t("run.from_server")}
            </Button>
            {showServer ? (
              <ul className="flex flex-col gap-1" aria-label={t("run.from_server")}>
                {(server.data?.models ?? []).map((m) => (
                  <li
                    key={m.id}
                    className="flex flex-wrap items-center gap-2 border-b border-frame/30 py-1 text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">{m.name}</span>
                    <Badge variant="info">{m.policy_type}</Badge>
                    <span className="tabular-nums text-xs">
                      {m.size_bytes !== null ? formatBytes(m.size_bytes) : ""}
                    </span>
                    <Button
                      size="sm"
                      disabled={m.status !== "ready" || pull.isPending}
                      onClick={() => {
                        pull.mutate(m.id);
                      }}
                    >
                      {t("run.pull")}
                    </Button>
                  </li>
                ))}
              </ul>
            ) : null}
            {pullJob && pullJob.status !== "succeeded" ? <JobProgress job={pullJob} /> : null}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {t("run.pair_for_server")}{" "}
            <Link to="/" className="underline">
              {t("run.pair_link")}
            </Link>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function checkLabel(t: TFunction<"station">, c: CompatCheck): string {
  const [kind, key] = c.id.split(":", 2);
  return t(`compat.${kind ?? c.id}`, { key: key ?? "", defaultValue: c.id });
}

function CompatPanel({
  model,
  profile,
  cameraMap,
  setCameraMap,
}: {
  model: ModelEntry;
  profile: RobotProfile | undefined;
  cameraMap: Record<string, string>;
  setCameraMap: (m: Record<string, string>) => void;
}) {
  const { t } = useTranslation("station");
  const compat = useCompat(model.key, profile?.id ?? null);
  const fix = useStationMutation(
    (p: RobotProfile) => api.put<RobotProfile>(`/robots/${encodeURIComponent(p.id)}`, p),
    [qk.robots, ["station", "models", model.key]],
  );
  const cams = Object.keys(profile?.cameras ?? {});
  const policyCams = Object.keys(model.input_features).filter((k) => k.startsWith("observation.images."));
  return (
    <div className="flex flex-col gap-2" data-testid="compat">
      <h3 className="font-extrabold text-base">{t("compat.title")}</h3>
      {compat.isLoading ? <p className="text-sm">{t("common.loading")}</p> : null}
      <StationError error={compat.error ?? fix.error} />
      <ul className="flex flex-col gap-1">
        {(compat.data?.checks ?? []).map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-2 text-sm" data-ok={c.ok}>
            {c.ok ? (
              <PxIcon name="check" className="text-success" label={t("compat.ok")} />
            ) : (
              <PxIcon name="close" className="text-destructive" label={t("compat.fail")} />
            )}
            <span>{checkLabel(t, c)}</span>
            {!c.ok && c.code ? (
              <span className="text-xs text-muted-foreground">
                {t(`compat.code_${c.code}`, {
                  expected: JSON.stringify(c.expected ?? ""),
                  actual: JSON.stringify(c.actual ?? ""),
                  defaultValue: c.code,
                })}
              </span>
            ) : null}
            {!c.ok && c.fix?.kind === "set_camera" && profile ? (
              <Button
                size="sm"
                variant="outline"
                disabled={fix.isPending}
                onClick={() => {
                  if (c.fix?.kind !== "set_camera") return;
                  const { camera, width, height } = c.fix;
                  const cam = camera ? profile.cameras[camera] : undefined;
                  if (!camera || !cam || width == null || height == null) return;
                  fix.mutate({
                    ...profile,
                    cameras: { ...profile.cameras, [camera]: { ...cam, width, height } },
                  });
                }}
              >
                {t("compat.fix_camera", { cam: c.fix.camera, w: c.fix.width, h: c.fix.height })}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {(compat.data?.warnings ?? []).map((w) => (
        <p key={w} className="text-xs text-muted-foreground">
          ⚠ {w}
        </p>
      ))}
      {policyCams.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {policyCams.map((k) => (
            <Field key={k} label={t("compat.map", { key: k })}>
              <NativeSelect
                value={cameraMap[k] ?? k.replace("observation.images.", "")}
                onChange={(e) => {
                  setCameraMap({ ...cameraMap, [k]: e.target.value });
                }}
              >
                {cams.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
                {!cams.includes(k.replace("observation.images.", "")) ? (
                  <option value={k.replace("observation.images.", "")} disabled>
                    {k.replace("observation.images.", "")} ({t("compat.missing")})
                  </option>
                ) : null}
              </NativeSelect>
            </Field>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function defaultRelTarget(profile: RobotProfile | undefined): number {
  const m = profile?.follower.max_relative_target;
  if (typeof m === "number") return m;
  if (m && typeof m === "object") return Math.min(...Object.values(m));
  return 5;
}

/** Language-conditioned policies need the task; ACT / Diffusion ignore it. */
const TASK_POLICIES = ["smolvla", "pi0", "pi05", "pi0fast"];

function RunSetup({ model, profile }: { model: ModelEntry; profile: RobotProfile | undefined }) {
  const { t } = useTranslation("station");
  const needsTask = TASK_POLICIES.includes(model.policy_type);
  const status = useStatus();
  const compat = useCompat(model.key, profile?.id ?? null);
  const loadJob = useLatestJob("load", model.key);
  const models = useModels();
  const loaded =
    (models.data?.loaded ?? status?.loaded_model) === model.key || loadJob?.status === "succeeded";
  const [device, setDevice] = useState<"auto" | "cpu" | "cuda" | "mps">("auto");
  const [cameraMap, setCameraMap] = useState<Record<string, string>>({});
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const [form, setForm] = useState({
    task: model.task ?? "",
    fps: model.fps ?? 30,
    episode_time_s: 30,
    num_episodes: 1,
    reset_time_s: 10,
    max_relative_target: defaultRelTarget(profile),
    record: false,
    dataset: `eval_${model.key.replace(/[^a-zA-Z0-9_]+/g, "_")}_${today}`,
  });
  const [advanced, setAdvanced] = useState(false);
  const profileCap = defaultRelTarget(profile);

  useEffect(() => {
    const d = compat.data?.defaults;
    if (!d) return;
    setForm((f) => ({ ...f, task: f.task || (d.task ?? ""), fps: d.fps ?? f.fps }));
  }, [compat.data?.defaults]);

  const load = useStationMutation(
    () => api.post<Job>(`/models/${encodeURIComponent(model.key)}/load`, { device }),
    [qk.models],
  );
  const start = useStationMutation((req: RunRequest) => api.post<Session>("/sessions/run", req));
  const capError = !advanced && form.max_relative_target > profileCap;
  const canStart =
    loaded &&
    compat.data?.ok !== false &&
    !capError &&
    (!needsTask || form.task.trim() !== "") &&
    status?.state === "idle";

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
  };
  const loadResult = loadJob?.status === "succeeded" ? loadJob.result : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("run.setup", { name: model.name })}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <CompatPanel model={model} profile={profile} cameraMap={cameraMap} setCameraMap={setCameraMap} />
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t("run.device")}>
            <NativeSelect
              value={device}
              onChange={(e) => {
                setDevice(e.target.value as typeof device);
              }}
            >
              {(["auto", "cuda", "mps", "cpu"] as const).map((d) => (
                <option key={d} value={d}>
                  {t(`device.${d}`)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Button
            variant={loaded ? "outline" : "default"}
            onClick={() => {
              load.mutate(undefined);
            }}
            disabled={load.isPending || loadJob?.status === "running"}
          >
            {loaded ? t("run.reload") : t("run.load")}
          </Button>
          {loaded ? <Badge variant="success">{t("run.loaded")}</Badge> : null}
        </div>
        {loadJob && loadJob.status !== "succeeded" ? <JobProgress job={loadJob} /> : null}
        {loadResult ? (
          <p className="text-sm text-muted-foreground" data-testid="load-result">
            {t("run.load_result", {
              device: scalar(loadResult.device),
              load: scalar(loadResult.load_s),
              warmup: scalar(loadResult.warmup_ms),
            })}
          </p>
        ) : null}
        <StationError error={load.error} />
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canStart) return;
            start.mutate({
              model: model.key,
              task: form.task.trim(),
              fps: form.fps,
              episode_time_s: form.episode_time_s,
              num_episodes: form.num_episodes,
              reset_time_s: form.reset_time_s,
              camera_map: Object.fromEntries(
                Object.keys(model.input_features)
                  .filter((k) => k.startsWith("observation.images."))
                  .map((k) => [k, cameraMap[k] ?? k.replace("observation.images.", "")]),
              ),
              max_relative_target: form.max_relative_target,
              reset_with_leader: false,
              record: form.record,
              dataset: form.record ? form.dataset : null,
            });
          }}
        >
          <Field label={t("run.task")} className="sm:col-span-2" required={needsTask}>
            <Input
              value={form.task}
              onChange={(e) => {
                set("task", e.target.value);
              }}
            />
          </Field>
          <Field label={t("run.fps")}>
            <Input
              type="number"
              min={1}
              max={60}
              value={form.fps}
              onChange={(e) => {
                set("fps", Number(e.target.value));
              }}
            />
          </Field>
          <Field label={t("run.episode_time")}>
            <Input
              type="number"
              min={1}
              max={600}
              value={form.episode_time_s}
              onChange={(e) => {
                set("episode_time_s", Number(e.target.value));
              }}
            />
          </Field>
          <Field label={t("run.episodes")}>
            <Input
              type="number"
              min={1}
              max={100}
              value={form.num_episodes}
              onChange={(e) => {
                set("num_episodes", Number(e.target.value));
              }}
            />
          </Field>
          <Field label={t("run.reset_time")}>
            <Input
              type="number"
              min={0}
              max={120}
              value={form.reset_time_s}
              onChange={(e) => {
                set("reset_time_s", Number(e.target.value));
              }}
            />
          </Field>
          <Field
            label={t("run.max_rel")}
            description={t("run.max_rel_hint", { cap: profileCap })}
            {...(capError ? { error: t("run.max_rel_error", { cap: profileCap }) } : {})}
          >
            <Input
              type="number"
              step={0.5}
              min={0.5}
              value={form.max_relative_target}
              onChange={(e) => {
                set("max_relative_target", Number(e.target.value));
              }}
            />
          </Field>
          <label className="flex items-center gap-2 self-end text-sm">
            <Checkbox
              checked={advanced}
              onChange={(e) => {
                setAdvanced(e.target.checked);
              }}
            />
            {t("run.advanced")}
          </label>
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <Checkbox
              checked={form.record}
              onChange={(e) => {
                set("record", e.target.checked);
              }}
            />
            {t("run.record_eval")}
          </label>
          {form.record ? (
            <Field label={t("run.eval_dataset")} className="sm:col-span-2">
              <Input
                value={form.dataset}
                onChange={(e) => {
                  set("dataset", e.target.value);
                }}
              />
            </Field>
          ) : null}
          <StationError error={start.error} className="sm:col-span-2" />
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <Button type="submit" size="lg" disabled={!canStart || start.isPending}>
              <PxIcon name="play" /> {t("run.start")}
            </Button>
            {!loaded ? <span className="text-sm text-muted-foreground">{t("run.load_first")}</span> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function RunLive({ session }: { session: Session }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const control = useSessionControl();
  const critical = useCritical();
  const disabled = critical || status?.state !== "inferring";
  const arms = status?.robot?.arms.leader ? (["follower", "leader"] as const) : (["follower"] as const);
  return (
    <LiveLayout
      chart
      arms={[...arms]}
      header={
        <Card>
          <CardContent className="grid gap-4 pt-3 sm:pt-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,16rem)]">
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">
                {t("run.running_model", { model: session.model ?? "?" })} · {session.task}
              </p>
              <SessionTimer session={session} />
            </div>
            <div className="flex flex-wrap items-start gap-2 md:flex-col">
              <Button
                size="lg"
                variant="outline"
                disabled={disabled || !session.controls.next}
                onClick={() => {
                  control("next");
                }}
              >
                <PxIcon name="skip" /> {t("controls.next")}
              </Button>
              <Button
                size="lg"
                variant="destructive"
                disabled={disabled || !session.controls.stop}
                onClick={() => {
                  control("stop");
                }}
              >
                <PxIcon name="stop" /> {t("controls.stop")}
              </Button>
            </div>
            <LoopStats targetFps={session.fps} inference />
          </CardContent>
        </Card>
      }
    />
  );
}

interface Summary {
  session: Session;
  duration: number;
  peaks: Record<string, number>;
  alerts: number;
}

function RunSummary({ summary, onClose }: { summary: Summary; onClose: () => void }) {
  const { t } = useTranslation("station");
  const peaks = Object.entries(summary.peaks).sort((a, b) => b[1] - a[1]);
  return (
    <Card data-testid="run-summary">
      <CardHeader>
        <CardTitle>{t("run.summary")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <p>
          {t("run.summary_line", {
            duration: formatClock(summary.duration),
            episodes: summary.session.episode.saved || summary.session.episode.index,
            alerts: summary.alerts,
          })}
        </p>
        {peaks.length ? (
          <ul className="grid grid-cols-2 gap-x-4 sm:grid-cols-3">
            {peaks.map(([k, v]) => (
              <li key={k} className="tabular-nums">
                {k}: {v}°C
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/sessions">{t("run.session_telemetry")}</Link>
          </Button>
          {summary.session.dataset ? (
            <Button asChild variant="outline" size="sm">
              <Link to={`/datasets/${encodeURIComponent(summary.session.dataset)}`}>
                {t("run.eval_dataset_link")}
              </Link>
            </Button>
          ) : null}
          <Button size="sm" onClick={onClose}>
            {t("common.close")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function RunModelPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const { store } = useRuntime();
  const robots = useRobots();
  const models = useModels();
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("model"));
  const session = status?.session?.kind === "run" ? status.session : null;
  const last = useRef<{ session: Session; startedAt: number } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    if (session) {
      if (last.current?.session.id !== session.id) {
        store.resetPeaks();
        last.current = { session, startedAt: Date.now() };
      } else last.current.session = session;
    } else if (last.current) {
      const final = store.getSnapshot().lastSession;
      setSummary({
        session: final?.id === last.current.session.id ? final : last.current.session,
        duration: (Date.now() - last.current.startedAt) / 1000,
        peaks: { ...store.getSnapshot().peaks },
        alerts: store.getSnapshot().alertCount,
      });
      last.current = null;
    }
  }, [session, store]);

  const profile = useMemo(() => {
    const id = status?.robot?.id ?? robots.data?.active;
    return robots.data?.robots.find((r) => r.id === id);
  }, [robots.data, status?.robot?.id]);
  const model = models.data?.models.find((m) => m.key === selected);

  if (session) {
    return (
      <div>
        <PageHeader title={t("run.title")} description={t("run.live_desc")} />
        <RunLive session={session} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("run.title")} description={t("run.desc")} />
      {status?.state === "estopped" ? <LiveLayout header={null} /> : null}
      {summary ? (
        <RunSummary
          summary={summary}
          onClose={() => {
            setSummary(null);
          }}
        />
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <ModelPicker selected={selected} onSelect={setSelected} />
        {model ? <RunSetup key={model.key} model={model} profile={profile} /> : null}
      </div>
    </div>
  );
}
