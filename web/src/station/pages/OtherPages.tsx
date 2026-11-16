/** Welcome / pair (§6.1), Train (§6.8), Models, Sessions and Settings (§6.10). */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Mascot } from "@/components/Mascot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Progress } from "@/components/ui/misc";
import { formatDateTime } from "@/lib/format";
import { api } from "../api/client";
import {
  qk,
  useDatasets,
  useModels,
  useServer,
  useServerRuns,
  useSessions,
  useSettings,
  useStationMutation,
} from "../api/hooks";
import type { Job, LocalDataset, Settings } from "../api/types";
import { JobProgress, formatBytes, useLatestJob } from "../components/controls";
import { PairForm } from "../components/PairForm";
import { StationError } from "../components/StationError";
import { Sprite } from "@/hibiscus/PixelAnim";
import { maxTempLimit, validateThresholds } from "../health";
import { useStation, useStatus } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";

export function WelcomePage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <Mascot mood="wave" />
        <div className="min-w-0 flex-1">
          <h1 className="font-extrabold text-2xl">{t("welcome.title")}</h1>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t("welcome.lead")}</p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("welcome.robot")}</CardTitle>
            <CardDescription>{t("welcome.robot_desc")}</CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-3">
            <Sprite name="arm_home" />
            <Button asChild>
              <Link to="/robot">{t("welcome.robot_cta")}</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("welcome.pair")}</CardTitle>
            <CardDescription>{t("welcome.pair_desc")}</CardDescription>
          </CardHeader>
          <CardContent>
            {status?.server.paired ? (
              <p className="text-sm">
                {t("welcome.paired", { url: status.server.url ?? "", ws: status.server.workspace ?? "" })}
              </p>
            ) : (
              <PairForm />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** The server's New-run wizard with the uploaded version preselected (`runs/new?version=<id>`). */
export function trainUrl(server: string, workspace: string, d: LocalDataset): string | null {
  const up = d.uploaded;
  if (!up) return null;
  if (up.train_url) return up.train_url;
  if (!up.version_id) return null;
  try {
    const u = new URL(`/w/${encodeURIComponent(workspace)}/runs/new`, server);
    u.searchParams.set("version", up.version_id);
    return u.toString();
  } catch {
    return null;
  }
}

export function TrainPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const datasets = useDatasets();
  const navigate = useNavigate();
  const uploaded = (datasets.data?.datasets ?? []).filter((d) => d.uploaded);
  const [pick, setPick] = useState<string | null>(null);
  const current = uploaded.find((d) => d.name === pick) ?? uploaded[0];
  const runs = useServerRuns(current?.uploaded?.dataset_id ?? null);
  const pull = useStationMutation(
    (id: string) => api.post<Job>("/models/pull", { server_model_id: id }),
    [qk.models],
  );
  const pullJob = useLatestJob("pull");
  if (!status?.server.paired) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={t("train.title")} description={t("train.desc")} />
        <Card>
          <CardContent className="pt-3 sm:pt-4">
            <PairForm />
          </CardContent>
        </Card>
      </div>
    );
  }
  const link =
    current && status.server.url ? trainUrl(status.server.url, status.server.workspace ?? "", current) : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("train.title")} description={t("train.desc")} />
      {uploaded.length === 0 ? (
        <p className="text-sm">
          {t("train.none")}{" "}
          <Link className="underline" to="/upload">
            {t("nav.upload")}
          </Link>
        </p>
      ) : (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-3 sm:pt-4">
            <Field label={t("train.dataset")}>
              <NativeSelect
                value={current?.name ?? ""}
                onChange={(e) => {
                  setPick(e.target.value);
                }}
              >
                {uploaded.map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.name} (v{d.uploaded?.version})
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {link ? (
              <Button asChild className="self-start">
                <a href={link} target="_blank" rel="noreferrer noopener">
                  {t("train.open")} <PxIcon name="external" />
                </a>
              </Button>
            ) : null}
            <p className="text-xs text-muted-foreground">{t("train.no_local")}</p>
          </CardContent>
        </Card>
      )}
      {current ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("train.runs")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <StationError error={runs.error ?? pull.error} />
            {(runs.data?.runs ?? []).length === 0 && runs.isSuccess ? (
              <p className="text-sm text-muted-foreground">{t("train.no_runs")}</p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {(runs.data?.runs ?? []).map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <a href={r.url} target="_blank" rel="noreferrer noopener" className="underline">
                    #{r.number}
                  </a>
                  <Badge variant="info">{r.policy_type}</Badge>
                  <Badge
                    variant={
                      r.status === "succeeded" ? "success" : r.status === "failed" ? "destructive" : "outline"
                    }
                  >
                    {r.status}
                  </Badge>
                  {r.progress !== null ? (
                    <Progress value={r.progress * 100} className="w-24" aria-label={t("train.progress")} />
                  ) : null}
                  {r.status === "succeeded" ? (
                    r.model_id ? (
                      <Button
                        size="sm"
                        disabled={pull.isPending}
                        onClick={() => {
                          if (r.model_id)
                            pull.mutate(r.model_id, {
                              onSuccess: () => {
                                navigate("/run");
                              },
                            });
                        }}
                      >
                        {t("train.pull_run")}
                      </Button>
                    ) : (
                      <Button asChild size="sm" variant="outline">
                        <Link to="/run">{t("train.pull_run")}</Link>
                      </Button>
                    )
                  ) : null}
                </li>
              ))}
            </ul>
            {pullJob && pullJob.status !== "succeeded" ? <JobProgress job={pullJob} /> : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export function ModelsPage() {
  const { t } = useTranslation("station");
  const models = useModels();
  const del = useStationMutation((key: string) => api.del(`/models/${encodeURIComponent(key)}`), [qk.models]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("models.title")}
        description={t("models.desc")}
        actions={
          <Button asChild>
            <Link to="/run">{t("models.import")}</Link>
          </Button>
        }
      />
      <StationError error={models.error ?? del.error} />
      <ul className="grid gap-3 md:grid-cols-2">
        {(models.data?.models ?? []).map((m) => (
          <li key={m.key}>
            <Card>
              <CardContent className="flex flex-col gap-2 pt-3 text-sm sm:pt-4">
                <span className="font-extrabold text-base">{m.name}</span>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">{m.policy_type}</Badge>
                  <Badge variant="outline">{t(`run.source_${m.source}`)}</Badge>
                  {m.verified ? (
                    <Badge variant="success">{t("run.verified")}</Badge>
                  ) : (
                    <Badge variant="warning">{t("run.unverified")}</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(m.size_bytes)} · {m.fps ? `${m.fps} fps · ` : ""}
                  {m.task ?? ""}
                </p>
                <div className="flex gap-2">
                  <Button asChild size="sm">
                    <Link to={`/run?model=${encodeURIComponent(m.key)}`}>{t("models.run")}</Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      del.mutate(m.key);
                    }}
                  >
                    {t("common.remove")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SessionsPage() {
  const { t, i18n } = useTranslation("station");
  const sessions = useSessions();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("sessions.title")} description={t("sessions.desc")} />
      <StationError error={sessions.error} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-frame text-left text-xs text-muted-foreground">
              <th scope="col" className="pr-2 font-normal">
                {t("sessions.started")}
              </th>
              <th scope="col" className="pr-2 font-normal">
                {t("sessions.kind")}
              </th>
              <th scope="col" className="pr-2 font-normal">
                {t("sessions.subject")}
              </th>
              <th scope="col" className="pr-2 font-normal">
                {t("sessions.outcome")}
              </th>
              <th scope="col" className="font-normal">
                {t("sessions.max_temp")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(sessions.data?.sessions ?? []).map((s) => (
              <tr key={s.id} className="border-b border-frame/30">
                <td className="py-1 pr-2">{formatDateTime(s.started_at, i18n.language)}</td>
                <td className="py-1 pr-2">{t(`session.kind_${s.kind}`)}</td>
                <td className="py-1 pr-2">{s.dataset ?? s.model ?? "–"}</td>
                <td className="py-1 pr-2">{t(`reasons.${s.outcome}`, { defaultValue: s.outcome })}</td>
                <td className="py-1 tabular-nums">{s.max_temp_c !== null ? `${s.max_temp_c}°C` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const selLimits = (s: StationSnapshot) => s.limits;

function SettingsForm({ initial }: { initial: Settings }) {
  const { t } = useTranslation("station");
  const [s, setS] = useState<Settings>(initial);
  const status = useStatus();
  const limits = useStation(selLimits);
  const maxTemp = maxTempLimit(limits);
  useEffect(() => {
    setS(initial);
  }, [initial]);
  const save = useStationMutation((body: Settings) => api.put<Settings>("/settings", body), [qk.settings]);
  const errs = validateThresholds(s.thresholds, maxTemp);
  const num = (v: string) => Number(v);
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (errs.length === 0) save.mutate(s);
      }}
    >
      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="mb-2 font-extrabold text-base">{t("settings.thresholds")}</legend>
        <Field label={t("settings.warn")}>
          <Input
            type="number"
            value={s.thresholds.temp_warn_c}
            onChange={(e) => {
              setS({ ...s, thresholds: { ...s.thresholds, temp_warn_c: num(e.target.value) } });
            }}
          />
        </Field>
        <Field label={t("settings.hot")}>
          <Input
            type="number"
            value={s.thresholds.temp_hot_c}
            onChange={(e) => {
              setS({ ...s, thresholds: { ...s.thresholds, temp_hot_c: num(e.target.value) } });
            }}
          />
        </Field>
        <Field label={t("settings.critical")} description={t("settings.critical_hint", { max: maxTemp })}>
          <Input
            type="number"
            value={s.thresholds.temp_critical_c}
            onChange={(e) => {
              setS({ ...s, thresholds: { ...s.thresholds, temp_critical_c: num(e.target.value) } });
            }}
          />
        </Field>
        {errs.length ? (
          <ul className="text-sm text-destructive sm:col-span-3" role="alert">
            {errs.map((k) => (
              <li key={k}>{t(k, { max: maxTemp })}</li>
            ))}
          </ul>
        ) : null}
      </fieldset>
      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="mb-2 font-extrabold text-base">{t("settings.telemetry")}</legend>
        <Field label={t("settings.hot_hz")}>
          <Input
            type="number"
            step={0.5}
            value={s.telemetry.hot_hz}
            onChange={(e) => {
              setS({ ...s, telemetry: { ...s.telemetry, hot_hz: num(e.target.value) } });
            }}
          />
        </Field>
        <Field label={t("settings.cool_hz")}>
          <Input
            type="number"
            step={0.5}
            value={s.telemetry.cool_hz}
            onChange={(e) => {
              setS({ ...s, telemetry: { ...s.telemetry, cool_hz: num(e.target.value) } });
            }}
          />
        </Field>
      </fieldset>
      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="mb-2 font-extrabold text-base">{t("settings.preview")}</legend>
        <Field label={t("settings.preview_width")}>
          <NativeSelect
            value={s.preview.width}
            onChange={(e) => {
              setS({ ...s, preview: { ...s.preview, width: num(e.target.value) } });
            }}
          >
            {[160, 240, 320, 480, 640].map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label={t("settings.preview_fps")}>
          <Input
            type="number"
            min={1}
            max={30}
            value={s.preview.fps}
            onChange={(e) => {
              setS({ ...s, preview: { ...s.preview, fps: num(e.target.value) } });
            }}
          />
        </Field>
        <Field label={t("run.device")}>
          <NativeSelect
            value={s.device}
            onChange={(e) => {
              setS({ ...s, device: e.target.value as Settings["device"] });
            }}
          >
            {(["auto", "cuda", "mps", "cpu"] as const).map((d) => (
              <option key={d} value={d}>
                {t(`device.${d}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={s.safety.deadman_replay}
          onChange={(e) => {
            setS({ ...s, safety: { ...s.safety, deadman_replay: e.target.checked } });
          }}
        />
        {t("settings.deadman")}
      </label>
      <p className="text-xs text-muted-foreground">
        {t("settings.data_dir")}: <span className="font-mono">{status?.station.home ?? ""}</span>
      </p>
      <StationError error={save.error} />
      {save.isSuccess ? (
        <p role="status" className="text-sm text-success">
          {t("settings.saved")}
        </p>
      ) : null}
      <Button type="submit" className="self-start" disabled={errs.length > 0 || save.isPending}>
        {t("common.save")}
      </Button>
    </form>
  );
}

export function SettingsPage() {
  const { t } = useTranslation("station");
  const settings = useSettings();
  const server = useServer();
  const status = useStatus();
  const unpair = useStationMutation(() => api.del("/server"), [qk.server, qk.status]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("settings.title")} />
      <Card>
        <CardContent className="pt-3 sm:pt-4">
          <StationError error={settings.error} />
          {settings.data ? <SettingsForm initial={settings.data} /> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.server")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {server.data?.paired ? (
            <>
              <p className="text-sm">
                {t("welcome.paired", { url: server.data.url ?? "", ws: server.data.workspace ?? "" })}
              </p>
              <Button
                variant="outline"
                className="self-start"
                onClick={() => {
                  unpair.mutate(undefined);
                }}
              >
                {t("settings.unpair")}
              </Button>
            </>
          ) : (
            <PairForm />
          )}
          <StationError error={unpair.error} />
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        {t("settings.versions", {
          station: status?.station.version ?? "?",
          lerobot: status?.station.lerobot ?? "?",
          device: status?.station.device ?? "?",
        })}
        {status?.station.mock ? ` · ${t("settings.mock")}` : ""}
      </p>
    </div>
  );
}
