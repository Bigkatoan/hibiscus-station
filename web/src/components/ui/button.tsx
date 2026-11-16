import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Pixel buttons: raised 9-slice frames (12×12, slice 4 → 8 px border). Day uses the synced sprites
 * (public/pixel/ui_button*.png), night flat indigo frames; label colours live in index.css
 * (.px-btn-*) and are checked against WCAG AA in pixelTheme.test.ts (BUTTON_COLOURS).
 */
export const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap text-sm font-extrabold disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "px-btn px-btn-green hover:brightness-110 active:translate-y-[2px] active:brightness-95",
        destructive: "px-btn px-btn-red hover:brightness-110 active:translate-y-[2px] active:brightness-95",
        outline: "px-btn px-btn-wood hover:brightness-105 active:translate-y-[2px] active:brightness-95",
        secondary: "px-btn px-btn-wood hover:brightness-105 active:translate-y-[2px] active:brightness-95",
        ghost:
          "border-2 border-transparent hover:border-frame hover:bg-accent hover:text-accent-foreground active:translate-y-[2px]",
        link: "font-sans text-sm font-bold text-primary underline decoration-2 underline-offset-4 hover:decoration-4",
      },
      size: {
        default: "h-10 px-2",
        sm: "h-9 px-1",
        lg: "h-12 px-4",
        icon: "h-10 w-10 p-0",
      },
    },
    compoundVariants: [
      { variant: "ghost", size: "default", className: "px-3" },
      { variant: "ghost", size: "sm", className: "px-2" },
    ],
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...(asChild ? {} : { type: type ?? "button" })}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
