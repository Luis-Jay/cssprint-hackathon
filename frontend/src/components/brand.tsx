import { cn } from "@/lib/utils";

export const PRODUCT_NAME = "Negosyo Copilot";

/** The sun from the flag: a disc with eight rays. */
export function SunMark({ className }: { className?: string }) {
  const rays = Array.from({ length: 8 }, (_, i) => i * 45);
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" className={cn("text-gold", className)}>
      <circle cx="24" cy="24" r="7" fill="currentColor" />
      {rays.map((deg) => (
        <line
          key={deg}
          x1="24"
          y1="7"
          x2="24"
          y2="12"
          stroke="currentColor"
          strokeWidth="3.2"
          strokeLinecap="round"
          transform={`rotate(${deg} 24 24)`}
        />
      ))}
    </svg>
  );
}

/** Logo lockup. `badge` puts the sun in a blue disc, for white backgrounds. */
export function Logo({
  badge = true,
  className,
  textClassName,
}: {
  badge?: boolean;
  className?: string;
  textClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      {badge ? (
        <span className="grid size-9 place-items-center rounded-full bg-primary">
          <SunMark className="size-6" />
        </span>
      ) : (
        <SunMark className="size-8" />
      )}
      <span className={cn("font-display text-lg font-bold tracking-tight", textClassName)}>
        {PRODUCT_NAME}
      </span>
    </span>
  );
}

export function FlagStripe({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("flag-stripe w-full", className)} />;
}
