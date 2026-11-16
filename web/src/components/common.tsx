import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, type ButtonProps } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Alert, AlertTitle } from "@/components/ui/misc";
import { cn } from "@/lib/utils";

export function Spinner({ className, label }: { className?: string; label?: string }) {
  const { t } = useTranslation();
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-muted-foreground", className)}>
      <PxIcon name="spinner" className="px-spin" />
      <span className="sr-only">{label ?? t("common.loading")}</span>
    </span>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 max-w-full">
        <h1 className="min-w-0 font-extrabold text-2xl [overflow-wrap:anywhere]">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

/**
 * Generic error for the shared dialogs (ConfirmButton): never the server `detail` text. Station API
 * errors are localised from their `code` by station/components/StationError.tsx.
 */
export function ErrorAlert({ error, className }: { error: unknown; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const requestId =
    typeof error === "object" && "requestId" in error
      ? (error as { requestId?: string }).requestId
      : undefined;
  return (
    <Alert variant="destructive" className={className}>
      <div className="flex gap-2">
        <PxIcon name="warning" className="mt-0.5 shrink-0" />
        <div>
          <AlertTitle>{t("errors.unknown_error")}</AlertTitle>
          {requestId ? (
            <p className="text-xs text-muted-foreground">{t("errors.request_id", { id: requestId })}</p>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}

export interface ConfirmButtonProps extends Omit<ButtonProps, "onClick"> {
  title: string;
  description?: string;
  confirmLabel: string;
  onConfirm: () => unknown;
  destructive?: boolean;
}

/** Button that asks for confirmation in an accessible dialog before running `onConfirm`. */
export function ConfirmButton({
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
  children,
  ...buttonProps
}: ConfirmButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        setError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button {...buttonProps}>{children}</Button>
      </DialogTrigger>
      <DialogContent {...(description ? {} : { "aria-describedby": undefined })}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <ErrorAlert error={error} />
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onConfirm();
                setOpen(false);
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <PxIcon name="spinner" className="px-spin" /> : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
