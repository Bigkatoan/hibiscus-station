/**
 * Datasets & Upload (§6.7): local datasets, the episode list with its telemetry review chart
 * (temperature per joint, alerts as markers), replay, delete, and the resumable upload with
 * progress (hashing → uploading → done).
 */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { LineChart } from "@/components/charts/LineChart";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Mascot } from "@/components/Mascot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { api } from "../api/client";
import {
  qk,
  useDataset,
  useDatasets,
  useEpisodeTelemetry,
  useServerDatasets,
  useStationMutation,
} from "../api/hooks";
import type { Job, LocalDatasetDetail, Session } from "../api/types";
import { JobProgress, formatBytes, scalar, useLatestJob } from "../components/controls";
import { PairForm } from "../components/PairForm";
import { StationError } from "../components/StationError";
import { DEFAULT_THRESHOLDS, levelCss, peakTemp, tempLevel } from "../health";
import { useStatus } from "../ws/StationProvider";

export function DatasetsPage() {
  const { t } = useTranslation("station");
  const datasets = useDatasets();
  const list = datasets.data?.datasets ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("datasets.title")} description={t("datasets.desc")} />
      <StationError error={datasets.error} />
      {list.length === 0 && datasets.isSuccess ? (
        <div className="flex items-center gap-3 border-2 border-dashed border-frame/50 p-4">
          <Mascot mood="idle" size="mini" />
          <p className="text-sm">
            {t("datasets.empty")}{" "}
            <Link className="underline" to="/record">
              {t("nav.record")}
            </Link>
          </p>
        </div>
      ) : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map((d) => (
          <li key={d.name}>
            <Card>
              <CardContent className="flex flex-col gap-1 pt-3 text-sm sm:pt-4">
                <Link
                  to={`/datasets/${encodeURIComponent(d.name)}`}
                  className="font-extrabold text-base underline"
                >
                  {d.name}
                </Link>
                <p>
                  {t("datasets.summary", {
                    episodes: d.episodes,
                    frames: d.frames,
                    fps: d.fps,
                    size: formatBytes(d.size_bytes),
                  })}
                </p>
                <p className="text-xs text-muted-foreground">{d.cameras.join(", ")}</p>
                <div className="flex flex-wrap gap-2">
                  {d.finalized ? (
                    <Badge variant="success">{t("datasets.finalized")}</Badge>
                  ) : (
                    <Badge variant="warning">{t("datasets.not_finalized")}</Badge>
                  )}
                  {d.uploaded ? (
                    <Badge variant="info">{t("datasets.uploaded", { v: d.uploaded.version })}</Badge>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TelemetryChart({ name, index }: { name: string; index: number }) {
  const { t } = useTranslation("station");
  const tel = useEpisodeTelemetry(name, index);
  const series = useMemo(() => {
    const d = tel.data;
    if (!d) return [];
    return Object.entries(d.temp_c.follower ?? {}).map(([motor, ys]) => ({ label: motor, x: d.t, y: ys }));
  }, [tel.data]);
  const alerts = tel.data?.alerts ?? [];
  return (
    <div className="flex flex-col gap-2" data-testid="episode-telemetry">
      <StationError error={tel.error} />
      {series.length ? (
        <LineChart
          title={t("datasets.temp_chart", { n: index + 1 })}
          series={series}
          height={200}
          xLabel={t("joints.seconds")}
          markerX={alerts[0]?.t ?? null}
        />
      ) : tel.isSuccess ? (
        <p className="text-sm text-muted-foreground">{t("datasets.no_telemetry")}</p>
      ) : null}
      {alerts.length ? (
        <ul className="text-xs">
          {alerts.map((a) => (
            <li key={`${a.t}-${a.motor ?? ""}-${a.kind}`}>
              <span
                className="mr-1 inline-block border px-1"
                style={levelCss(a.level === "info" ? "ok" : a.level)}
              >
                {t(`level.${a.level === "info" ? "ok" : a.level}`)}
              </span>
              {a.t.toFixed(1)} s · {a.motor ?? a.kind} {a.value !== null ? `· ${a.value}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function UploadCard({ detail }: { detail: LocalDatasetDetail }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const paired = Boolean(status?.server.paired);
  const serverDatasets = useServerDatasets(paired);
  const [target, setTarget] = useState<"new" | "version">("new");
  const [newName, setNewName] = useState(detail.name);
  const [datasetId, setDatasetId] = useState("");
  const job = useLatestJob("upload", detail.name);
  const upload = useStationMutation(
    (body: { new_dataset_name?: string; dataset_id?: string }) =>
      api.post<Job>(`/datasets/${encodeURIComponent(detail.name)}/upload`, body),
    [qk.datasets],
  );
  if (!paired) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("upload.title")}</CardTitle>
          <CardDescription>{t("upload.pair_first")}</CardDescription>
        </CardHeader>
        <CardContent>
          <PairForm />
        </CardContent>
      </Card>
    );
  }
  const running = job && (job.status === "running" || job.status === "queued");
  const done = job?.status === "succeeded" ? job.result : null;
  return (
    <Card data-testid="upload-card">
      <CardHeader>
        <CardTitle>{t("upload.title")}</CardTitle>
        <CardDescription>{t("upload.desc", { server: status?.server.url ?? "" })}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!detail.finalized ? <p className="text-sm text-destructive">{t("upload.not_finalized")}</p> : null}
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            upload.mutate(
              target === "new" ? { new_dataset_name: newName.trim() } : { dataset_id: datasetId },
            );
          }}
        >
          <Field label={t("upload.target")}>
            <NativeSelect
              value={target}
              onChange={(e) => {
                setTarget(e.target.value as "new" | "version");
              }}
            >
              <option value="new">{t("upload.target_new")}</option>
              <option value="version">{t("upload.target_version")}</option>
            </NativeSelect>
          </Field>
          {target === "new" ? (
            <Field label={t("upload.new_name")}>
              <Input
                value={newName}
                onChange={(e) => {
                  setNewName(e.target.value);
                }}
              />
            </Field>
          ) : (
            <Field label={t("upload.server_dataset")}>
              <NativeSelect
                value={datasetId}
                onChange={(e) => {
                  setDatasetId(e.target.value);
                }}
              >
                <option value="">{t("upload.pick")}</option>
                {(serverDatasets.data?.datasets ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} (v{d.latest_version ?? 0})
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <StationError error={upload.error} className="sm:col-span-2" />
          <div className="sm:col-span-2">
            <Button
              type="submit"
              disabled={
                Boolean(running) ||
                upload.isPending ||
                !detail.finalized ||
                (target === "new" ? !newName.trim() : !datasetId)
              }
            >
              {t("upload.start")}
            </Button>
          </div>
        </form>
        {job ? <JobProgress job={job} /> : null}
        {done ? (
          <p className="flex items-center gap-2 text-sm" data-testid="upload-done">
            <PxIcon name="check" className="text-success" />
            {t("upload.done", { v: scalar(done.version) })}
            {typeof done.server_url === "string" ? (
              <a
                href={done.server_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 underline"
              >
                {t("upload.open")} <PxIcon name="external" />
              </a>
            ) : null}
          </p>
        ) : null}
        {job?.status === "failed" ? (
          <p className="text-xs text-muted-foreground">{t("upload.resume_hint")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function DatasetDetailPage() {
  const { t } = useTranslation("station");
  const { name = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const status = useStatus();
  const detail = useDataset(name);
  const [episode, setEpisode] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const replay = useStationMutation((i: number) =>
    api.post<Session>("/sessions/replay", { dataset: name, episode: i }),
  );
  const del = useStationMutation(() => api.del(`/datasets/${encodeURIComponent(name)}`), [qk.datasets]);
  const d = detail.data;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={name}
        description={
          d
            ? t("datasets.summary", {
                episodes: d.episodes,
                frames: d.frames,
                fps: d.fps,
                size: formatBytes(d.size_bytes),
              })
            : undefined
        }
        actions={
          confirmDelete ? (
            <>
              <Button
                variant="destructive"
                onClick={() => {
                  del.mutate(undefined, {
                    onSuccess: () => {
                      navigate("/datasets");
                    },
                  });
                }}
              >
                {t("datasets.confirm_delete")}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setConfirmDelete(false);
                }}
              >
                {t("common.cancel")}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              onClick={() => {
                setConfirmDelete(true);
              }}
            >
              {t("datasets.delete")}
            </Button>
          )
        }
      />
      <StationError error={detail.error ?? del.error ?? replay.error} />
      {d ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="flex flex-col gap-4">
            {params.get("upload") === "1" || d.uploaded === null ? <UploadCard detail={d} /> : null}
            {d.uploaded ? (
              <p className="text-sm">
                {t("datasets.uploaded", { v: d.uploaded.version })} ·{" "}
                <a
                  className="underline"
                  href={d.uploaded.server_url ?? undefined}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {t("upload.open")}
                </a>
              </p>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>{t("datasets.episodes")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-1">
                  {d.episode_list.map((e) => {
                    const max = peakTemp(e.max_temp_c);
                    return (
                      <li
                        key={e.index}
                        className="flex flex-wrap items-center gap-2 border-b border-frame/30 py-1 text-sm"
                      >
                        <button
                          type="button"
                          className="font-extrabold text-base underline"
                          aria-pressed={episode === e.index}
                          onClick={() => {
                            setEpisode(e.index);
                          }}
                        >
                          #{e.index + 1}
                        </button>
                        <span className="tabular-nums">
                          {e.length_s !== null ? e.length_s.toFixed(1) : "–"} s
                        </span>
                        {max !== null ? (
                          <span
                            className="border px-1 tabular-nums text-xs"
                            style={levelCss(tempLevel(max, DEFAULT_THRESHOLDS))}
                          >
                            {t("datasets.max_temp", { v: max })}
                          </span>
                        ) : null}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto"
                          disabled={status?.state !== "idle" || replay.isPending}
                          onClick={() => {
                            replay.mutate(e.index, {
                              onSuccess: () => {
                                navigate("/replay");
                              },
                            });
                          }}
                        >
                          {t("datasets.replay")}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>{t("datasets.telemetry")}</CardTitle>
              <CardDescription>{t("datasets.telemetry_desc")}</CardDescription>
            </CardHeader>
            <CardContent>
              {episode !== null ? (
                <TelemetryChart name={name} index={episode} />
              ) : (
                <p className="text-sm text-muted-foreground">{t("datasets.pick_episode")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
