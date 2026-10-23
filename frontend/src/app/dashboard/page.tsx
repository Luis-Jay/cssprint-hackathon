"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, LogOut, MapPin, MessageCircle, PencilLine } from "lucide-react";
import { FlagStripe, SunMark } from "@/components/brand";
import { StageCard } from "@/components/StageTimeline";
import { ChatPanel } from "@/components/ChatPanel";
import { PermitSummary } from "@/components/PermitSummary";
import {
  FEE_BASIS_CAPITAL,
  FEE_BREAKDOWN,
  FEE_DISCLAIMER,
  FEE_TOTAL,
  ROADMAP_DISCLAIMER,
  stageShortLabel,
} from "@/lib/roadmap-data";
import { formatPeso, useCompliance } from "@/lib/compliance-store";
import { cn } from "@/lib/utils";

/** BMBE (RA 9178) covers businesses with assets under ₱3M. */
const BMBE_LIMIT = 3_000_000;

export default function Page() {
  const router = useRouter();
  const {
    profile, stages, isStageComplete, isStageUnlocked, currentStageIndex, roadmapSource,
    signedIn, name, signOut, authLoading, sessionId, restartOnboarding,
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
  const [question, setQuestion] = useState("");
  const [ask, setAsk] = useState<{ id: string; text: string } | null>(null);

  const capital = Number(String(profile.capital).replace(/[^\d.]/g, ""));
  const bmbe = capital > 0 && capital < BMBE_LIMIT;
  const allDone = stages.every((s) => isStageComplete(s.id));
  // Once everything is done the summary is the home view; the stages stay one click away.
  const [showRoadmap, setShowRoadmap] = useState(false);

  const submitQuestion = (e: React.FormEvent) => {
    e.preventDefault();
    const text = question.trim();
    if (text) setAsk({ id: crypto.randomUUID(), text });
    setQuestion("");
    setChatOpen(true);
  };

  if (!stage) return null;

  return (
    <div className="min-h-screen bg-surface print:bg-white">
      <FlagStripe className="print:hidden" />
      <header className="border-b border-border bg-card print:hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary">
              <SunMark className="size-7" />
            </span>
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
              <p className="mt-1 font-display text-3xl font-extrabold text-primary">{FEE_TOTAL}</p>
              <dl className="mt-5 divide-y divide-border border-t border-border">
                {FEE_BREAKDOWN.map((f) => (
                  <div key={f.short} className="flex items-baseline justify-between gap-3 py-3.5">
                    <dt className="text-sm">{f.short}</dt>
                    <dd className="shrink-0 text-sm font-bold">{f.amount}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                Estimates based on {formatPeso(String(FEE_BASIS_CAPITAL))} capital.
                {capital > 0 && capital !== FEE_BASIS_CAPITAL &&
                  ` Yours is ${formatPeso(profile.capital)}, so the mayor's permit fee will differ.`}
              </p>
              <details className="mt-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium hover:text-foreground">About these numbers</summary>
                <p className="mt-2 leading-relaxed">{FEE_DISCLAIMER}</p>
              </details>
            </section>

            <section className="rounded-[2rem] bg-primary p-7 text-primary-foreground">
              <h2 className="text-2xl font-extrabold">Ask the copilot</h2>
              <p className="mt-2 text-primary-foreground/80">
                Questions about a permit, fee or form? Ask in plain words.
              </p>
              <form onSubmit={submitQuestion} className="mt-5 flex gap-2">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="How long does DTI take?"
                  aria-label="Ask the copilot"
                  className="h-12 min-w-0 flex-1 rounded-full bg-card px-5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-gold"
                />
                <button
                  type="submit"
                  aria-label="Ask"
                  className="grid size-12 shrink-0 place-items-center rounded-full bg-gold text-gold-foreground transition-transform hover:scale-105"
                >
                  <ArrowRight className="size-5" />
                </button>
              </form>
            </section>
          </aside>
        </div>
      </main>
      )}

      {/* Copilot drawer. Stays mounted so the conversation survives closing it. */}
      <div
        className={cn("fixed inset-0 z-40 bg-foreground/30 transition-opacity print:hidden", chatOpen ? "opacity-100" : "pointer-events-none opacity-0")}
        onClick={() => setChatOpen(false)}
        aria-hidden="true"
      />
      <aside
        aria-label="Copilot"
        aria-hidden={!chatOpen}
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-full max-w-md shadow-lift transition-transform duration-300 print:hidden",
          chatOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <ChatPanel stageId={stage.id} ask={ask} onHide={() => setChatOpen(false)} />
      </aside>

      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-primary px-5 py-3 font-semibold text-primary-foreground shadow-lift lg:hidden print:hidden"
        >
          <MessageCircle className="size-5" /> Copilot
        </button>
      )}
    </div>
  );
}
