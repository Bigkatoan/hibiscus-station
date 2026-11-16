import { useId, type ReactElement, type ReactNode } from "react";
import { cloneElement, isValidElement } from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FieldProps {
  label: ReactNode;
  /** The control; receives id / aria-describedby / aria-invalid. */
  children: ReactElement<Record<string, unknown>>;
  description?: ReactNode;
  error?: string | undefined;
  className?: string;
  id?: string;
  required?: boolean;
}

/** Label + control + help + error, wired for screen readers (WCAG 1.3.1, 3.3.1, 3.3.2). */
export function Field({ label, children, description, error, className, id, required }: FieldProps) {
  const autoId = useId();
  const controlId = id ?? `f-${autoId}`;
  const descId = description ? `${controlId}-desc` : undefined;
  const errId = error ? `${controlId}-err` : undefined;
  const describedBy = [descId, errId].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id: controlId,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        "aria-required": required ? true : undefined,
      })
    : children;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={controlId}>
        {label}
        {required ? (
          <span aria-hidden className="ml-0.5 text-destructive">
            *
          </span>
        ) : null}
      </Label>
      {control}
      {description ? (
        <p id={descId} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      {error ? (
        <p id={errId} className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
