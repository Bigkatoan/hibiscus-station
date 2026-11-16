import * as TabsPrimitive from "@radix-ui/react-tabs";
import { PxIcon } from "@/hibiscus/PixelAnim";
import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type ElementRef,
} from "react";
import { cn, overflowState } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

/**
 * Tab strip. On narrow screens it scrolls horizontally; pixel-style chevron buttons appear on the
 * side(s) that have more tabs, so users can tell the strip is cut off (CX-10). The chevrons are a
 * pointer/touch aid only (keyboard users move between tabs with the arrow keys).
 */
export const TabsList = forwardRef<
  ElementRef<typeof TabsPrimitive.List>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, onScroll, ...props }, ref) => {
  const inner = useRef<ElementRef<typeof TabsPrimitive.List> | null>(null);
  const setRefs = useCallback(
    (node: ElementRef<typeof TabsPrimitive.List> | null) => {
      inner.current = node;
      if (typeof ref === "function") ref(node);
      else if (ref) ref.current = node;
    },
    [ref],
  );
  const [more, setMore] = useState({ left: false, right: false });
  const update = useCallback(() => {
    const el = inner.current;
    if (!el) return;
    const next = overflowState(el);
    setMore((prev) => (prev.left === next.left && prev.right === next.right ? prev : next));
  }, []);
  useEffect(() => {
    const el = inner.current;
    if (!el) return undefined;
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [update]);
  const nudge = (dir: 1 | -1) => {
    const el = inner.current;
    if (!el) return;
    el.scrollBy({ left: dir * Math.max(80, el.clientWidth * 0.6), behavior: "smooth" });
  };
  const chevron =
    "absolute bottom-[2px] z-10 flex h-9 w-7 items-center justify-center border-2 border-frame bg-secondary text-secondary-foreground";
  return (
    <div className="relative w-full min-w-0 max-w-full">
      <TabsPrimitive.List
        ref={setRefs}
        onScroll={(e) => {
          update();
          onScroll?.(e);
        }}
        className={cn(
          "flex max-w-full items-end justify-start gap-1 overflow-x-auto border-b-2 border-frame px-1 pt-1 text-secondary-foreground [scrollbar-width:thin]",
          more.left && "pl-8",
          more.right && "pr-8",
          className,
        )}
        {...props}
      />
      {more.left ? (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          data-testid="tabs-more-left"
          className={cn(chevron, "left-0")}
          onClick={() => {
            nudge(-1);
          }}
        >
          <PxIcon name="chevron_left" />
        </button>
      ) : null}
      {more.right ? (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          data-testid="tabs-more-right"
          className={cn(chevron, "right-0")}
          onClick={() => {
            nudge(1);
          }}
        >
          <PxIcon name="chevron_right" />
        </button>
      ) : null}
    </div>
  );
});
TabsList.displayName = "TabsList";

export const TabsTrigger = forwardRef<
  ElementRef<typeof TabsPrimitive.Trigger>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "-mb-[2px] inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap border-2 border-frame bg-secondary px-3 font-extrabold text-base text-secondary-foreground hover:brightness-105 focus-visible:shadow-none focus-visible:outline-offset-[-5px] disabled:pointer-events-none disabled:opacity-50 data-[state=active]:h-10 data-[state=active]:border-b-card data-[state=active]:bg-card data-[state=active]:text-card-foreground [&_img]:shrink-0",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = forwardRef<
  ElementRef<typeof TabsPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("mt-4", className)} {...props} />
));
TabsContent.displayName = "TabsContent";
