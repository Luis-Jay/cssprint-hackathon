import { useId } from "react";
import { cn } from "@/lib/utils";

/** The name of Sellyo's assistant. */
export const ASSISTANT_NAME = "GabAI";

/**
 * The designed avatar artwork, if you have it. Put a square PNG of the avatar
 * (without the notification badge) in frontend/public/brand/ and set the path
 * here, e.g. "/brand/gabai.png". While it is null the drawn avatar is used.
 */
const AVATAR_IMAGE: string | null = null;

/**
 * GabAI: a smiling guide in a salakot and barong, on a flag-blue disc.
 */
export function GabAIAvatar({ className }: { className?: string }) {
  const clip = useId();

  if (AVATAR_IMAGE) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- tiny static brand asset
      <img src={AVATAR_IMAGE} alt="" aria-hidden="true" className={cn("shrink-0 rounded-full object-cover", className)} />
    );
  }

  return (
    <svg viewBox="0 0 100 100" aria-hidden="true" className={cn("shrink-0 rounded-full", className)}>
      <defs>
        <clipPath id={clip}>
          <circle cx="50" cy="50" r="50" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clip})`}>
        <rect width="100" height="100" fill="#0038a8" />

        {/* Barong */}
        <path d="M12 104 C14 80 32 71 50 71 C68 71 86 80 88 104 Z" fill="#f3e9d6" />
        <path d="M40 70 L50 84 L60 70 L56 69 L50 78 L44 69 Z" fill="#ffffff" stroke="#d8c48f" strokeWidth="1.2" strokeLinejoin="round" />
        <path d="M50 84 V104 M43 86 V104 M57 86 V104" stroke="#d8c48f" strokeWidth="1.3" />
        <circle cx="33" cy="88" r="3" fill="#fcd116" />

        {/* Neck and head */}
        <rect x="44" y="58" width="12" height="15" rx="3" fill="#c48459" />
        <circle cx="34.5" cy="47" r="4" fill="#d6996a" />
        <circle cx="65.5" cy="47" r="4" fill="#d6996a" />
        <ellipse cx="50" cy="46" rx="15.5" ry="16.5" fill="#d6996a" />
        <path d="M35 40 C36 32 64 32 65 40 L65 36 C62 29 38 29 35 36 Z" fill="#1f2340" />

        {/* Face */}
        <circle cx="44" cy="45.5" r="2.2" fill="#1b1d33" />
        <circle cx="56" cy="45.5" r="2.2" fill="#1b1d33" />
        <circle cx="40.5" cy="51.5" r="3.2" fill="#e08a74" opacity="0.65" />
        <circle cx="59.5" cy="51.5" r="3.2" fill="#e08a74" opacity="0.65" />
        <path d="M45 54 Q50 58.5 55 54" fill="none" stroke="#7a3e22" strokeWidth="2" strokeLinecap="round" />

        {/* Salakot: brim first, so the crown sits on top of it */}
        <ellipse cx="50" cy="34" rx="27" ry="6" fill="#e9c26a" stroke="#b8862d" strokeWidth="1.2" />
        <path d="M48.4 18 L50 7 L51.6 18 Z" fill="#fcd116" />
        <path d="M33.5 34 C33 15 67 15 66.5 34 Z" fill="#e9c26a" stroke="#b8862d" strokeWidth="1.2" />
        <path d="M37.5 21.5 Q50 18 62.5 21.5 M35 25.5 Q50 22.5 65 25.5" fill="none" stroke="#b8862d" strokeWidth="1" />
        <path d="M34 28 Q50 26 66 28 L66.4 33.6 Q50 31.6 33.6 33.6 Z" fill="#ce1126" />
      </g>
    </svg>
  );
}
