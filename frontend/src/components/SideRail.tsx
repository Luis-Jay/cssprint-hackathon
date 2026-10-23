"use client";

import { Landmark } from "lucide-react";
import { Logo } from "@/components/brand";
import { cn } from "@/lib/utils";

/**
 * The blue side rail: onboarding steps plus the "Where to go" shortcut.
 *
 * Full width beside the onboarding form; `compact` is the narrow version on
 * the Where to go page, hidden below the lg breakpoint where the header's
 * Back link does the job.
 */
export function SideRail({
  steps,
  current,
  completedThrough = -1,
  whereToGoActive = false,
  onWhereToGo,
  onStep,
  compact = false,
}: {
  steps: string[];
  /** Index of the step being filled in; null when on another page. */
  current: number | null;
  /** Steps up to and including this index are shown as done. */
  completedThrough?: number;
  whereToGoActive?: boolean;
  onWhereToGo?: () => void;
  /** Makes the step names clickable. */
  onStep?: (index: number) => void;
  compact?: boolean;
}) {
  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col bg-primary text-primary-foreground",
        compact
          ? "sticky top-0 hidden h-screen w-60 px-6 py-8 lg:flex"
          : "px-6 py-6 lg:w-[31%] lg:max-w-md lg:px-14 lg:py-14",
      )}
    >
      <Logo badge={false} textClassName={cn("text-primary-foreground", compact && "text-base")} />

      <ol
        className={cn(
          "flex",
          compact
            ? "my-auto flex-col gap-5"
            : "mt-8 gap-5 overflow-x-auto lg:my-auto lg:flex-col lg:gap-6",
        )}
      >
        {steps.map((label, i) => {
          const dot = (
            <span
              className={cn(
                "shrink-0 rounded-full",
                compact ? "size-3" : "size-3.5 lg:size-4",
                i === current
                  ? "bg-gold"
                  : i <= completedThrough
                    ? "bg-primary-foreground"
                    : "border-2 border-primary-foreground/60",
              )}
            />
          );
          const text = (
            <span
              className={cn(
                compact ? "text-base" : "text-sm lg:text-xl",
                i === current ? "font-bold" : "text-primary-foreground/80",
              )}
            >
              {label}
            </span>
          );
          return (
            <li key={label} className="shrink-0">
              {onStep ? (
                <button
                  type="button"
                  onClick={() => onStep(i)}
                  className="flex items-center gap-3 hover:underline lg:gap-4"
                >
                  {dot}
                  {text}
                </button>
              ) : (
                <span className="flex items-center gap-3 lg:gap-4">
                  {dot}
                  {text}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {onWhereToGo && (
        <button
          type="button"
          onClick={onWhereToGo}
          aria-current={whereToGoActive ? "page" : undefined}
          className={cn(
            "mt-6 hidden items-center gap-3 rounded-2xl text-left font-semibold transition-colors lg:flex",
            compact ? "px-4 py-3" : "px-5 py-4",
            whereToGoActive
              ? "bg-primary-foreground text-primary"
              : "bg-primary-foreground/12 hover:bg-primary-foreground/20",
          )}
        >
          <Landmark className={cn("size-5", whereToGoActive ? "text-primary" : "text-gold")} />
          Where to go
        </button>
      )}
      <p className="mt-4 hidden text-sm text-primary-foreground/75 lg:block">Takes about two minutes.</p>
    </aside>
  );
}
