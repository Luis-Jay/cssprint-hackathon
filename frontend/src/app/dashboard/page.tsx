"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { LogOut, MapPin, PencilLine } from "lucide-react";
import { ASSISTANT_NAME, GabAIAvatar } from "@/components/gabai";
import { FlagStripe, SellyoIcon } from "@/components/brand";
import { StageCard } from "@/components/StageTimeline";
import { ChatPanel } from "@/components/ChatPanel";
import { PermitSummary } from "@/components/PermitSummary";
import {
  FEE_BASIS_CAPITAL,
  FEE_DISCLAIMER,
  ROADMAP_DISCLAIMER,
  stageShortLabel,
} from "@/lib/roadmap-data";
import { formatPeso, useCompliance } from "@/lib/compliance-store";
import { feeEstimate } from "@/lib/fees";
import { cn } from "@/lib/utils";

/** BMBE (RA 9178) covers businesses with assets under ₱3M. */
const BMBE_LIMIT = 3_000_000;

export default function Page() {
  const router = useRouter();
  const {
    profile, stages, isStageComplete, isStageUnlocked, currentStageIndex, roadmapSource,
    signedIn, name, signOut, authLoading, sessionId, restartOnboarding, inbox, roadmap,
  } = useCompliance();

  // A rejected token wipes the workspace; send them back to sign in rather
  // than leaving them on an empty dashboard.
  useEffect(() => {
    if (!authLoading && !signedIn && !sessionId) router.replace("/");
  }, [authLoading, signedIn, sessionId, router]);

  const current = stages.find((s) => !isStageComplete(s.id)) ?? stages[stages.length - 1];
  const [viewing, setViewing] = useState<string | null>(null);
  const stage = stages.find((s) => s.id === viewing) ?? current;

  const [chatOpen, setChatOpen] = useState(false);
  // Replies (e.g. upload checks) that arrived since GabAI was last closed.
  const [lastSeen, setLastSeen] = useState(() => Date.now());
  const unread = inbox.filter((m) => (m.at ?? 0) > lastSeen).length;
  const closeChat = () => {
    setChatOpen(false);
    setLastSeen(Date.now());
  };

  const capital = Number(String(profile.capital).replace(/[^\d.]/g, ""));
  const fees = feeEstimate(roadmap, stages);
  const bmbe = capital > 0 && capital < BMBE_LIMIT;
  const allDone = stages.every((s) => isStageComplete(s.id));
  // Once everything is done the summary is the home view; the stages stay one click away.
  const [showRoadmap, setShowRoadmap] = useState(false);


  if (!stage) return null;

  return (
    <div className="min-h-screen bg-surface print:bg-white">
      <FlagStripe className="print:hidden" />
      <header className="border-b border-border bg-card print:hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <SellyoIcon />
            <div className="min-w-0">
              <p className="truncate font-display text-lg font-bold leading-tight">
                {profile.businessName || "Your business"}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                {profile.district} · {profile.entity}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-4">
            {bmbe && (
              <span className="hidden rounded-full bg-gold-soft px-4 py-1.5 text-sm font-semibold text-gold-foreground sm:inline">
                BMBE eligible
              </span>
            )}
            <Link
              href="/where-to-go"
              className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground print:hidden"
            >
              <MapPin className="size-4" /> <span className="hidden md:inline">Where to go</span>
            </Link>
            <button
              type="button"
              onClick={() => {
                restartOnboarding();
                router.push("/onboarding");
              }}
              className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
              title="Change your answers and rebuild the roadmap"
            >
              <PencilLine className="size-4" /> <span className="hidden md:inline">Edit answers</span>
            </button>
            {signedIn && (
              <button
                type="button"
                title={`Signed in as ${name}`}
                onClick={async () => {
                  await signOut();
                  router.push("/");
                }}
                className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
              >
                <LogOut className="size-4" /> <span className="hidden md:inline">Sign out</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {allDone && !showRoadmap ? (
      <main className="mx-auto max-w-4xl px-5 pb-16 pt-10 sm:px-8 print:max-w-none print:p-0">
        <PermitSummary onViewRoadmap={() => setShowRoadmap(true)} />
      </main>
      ) : (
      <main className="mx-auto max-w-6xl px-5 pb-16 pt-10 sm:px-8">
        <div className="flex items-end justify-between gap-4">
          <h1 className="text-4xl font-extrabold sm:text-5xl">Your roadmap</h1>
          {allDone ? (
            <button
              type="button"
              onClick={() => setShowRoadmap(false)}
              className="pb-1 font-semibold text-primary hover:underline"
            >
              View your permit summary
            </button>
          ) : (
            <p className="pb-1 text-muted-foreground">
              Stage {currentStageIndex} of {stages.length}
            </p>
          )}
        </div>

        {/* Stage tabs */}
        <nav className="mt-6 grid gap-3" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
          {stages.map((s) => {
            const reached = isStageComplete(s.id) || s.id === current?.id;
            const selected = s.id === stage.id;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setViewing(s.id)}
                aria-current={selected ? "step" : undefined}
                className="group min-w-0 text-left"
              >
                <span className={cn(
                  "block h-1.5 rounded-full transition-colors",
                  reached ? "bg-primary" : "bg-input group-hover:bg-primary/40",
                )} />
                <span className={cn(
                  "mt-2 block truncate text-xs sm:text-sm",
                  selected ? "font-semibold text-primary" : "text-muted-foreground",
                  !isStageUnlocked(s.id) && !selected && "opacity-70",
                )}>
                  <span className="sm:hidden">{s.index}</span>
                  <span className="hidden sm:inline">{s.index} · {stageShortLabel(s)}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            <StageCard stage={stage} />
            <p className="mt-4 px-2 text-xs leading-relaxed text-muted-foreground">
              {roadmapSource === "rag" || roadmapSource === "cache"
                ? "Tailored to your answers from Manila ordinances. "
                : roadmapSource === "template"
                  ? "Standard Manila roadmap. "
                  : "Offline roadmap: the compliance service could not be reached. "}
              {ROADMAP_DISCLAIMER}
            </p>
          </div>

          <aside className="space-y-6">
            <section className="rounded-[2rem] bg-card p-7 shadow-soft">
              <p className="text-sm text-muted-foreground">Estimated total fees</p>
              <p className="mt-1 font-display text-3xl font-extrabold text-primary">{fees.total}</p>
              <dl className="mt-5 divide-y divide-border border-t border-border">
                {fees.items.map((f, i) => (
                  <div key={`${f.label}-${i}`} className="flex items-baseline justify-between gap-3 py-3.5">
                    <dt className="text-sm">{f.label}</dt>
                    <dd className="shrink-0 text-sm font-bold">{f.amount}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {fees.basis}
                {!roadmap?.length && capital > 0 && capital !== FEE_BASIS_CAPITAL &&
                  ` Yours is ${formatPeso(profile.capital)}, so the mayor's permit fee will differ.`}
              </p>
              <details className="mt-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium hover:text-foreground">About these numbers</summary>
                <p className="mt-2 leading-relaxed">{FEE_DISCLAIMER}</p>
              </details>
            </section>

          </aside>
        </div>
      </main>
      )}

      {/* GabAI drawer. Stays mounted so the conversation survives closing it. */}
      <div
        className={cn("fixed inset-0 z-40 bg-foreground/30 transition-opacity print:hidden", chatOpen ? "opacity-100" : "pointer-events-none opacity-0")}
        onClick={closeChat}
        aria-hidden="true"
      />
      <aside
        aria-label={ASSISTANT_NAME}
        aria-hidden={!chatOpen}
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-full max-w-md shadow-lift transition-transform duration-300 print:hidden",
          chatOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <ChatPanel stageId={stage.id} onHide={closeChat} />
      </aside>

      {!chatOpen && (
        <div className="fixed bottom-6 right-6 z-30 flex items-center gap-3 print:hidden">
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="hidden rounded-full bg-card px-5 py-3 text-sm font-semibold shadow-lift transition-transform hover:-translate-y-0.5 sm:block"
          >
            Need help with permits? Ask Gab.
          </button>
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            aria-label={unread ? `Open ${ASSISTANT_NAME}, ${unread} new` : `Open ${ASSISTANT_NAME}`}
            className="relative rounded-full shadow-[0_8px_28px_rgb(0_56_168/0.35)] transition-transform hover:scale-105"
          >
            <GabAIAvatar className="size-16" />
            {unread > 0 && (
              <span className="absolute -right-1 -top-1 grid min-w-7 place-items-center rounded-full border-[3px] border-card bg-flag-red px-1.5 py-0.5 text-sm font-bold leading-none text-white">
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
