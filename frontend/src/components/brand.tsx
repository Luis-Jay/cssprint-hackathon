import { cn } from "@/lib/utils";

export const PRODUCT_NAME = "Sellyo";

/**
 * The designed logo artwork, if you have it. Put a transparent PNG (or SVG)
 * of the envelope in frontend/public/brand/ and set the path here, e.g.
 * "/brand/sellyo-mark.png". While it is null the drawn SellyoMark below is used.
 */
const LOGO_IMAGE: string | null = null;

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

/**
 * Sellyo's mark: a parchment envelope with blue line-work, sealed with a red
 * wax seal carrying the flag's sun. A flat take on the textured artwork, so
 * it stays crisp down to favicon size.
 */
export function SellyoMark({ className }: { className?: string }) {
  if (LOGO_IMAGE) {
    // eslint-disable-next-line @next/next/no-img-element -- tiny static brand asset
    return <img src={LOGO_IMAGE} alt="" aria-hidden="true" className={cn("object-contain", className)} />;
  }
  const rays = Array.from({ length: 8 }, (_, i) => i * 45);
  return (
    <svg viewBox="0 0 64 48" aria-hidden="true" className={className}>
      {/* Envelope */}
      <rect x="3" y="5" width="58" height="38" rx="3" fill="#f4e7c5" stroke="#0038a8" strokeWidth="2.4" />
      <path d="M4.5 7 L32 27 L59.5 7" fill="none" stroke="#0038a8" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M4.5 41 L24 22 M59.5 41 L40 22" fill="none" stroke="#0038a8" strokeWidth="1.8" />
      {/* Wax seal: an uneven blob, a pressed rim, and the sun */}
      <path
        d="M36.5 14.5c3.2-.6 6.4 1.4 7.6 4.2 2.6.6 4 3.6 3 6.2 1.4 2.6.2 6-2.6 7-.9 3-4.3 4.6-7.2 3.5-2.4 1.9-6.1 1.2-7.6-1.4-3-.1-5.2-3-4.5-5.9-2-2.2-1.4-5.8 1.2-7.2.3-3.1 3.5-5.3 6.5-4.7 1.1-1.2 2.4-1.8 3.6-1.7z"
        fill="#ce1126"
      />
      <circle cx="36" cy="25" r="7.6" fill="none" stroke="#9e0b1c" strokeWidth="1.6" />
      <circle cx="36" cy="25" r="2.6" fill="#fcd116" />
      {rays.map((deg) => (
        <line
          key={deg}
          x1="36"
          y1="19.4"
          x2="36"
          y2="21"
          stroke="#fcd116"
          strokeWidth="1.4"
          strokeLinecap="round"
          transform={`rotate(${deg} 36 25)`}
        />
      ))}
    </svg>
  );
}

/** Logo lockup: the envelope beside the wordmark. Pass a light text class on blue. */
export function Logo({
  className,
  textClassName,
  markClassName,
}: {
  className?: string;
  textClassName?: string;
  markClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <SellyoMark className={cn("h-8 w-auto", markClassName)} />
      <span className={cn("font-display text-xl font-extrabold tracking-tight", textClassName)}>
        {PRODUCT_NAME}
      </span>
    </span>
  );
}

/** The square app icon: the envelope on a blue tile, for avatars and headers. */
export function SellyoIcon({ className }: { className?: string }) {
  return (
    <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl bg-primary", className)}>
      <SellyoMark className="h-[58%] w-auto" />
    </span>
  );
}

export function FlagStripe({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("flag-stripe w-full", className)} />;
}
