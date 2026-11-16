/**
 * Tab "Nhận diện / Detection" (station-programs.md §4 camera, §8): live camera preview with a
 * region drawn on it, colour rules (OpenCV HSV ranges) or an ONNX classifier, and the live label
 * and confidence (`POST /detectors/{id}/test` on the latest frame, never in the control tick).
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmButton, Spinner } from "@/components/common";
import { Field } from "@/components/Field";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Progress } from "@/components/ui/misc";
import { api } from "../../api/client";
import { qk, useDetectors, useStationMutation } from "../../api/hooks";
import type { ColorRule, Detector, DetectorInput, DetectorResult, DetectorSpec, Roi } from "../../api/types";
import { CameraTile } from "../../components/CameraGrid";
import { StationError } from "../../components/StationError";
import { isItemId, slugify } from "../../programs/blockly/serialize";
import { useStatus } from "../../ws/StationProvider";

const enc = encodeURIComponent;

/** OpenCV HSV (H 0–179, S/V 0–255) → CSS rgb(). */
export function hsvToRgb(h: number, s: number, v: number): string {
  const hh = (h * 2) / 60;
  const ss = s / 255;
  const vv = v / 255;
  const c = vv * ss;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  const [r, g, b] =
    hh < 1
      ? [c, x, 0]
      : hh < 2
        ? [x, c, 0]
        : hh < 3
          ? [0, c, x]
          : hh < 4
            ? [0, x, c]
            : hh < 5
              ? [x, 0, c]
              : [c, 0, x];
  const m = vv - c;
  const to = (u: number) => Math.round((u + m) * 255);
  return `rgb(${to(r)} ${to(g)} ${to(b)})`;
}

/** Middle hue of a rule (wrapping around red when h_min > h_max). */
export function midHue(r: ColorRule): number {
  if (r.h_min <= r.h_max) return (r.h_min + r.h_max) / 2;
  return ((r.h_min + r.h_max + 180) / 2) % 180;
}

export const PRESETS: Record<string, Omit<ColorRule, "label">> = {
  red: { h_min: 170, h_max: 8, s_min: 120, s_max: 255, v_min: 70, v_max: 255, min_fraction: 0.05 },
  orange: { h_min: 9, h_max: 20, s_min: 120, s_max: 255, v_min: 80, v_max: 255, min_fraction: 0.05 },
  yellow: { h_min: 21, h_max: 34, s_min: 100, s_max: 255, v_min: 80, v_max: 255, min_fraction: 0.05 },
  green: { h_min: 35, h_max: 85, s_min: 80, s_max: 255, v_min: 50, v_max: 255, min_fraction: 0.05 },
  blue: { h_min: 100, h_max: 125, s_min: 120, s_max: 255, v_min: 50, v_max: 255, min_fraction: 0.05 },
};

const DEFAULT_ROI: Roi = { x: 0.3, y: 0.3, w: 0.4, h: 0.4 };

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function round3(v: number): number {
  return Math.round(v * 1000) / 1000;
}

/** Drag a rectangle on the camera frame; the result is normalised to the frame (0..1). */
export function RoiOverlay({
  roi,
  onChange,
  label,
}: {
  roi: Roi;
  onChange: (r: Roi) => void;
  label: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const point = (e: ReactPointerEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (!r || r.width === 0 || r.height === 0) return { x: 0, y: 0 };
    return { x: clamp01((e.clientX - r.left) / r.width), y: clamp01((e.clientY - r.top) / r.height) };
  };
  const update = (e: ReactPointerEvent) => {
    const a = start.current;
    if (!a) return;
    const b = point(e);
    const w = Math.abs(b.x - a.x);
    const h = Math.abs(b.y - a.y);
    if (w < 0.01 || h < 0.01) return;
    onChange({ x: round3(Math.min(a.x, b.x)), y: round3(Math.min(a.y, b.y)), w: round3(w), h: round3(h) });
  };
  return (
    <div
      ref={box}
      className="absolute inset-0 cursor-crosshair touch-none"
      data-testid="roi-overlay"
      // Pointer-only drawing surface; keyboard users set the region with the number fields below.
      aria-hidden
      title={label}
      onPointerDown={(e) => {
        start.current = point(e);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={update}
      onPointerUp={(e) => {
        update(e);
        start.current = null;
      }}
    >
      <div
        className="pointer-events-none absolute border-4 border-dashed border-[#5ef1e3]"
        style={{
          left: `${roi.x * 100}%`,
          top: `${roi.y * 100}%`,
          width: `${roi.w * 100}%`,
          height: `${roi.h * 100}%`,
        }}
        data-testid="roi-box"
      />
    </div>
  );
}

function RuleRow({
  rule,
  onChange,
  onRemove,
  index,
}: {
  rule: ColorRule;
  onChange: (r: ColorRule) => void;
  onRemove: () => void;
  index: number;
}) {
  const { t } = useTranslation("station");
  const n = (k: keyof ColorRule, v: string, max: number) =>
    onChange({ ...rule, [k]: Math.min(max, Math.max(0, Math.round(Number(v) || 0))) });
  const numField = (k: "h_min" | "h_max" | "s_min" | "v_min", max: number) => (
    <Field label={t(`programs.det.${k}`)}>
      <Input
        type="number"
        min={0}
        max={max}
        value={rule[k] ?? 0}
        className="w-20"
        onChange={(e) => {
          n(k, e.target.value, max);
        }}
      />
    </Field>
  );
  return (
    <li
      className="flex flex-wrap items-end gap-2 border-b border-frame/30 pb-2"
      data-testid={`rule-${index}`}
    >
      <span
        aria-hidden
        className="mb-1 inline-block h-8 w-8 border-2 border-frame"
        style={{ background: hsvToRgb(midHue(rule), Math.max(rule.s_min ?? 0, 160), 220) }}
      />
      <Field label={t("programs.det.label")}>
        <Input
          value={rule.label}
          maxLength={40}
          className="w-28"
          onChange={(e) => {
            onChange({ ...rule, label: e.target.value });
          }}
        />
      </Field>
      {numField("h_min", 179)}
      {numField("h_max", 179)}
      {numField("s_min", 255)}
      {numField("v_min", 255)}
      <Field label={t("programs.det.min_fraction")}>
        <Input
          type="number"
          min={1}
          max={100}
          value={Math.round((rule.min_fraction ?? 0.05) * 100)}
          className="w-20"
          onChange={(e) => {
            onChange({ ...rule, min_fraction: Math.min(1, Math.max(0.01, Number(e.target.value) / 100)) });
          }}
        />
      </Field>
      <Button
        variant="ghost"
        size="sm"
        onClick={onRemove}
        aria-label={t("programs.det.remove_rule", { label: rule.label })}
      >
        <PxIcon name="trash" />
      </Button>
    </li>
  );
}

function ResultPanel({ result }: { result: DetectorResult }) {
  const { t } = useTranslation("station");
  return (
    <div className="flex flex-col gap-2" role="status" aria-live="polite" data-testid="detector-result">
      <p className="font-extrabold text-xl">
        {result.label === null ? t("programs.det.no_label") : t("programs.det.sees", { label: result.label })}
      </p>
      <Progress value={result.confidence * 100} aria-label={t("programs.det.confidence")} />
      <p className="text-sm tabular-nums">
        {t("programs.det.confidence_value", {
          pct: (result.confidence * 100).toFixed(0),
          ms: result.ms.toFixed(1),
        })}
      </p>
      <ul className="flex flex-wrap gap-2 text-xs tabular-nums">
        {Object.entries(result.scores).map(([k, v]) => (
          <li key={k}>
            <Badge variant={k === result.label ? "success" : "outline"}>
              {k} {(v * 100).toFixed(0)}%
            </Badge>
          </li>
        ))}
      </ul>
      {result.annotated_jpeg_b64 ? (
        <img
          src={`data:image/jpeg;base64,${result.annotated_jpeg_b64}`}
          alt={t("programs.det.annotated")}
          className="pixelated max-w-xs border-2 border-frame"
        />
      ) : null}
    </div>
  );
}

function emptySpec(camera: string): DetectorSpec {
  return {
    kind: "color",
    camera,
    roi: DEFAULT_ROI,
    rules: [{ label: "red", ...PRESETS.red }],
  } as DetectorSpec;
}

function DetectorEditor({
  detector,
  onSaved,
  onDeleted,
}: {
  detector: Detector | null;
  onSaved: (id: string) => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const cameras = (status?.cameras ?? []).map((c) => c.name);
  const [name, setName] = useState(detector?.name ?? "");
  const [id, setId] = useState(detector?.id ?? "");
  const [spec, setSpec] = useState<DetectorSpec>(detector?.spec ?? emptySpec(cameras[0] ?? "front"));
  const [labelsText, setLabelsText] = useState(spec.kind === "classifier" ? spec.labels.join(", ") : "");
  const [live, setLive] = useState(false);
  const isNew = detector === null;
  const effectiveId = isNew ? id || slugify(name) : detector.id;
  const save = useStationMutation(
    (body: DetectorInput) => api.put<Detector>(`/detectors/${enc(effectiveId)}`, body),
    [qk.detectors],
  );
  const del = useStationMutation(() => api.del(`/detectors/${enc(effectiveId)}`), [qk.detectors]);
  const upload = useStationMutation(
    (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post<Detector>(`/detectors/${enc(effectiveId)}/model`, fd);
    },
    [qk.detectors],
  );
  const testOnce = useStationMutation((s: DetectorSpec) =>
    api.post<DetectorResult>(`/detectors/${enc(effectiveId || "draft")}/test`, { spec: s, annotate: true }),
  );
  const liveQ = useQuery({
    queryKey: ["station", "detectors", effectiveId, "live", spec],
    queryFn: () =>
      api.post<DetectorResult>(`/detectors/${enc(effectiveId || "draft")}/test`, { spec, annotate: false }),
    enabled: live && isItemId(effectiveId || "draft"),
    refetchInterval: 1000,
    retry: false,
  });
  useEffect(() => {
    if (!status?.cameras.some((c) => c.name === spec.camera) && cameras[0])
      setSpec((s) => ({ ...s, camera: cameras[0] ?? s.camera }));
    // only when the camera list changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras.join(",")]);

  const setKind = (kind: "color" | "classifier") => {
    if (kind === spec.kind) return;
    if (kind === "classifier") {
      setSpec({
        kind,
        camera: spec.camera,
        roi: spec.roi ?? null,
        labels: ["red", "blue"],
        input_size: 224,
        min_confidence: 0.5,
        none_label: null,
      });
      setLabelsText("red, blue");
    } else setSpec({ ...emptySpec(spec.camera), roi: spec.roi ?? DEFAULT_ROI });
  };
  const roi = spec.roi ?? DEFAULT_ROI;
  const rules = spec.kind === "color" ? spec.rules : [];
  const setRules = (r: ColorRule[]) => {
    if (spec.kind === "color") setSpec({ ...spec, rules: r });
  };
  const labelsValid = spec.kind !== "classifier" || spec.labels.length >= 2;
  const rulesValid =
    spec.kind !== "color" ||
    (rules.length > 0 &&
      rules.every((r) => r.label.trim() !== "") &&
      new Set(rules.map((r) => r.label)).size === rules.length);
  const valid = name.trim() !== "" && isItemId(effectiveId) && labelsValid && rulesValid;
  const result = (live ? liveQ.data : undefined) ?? testOnce.data;

  return (
    <Card data-testid="detector-editor">
      <CardHeader>
        <CardTitle>{isNew ? t("programs.det.new_title") : detector.name}</CardTitle>
        <CardDescription>{t("programs.det.editor_desc")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          <Field label={t("programs.det.camera")}>
            <NativeSelect
              value={spec.camera}
              onChange={(e) => {
                setSpec({ ...spec, camera: e.target.value });
              }}
            >
              {cameras.length === 0 ? <option value={spec.camera}>{spec.camera}</option> : null}
              {cameras.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <CameraTile
            key={spec.camera}
            name={spec.camera}
            cam={status?.cameras.find((c) => c.name === spec.camera)}
            overlay={
              <RoiOverlay
                roi={roi}
                label={t("programs.det.draw_roi")}
                onChange={(r) => {
                  setSpec({ ...spec, roi: r });
                }}
              />
            }
          />
          <p className="text-xs text-muted-foreground">{t("programs.det.draw_roi")}</p>
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">{t("programs.det.roi")}</legend>
            {(["x", "y", "w", "h"] as const).map((k) => (
              <Field key={k} label={t(`programs.det.roi_${k}`)}>
                <Input
                  type="number"
                  step={1}
                  min={k === "w" || k === "h" ? 1 : 0}
                  max={100}
                  value={Math.round(roi[k] * 100)}
                  className="w-20"
                  onChange={(e) => {
                    const v = clamp01(Number(e.target.value) / 100);
                    setSpec({
                      ...spec,
                      roi: { ...roi, [k]: k === "w" || k === "h" ? Math.max(0.01, v) : v },
                    });
                  }}
                />
              </Field>
            ))}
          </fieldset>
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <Field label={t("programs.det.name")} className="min-w-[10rem] flex-1">
              <Input
                value={name}
                maxLength={80}
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
            </Field>
            {isNew ? (
              <Field label={t("programs.det.id")} description={t("programs.det.id_hint")}>
                <Input
                  value={id}
                  placeholder={slugify(name)}
                  className="w-40"
                  onChange={(e) => {
                    setId(e.target.value.toLowerCase());
                  }}
                />
              </Field>
            ) : null}
            <Field label={t("programs.det.kind")}>
              <NativeSelect
                value={spec.kind}
                onChange={(e) => {
                  setKind(e.target.value as "color" | "classifier");
                }}
              >
                <option value="color">{t("programs.det.kind_color")}</option>
                <option value="classifier">{t("programs.det.kind_classifier")}</option>
              </NativeSelect>
            </Field>
          </div>
          {spec.kind === "color" ? (
            <div className="flex flex-col gap-2">
              <ul className="flex flex-col gap-2" aria-label={t("programs.det.rules")}>
                {rules.map((r, i) => (
                  <RuleRow
                    key={i}
                    index={i}
                    rule={r}
                    onChange={(nr) => {
                      setRules(rules.map((x, k) => (k === i ? nr : x)));
                    }}
                    onRemove={() => {
                      setRules(rules.filter((_, k) => k !== i));
                    }}
                  />
                ))}
              </ul>
              <div className="flex flex-wrap gap-2">
                {Object.entries(PRESETS).map(([label, p]) => (
                  <Button
                    key={label}
                    size="sm"
                    variant="outline"
                    disabled={rules.length >= 8 || rules.some((r) => r.label === label)}
                    onClick={() => {
                      setRules([...rules, { label, ...p }]);
                    }}
                  >
                    <span
                      aria-hidden
                      className="inline-block h-3 w-3 border border-frame"
                      style={{ background: hsvToRgb(midHue({ label, ...p }), 200, 220) }}
                    />
                    {t("programs.det.add_rule", { label: t(`programs.det.colour_${label}`) })}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Field label={t("programs.det.labels")} description={t("programs.det.labels_hint")}>
                <Input
                  value={labelsText}
                  onChange={(e) => {
                    setLabelsText(e.target.value);
                    const labels = e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean)
                      .slice(0, 64);
                    setSpec({ ...spec, labels });
                  }}
                />
              </Field>
              <div className="flex flex-wrap gap-3">
                <Field label={t("programs.det.input_size")}>
                  <Input
                    type="number"
                    min={32}
                    max={640}
                    value={spec.input_size ?? 224}
                    className="w-24"
                    onChange={(e) => {
                      setSpec({
                        ...spec,
                        input_size: Math.min(640, Math.max(32, Number(e.target.value) || 224)),
                      });
                    }}
                  />
                </Field>
                <Field label={t("programs.det.min_confidence")}>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={Math.round((spec.min_confidence ?? 0.5) * 100)}
                    className="w-24"
                    onChange={(e) => {
                      setSpec({ ...spec, min_confidence: clamp01(Number(e.target.value) / 100) });
                    }}
                  />
                </Field>
              </div>
              {!isNew ? (
                <Field
                  label={t("programs.det.model")}
                  description={
                    detector.model_file
                      ? t("programs.det.model_set", { file: detector.model_file })
                      : t("programs.det.model_missing")
                  }
                >
                  <Input
                    type="file"
                    accept=".onnx"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) upload.mutate(f);
                    }}
                  />
                </Field>
              ) : (
                <p className="text-xs text-muted-foreground">{t("programs.det.model_after_save")}</p>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={!valid || save.isPending}
              onClick={() => {
                save.mutate({ name: name.trim(), spec }, { onSuccess: (d) => onSaved(d.id) });
              }}
            >
              <PxIcon name="check" /> {t("common.save")}
            </Button>
            <Button
              variant="outline"
              disabled={!rulesValid || !labelsValid || testOnce.isPending}
              onClick={() => {
                testOnce.mutate(spec);
              }}
            >
              <PxIcon name="eye" /> {t("programs.det.test")}
            </Button>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={live}
                onChange={(e) => {
                  setLive(e.target.checked);
                }}
              />
              {t("programs.det.live")}
            </label>
            {!isNew ? (
              <ConfirmButton
                variant="ghost"
                destructive
                className="ml-auto"
                title={t("programs.det.delete_title", { name: detector.name })}
                confirmLabel={t("common.remove")}
                aria-label={t("programs.det.delete_title", { name: detector.name })}
                onConfirm={() => del.mutateAsync(undefined).then(onDeleted)}
              >
                <PxIcon name="trash" />
              </ConfirmButton>
            ) : null}
          </div>
          <StationError error={save.error ?? testOnce.error ?? upload.error ?? (live ? liveQ.error : null)} />
          {result ? <ResultPanel result={result} /> : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function DetectionTab() {
  const { t } = useTranslation("station");
  const detectors = useDetectors();
  const list = detectors.data?.detectors ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected === "__new__" ? null : (list.find((d) => d.id === selected) ?? list[0] ?? null);
  const creating = selected === "__new__" || (list.length === 0 && !detectors.isLoading);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("programs.det.pick")}>
          <NativeSelect
            value={creating ? "__new__" : (current?.id ?? "")}
            onChange={(e) => {
              setSelected(e.target.value);
            }}
          >
            {list.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
            <option value="__new__">{t("programs.det.new")}</option>
          </NativeSelect>
        </Field>
        <Button
          variant="outline"
          onClick={() => {
            setSelected("__new__");
          }}
        >
          <PxIcon name="plus" /> {t("programs.det.new")}
        </Button>
      </div>
      <StationError error={detectors.error} />
      {detectors.isLoading ? <Spinner /> : null}
      {detectors.isLoading ? null : (
        <DetectorEditor
          key={creating ? "__new__" : (current?.id ?? "none")}
          detector={creating ? null : current}
          onSaved={setSelected}
          onDeleted={() => {
            setSelected(null);
          }}
        />
      )}
    </div>
  );
}
