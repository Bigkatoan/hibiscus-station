/**
 * Joint state vs commanded action (§6.5, §6.9): per joint the leader / observed / action / sent
 * values, a position bar, a "clipped" chip, and (run view) a 10 s observed-vs-commanded chart.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { LineChart } from "@/components/charts/LineChart";
import { cn } from "@/lib/utils";
import { useStation } from "../ws/StationProvider";
import { jointName, type StationSnapshot } from "../ws/store";
import { fmt } from "../health";

const selJoints = (s: StationSnapshot) => s.joints;
const selHist = (s: StationSnapshot) => s.jointHist;

function value(rec: Record<string, number> | null | undefined, joint: string): number | null {
  if (!rec) return null;
  return rec[`${joint}.pos`] ?? rec[joint] ?? null;
}

function PosBar({ v, joint }: { v: number | null; joint: string }) {
  // Joints are degrees (use_degrees=True, about ±180); the gripper is 0–100.
  const gripper = joint === "gripper";
  const lo = gripper ? 0 : -180;
  const hi = gripper ? 100 : 180;
  const pct = v === null ? 0 : ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * 100;
  return (
    <span className="relative inline-block h-3 w-16 border-2 border-frame bg-muted sm:w-24" aria-hidden>
      <span className="absolute inset-y-0 w-1 bg-primary" style={{ left: `calc(${pct}% - 2px)` }} />
    </span>
  );
}

export function JointPanel({ chart = false, className }: { chart?: boolean; className?: string }) {
  const { t } = useTranslation("station");
  const joints = useStation(selJoints);
  const hist = useStation(selHist);
  const names = useMemo(
    () => Object.keys(joints?.arms.follower ?? {}).map(jointName),
    [joints?.arms.follower],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked && names.includes(picked) ? picked : (names[0] ?? null);
  const hasLeader = Boolean(joints?.arms.leader);
  const hasAction = Boolean(joints?.action);
  const hasSent = Boolean(joints?.sent);
  const clippedNow = new Set((joints?.clipped ?? []).map(jointName));

  const series = useMemo(() => {
    if (!selected) return [];
    return [
      { label: t("joints.observed"), x: hist.t, y: hist.obs[selected] ?? [] },
      { label: t("joints.commanded"), x: hist.t, y: hist.cmd[selected] ?? [] },
    ];
  }, [hist, selected, t]);
  const clipT = selected ? hist.clipped[selected] : undefined;

  if (!joints) {
    return <p className={cn("text-sm text-muted-foreground", className)}>{t("joints.waiting")}</p>;
  }
  return (
    <section
      aria-label={t("joints.title")}
      className={cn("flex min-w-0 flex-col gap-2", className)}
      data-testid="joint-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-frame text-left text-xs text-muted-foreground">
              <th scope="col" className="pr-2 font-normal">
                {t("joints.joint")}
              </th>
              {hasLeader ? (
                <th scope="col" className="pr-2 font-normal">
                  {t("joints.leader")}
                </th>
              ) : null}
              <th scope="col" className="pr-2 font-normal">
                {t("joints.follower")}
              </th>
              {hasAction ? (
                <th scope="col" className="pr-2 font-normal">
                  {t("joints.action")}
                </th>
              ) : null}
              {hasSent ? (
                <th scope="col" className="pr-2 font-normal">
                  {t("joints.sent")}
                </th>
              ) : null}
              <th scope="col" className="font-normal">
                <span className="sr-only">{t("joints.position")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {names.map((j) => {
              const obs = value(joints.arms.follower, j);
              const clipped = clippedNow.has(j);
              return (
                <tr
                  key={j}
                  data-testid={`joint-${j}`}
                  className={cn("border-b border-frame/30", chart && selected === j && "bg-accent/40")}
                >
                  <th scope="row" className="py-1 pr-2 text-left font-normal">
                    {chart ? (
                      <button
                        type="button"
                        className="underline decoration-dotted underline-offset-2"
                        aria-pressed={selected === j}
                        onClick={() => {
                          setPicked(j);
                        }}
                      >
                        {j}
                      </button>
                    ) : (
                      j
                    )}
                  </th>
                  {hasLeader ? (
                    <td className="py-1 pr-2 tabular-nums">{fmt(value(joints.arms.leader, j))}</td>
                  ) : null}
                  <td className="py-1 pr-2 tabular-nums">{fmt(obs)}</td>
                  {hasAction ? (
                    <td className="py-1 pr-2 tabular-nums">{fmt(value(joints.action, j))}</td>
                  ) : null}
                  {hasSent ? (
                    <td className="py-1 pr-2 tabular-nums">
                      {fmt(value(joints.sent, j))}
                      {clipped ? (
                        <span className="px-notch ml-1 bg-warning px-1 text-xs text-warning-foreground">
                          {t("joints.clipped")}
                        </span>
                      ) : null}
                    </td>
                  ) : null}
                  <td className="py-1">
                    <PosBar v={obs} joint={j} />
                    {!hasSent && clipped ? (
                      <span className="px-notch ml-1 bg-warning px-1 text-xs text-warning-foreground">
                        {t("joints.clipped")}
                      </span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {chart && selected ? (
        <LineChart
          title={t("joints.chart_title", { joint: selected })}
          series={series}
          height={160}
          xLabel={t("joints.seconds")}
          markerX={clipT?.[clipT.length - 1] ?? null}
        />
      ) : null}
    </section>
  );
}
