/**
 * Tab "Chương trình / Programs" (station-programs.md §5, §8, P3): pick or create a program, edit it
 * in the Blockly editor (Hibiscus theme, toolbox from `GET /programs/blocks`), edit its operator
 * buttons, save (the Station compiles), check, and run it from the run panel with the running block
 * highlighted live.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmButton, Spinner } from "@/components/common";
import { Field } from "@/components/Field";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert, AlertTitle } from "@/components/ui/misc";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import {
  qk,
  useBlockCatalog,
  useDetectors,
  useModels,
  usePoses,
  useProgram,
  usePrograms,
  useProgramStateQuery,
  useRobots,
  useStationMutation,
  useTrajectories,
} from "../../api/hooks";
import type {
  BlockSpec,
  CheckIssue,
  CheckReport,
  OperatorButton,
  Program,
  ProgramInput,
} from "../../api/types";
import { StationError } from "../../components/StationError";
import { emptyRefs, SO101_JOINTS, type EditorRefs } from "../../programs/blockly/refs";
import {
  asEditorDoc,
  blockIds,
  emptyProgram,
  isItemId,
  slugify,
  specIndex,
  stableJson,
  walkBlocks,
  type EditorDoc,
} from "../../programs/blockly/serialize";
import { useStation, useStatus } from "../../ws/StationProvider";
import { RunPanel } from "./RunPanel";
import { blockDetail, isLive } from "./shared";

const BlocklyEditor = lazy(() => import("../../programs/blockly/BlocklyEditor"));

const enc = encodeURIComponent;

function ButtonsEditor({
  buttons,
  onChange,
  disabled,
}: {
  buttons: OperatorButton[];
  onChange: (b: OperatorButton[]) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation("station");
  const [label, setLabel] = useState("");
  const name = slugify(label);
  const ok =
    label.trim() !== "" && isItemId(name) && !buttons.some((b) => b.name === name) && buttons.length < 12;
  return (
    <section aria-labelledby="op-buttons-title" className="flex flex-col gap-2">
      <h2 id="op-buttons-title" className="font-extrabold text-sm">
        {t("programs.editor.buttons_title")}
      </h2>
      <p className="text-xs text-muted-foreground">{t("programs.editor.buttons_desc")}</p>
      <ul className="flex flex-wrap gap-2">
        {buttons.map((b) => (
          <li
            key={b.name}
            className="flex items-center gap-1 border-2 border-frame bg-card px-2 py-1 text-sm"
          >
            <span className="font-bold">{b.label}</span>
            <span className="text-xs text-muted-foreground">({b.name})</span>
            <Button
              size="sm"
              variant="ghost"
              disabled={disabled}
              aria-label={t("programs.editor.remove_button", { label: b.label })}
              onClick={() => {
                onChange(buttons.filter((x) => x.name !== b.name));
              }}
            >
              <PxIcon name="close" />
            </Button>
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ok) return;
          onChange([...buttons, { name, label: label.trim() }]);
          setLabel("");
        }}
      >
        <Field label={t("programs.editor.button_label")}>
          <Input
            value={label}
            maxLength={40}
            disabled={disabled}
            className="w-48"
            onChange={(e) => {
              setLabel(e.target.value);
            }}
          />
        </Field>
        <Button type="submit" variant="outline" disabled={!ok || disabled}>
          <PxIcon name="plus" /> {t("programs.editor.add_button")}
        </Button>
      </form>
    </section>
  );
}

function NewProgramForm({ existing, onCreated }: { existing: string[]; onCreated: (id: string) => void }) {
  const { t } = useTranslation("station");
  const [name, setName] = useState("");
  const id = slugify(name);
  const create = useStationMutation(
    (body: ProgramInput) => api.put<Program>(`/programs/${enc(id)}`, body),
    [qk.programs],
  );
  const taken = existing.includes(id);
  // Programs belong to a robot profile: the connected one, else the active one (the Station's rule).
  const status = useStatus();
  const robots = useRobots();
  const profileId = status?.robot?.id ?? robots.data?.active ?? null;
  const profile = robots.data?.robots.find((r) => r.id === profileId) ?? null;
  const noProfile = robots.isSuccess && profile === null;
  if (noProfile) {
    return (
      <Alert variant="warning" data-testid="program-no-profile">
        <AlertTitle>{t("programs.editor.no_profile")}</AlertTitle>
        <p className="mt-1 text-sm">
          {t("programs.editor.no_profile_hint")}{" "}
          <Link to="/robot" className="underline">
            {t("nav.robot")}
          </Link>
        </p>
      </Alert>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!id || taken) return;
        create.mutate(
          { name: name.trim(), editor: emptyProgram(), buttons: [] },
          { onSuccess: (p) => onCreated(p.id) },
        );
      }}
    >
      <Field
        label={t("programs.editor.new_name")}
        description={id ? t("programs.editor.new_id", { id }) : t("programs.editor.new_hint")}
        error={taken ? t("programs.editor.id_taken") : undefined}
      >
        <Input
          value={name}
          maxLength={80}
          className="w-56"
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </Field>
      <Button type="submit" disabled={!id || taken || create.isPending}>
        <PxIcon name="plus" /> {t("programs.editor.create")}
      </Button>
      {profile && !status?.robot?.connected ? (
        <p className="w-full text-xs text-muted-foreground" data-testid="program-profile-note">
          {t("programs.editor.for_profile", { name: profile.name || profile.id })}
        </p>
      ) : null}
      <StationError error={create.error} className="w-full" />
    </form>
  );
}

/** The editor's dropdown lists, from the live Station stores (labels translated). */
function useEditorRefs(buttons: OperatorButton[]): EditorRefs {
  const { t } = useTranslation("station");
  const trajectories = useTrajectories();
  const poses = usePoses();
  const detectors = useDetectors();
  const models = useModels();
  const status = useStatus();
  const signals = useStation((s) => s.signals);
  return useMemo(() => {
    const base = emptyRefs();
    return {
      ...base,
      trajectories: (trajectories.data?.trajectories ?? [])
        .filter((x) => x.status !== "draft")
        .map((x) => ({ value: x.id, label: x.name })),
      poses: (poses.data?.poses ?? []).map((p) => ({ value: p.name, label: p.name })),
      detectors: (detectors.data?.detectors ?? []).map((d) => ({
        value: d.id,
        label: d.name,
        labels: d.labels,
      })),
      models: (models.data?.models ?? []).map((m) => ({ value: m.key, label: m.name })),
      cameras: (status?.cameras ?? []).map((c) => c.name),
      buttons: buttons.map((b) => ({ value: b.name, label: b.label })),
      signals: Object.keys(signals),
      joints: SO101_JOINTS,
      text: {
        none: t("programs.editor.ref_none"),
        detectorCamera: t("programs.editor.ref_detector_camera"),
        anyMotor: t("programs.editor.ref_any_motor"),
        anyLabel: t("programs.editor.ref_any_label"),
        missing: t("programs.editor.ref_missing"),
      },
    };
  }, [trajectories.data, poses.data, detectors.data, models.data, status?.cameras, buttons, signals, t]);
}

function ProgramWorkspace({ program, onDeleted }: { program: Program; onDeleted: () => void }) {
  const { t } = useTranslation("station");
  const qc = useQueryClient();
  const catalog = useBlockCatalog();
  const live = useStation((s) => s.program);
  useProgramStateQuery(program.id);
  const [doc, setDoc] = useState<EditorDoc>(() => asEditorDoc(program.editor));
  const [saved, setSaved] = useState(() =>
    stableJson({ e: asEditorDoc(program.editor), b: program.buttons, n: program.name }),
  );
  const [name, setName] = useState(program.name);
  const [buttons, setButtons] = useState<OperatorButton[]>(program.buttons);
  const [issues, setIssues] = useState<CheckIssue[]>(program.issues);
  const [version, setVersion] = useState(program.version);
  const [dryRunVersion, setDryRunVersion] = useState(program.dry_run_version);
  const refs = useEditorRefs(buttons);
  const running = live?.program_id === program.id && isLive(live);
  const dirty = stableJson({ e: doc, b: buttons, n: name }) !== saved;

  const save = useStationMutation(
    (body: ProgramInput) => api.put<Program>(`/programs/${enc(program.id)}`, body),
    [qk.programs],
  );
  const check = useStationMutation(() => api.post<CheckReport>(`/programs/${enc(program.id)}/check`));
  const del = useStationMutation(() => api.del(`/programs/${enc(program.id)}`));

  const applySaved = useCallback(
    (p: Program) => {
      setSaved(stableJson({ e: doc, b: buttons, n: name }));
      setIssues(p.issues);
      setVersion(p.version);
      setDryRunVersion(p.dry_run_version);
      qc.setQueryData(qk.program(p.id), p);
    },
    [doc, buttons, name, qc],
  );

  const doSave = useCallback(async (): Promise<boolean> => {
    try {
      const p = await save.mutateAsync({
        name: name.trim() || program.name,
        editor: doc,
        buttons,
      });
      applySaved(p);
      return true;
    } catch {
      return false;
    }
  }, [save, name, program.name, doc, buttons, applySaved]);

  // A dry run that passed moves `dry_run_version` (completed, or stopped by the operator: a
  // `repeat forever` program never completes). The Station decides; ask it once the dry run ends.
  const dryRunEnded =
    live?.program_id === program.id && live.dry_run && !isLive(live) ? `${live.run_id}:${live.status}` : null;
  useEffect(() => {
    if (!dryRunEnded) return undefined;
    let current = true;
    api
      .get<Program>(`/programs/${enc(program.id)}`)
      .then((p) => {
        if (current) setDryRunVersion(p.dry_run_version);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [dryRunEnded, program.id]);

  const issueText = useCallback(
    (i: CheckIssue) => t(`programs.issues.${i.code}`, { ...i.params, defaultValue: i.code }),
    [t],
  );
  const specs = useMemo(
    () => (catalog.data ? specIndex(catalog.data) : new Map<string, BlockSpec>()),
    [catalog.data],
  );
  const blocks = useMemo(() => new Map([...walkBlocks(doc)].map((b) => [b.id, b])), [doc]);
  const blockLabel = useCallback(
    (id: string) => {
      const b = blocks.get(id);
      const kind = b ? (specs.get(b.type)?.ast ?? b.type) : null;
      if (!b || !kind) return id;
      const what = t(`programs.ast.${kind}`, { defaultValue: kind });
      const detail = blockDetail(b.fields ?? {}, refs);
      return detail ? `${what} ${detail}` : what;
    },
    [blocks, specs, refs, t],
  );
  const ids = useMemo(() => blockIds(doc), [doc]);
  const detectorsUsed = useMemo(
    () => [
      ...new Set(
        [...walkBlocks(doc)].map((b) => b.fields?.DETECTOR).filter((v): v is string => typeof v === "string"),
      ),
    ],
    [doc],
  );
  const highlight = running && live.block_id && ids.has(live.block_id) ? live.block_id : null;
  const errors = issues.filter((i) => i.severity === "error");

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-3 pt-3 sm:pt-4">
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t("programs.editor.name")} className="min-w-[12rem] flex-1">
              <Input
                value={name}
                maxLength={80}
                disabled={running}
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
            </Field>
            <Badge variant="outline" className="mb-2">
              {t("programs.editor.version", { v: version })}
            </Badge>
            {dirty ? (
              <Badge variant="warning" className="mb-2" data-testid="unsaved">
                {t("programs.editor.unsaved")}
              </Badge>
            ) : null}
            <Button
              disabled={running || save.isPending || !dirty}
              onClick={() => {
                void doSave();
              }}
            >
              <PxIcon name="check" /> {t("common.save")}
            </Button>
            <Button
              variant="outline"
              disabled={running || check.isPending || dirty}
              onClick={() => {
                check.mutate(undefined, {
                  onSuccess: (r) => {
                    setIssues(r.issues);
                  },
                });
              }}
            >
              <PxIcon name="search" /> {t("programs.editor.check")}
            </Button>
            <ConfirmButton
              variant="ghost"
              destructive
              disabled={running}
              title={t("programs.editor.delete_title", { name: program.name })}
              confirmLabel={t("common.remove")}
              aria-label={t("programs.editor.delete_title", { name: program.name })}
              onConfirm={async () => {
                await del.mutateAsync(undefined);
                qc.removeQueries({ queryKey: qk.program(program.id) });
                await qc.refetchQueries({ queryKey: qk.programs, exact: true });
                onDeleted();
              }}
            >
              <PxIcon name="trash" />
            </ConfirmButton>
          </div>
          <StationError error={save.error ?? check.error ?? del.error ?? catalog.error} />
          {issues.length > 0 ? (
            <ul
              className="flex flex-col gap-1 text-sm"
              aria-label={t("programs.editor.issues")}
              data-testid="program-issues"
            >
              {issues.map((i) => (
                <li key={i.id} className="flex items-start gap-2" data-severity={i.severity}>
                  <PxIcon
                    name={i.severity === "error" ? "warning" : "info"}
                    className={i.severity === "error" ? "text-destructive" : "text-info"}
                  />
                  <span>
                    {issueText(i)}
                    {i.block_id ? (
                      <span className="text-xs text-muted-foreground"> · {blockLabel(i.block_id)}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex items-center gap-2 text-sm text-success" data-testid="program-ok">
              <PxIcon name="check" /> {t("programs.editor.no_issues")}
            </p>
          )}
          {errors.length === 0 && dryRunVersion === version ? (
            <p className="text-xs text-muted-foreground">{t("programs.editor.dry_done")}</p>
          ) : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="h-[60vh] min-h-[24rem] border-4 border-frame" data-testid="editor-frame">
            {catalog.data ? (
              <Suspense fallback={<Spinner className="m-4" />}>
                <BlocklyEditor
                  catalog={catalog.data}
                  refs={refs}
                  doc={doc}
                  docKey={program.id}
                  onChange={setDoc}
                  highlight={highlight}
                  issues={issues}
                  issueText={issueText}
                  readOnly={running}
                />
              </Suspense>
            ) : (
              <Spinner className="m-4" />
            )}
          </div>
          <ButtonsEditor buttons={buttons} onChange={setButtons} disabled={running} />
        </div>
        <RunPanel
          programId={program.id}
          ensureSaved={() => (dirty ? doSave() : Promise.resolve(true))}
          onReport={(r) => {
            setIssues(r.issues);
          }}
          issueText={issueText}
          blockLabel={blockLabel}
          detectors={detectorsUsed}
          dryRunVersion={dryRunVersion}
          version={version}
        />
      </div>
    </div>
  );
}

export function ProgramTab() {
  const { t } = useTranslation("station");
  const programs = usePrograms();
  const live = useStation((s) => s.program);
  const list = programs.data?.programs ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // A running program is the one to show after a reload.
  const id = selected ?? (live && isLive(live) ? live.program_id : null) ?? list[0]?.id ?? null;
  const program = useProgram(id);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        {list.length > 0 ? (
          <Field label={t("programs.editor.pick")}>
            <NativeSelect
              value={id ?? ""}
              onChange={(e) => {
                setSelected(e.target.value);
                setCreating(false);
              }}
            >
              {list.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.ok ? "" : ` (${t("programs.editor.has_errors")})`}
                </option>
              ))}
            </NativeSelect>
          </Field>
        ) : null}
        <Button
          variant="outline"
          aria-expanded={creating}
          onClick={() => {
            setCreating((v) => !v);
          }}
        >
          <PxIcon name="plus" /> {t("programs.editor.new")}
        </Button>
      </div>
      {creating || (list.length === 0 && !programs.isLoading) ? (
        <Card>
          <CardContent className="pt-3 sm:pt-4">
            <NewProgramForm
              existing={list.map((p) => p.id)}
              onCreated={(nid) => {
                setSelected(nid);
                setCreating(false);
              }}
            />
          </CardContent>
        </Card>
      ) : null}
      <StationError error={programs.error ?? program.error} />
      {program.data ? (
        <ProgramWorkspace
          key={program.data.id}
          program={program.data}
          onDeleted={() => {
            setSelected(null);
          }}
        />
      ) : null}
    </div>
  );
}
