import {
  forwardRef,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

/** Sunken pixel field: 2px outline, inner top-left shadow, glow focus ring (index.css). */
const fieldBase =
  "px-field flex w-full px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-destructive aria-[invalid=true]:border-dashed";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        fieldBase,
        "h-10 file:border-0 file:bg-transparent file:text-sm file:font-medium",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea className={cn(fieldBase, "min-h-[80px]", className)} ref={ref} {...props} />
  ),
);
Textarea.displayName = "Textarea";

/** Native <select>: fully accessible and keyboard-friendly on every platform. */
export const NativeSelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select className={cn(fieldBase, "px-select h-10 appearance-none pr-9", className)} ref={ref} {...props}>
      {children}
    </select>
  ),
);
NativeSelect.displayName = "NativeSelect";

export const Checkbox = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, "type">>(
  ({ className, ...props }, ref) => (
    <input
      type="checkbox"
      className={cn("h-5 w-5 shrink-0 accent-[rgb(var(--primary))]", className)}
      ref={ref}
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";
