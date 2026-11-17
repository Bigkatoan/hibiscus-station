/**
 * Record (§6.6): setup form, then the running view (cameras, joints, motor health) with the phase
 * header, episode timer, big Next → / ← Re-record / Stop (Esc) controls (same keys as lerobot),
 * the saved-episode strip and the end card.
 */
import { PxIcon } from "@/hibiscus/PixelAnim";
import type { TFunction } from "i18next";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Mascot } from "@/components/Mascot";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { formatSize } from "@/lib/format";
import { api } from "../api/client";
import { qk, useDataset, useDatasets, useStationMutation } from "../api/hooks";
import type { CameraStatus, RecordRequest, Session } from "../api/types";

/** The record form keeps every field set (the request type has server defaults). */
type RecordForm = Required<RecordRequest>;
import { isTextInput } from "../components/EStopButton";
import { LiveLayout } from "../components/LiveLayout";
import { LoopStats, SessionTimer } from "../components/SessionWidgets";
import { StationError } from "../components/StationError";
import { useCritical, useSessionControl } from "../components/controls";
import { DEFAULT_THRESHOLDS, levelCss, peakTemp, tempLevel } from "../health";
import { useRuntime, useStatus } from "../ws/StationProvider";
import type { SessionEndInfo } from "../ws/store";

/** MB per episode: about 2 Mbit/s of encoded video per 640×480@30 camera (scaled by pixels × fps). */
export function estimateEpisodeMb(
  cameras: CameraStatus[],
  fps: number,
  seconds: number,
  video: boolean,
): number {
  const perCam = cameras.map((c) => {
    const px = (c.width * c.height) / (640 * 480);
    return video ? 0.25 * px * (fps / 30) * seconds : ((c.width * c.height * 3) / 1e6 / 10) * fps * seconds;
  });
  const state = 0.0005 * fps * seconds; // parquet joint rows
  return perCam.reduce((a, b) => a + b, 0) + state;
}

/** Arrow keys + Esc while recording (ignored inside text fields). */
export function useRecordKeys(enabled: boolean, onKey: (a: "next" | "rerecord" | "stop") => void): void {
  const cb = useRef(onKey);
  cb.current = onKey;
  useEffect(() => {
    if (!enabled) return undefined;
    const h = (e: KeyboardEvent) => {
      if (isTextInput(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowRight") cb.current("next");
      else if (e.key === "ArrowLeft") cb.current("rerecord");
      else if (e.key === "Escape") cb.current("stop");
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", h);
    return () => {
      window.removeEventListener("keydown", h);
    };
  }, [enabled]);
}

function EpisodeStrip({ dataset, saved }: { dataset: string; saved: number }) {
  const { t } = useTranslation("station");
  // Nothing to show before the first saved episode, and a new dataset that keeps none is removed
  // when the session ends: never ask for it then (QC 0.2.9 QD-18, a console 404).
  const detail = useDataset(dataset, saved > 0);
  const { refetch } = detail;
  useEffect(() => {
    if (saved > 0) void refetch();
  }, [saved, refetch]);
  const eps = detail.data?.episode_list ?? [];
  if (eps.length === 0) return null;
  return (
    <section aria-label={t("record.saved_episodes")}>
      <h3 className="mb-1 font-extrabold text-base">{t("record.saved_episodes")}</h3>
      <ol className="flex gap-2 overflow-x-auto pb-1">
        {eps.map((e) => {
          const max = peakTemp(e.max_temp_c);
          const level = tempLevel(max, DEFAULT_THRESHOLDS);
          return (
            <li
              key={e.index}
              className="flex shrink-0 flex-col items-center border-2 border-frame bg-card px-2 py-1 text-xs"
            >
              <span className="font-extrabold text-base">#{e.index + 1}</span>
              <span className="tabular-nums">{e.length_s !== null ? e.length_s.toFixed(1) : "–"} s</span>
              {max !== null ? (
                <span
                  className="mt-0.5 inline-flex items-center gap-0.5 border px-0.5 tabular-nums"
                  style={levelCss(level)}
                >
                  <PxIcon name="thermo" />
                  {max}°
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function RecordLive({ session }: { session: Session }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const control = useSessionControl();
  const critical = useCritical();
  const live = status?.state === "recording" && !critical;
  useRecordKeys(live, (a) => {
    if (a === "next" && session.controls.next) control("next");
    if (a === "rerecord" && session.controls.rerecord) control("rerecord");
    if (a === "stop" && session.controls.stop) control("stop");
  });
  return (
    <div className="flex flex-col gap-4">
      <LiveLayout
        header={
          <Card>
            <CardContent className="flex flex-col gap-4 pt-3 sm:pt-4">
              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,14rem)]">
                <div className="min-w-0">
                  <p className="text-sm text-muted-foreground">
                    {session.dataset} · {session.task}
                  </p>
                  <SessionTimer session={session} />
                </div>
                <LoopStats targetFps={session.fps} />
              </div>
              <div className="grid grid-cols-3 gap-2" role="group" aria-label={t("record.controls")}>
                <Button
                  size="lg"
                  variant="outline"
                  className="h-16 flex-col gap-0"
                  aria-keyshortcuts="ArrowLeft"
                  disabled={!live || !session.controls.rerecord}
                  onClick={() => {
                    control("rerecord");
                  }}
                >
                  <span className="flex items-center gap-1">
                    <PxIcon name="arrow_left" /> {t("controls.rerecord")}
                  </span>
                  <kbd className="text-xs opacity-80">←</kbd>
                </Button>
                <Button
                  size="lg"
                  className="h-16 flex-col gap-0"
                  aria-keyshortcuts="ArrowRight"
                  disabled={!live || !session.controls.next}
                  onClick={() => {
                    control("next");
                  }}
                >
                  <span className="flex items-center gap-1">
                    {t("controls.next")} <PxIcon name="arrow_right" />
                  </span>
                  <kbd className="text-xs opacity-80">→</kbd>
                </Button>
                <Button
                  size="lg"
                  variant="destructive"
                  className="h-16 flex-col gap-0"
                  aria-keyshortcuts="Escape"
                  disabled={!live || !session.controls.stop}
                  onClick={() => {
                    control("stop");
                  }}
                >
                  <span className="flex items-center gap-1">
                    <PxIcon name="stop" /> {t("controls.stop")}
                  </span>
                  <kbd className="text-xs opacity-80">Esc</kbd>
                </Button>
              </div>
              {session.episode.phase === "saving" || status?.state === "stopping" ? (
                <p className="text-sm font-bold" role="status" data-testid="record-saving">
                  {t("record.saving_note")}
                </p>
              ) : null}
              {session.dataset ? (
                <EpisodeStrip dataset={session.dataset} saved={session.episode.saved} />
              ) : null}
            </CardContent>
          </Card>
        }
      />
    </div>
  );
}

function RecordSetup() {
  const { t, i18n } = useTranslation("station");
  const status = useStatus();
  const datasets = useDatasets();
  const [form, setForm] = useState<RecordForm>({
    dataset: "",
    mode: "new",
    task: "",
    num_episodes: 20,
    episode_time_s: 30,
    reset_time_s: 10,
    fps: 30,
    video: true,
    on_timeout: "save",
    countdown_s: 3,
  });
  const start = useStationMutation(
    (req: RecordRequest) => api.post<Session>("/sessions/record", req),
    [qk.datasets],
  );
  const set = <K extends keyof RecordForm>(k: K, v: RecordForm[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
  };
  const cams = status?.cameras ?? [];
  const mb = estimateEpisodeMb(cams, form.fps, form.episode_time_s, form.video);
  const nameOk = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$/.test(form.dataset);
  const exists = (datasets.data?.datasets ?? []).some((d) => d.name === form.dataset);
  const nameError =
    form.dataset && !nameOk
      ? t("record.name_invalid")
      : form.mode === "new" && exists
        ? t("record.name_exists")
        : undefined;
  const can = nameOk && !nameError && form.task.trim() !== "" && status?.state === "idle";

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("record.setup")}</CardTitle>
        <CardDescription>{t("record.setup_desc")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (can) start.mutate({ ...form, task: form.task.trim() });
          }}
        >
          <Field label={t("record.mode")}>
            <NativeSelect
              value={form.mode}
              onChange={(e) => {
                set("mode", e.target.value as RecordForm["mode"]);
              }}
            >
              <option value="new">{t("record.mode_new")}</option>
              <option value="append" disabled={(datasets.data?.datasets ?? []).length === 0}>
                {t("record.mode_append")}
              </option>
            </NativeSelect>
          </Field>
          {form.mode === "new" ? (
            <Field label={t("record.dataset")} required {...(nameError ? { error: nameError } : {})}>
              <Input
                value={form.dataset}
                placeholder="picknplace_red"
                onChange={(e) => {
                  set("dataset", e.target.value);
                }}
              />
            </Field>
          ) : (
            <Field label={t("record.dataset")} required>
              <NativeSelect
                value={form.dataset}
                onChange={(e) => {
                  const d = datasets.data?.datasets.find((x) => x.name === e.target.value);
                  setForm((f) => ({
                    ...f,
                    dataset: e.target.value,
                    task: d?.task ?? f.task,
                    fps: d?.fps ?? f.fps,
                  }));
                }}
              >
                <option value="">{t("record.pick_dataset")}</option>
                {(datasets.data?.datasets ?? []).map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.name} ({d.episodes})
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <Field
            label={t("record.task")}
            className="sm:col-span-2"
            required
            description={t("record.task_hint")}
          >
            <Input
              value={form.task}
              placeholder={t("record.task_placeholder")}
              onChange={(e) => {
                set("task", e.target.value);
              }}
            />
          </Field>
          <Field label={t("record.episodes")}>
            <Input
              type="number"
              min={1}
              max={500}
              value={form.num_episodes}
              onChange={(e) => {
                set("num_episodes", Number(e.target.value));
              }}
            />
          </Field>
          <Field label={t("record.episode_time")}>
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
          <Field label={t("record.reset_time")}>
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
          <Field label={t("record.fps")}>
            <NativeSelect
              value={form.fps}
              disabled={form.mode === "append"}
              onChange={(e) => {
                set("fps", Number(e.target.value));
              }}
            >
              <option value={15}>15</option>
              <option value={30}>30</option>
            </NativeSelect>
          </Field>
          <Field label={t("record.on_timeout")} description={t("record.on_timeout_hint")}>
            <NativeSelect
              value={form.on_timeout}
              onChange={(e) => {
                set("on_timeout", e.target.value as RecordForm["on_timeout"]);
              }}
            >
              <option value="save">{t("record.timeout_save")}</option>
              <option value="discard">{t("record.timeout_discard")}</option>
            </NativeSelect>
          </Field>
          <label className="flex items-center gap-2 self-end text-sm">
            <Checkbox
              checked={form.video}
              onChange={(e) => {
                set("video", e.target.checked);
              }}
            />
            {t("record.video")}
          </label>
          <p className="text-sm text-muted-foreground sm:col-span-2" data-testid="disk-estimate">
            {t("record.estimate", {
              size: formatSize(mb * 1e6, i18n.language),
              total: formatSize(mb * 1e6 * form.num_episodes, i18n.language),
              count: cams.length,
            })}
          </p>
          <StationError error={start.error} className="sm:col-span-2" />
          <div className="sm:col-span-2">
            <Button type="submit" size="lg" disabled={!can || start.isPending}>
              {t("record.start")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/** The dataset's folder on this computer, shown on request, with a copy button. */
function DatasetPath({ path }: { path: string }) {
  const { t } = useTranslation("station");
  const [copied, setCopied] = useState(false);
  // navigator.clipboard exists only in a secure context (127.0.0.1 is one; a LAN address is not)
  const canCopy = typeof navigator !== "undefined" && "clipboard" in navigator;
  return (
    <details className="mt-1 text-sm" data-testid="record-path">
      <summary className="cursor-pointer text-muted-foreground underline">{t("record.path_show")}</summary>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <code className="min-w-0 break-all text-xs">{path}</code>
        {canCopy ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(path).then(
                () => {
                  setCopied(true);
                },
                () => undefined,
              );
            }}
          >
            <PxIcon name="copy" /> {copied ? t("record.path_copied") : t("record.path_copy")}
          </Button>
        ) : null}
      </div>
    </details>
  );
}

/** What the end of a record session says about the episodes it did not keep (QC 0.2.9 QD-12). */
interface RecordEnd {
  /** The episode in progress was dropped (an e-stop or a fault in the middle of it). */
  dropped: boolean;
  /** The dataset still exists (false: a new dataset that kept no episode was removed). */
  kept: boolean;
  /** Why the session ended: "stopped", "completed", or an e-stop / fault reason. */
  reason: string;
}

function recordEnd(end: SessionEndInfo | null, last: Session): RecordEnd {
  const summary = (end?.id === last.id ? end.summary : null) ?? {};
  const raw = end?.id === last.id ? (end.reason ?? end.outcome) : last.outcome;
  return {
    dropped: summary.dropped_in_progress === true,
    // an older Station sends no flag: with no episode saved, a new dataset was removed
    kept: typeof summary.dataset_kept === "boolean" ? summary.dataset_kept : last.episode.saved > 0,
    // the mock and older Stations prefix e-stop outcomes with "estop_"
    reason: raw.startsWith("estop_") ? raw.slice("estop_".length) : raw,
  };
}

function droppedText(t: TFunction<"station">, ended: Session, info: RecordEnd): string {
  return t("record.dropped", {
    n: ended.episode.saved + 1,
    reason: t(`reasons.${info.reason}`, { defaultValue: t("reasons.internal") }),
  });
}

function NothingSaved({
  ended,
  info,
  onAgain,
}: {
  ended: Session;
  info: RecordEnd | null;
  onAgain: () => void;
}) {
  const { t } = useTranslation("station");
  const end = info ?? { dropped: false, kept: false, reason: ended.outcome };
  const name = ended.dataset ?? "";
  let why: string;
  if (end.dropped) why = droppedText(t, ended, end);
  else if (end.reason === "stopped" || end.reason === "completed") why = t("record.none_stopped");
  else
    why = t("record.none_ended", {
      reason: t(`reasons.${end.reason}`, { defaultValue: t("reasons.internal") }),
    });
  return (
    <Card data-testid="record-none">
      <CardContent className="flex flex-wrap items-center gap-4 pt-3 sm:pt-4">
        <Mascot mood="idle" />
        <div className="min-w-[min(14rem,100%)] flex-1" role="status">
          <p className="break-words font-extrabold text-base">{t("record.none_title")}</p>
          <p className="text-sm">{why}</p>
          <p className="text-sm text-muted-foreground">
            {end.kept ? t("record.none_kept", { name }) : t("record.none_removed", { name })}
          </p>
        </div>
        <Button onClick={onAgain}>{t("record.again")}</Button>
      </CardContent>
    </Card>
  );
}

export function RecordPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const datasets = useDatasets();
  const { store } = useRuntime();
  const session = status?.session?.kind === "record" ? status.session : null;
  const wasRecording = useRef(false);
  const [ended, setEnded] = useState<Session | null>(null);
  const [endInfo, setEndInfo] = useState<RecordEnd | null>(null);
  useEffect(() => {
    if (session) {
      wasRecording.current = true;
      setEnded(null);
      setEndInfo(null);
    } else if (wasRecording.current) {
      wasRecording.current = false;
      // The store keeps the final `session` message (phase "done", saved count, summary).
      const snap = store.getSnapshot();
      const last = snap.lastSession;
      setEnded(last?.kind === "record" ? last : null);
      setEndInfo(last?.kind === "record" ? recordEnd(snap.lastEnd, last) : null);
    }
  }, [session, store]);

  const endedPath = ended?.dataset
    ? datasets.data?.datasets.find((d) => d.name === ended.dataset)?.root
    : undefined;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("record.title")} description={t("record.desc")} />
      {session ? <RecordLive session={session} /> : null}
      {!session && ended?.episode.saved === 0 ? (
        <NothingSaved
          ended={ended}
          info={endInfo}
          onAgain={() => {
            setEnded(null);
          }}
        />
      ) : null}
      {!session && ended && ended.episode.saved > 0 ? (
        <Card data-testid="record-done">
          {/* QC 0.2.9 QD-11: at 390 px the text wraps under the mascot / above the buttons instead of
              squeezing into a one-word column; the local path sits behind a disclosure. */}
          <CardContent className="flex flex-wrap items-center gap-4 pt-3 sm:pt-4">
            <Mascot mood="happy" />
            <div className="min-w-[min(14rem,100%)] flex-1" data-testid="record-done-text">
              <p className="break-words font-extrabold text-base">
                {t("record.done", { count: ended.episode.saved, name: ended.dataset ?? "" })}
              </p>
              {endInfo?.dropped ? (
                <p className="text-sm text-muted-foreground" data-testid="record-dropped">
                  {droppedText(t, ended, endInfo)}
                </p>
              ) : null}
              {endedPath ? <DatasetPath path={endedPath} /> : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to={`/datasets/${encodeURIComponent(ended.dataset ?? "")}?upload=1`}>
                  {t("record.upload")}
                </Link>
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setEnded(null);
                }}
              >
                {t("record.more")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!session && !ended ? <RecordSetup /> : null}
    </div>
  );
}
