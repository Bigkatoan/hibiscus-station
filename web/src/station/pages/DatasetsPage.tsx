/**
 * Datasets & Upload (§6.7): local datasets, the episode list with its review (every camera's video
 * in step with the telemetry chart: temperature per joint, alerts as markers, F-72), replay, delete,
 * and the resumable upload with progress (hashing → uploading → done).
 */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useCallback, useMemo, useRef, useState } from "react";
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
  useEpisodeVideos,
  useServerDatasets,
  useStationMutation,
} from "../api/hooks";
import type { Job, LocalDatasetDetail, Session } from "../api/types";
import { JobProgress, formatBytes, scalar, useLatestJob } from "../components/controls";
import { EpisodePlayer, type EpisodeClock } from "../components/EpisodeViewer";
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

/**
 * Seconds into the episode of each telemetry line: frames recorded so far / fps (the video's own
 * time base), else the time since the episode's first line (telemetry from before F-72).
 */
/**
 * Only a written episode has videos to show. Hotfix 0.2.10 (D-2) adds `EpisodeSummary.state`
 * (saved / saving / unreadable); rows without it come from a Station before that hotfix.
 */
export function episodeReviewable(e: object | undefined): boolean {
  if (!e) return false;
  const state = (e as { state?: unknown }).state;
  return state === undefined || state === "saved";
}

export function episodeSeconds(
  t: readonly number[],
  frameIndex: readonly (number | null)[],
  fps: number | null,
) {
  const t0 = t[0] ?? 0;
  return t.map((x, i) => {
    const f = frameIndex[i];
    return fps && f !== null && f !== undefined ? f / fps : x - t0;
  });
}

function TelemetryChart({
  name,
  index,
  fps,
  time,
  onSeek,
  duration,
}: {
  name: string;
  index: number;
  fps: number | null;
  time: number | null;
  onSeek: (t: number) => void;
  /** The episode's length: the x axis spans 0 – duration so a click reaches every frame (QV-9). */
  duration: number | null;
}) {
  const { t } = useTranslation("station");
  const tel = useEpisodeTelemetry(name, index);
  const hover = useRef<number | null>(null);
  const series = useMemo(() => {
    const d = tel.data;
    if (!d) return [];
    const x = episodeSeconds(d.t, d.frame_index ?? [], fps);
    return Object.entries(d.temp_c.follower ?? {}).map(([motor, ys]) => ({ label: motor, x, y: ys }));
  }, [tel.data, fps]);
  const alerts = tel.data?.alerts ?? [];
  const t0 = tel.data?.t[0] ?? 0;
  return (
    <div className="flex flex-col gap-2" data-testid="episode-telemetry">
      <StationError error={tel.error} />
      {series.length ? (
        // A click on the chart moves the videos there (the scrubber is the keyboard way).
        // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
        <div
          className="cursor-crosshair"
          onClick={() => {
            if (hover.current !== null) onSeek(Math.max(0, hover.current));
          }}
        >
          <LineChart
            title={t("datasets.temp_chart", { n: index + 1 })}
            series={series}
            height={200}
            xLabel={t("joints.seconds")}
            markerX={time ?? (alerts[0] ? alerts[0].t - t0 : null)}
            {...(duration ? { xRange: [0, duration] as const } : {})}
            onCursorX={(x) => {
              hover.current = x;
            }}
          />
        </div>
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
              {(a.t - t0).toFixed(1)} s · {a.motor ?? a.kind} {a.value !== null ? `· ${a.value}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** F-72: the episode's cameras and its telemetry chart, on one clock. */
function EpisodeReview({ name, index, fps }: { name: string; index: number; fps: number | null }) {
  const { t } = useTranslation("station");
  const videos = useEpisodeVideos(name, index);
  const [clock, setClock] = useState<EpisodeClock | null>(null);
  const [seekRequest, setSeekRequest] = useState<{ t: number; nonce: number } | null>(null);
  const onClock = useCallback((c: EpisodeClock) => {
    setClock(c);
  }, []);
  const onSeek = useCallback((v: number) => {
    setSeekRequest((r) => ({ t: v, nonce: (r?.nonce ?? 0) + 1 }));
  }, []);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Card data-testid="episode-review">
        <CardHeader>
          <CardTitle>{t("datasets.video_title", { n: index + 1 })}</CardTitle>
          <CardDescription>{t("datasets.video_desc")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <StationError error={videos.error} />
          {videos.data ? (
            <EpisodePlayer
              key={`${name}/${String(index)}`}
              videos={videos.data}
              onClock={onClock}
              seekRequest={seekRequest}
            />
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("datasets.telemetry")}</CardTitle>
          <CardDescription>{t("datasets.telemetry_desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <TelemetryChart
            name={name}
            index={index}
            fps={fps}
            time={videos.data && clock ? clock.time : null}
            onSeek={onSeek}
            duration={clock?.duration ?? videos.data?.length_s ?? null}
          />
        </CardContent>
      </Card>
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
          {episode !== null && episodeReviewable(d.episode_list.find((e) => e.index === episode)) ? (
            <EpisodeReview key={`${name}/${String(episode)}`} name={name} index={episode} fps={d.fps} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{t("datasets.review")}</CardTitle>
                <CardDescription>{t("datasets.video_desc")}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{t("datasets.pick_episode")}</p>
              </CardContent>
            </Card>
          )}
        </div>
      ) : null}
    </div>
  );
}
