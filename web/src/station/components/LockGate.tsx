/**
 * A locked wizard step (field report 0.2.8: the rail showed a lock but the page still worked). The
 * page opens and says why it is locked, with a link to the step to do first; its controls are
 * disabled (`<fieldset disabled>`) until the lock lifts. "Pair first" is resolved on the page
 * itself (the Train page is the pairing form), so that page stays usable.
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWizardSteps } from "../StationShell";

/** Where each lock is lifted (null: on the page itself, or by the e-stop dock). */
export const LOCK_TARGET: Record<string, { to: string; step: string } | null> = {
  connect_first: { to: "/robot", step: "robot" },
  needs_leader: { to: "/robot", step: "robot" },
  calibrate_first: { to: "/calibrate", step: "calibrate" },
  calibrate_leader: { to: "/calibrate", step: "calibrate" },
  record_first: { to: "/record", step: "record" },
  pair_first: null,
  estopped: null,
};
const RESOLVED_ON_PAGE = new Set(["pair_first"]);

export function LockGate({ step, children }: { step: string; children: ReactNode }) {
  const { t } = useTranslation("station");
  const { steps, ready } = useWizardSteps();
  const s = steps.find((x) => x.key === step);
  const lock = ready && s?.lock ? s.lock : null;
  const target = lock ? (LOCK_TARGET[lock] ?? null) : null;
  const disabled = lock !== null && !RESOLVED_ON_PAGE.has(lock);
  // The page is always rendered inside the same fieldset, so a lock that comes and goes (an e-stop
  // during a run) never remounts it and its local state (the run summary) survives.
  return (
    <div className="flex flex-col gap-4">
      {lock ? (
        <div
          role="alert"
          data-testid="lock-gate"
          data-lock={lock}
          className="flex items-start gap-3 border-4 border-frame bg-card px-3 py-3"
        >
          <PxIcon name="lock" className="mt-1 shrink-0" />
          <div className="flex min-w-0 flex-col gap-1">
            <p className="font-extrabold">{t("lock.title")}</p>
            <p className="text-sm">{t(`lock.${lock}`)}</p>
            {s?.why ? <p className="break-words font-mono text-xs text-muted-foreground">{s.why}</p> : null}
            {disabled ? <p className="text-xs text-muted-foreground">{t("lock.disabled")}</p> : null}
            {target ? (
              <Button asChild size="sm" className="mt-1 self-start">
                <Link to={target.to}>
                  {t("lock.go", { step: t(`nav.${target.step}`) })} <PxIcon name="arrow_right" />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
      <fieldset
        disabled={disabled}
        aria-disabled={disabled || undefined}
        data-testid={disabled ? "locked-content" : undefined}
        // An e-stop latch is short-lived and the live view (arm, joints, cameras) matters then:
        // its controls are disabled but the page is not dimmed.
        className={cn("m-0 min-w-0 border-0 p-0", disabled && lock !== "estopped" && "opacity-60")}
      >
        {children}
      </fieldset>
    </div>
  );
}
