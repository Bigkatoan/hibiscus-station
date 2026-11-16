/**
 * The values the editor's reference dropdowns offer (trajectories, poses, detectors and their
 * labels, models, cameras, operator buttons, signals, joints, motors, keys). Pure data, filled by
 * the program screen from the REST queries; the custom dropdown field reads it every time a menu
 * opens, so a new trajectory appears without reloading the workspace.
 */
import type { RefKind } from "./serialize";

export interface RefOption {
  value: string;
  label: string;
}

export interface DetectorRef extends RefOption {
  labels: string[];
}

export interface EditorRefs {
  trajectories: RefOption[];
  poses: RefOption[];
  detectors: DetectorRef[];
  models: RefOption[];
  cameras: string[];
  buttons: RefOption[];
  signals: string[];
  joints: string[];
  /** Translated texts for the placeholder options. */
  text: { none: string; detectorCamera: string; anyMotor: string; anyLabel: string; missing: string };
}

export const SO101_JOINTS = [
  "shoulder_pan",
  "shoulder_lift",
  "elbow_flex",
  "wrist_flex",
  "wrist_roll",
  "gripper",
];
export const OPERATOR_KEYS = "0123456789abcdefghijklmnopqrstuvwxyz".split("");

export function emptyRefs(): EditorRefs {
  return {
    trajectories: [],
    poses: [],
    detectors: [],
    models: [],
    cameras: [],
    buttons: [],
    signals: [],
    joints: SO101_JOINTS,
    text: { none: "-", detectorCamera: "-", anyMotor: "*", anyLabel: "*", missing: "?" },
  };
}

let current: EditorRefs = emptyRefs();

export function setEditorRefs(refs: EditorRefs): void {
  current = refs;
}

export function editorRefs(): EditorRefs {
  return current;
}

const plain = (vs: string[]): RefOption[] => vs.map((v) => ({ value: v, label: v }));

/**
 * Menu options for one reference field: `[label, value]` pairs. `optional` fields (camera, label of
 * a confidence block) start with an empty value meaning "the default". `detector` is the value of
 * the block's DETECTOR field (for `label`), `value` the field's current value, which is kept even
 * when it no longer exists (shown as "id ?") so a stale program still opens.
 */
export function refOptions(
  kind: RefKind,
  opts: { optional?: boolean; detector?: string | null; value?: string | null; refs?: EditorRefs } = {},
): [string, string][] {
  const r = opts.refs ?? current;
  let list: RefOption[];
  let empty: string | null = null;
  switch (kind) {
    case "trajectory":
      list = r.trajectories;
      break;
    case "pose":
      list = r.poses;
      break;
    case "detector":
      list = r.detectors;
      break;
    case "label": {
      const det = r.detectors.find((d) => d.value === opts.detector);
      list = plain(det?.labels ?? []);
      if (opts.optional) empty = r.text.anyLabel;
      break;
    }
    case "camera":
      list = plain(r.cameras);
      if (opts.optional) empty = r.text.detectorCamera;
      break;
    case "model":
      list = r.models;
      break;
    case "button":
      list = r.buttons;
      break;
    case "signal":
      list = plain(r.signals);
      break;
    case "joint":
      list = plain(r.joints);
      break;
    case "motor": {
      const motors: [string, string][] = [
        [r.text.anyMotor, "any"],
        ...r.joints.map((j): [string, string] => [j, j]),
      ];
      return [...motors, ...keep(opts.value, ["any", ...r.joints], r)];
    }
    case "key":
      list = plain(OPERATOR_KEYS);
      break;
  }
  const out: [string, string][] = [];
  if (empty !== null) out.push([empty, ""]);
  out.push(...list.map((o): [string, string] => [o.label, o.value]));
  out.push(
    ...keep(
      opts.value,
      out.map((o) => o[1]),
      r,
    ),
  );
  if (out.length === 0) out.push([r.text.none, ""]);
  return out;
}

function keep(value: string | null | undefined, known: string[], r: EditorRefs): [string, string][] {
  if (!value || known.includes(value)) return [];
  return [[`${value} ${r.text.missing}`, value]];
}
