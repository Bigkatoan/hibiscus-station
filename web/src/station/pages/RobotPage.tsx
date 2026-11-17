/**
 * Robot (§6.2): profiles, port picker with "find by unplugging" / "find by moving", connect, and,
 * once connected, live joints and the motor health panel (the first place users see temperatures).
 */
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { api } from "../api/client";
import { qk, useCalibrations, usePortProbe, usePorts, useRobots, useStationMutation } from "../api/hooks";
import type { Port, PortProbe, RobotProfile, Status } from "../api/types";
import { GoHomeButton, RelaxButton, SetHomeButton } from "../components/HomeControls";
import { JointPanel } from "../components/JointPanel";
import { MotorHealthPanel } from "../components/MotorHealthPanel";
import { StationError } from "../components/StationError";
import { Sprite } from "@/hibiscus/PixelAnim";
import { useStatus } from "../ws/StationProvider";

export function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "robot"
  );
}

function portLabel(p: Port): string {
  return `${p.stable_path ?? p.device}${p.description ? ` · ${p.description}` : ""}${p.vid_pid ? ` (${p.vid_pid})` : ""}`;
}

type Role = "follower" | "leader";

export interface RoleWarning {
  slot: Role;
  /** The role this port's voltage suggests (the other one). */
  looks_like: Role;
  voltage_v: number;
}

/**
 * Voltage hints for the two slots. A slot gets a warning when its port reads like the other role
 * (follower at ~5 V, leader at >= 7 V). The UI offers a swap; it never swaps by itself.
 */
export function roleWarnings(follower: PortProbe | undefined, leader: PortProbe | undefined): RoleWarning[] {
  const out: RoleWarning[] = [];
  if (follower?.voltage_v != null && follower.role_hint === "leader")
    out.push({ slot: "follower", looks_like: "leader", voltage_v: follower.voltage_v });
  if (leader?.voltage_v != null && leader.role_hint === "follower")
    out.push({ slot: "leader", looks_like: "follower", voltage_v: leader.voltage_v });
  return out;
}

function FindPortDialog({
  role,
  method,
  exclude,
  open,
  onOpenChange,
  onFound,
}: {
  role: Role;
  method: "unplug" | "motion";
  exclude: string[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onFound: (p: Port) => void;
}) {
  const { t } = useTranslation("station");
  const [before, setBefore] = useState<string[] | null>(null);
  const [found, setFound] = useState<Port | null>(null);
  const snap = useStationMutation(() =>
    api.post<{ ports_before: string[] }>("/ports/detect", { method: "unplug" }),
  );
  const detect = useStationMutation((body: { method: string; ports_before?: string[] }) =>
    api.post<{ port: Port }>("/ports/detect", { ...body, exclude, timeout_s: 15 }),
  );
  const roleName = t(`robot.role_${role}`);
  const reset = () => {
    setBefore(null);
    setFound(null);
    snap.reset();
    detect.reset();
  };
  const run = () => {
    if (method === "motion") {
      detect.mutate(
        { method: "motion" },
        {
          onSuccess: (r) => {
            setFound(r.port);
          },
        },
      );
    } else if (before === null) {
      snap.mutate(undefined, {
        onSuccess: (r) => {
          setBefore(r.ports_before);
          detect.mutate(
            { method: "unplug", ports_before: r.ports_before },
            {
              onSuccess: (x) => {
                setFound(x.port);
              },
            },
          );
        },
      });
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t(method === "unplug" ? "robot.find_role_unplug" : "robot.find_role_motion", {
              role: roleName,
            })}
          </DialogTitle>
          <DialogDescription>
            {t(method === "unplug" ? "robot.find_unplug_desc_role" : "robot.find_motion_desc_role", {
              role: roleName,
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3">
          <Sprite name="icon_plug" />
          <p className="text-sm" role="status">
            {found
              ? t("robot.found_role", { port: found.stable_path ?? found.device, role: roleName })
              : detect.isPending
                ? t(method === "unplug" ? "robot.unplug_now_role" : "robot.move_now_role", {
                    role: roleName,
                  })
                : t("robot.find_ready")}
          </p>
        </div>
        <StationError error={snap.error ?? detect.error} />
        <DialogFooter>
          {found ? (
            <Button
              onClick={() => {
                onFound(found);
                reset();
                onOpenChange(false);
              }}
            >
              {t("robot.use_port_role", { role: roleName })}
            </Button>
          ) : (
            <Button onClick={run} disabled={detect.isPending || snap.isPending}>
              {t("robot.find_start")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PortPicker({
  arm: role,
  label,
  value,
  other,
  hint,
  onChange,
  optional,
}: {
  arm: Role;
  label: string;
  value: string;
  /** The port of the other arm: never offered by "find by moving" for this one. */
  other: string;
  hint: PortProbe | undefined;
  onChange: (v: string) => void;
  optional?: boolean;
}) {
  const { t } = useTranslation("station");
  const ports = usePorts();
  const [dialog, setDialog] = useState<"unplug" | "motion" | null>(null);
  const list = ports.data?.ports ?? [];
  const known = list.some((p) => (p.stable_path ?? p.device) === value);
  return (
    <div className="flex flex-col gap-2">
      <Field label={label}>
        <NativeSelect
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        >
          <option value="">{optional ? t("robot.no_leader") : t("robot.pick_port")}</option>
          {!known && value ? <option value={value}>{value}</option> : null}
          {list.map((p) => (
            <option key={p.device} value={p.stable_path ?? p.device} disabled={p.in_use_by !== null}>
              {portLabel(p)}
              {p.in_use_by ? ` — ${t("robot.in_use", { by: p.in_use_by })}` : ""}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          data-testid={`find-${role}-motion`}
          onClick={() => {
            setDialog("motion");
          }}
        >
          {t("robot.find_role_motion", { role: t(`robot.role_${role}`) })}
        </Button>
        <Button
          size="sm"
          variant="outline"
          data-testid={`find-${role}-unplug`}
          onClick={() => {
            setDialog("unplug");
          }}
        >
          {t("robot.find_role_unplug", { role: t(`robot.role_${role}`) })}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void ports.refetch()}>
          {t("robot.refresh_ports")}
        </Button>
      </div>
      {value && hint ? <ProbeHint probe={hint} /> : null}
      <FindPortDialog
        role={role}
        exclude={other ? [other] : []}
        method={dialog ?? "unplug"}
        open={dialog !== null}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        onFound={(p) => {
          onChange(p.stable_path ?? p.device);
        }}
      />
    </div>
  );
}

function ProbeHint({ probe }: { probe: PortProbe }) {
  const { t } = useTranslation("station");
  if (probe.in_use_by) return null;
  if (probe.voltage_v == null)
    return <p className="text-xs text-muted-foreground">{t("robot.probe_none")}</p>;
  const fw = probe.firmware ? ` · fw ${probe.firmware}` : "";
  const key = probe.role_hint ? `robot.probe_looks_${probe.role_hint}` : "robot.probe_unknown";
  return (
    <p className="text-xs text-muted-foreground" data-testid="probe-hint">
      {t(key, { v: probe.voltage_v.toFixed(1) })}
      {fw}
    </p>
  );
}

const isMockProfile = (r: RobotProfile): boolean => r.follower.type === "hibiscus_mock_follower";

/** A new SO-101 profile with the detected USB serial ports filled in (follower first, leader second). */
export function realArmDraft(ports: readonly Port[]): RobotProfile {
  const usb = ports.filter((p) => p.vid_pid !== null && p.in_use_by === null);
  const draft = emptyProfile();
  draft.name = "SO-101";
  draft.follower.port = usb[0] ? (usb[0].stable_path ?? usb[0].device) : "";
  if (usb[1])
    draft.leader = { type: "so101_leader", port: usb[1].stable_path ?? usb[1].device, calibration_id: "" };
  return draft;
}

function CalibrationIdField({
  label,
  arm,
  value,
  fallback,
  onChange,
}: {
  label: string;
  arm: "follower" | "leader";
  value: string;
  fallback: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation("station");
  const files = useCalibrations();
  const own = arm === "follower" ? "so_follower" : "so_leader";
  const ids = (files.data?.files ?? [])
    .filter((f) => f.arm === arm && (f.dir ?? own) === own)
    .map((f) => f.id);
  return (
    <Field label={label}>
      <NativeSelect
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        data-testid={`cal-id-${arm}`}
      >
        <option value="">{t("robot.cal_new", { id: fallback })}</option>
        {value && !ids.includes(value) ? <option value={value}>{value}</option> : null}
        {ids.map((id) => (
          <option key={id} value={id}>
            {t("robot.cal_existing", { id })}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}

function emptyProfile(): RobotProfile {
  return {
    id: "",
    name: "",
    follower: {
      type: "so101_follower",
      port: "",
      calibration_id: "",
      max_relative_target: 5,
      rest_pose: null,
      on_session_end: "hold",
      disable_torque_on_disconnect: true,
      allow_fast_replay: false,
      grip_hold: { gap_min: 3, load_min_pct: 15 },
    },
    leader: null,
    cameras: {},
    thresholds: null,
    safety_ack: false,
  };
}

function ProfileForm({ initial, onDone }: { initial: RobotProfile | null; onDone: () => void }) {
  const { t } = useTranslation("station");
  const [p, setP] = useState<RobotProfile>(initial ?? emptyProfile());
  const [leaderPort, setLeaderPort] = useState(initial?.leader?.port ?? "");
  const [leaderCal, setLeaderCal] = useState(initial?.leader?.calibration_id ?? "");
  const isNew = initial === null || initial.id === "";
  const save = useStationMutation(
    (prof: RobotProfile) => api.put<RobotProfile>(`/robots/${encodeURIComponent(prof.id)}`, prof),
    [qk.robots],
  );
  const kind = p.follower.type === "so100_follower" ? "so100" : "so101";
  const probePorts = [p.follower.port, leaderPort].filter((x) => x !== "");
  const probe = usePortProbe(probePorts);
  const probeOf = (port: string) => (port ? probe.data?.ports.find((x) => x.device === port) : undefined);
  const warnings = roleWarnings(probeOf(p.follower.port), probeOf(leaderPort));
  // Swap the ports only: each calibration id stays with its role (slot).
  const swap = () => {
    const f = p.follower.port;
    setP({ ...p, follower: { ...p.follower, port: leaderPort } });
    setLeaderPort(f);
  };
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const id = isNew ? slugify(p.name) : p.id;
        const prof: RobotProfile = {
          ...p,
          id,
          follower: { ...p.follower, calibration_id: p.follower.calibration_id || `${id}_follower` },
          leader: leaderPort
            ? {
                type: kind === "so100" ? "so100_leader" : "so101_leader",
                port: leaderPort,
                calibration_id: leaderCal || `${id}_leader`,
              }
            : null,
        };
        save.mutate(prof, { onSuccess: onDone });
      }}
    >
      <Field label={t("robot.name")} required>
        <Input
          value={p.name}
          onChange={(e) => {
            setP({ ...p, name: e.target.value });
          }}
          placeholder="Desk SO-101"
        />
      </Field>
      <Field label={t("robot.type")}>
        <NativeSelect
          value={kind}
          onChange={(e) => {
            setP({
              ...p,
              follower: {
                ...p.follower,
                type: e.target.value === "so100" ? "so100_follower" : "so101_follower",
              },
            });
          }}
        >
          <option value="so101">SO-101</option>
          <option value="so100">SO-100</option>
        </NativeSelect>
      </Field>
      <PortPicker
        arm="follower"
        label={t("robot.follower_port")}
        value={p.follower.port}
        other={leaderPort}
        hint={probeOf(p.follower.port)}
        onChange={(v) => {
          setP({ ...p, follower: { ...p.follower, port: v } });
        }}
      />
      <PortPicker
        arm="leader"
        label={t("robot.leader_port")}
        value={leaderPort}
        other={p.follower.port}
        hint={probeOf(leaderPort)}
        onChange={setLeaderPort}
        optional
      />
      <div className="flex flex-col gap-2 sm:col-span-2">
        {warnings.map((w) => (
          <p
            key={w.slot}
            role="alert"
            data-testid={`role-warning-${w.slot}`}
            className="border-2 border-frame bg-warning px-2 py-1 text-sm text-warning-foreground"
          >
            {t("robot.role_warning", {
              slot: t(`robot.role_${w.slot}`),
              v: w.voltage_v.toFixed(1),
              looks: t(`robot.role_${w.looks_like}`),
            })}
          </p>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={warnings.length > 0 ? "default" : "outline"}
            disabled={!p.follower.port && !leaderPort}
            data-testid="swap-arms"
            onClick={swap}
          >
            {t("robot.swap_arms")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={probePorts.length === 0 || probe.isFetching}
            onClick={() => void probe.refetch()}
          >
            {t("robot.probe_again")}
          </Button>
        </div>
      </div>
      <CalibrationIdField
        label={t("robot.cal_follower")}
        arm="follower"
        value={p.follower.calibration_id}
        fallback={`${isNew ? slugify(p.name) : p.id}_follower`}
        onChange={(v) => {
          setP({ ...p, follower: { ...p.follower, calibration_id: v } });
        }}
      />
      {leaderPort ? (
        <CalibrationIdField
          label={t("robot.cal_leader")}
          arm="leader"
          value={leaderCal}
          fallback={`${isNew ? slugify(p.name) : p.id}_leader`}
          onChange={setLeaderCal}
        />
      ) : null}
      <Field label={t("robot.on_end")}>
        <NativeSelect
          value={p.follower.on_session_end}
          onChange={(e) => {
            setP({ ...p, follower: { ...p.follower, on_session_end: e.target.value as "hold" | "relax" } });
          }}
        >
          <option value="hold">{t("robot.on_end_hold")}</option>
          <option value="relax">{t("robot.on_end_relax")}</option>
        </NativeSelect>
      </Field>
      <StationError error={save.error} className="sm:col-span-2" />
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={!p.name.trim() || !p.follower.port || save.isPending}>
          {t("common.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function ConnectedPanel({ profile }: { profile: RobotProfile }) {
  const { t } = useTranslation("station");
  const status = useStatus();
  const torque = useStationMutation((enabled: boolean) =>
    api.post<Status>("/robots/torque", { arm: "follower", enabled }),
  );
  const torqueOn = status?.robot?.follower_torque ?? false;
  const canTorque = status?.state === "idle" || status?.state === "estopped";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t("joints.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <JointPanel />
          <div className="flex flex-wrap items-start gap-2">
            <SetHomeButton />
            <GoHomeButton />
            {torqueOn ? (
              <RelaxButton />
            ) : (
              <Button
                variant="outline"
                disabled={!canTorque || torque.isPending}
                onClick={() => {
                  torque.mutate(true);
                }}
              >
                {t("robot.torque_on")}
              </Button>
            )}
          </div>
          {profile.follower.rest_pose ? (
            <p className="text-xs text-muted-foreground">{t("robot.rest_saved")}</p>
          ) : null}
          <StationError error={torque.error} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("health.title")}</CardTitle>
          <CardDescription>{t("robot.health_desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <MotorHealthPanel />
        </CardContent>
      </Card>
    </div>
  );
}

export function RobotPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const robots = useRobots();
  const [editing, setEditing] = useState<RobotProfile | "new" | null>(null);
  const connect = useStationMutation((id: string) =>
    api.post<Status>(`/robots/${encodeURIComponent(id)}/connect`, {}),
  );
  const disconnect = useStationMutation(() => api.post<Status>("/robots/disconnect", {}));
  const list = robots.data?.robots ?? [];
  const ports = usePorts();
  const realPorts = (ports.data?.ports ?? []).filter((p) => p.vid_pid !== null);
  const demoMode = Boolean(status?.station.mock);
  const usingDemo =
    Boolean(status?.robot?.mock) || (!demoMode && list.length > 0 && list.every(isMockProfile));
  const connectedId = status?.robot?.connected ? status.robot.id : null;
  const connected = list.find((r) => r.id === connectedId);
  const busy =
    status?.state !== "idle" &&
    status?.state !== "disconnected" &&
    status?.state !== "error" &&
    status?.state !== "estopped";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("robot.title")}
        description={t("robot.desc")}
        actions={
          <Button
            onClick={() => {
              setEditing("new");
            }}
            disabled={editing !== null}
          >
            {t("robot.new")}
          </Button>
        }
      />
      {editing ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {editing === "new" || editing.id === ""
                ? t("robot.new")
                : t("robot.edit", { name: editing.name })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ProfileForm
              initial={editing === "new" ? null : editing}
              onDone={() => {
                setEditing(null);
              }}
            />
          </CardContent>
        </Card>
      ) : null}
      {usingDemo && realPorts.length > 0 && editing === null ? (
        <div
          role="alert"
          data-testid="demo-banner"
          className="flex flex-col gap-2 border-4 border-[#f08a24] bg-[#ffc531] px-3 py-2 text-sm text-[#3b2027] sm:flex-row sm:items-center"
        >
          <p className="min-w-0 flex-1 font-bold">
            {t("demo.banner", { ports: realPorts.map((p) => p.device).join(", ") })}
          </p>
          <Button
            size="sm"
            onClick={() => {
              setEditing(realArmDraft(ports.data?.ports ?? []));
            }}
          >
            {t("demo.create_real")}
          </Button>
        </div>
      ) : null}
      {status?.state === "connecting" ? (
        <p role="status" className="border-2 border-frame bg-card p-2 text-sm">
          {t("robot.connecting")} {status.detail ?? ""}
        </p>
      ) : null}
      <StationError error={connect.error ?? disconnect.error} />
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map((r) => {
          const isConn = r.id === connectedId;
          return (
            <li key={r.id}>
              <Card>
                <CardContent className="flex flex-col gap-2 pt-3 sm:pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-extrabold text-base">{r.name}</span>
                    <Badge variant="outline">
                      {r.follower.type.startsWith("so100") ? "SO-100" : "SO-101"}
                    </Badge>
                    {isMockProfile(r) ? (
                      <Badge variant="warning" data-testid={`demo-badge-${r.id}`}>
                        {t("demo.chip")}
                      </Badge>
                    ) : null}
                    {isConn ? <Badge variant="success">{t("robot.connected")}</Badge> : null}
                  </div>
                  <p className="break-all text-xs text-muted-foreground">
                    {t("arm.follower")}: {r.follower.port}
                    <br />
                    {t("arm.leader")}: {r.leader?.port ?? t("robot.no_leader")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {isConn ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy || disconnect.isPending}
                        onClick={() => {
                          disconnect.mutate(undefined);
                        }}
                      >
                        <PxIcon name="plug" /> {t("robot.disconnect")}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        disabled={
                          connectedId !== null || connect.isPending || (isMockProfile(r) && !demoMode)
                        }
                        title={isMockProfile(r) && !demoMode ? t("demo.connect_disabled") : undefined}
                        onClick={() => {
                          connect.mutate(r.id);
                        }}
                      >
                        <PxIcon name="plug" /> {t("robot.connect")}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={isConn && busy}
                      onClick={() => {
                        setEditing(r);
                      }}
                    >
                      {t("common.edit")}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
      {list.length === 0 && !editing ? (
        <p className="text-sm text-muted-foreground">{t("robot.empty")}</p>
      ) : null}
      {connected ? <ConnectedPanel profile={connected} /> : null}
    </div>
  );
}
