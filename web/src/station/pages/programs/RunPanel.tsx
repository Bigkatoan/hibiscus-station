/**
 * Run panel of a block program (station-programs.md §5.1, §5.2, §8): big Start (dry run / on the
 * robot), Pause/Resume and Stop, the operator buttons and keys, `ask operator` choices, the dry-run
 * fakes, live variables and condition values, camera previews and the run log. The program always
 * runs on the Station; this panel only sends commands and shows `program_state` / `program_log`.
 */
import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Mascot } from "@/components/Mascot";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "../../api/client";
import { qk, useDetectors, useProgramRun, useProgramRuns, useStationMutation } from "../../api/hooks";
import type {
  CheckIssue,
  CheckReport,
  FakeConditions,
  ProgramLogLine,
  ProgramState,
  RunProgramRequest,
  Session,
} from "../../api/types";
import { CameraGrid } from "../../components/CameraGrid";
import { RobotTwin } from "../../twin/RobotTwin";
import { isTextInput } from "../../components/EStopButton";
import { StationError } from "../../components/StationError";
import { useRuntime, useStation, useStatus } from "../../ws/StationProvider";
import { isLive, logLineText, programMood, useProgramInput } from "./shared";

const enc = encodeURIComponent;

export interface RunPanelProps {
  programId: string;
  /** Saves the editor first when it has unsaved edits; resolves to false when the save failed. */
  ensureSaved: () => Promise<boolean>;
  /** Called with the check report before each run (the editor marks the issues). */
  onReport: (r: CheckReport) => void;
  issueText: (i: CheckIssue) => string;
  /** Labels of the blocks (by block id) for the condition list. */
  blockLabel: (blockId: string) => string;
  /** Detector ids the program reads (fake buttons on a dry run). */
  detectors: string[];
  dryRunVersion: number | null;
  version: number | null;
}

/** Keys 0-9/a-z the operator can press while the program runs (never Space: that is the e-stop). */
function useOperatorKeys(state: ProgramState | null, send: (k: string) => void): void {
  useEffect(() => {
    if (!state || !isLive(state) || state.keys.length === 0) return undefined;
    const keys = new Set(state.keys);
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.ctrlKey || e.metaKey || e.altKey || isTextInput(e.target)) return;
      const k = e.key.toLowerCase();
      if (k.length === 1 && keys.has(k)) {
        e.preventDefault();
        send(k);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [state, send]);
}

function ConfirmDialog({
  issues,
  issueText,
  onCancel,
  onRun,
}: {
  issues: CheckIssue[];
  issueText: (i: CheckIssue) => string;
  onCancel: () => void;
  onRun: (ids: string[]) => void;
}) {
  const { t } = useTranslation("station");
  const [acked, setAcked] = useState<string[]>([]);
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("programs.run.confirm_title")}</DialogTitle>
          <DialogDescription>{t("programs.run.confirm_desc")}</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-2">
          {issues.map((i) => (
            <li key={i.id}>
              <label className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={acked.includes(i.id)}
                  onChange={(e) => {
                    setAcked(e.target.checked ? [...acked, i.id] : acked.filter((x) => x !== i.id));
                  }}
                />
                {issueText(i)}
              </label>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={acked.length !== issues.length}
            onClick={() => {
              onRun(acked);
            }}
          >
            <PxIcon name="play" /> {t("programs.run.confirm_run")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FakesPanel({
  programId,
  detectors,
  state,
}: {
  programId: string;
  detectors: string[];
  state: ProgramState;
}) {
  const { t } = useTranslation("station");
  const all = useDetectors();
  const [labels, setLabels] = useState<Record<string, string | null>>({});
  const [holding, setHolding] = useState(false);
  const fake = useMutation({
    mutationFn: (f: FakeConditions) => api.post<ProgramState>(`/programs/${enc(programId)}/fake`, f),
  });
  const list = (all.data?.detectors ?? []).filter((d) => detectors.includes(d.id));
  return (
    <section
      aria-labelledby="fakes-title"
      className="flex flex-col gap-2 border-2 border-dashed border-frame/50 p-2"
    >
      <h3 id="fakes-title" className="font-extrabold text-sm">
        {t("programs.run.fakes_title")}
      </h3>
      {list.map((d) => (
        <div
          key={d.id}
          className="flex flex-wrap items-center gap-1"
          role="group"
          aria-label={t("programs.run.fake_camera", { name: d.name })}
        >
          <span className="mr-1 text-sm">{t("programs.run.fake_camera", { name: d.name })}</span>
          {[...d.labels, null].map((l) => (
            <Button
              key={l ?? "__none__"}
              size="sm"
              variant={labels[d.id] === l && d.id in labels ? "default" : "outline"}
              aria-pressed={labels[d.id] === l && d.id in labels}
              disabled={!isLive(state)}
              onClick={() => {
                setLabels({ ...labels, [d.id]: l });
                fake.mutate({ detectors: { [d.id]: { label: l, confidence: 1 } } });
              }}
            >
              {l ?? t("programs.run.fake_none")}
            </Button>
          ))}
        </div>
      ))}
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={holding}
          disabled={!isLive(state)}
          onChange={(e) => {
            setHolding(e.target.checked);
            fake.mutate({ gripper_holding: e.target.checked });
          }}
        />
        {t("programs.run.fake_holding")}
      </label>
      <StationError error={fake.error} />
    </section>
  );
}

function OperatorPanel({ state, send }: { state: ProgramState; send: ReturnType<typeof useProgramInput> }) {
  const { t } = useTranslation("station");
  const live = isLive(state);
  if (state.buttons.length === 0 && state.keys.length === 0 && !state.ask) return null;
  return (
    <section aria-labelledby="operator-title" className="flex flex-col gap-2">
      <h3 id="operator-title" className="font-extrabold text-sm">
        {t("programs.run.operator_title")}
      </h3>
      {state.ask ? (
        <div
          className="flex flex-col gap-2 border-4 border-frame bg-warning p-3 text-warning-foreground"
          role="alertdialog"
          aria-labelledby="ask-q"
        >
          <p id="ask-q" className="font-extrabold text-lg">
            {state.ask.question}
          </p>
          <div className="flex flex-wrap gap-2">
            {state.ask.choices.map((c) => (
              <Button
                key={c}
                size="lg"
                onClick={() => {
                  send({ kind: "answer", value: c });
                }}
              >
                {c}
              </Button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {state.buttons.map((b) => (
          <Button
            key={b.name}
            size="lg"
            className="min-w-[8rem]"
            disabled={!live}
            onClick={() => {
              send({ kind: "button", value: b.name });
            }}
          >
            {b.label}
          </Button>
        ))}
        {state.keys.map((k) => (
          <Button
            key={k}
            size="lg"
            variant="outline"
            disabled={!live}
            aria-keyshortcuts={k}
            onClick={() => {
              send({ kind: "key", value: k });
            }}
          >
            <PxIcon name="keyboard" /> {t("programs.run.key", { key: k.toUpperCase() })}
          </Button>
        ))}
      </div>
    </section>
  );
}

export function RunPanel({
  programId,
  ensureSaved,
  onReport,
  issueText,
  blockLabel,
  detectors,
  dryRunVersion,
  version,
}: RunPanelProps) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const { store } = useRuntime();
  const program = useStation((s) => s.program);
  const log = useStation((s) => s.programLog);
  const runs = useProgramRuns(programId);
  const mine = program?.program_id === programId ? program : null;
  const other = program && program.program_id !== programId && isLive(program) ? program : null;
  const live = isLive(mine);
  const send = useProgramInput(mine ? programId : null);
  useOperatorKeys(mine, (k) => {
    send({ kind: "key", value: k });
  });
  const [confirm, setConfirm] = useState<{ issues: CheckIssue[]; dry: boolean } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [invalid, setInvalid] = useState(false);

  const run = useMutation({
    mutationFn: (body: RunProgramRequest) => api.post<Session>(`/programs/${enc(programId)}/run`, body),
    onSuccess: (s, body) => {
      if (!body.dry_run) store.setSession(s);
      void runs.refetch();
    },
  });
  const cmd = useStationMutation(
    (action: "pause" | "resume" | "stop") => api.post<ProgramState>(`/programs/${enc(programId)}/${action}`),
    [qk.programRuns(programId)],
  );

  const start = async (dry: boolean, confirmIds: string[] = []) => {
    setError(null);
    setInvalid(false);
    setPending(true);
    try {
      if (!(await ensureSaved())) return;
      const report = await api.post<CheckReport>(`/programs/${enc(programId)}/check`);
      onReport(report);
      if (!report.ok) {
        setInvalid(true);
        return;
      }
      const toConfirm = report.issues.filter((i) => i.severity === "confirm" && !confirmIds.includes(i.id));
      if (toConfirm.length) {
        setConfirm({ issues: toConfirm, dry });
        return;
      }
      await run.mutateAsync({ dry_run: dry, confirm: confirmIds, fps: 30 });
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  };

  const idle = status?.state === "idle";
  // The Station refuses every run, dry runs too, until the e-stop is reset.
  const estopped = status?.state === "estopped";
  const needsDry = version !== null && dryRunVersion !== version;
  const mood = programMood(mine);
  const vars = Object.entries(mine?.variables ?? {});
  const conds = mine?.conditions ?? [];
  // The WS only sends lines from now on: after a reload or a reconnect the run's earlier lines come
  // from its stored log, merged with the live ones by `seq`.
  const stored = useProgramRun(mine ? programId : null, mine?.run_id ?? null);
  const lines = useMemo(() => {
    const bySeq = new Map<number, ProgramLogLine>();
    for (const l of [...(stored.data?.lines ?? []), ...log])
      if (l.run_id === mine?.run_id) bySeq.set(l.seq, l);
    return [...bySeq.values()].sort((a, b) => a.seq - b.seq).slice(-80);
  }, [stored.data, log, mine?.run_id]);

  return (
    <Card data-testid="run-panel" data-status={mine?.status ?? "none"}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Mascot mood={mood} size="mini" label={t(`programs.mood.${mood}`)} />
          <span>{t("programs.run.title")}</span>
          {mine ? (
            <Badge
              variant={
                live
                  ? "info"
                  : mine.status === "completed"
                    ? "success"
                    : mine.status === "stopped"
                      ? "outline"
                      : "destructive"
              }
              data-testid="program-status"
            >
              {t(`programs.status.${mine.status}`)}
              {mine.dry_run ? ` · ${t("programs.run.dry")}` : ""}
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {other ? (
          <p className="text-sm text-warning-foreground">
            {t("programs.run.other_running", { id: other.program_id })}
          </p>
        ) : null}
        {!live ? (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <Button
                size="lg"
                variant="outline"
                className="min-h-14 min-w-[10rem] text-base"
                disabled={pending || estopped || Boolean(other)}
                onClick={() => {
                  void start(true);
                }}
              >
                <PxIcon name="play" /> {t("programs.run.start_dry")}
              </Button>
              <Button
                size="lg"
                className="min-h-14 min-w-[10rem] text-base"
                disabled={pending || !idle || Boolean(other)}
                onClick={() => {
                  void start(false);
                }}
              >
                <PxIcon name="robot" /> {t("programs.run.start_robot")}
              </Button>
            </div>
            {needsDry ? <p className="text-xs text-muted-foreground">{t("programs.run.dry_first")}</p> : null}
            {estopped ? (
              <p className="text-xs font-bold text-destructive">{t("programs.run.robot_estopped")}</p>
            ) : !idle ? (
              <p className="text-xs text-muted-foreground">{t("programs.run.robot_not_idle")}</p>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {mine?.status === "paused" || mine?.status === "pausing" ? (
              <Button
                size="lg"
                className="min-h-14 min-w-[9rem] text-base"
                disabled={cmd.isPending}
                onClick={() => {
                  cmd.mutate("resume");
                }}
              >
                <PxIcon name="play" /> {t("programs.run.resume")}
              </Button>
            ) : (
              <Button
                size="lg"
                variant="outline"
                className="min-h-14 min-w-[9rem] text-base"
                disabled={cmd.isPending}
                onClick={() => {
                  cmd.mutate("pause");
                }}
              >
                <PxIcon name="pause" /> {t("programs.run.pause")}
              </Button>
            )}
            <Button
              size="lg"
              variant="destructive"
              className="min-h-14 min-w-[9rem] text-base"
              disabled={cmd.isPending}
              onClick={() => {
                cmd.mutate("stop");
              }}
            >
              <PxIcon name="stop" /> {t("programs.run.stop")}
            </Button>
          </div>
        )}
        <StationError error={error ?? cmd.error} />
        {invalid ? (
          <p className="text-sm text-destructive" role="alert">
            {t("errors.program_invalid")}
          </p>
        ) : null}
        {mine ? (
          <div
            className="flex flex-col gap-1 text-sm"
            role="status"
            aria-live="polite"
            data-testid="program-now"
          >
            <p className="tabular-nums">
              {t("programs.run.now", {
                t: mine.t.toFixed(1),
                steps: t("programs.run.steps", { count: mine.steps }),
                block: mine.block_id ? blockLabel(mine.block_id) : "–",
              })}
            </p>
            {mine.waiting ? (
              <p className="text-muted-foreground">
                {t(`programs.run.waiting_${mine.waiting.kind}`)}
                {mine.waiting.timeout_s !== null
                  ? ` · ${t("programs.run.timeout_in", { s: Math.max(0, mine.waiting.since_s + mine.waiting.timeout_s - mine.t).toFixed(0) })}`
                  : ""}
              </p>
            ) : null}
            {/* Stopped and e-stopped are said by the badge; a fault or a timeout says what happened. */}
            {mine.message && (mine.status === "failed" || mine.status === "timeout") ? (
              <p className="font-bold">{mine.message}</p>
            ) : null}
          </div>
        ) : null}
        {mine ? <OperatorPanel state={mine} send={send} /> : null}
        {mine?.dry_run && live ? (
          <FakesPanel programId={programId} detectors={detectors} state={mine} />
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="vars-title">
            <h3 id="vars-title" className="mb-1 font-extrabold text-sm">
              {t("programs.run.variables")}
            </h3>
            {vars.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("programs.run.no_variables")}</p>
            ) : (
              <dl
                className="grid grid-cols-[auto_1fr] gap-x-3 text-sm tabular-nums"
                data-testid="program-vars"
              >
                {vars.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="font-bold">{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          <section aria-labelledby="conds-title">
            <h3 id="conds-title" className="mb-1 font-extrabold text-sm">
              {t("programs.run.conditions")}
            </h3>
            {conds.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("programs.run.no_conditions")}</p>
            ) : (
              <ul className="flex flex-col text-sm tabular-nums">
                {conds.map((c) => (
                  <li key={c.block_id} className="flex justify-between gap-2">
                    <span className="truncate">{blockLabel(c.block_id)}</span>
                    <span className={c.value === true ? "font-bold text-success" : ""}>
                      {c.value === null
                        ? (c.message ?? "?")
                        : typeof c.value === "boolean"
                          ? t(c.value ? "programs.run.value_true" : "programs.run.value_false")
                          : String(c.value)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        {/* Side by side when the panel is wide enough, else the twin goes under the cameras. */}
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(16rem,1fr))]">
          <CameraGrid />
          <RobotTwin legend={false} />
        </div>
        <section aria-labelledby="log-title">
          <h3 id="log-title" className="mb-1 font-extrabold text-sm">
            {t("programs.run.log")}
          </h3>
          <div role="log" aria-live="off" aria-labelledby="log-title">
            <ol
              className="max-h-56 overflow-y-auto border-2 border-frame bg-card p-2 font-mono text-xs"
              data-testid="program-log"
            >
              {lines.length === 0 ? (
                <li className="text-muted-foreground">{t("programs.run.log_empty")}</li>
              ) : null}
              {lines.map((l) => (
                <li
                  key={`${l.run_id}-${l.seq}`}
                  className={
                    l.level === "error"
                      ? "text-destructive"
                      : l.level === "warn"
                        ? "text-warning-foreground"
                        : ""
                  }
                >
                  <span className="tabular-nums text-muted-foreground">
                    {l.t.toFixed(1).padStart(6, " ")}
                  </span>{" "}
                  {logLineText(l, t, blockLabel)}
                </li>
              ))}
            </ol>
          </div>
        </section>
        {(runs.data?.runs ?? []).length > 0 ? (
          <section aria-labelledby="runs-title">
            <h3 id="runs-title" className="mb-1 font-extrabold text-sm">
              {t("programs.run.history")}
            </h3>
            <ul className="flex flex-col gap-1 text-xs tabular-nums">
              {(runs.data?.runs ?? []).slice(0, 5).map((r) => (
                <li key={r.run_id} className="flex flex-wrap gap-2">
                  <span>{new Date(r.started_at).toLocaleString()}</span>
                  <span>v{r.version}</span>
                  {r.dry_run ? <Badge variant="outline">{t("programs.run.dry")}</Badge> : null}
                  <span className="font-bold">
                    {r.outcome ? t(`programs.status.${r.outcome}`) : t("programs.status.running")}
                  </span>
                  <span>{t("programs.run.steps", { count: r.steps })}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardContent>
      {confirm ? (
        <ConfirmDialog
          issues={confirm.issues}
          issueText={issueText}
          onCancel={() => {
            setConfirm(null);
          }}
          onRun={(ids) => {
            const dry = confirm.dry;
            setConfirm(null);
            void start(dry, ids);
          }}
        />
      ) : null}
    </Card>
  );
}
