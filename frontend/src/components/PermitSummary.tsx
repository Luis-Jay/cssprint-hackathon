"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, Download, FileText, PencilLine, RotateCcw, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Logo } from "@/components/brand";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DEFAULT_PROFILE,
  LGU,
  formatPeso,
  useCompliance,
  type BusinessProfile,
} from "@/lib/compliance-store";
import { stageKind, stageRecordTitle, type Stage } from "@/lib/roadmap-data";
import { feeEstimate } from "@/lib/fees";
import { uploadedFileUrl } from "@/lib/use-document-upload";

/** BMBE (RA 9178) covers businesses with assets under ₱3M. */
const BMBE_LIMIT = 3_000_000;

/** How long a DTI business name registration stays valid. */
const DTI_VALID_YEARS = 5;

function formatDate(iso: string | undefined, opts: Intl.DateTimeFormatOptions) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString("en-US", opts);
}

const DAY = { month: "short", day: "numeric", year: "numeric" } as const;

/** "Sole Proprietorship" -> "Sole proprietorship" */
function sentenceCase(text: string) {
  return text ? text[0]!.toUpperCase() + text.slice(1).toLowerCase() : text;
}

/** The line under each permit: what the owner now holds for that stage. */
function permitDetail(stage: Stage, profile: BusinessProfile): string {
  switch (stageKind(stage)) {
    case "dti":
      return `Valid ${DTI_VALID_YEARS} years, renewable`;
    case "barangay":
      return profile.district;
    case "bureaus": {
      const held = [
        profile.servesFood && "Sanitary permit and health cards",
        profile.signage && "Signage permit",
        profile.renovating && "Building and occupancy review",
      ].filter(Boolean);
      return held.length ? held.join(" · ") : "Zoning and fire safety clearances";
    }
    case "mayor":
      return LGU;
    case "bir":
      return "No annual registration fee (EOPT Act)";
    default:
      return stage.agency;
  }
}

/** When the permit needs renewing. Confirm exact dates with each office. */
function renewal(stage: Stage, completedAt: string | undefined): string {
  switch (stageKind(stage)) {
    case "dti": {
      if (!completedAt) return `Valid ${DTI_VALID_YEARS} years`;
      const until = new Date(completedAt);
      until.setFullYear(until.getFullYear() + DTI_VALID_YEARS);
      return `Valid until ${until.toLocaleDateString("en-US", { month: "short", year: "numeric" })}`;
    }
    case "barangay":
    case "bureaus":
    case "mayor":
      return "Every January";
    case "bir":
      return "File returns on schedule";
    default:
      return "Check with the office";
  }
}

const NEXT_STEPS = [
  "Renew the barangay clearance, mayor's permit and local clearances each January.",
  "Keep filing BIR returns on time. Your Certificate of Registration lists which forms and when.",
  "Keep your original certificates together with this page.",
  "Confirm exact renewal dates with each office.",
];

function FeesPaid() {
  const { feesPaid, setFeesPaid } = useCompliance();
  const [editing, setEditing] = useState(!feesPaid);
  const [draft, setDraft] = useState(feesPaid);

  if (editing) {
    return (
      <form
        className="mt-2 flex gap-2 print:hidden"
        onSubmit={(e) => {
          e.preventDefault();
          setFeesPaid(draft.replace(/[^\d.]/g, ""));
          setEditing(false);
        }}
      >
        <input
          inputMode="decimal"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="What did you pay in total?"
          aria-label="Total fees paid in pesos"
          className="h-11 min-w-0 flex-1 rounded-xl border border-input bg-card px-3 text-base focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button type="submit" className="rounded-xl bg-primary px-4 font-semibold text-primary-foreground">
          Save
        </button>
      </form>
    );
  }

  return (
    <p className="mt-1 flex items-baseline gap-3">
      <span className="font-display text-4xl font-extrabold text-primary">
        {feesPaid ? formatPeso(feesPaid) : "Not recorded"}
      </span>
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground print:hidden"
      >
        <PencilLine className="size-3.5" /> Edit
      </button>
    </p>
  );
}

export function PermitSummary({ onViewRoadmap }: { onViewRoadmap: () => void }) {
  const router = useRouter();
  const { profile, stages, completedAt, uploads, feesPaid, restartOnboarding, setProfile, roadmap } =
    useCompliance();
  const estimate = feeEstimate(roadmap, stages).total;
  const [confirmRestart, setConfirmRestart] = useState(false);

  const capital = Number(String(profile.capital).replace(/[^\d.]/g, ""));
  const bmbe = capital > 0 && capital < BMBE_LIMIT;
  const name = profile.businessName || "Your business";
  const subtitle = [sentenceCase(profile.entity), profile.district, LGU].filter(Boolean).join(" · ");

  const share = async () => {
    const text = [
      `${name}: all ${stages.length} permit stages complete.`,
      ...stages.map((s) => `✓ ${stageRecordTitle(s)}`),
      feesPaid ? `Total fees paid: ${formatPeso(feesPaid)}` : `Estimated fees: ${estimate}`,
      "Made with Sellyo. Not an official government document.",
    ].join("\n");
    try {
      if (navigator.share) {
        await navigator.share({ title: `${name}: permit summary`, text });
      } else {
        await navigator.clipboard.writeText(text);
        toast.success("Summary copied", { description: "Paste it into a message or email." });
      }
    } catch {
      /* the share sheet was closed */
    }
  };

  return (
    <>
      <article
        id="permit-summary"
        className="rounded-[2rem] bg-card p-6 shadow-soft sm:p-10 print:rounded-none print:p-0 print:shadow-none"
      >
        <header className="flex items-center justify-between gap-4">
          <Logo className="text-sm" />
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Permit summary
          </p>
        </header>

        <div className="mt-10 flex items-center gap-5 print:mt-6">
          <span className="grid size-20 shrink-0 place-items-center rounded-full border-[3px] border-dashed border-primary p-1.5">
            <span className="grid size-full place-items-center rounded-full bg-primary">
              <Check className="size-8 text-gold" strokeWidth={3.5} />
            </span>
          </span>
          <div>
            <h2 className="text-4xl font-extrabold sm:text-5xl">You&apos;re all set.</h2>
            <p className="mt-1 font-semibold text-flag-red">All {stages.length} stages complete</p>
          </div>
        </div>

        <div className="mt-8 rounded-2xl bg-panel px-6 py-5 print:mt-5">
          <p className="font-display text-2xl font-bold">{name}</p>
          <p className="mt-1 text-muted-foreground">{subtitle}</p>
        </div>

        <table className="mt-8 w-full text-left print:mt-4">
          <thead>
            <tr className="border-b-2 border-foreground/70 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              <th className="py-3 pl-12 font-semibold">Your permits</th>
              <th className="hidden py-3 pr-4 font-semibold sm:table-cell">Completed</th>
              <th className="hidden py-3 font-semibold sm:table-cell">Renewal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {stages.map((s) => {
              const done = formatDate(completedAt[s.id], DAY);
              const file = uploads[s.id];
              const url = uploadedFileUrl(s.id);
              return (
                <tr key={s.id} className="align-top print:break-inside-avoid">
                  <td className="py-4 pr-4 print:py-2.5">
                    <div className="flex gap-4">
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary">
                        <Check className="size-4 text-primary-foreground" strokeWidth={3} />
                      </span>
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-semibold">
                          {stageRecordTitle(s)}
                          <span className={
                            file
                              ? "rounded-full bg-sage-soft px-2 py-0.5 text-[11px] font-semibold text-primary"
                              : "rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold text-muted-foreground"
                          }>
                            {file ? "Document checked" : "Marked done by you"}
                          </span>
                        </p>
                        <p className="text-sm text-muted-foreground">{permitDetail(s, profile)}</p>
                        {file && (
                          url ? (
                            <a href={url} target="_blank" rel="noreferrer"
                              className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                              <FileText className="size-3.5" /> {file}
                            </a>
                          ) : (
                            <p className="mt-1 inline-flex items-center gap-1 text-sm text-muted-foreground">
                              <FileText className="size-3.5" /> {file} on file
                            </p>
                          )
                        )}
                        {/* Phone layout: the date and renewal columns fold in here */}
                        <p className="mt-1 text-sm text-muted-foreground sm:hidden">
                          {done ? `Done ${done} · ` : ""}{renewal(s, completedAt[s.id])}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="hidden whitespace-nowrap py-4 pr-4 sm:table-cell">{done ?? "—"}</td>
                  <td className="hidden py-4 sm:table-cell">{renewal(s, completedAt[s.id])}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          <span className="font-semibold">Document checked</span>: you uploaded the issued document
          and it looked right to Sellyo&apos;s check, which can&apos;t confirm a document is genuine.{" "}
          <span className="font-semibold">Marked done by you</span>: no document was uploaded.
        </p>

        <div className="mt-8 grid items-start gap-8 border-t border-border pt-8 md:grid-cols-2 print:mt-4 print:grid-cols-2 print:break-inside-avoid print:pt-5">
          <section className="rounded-2xl border-2 border-foreground/70 p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Total fees paid
            </p>
            <FeesPaid />
            <p className="mt-2 text-sm text-muted-foreground">Original estimate {estimate}</p>
            {bmbe && (
              <p className="mt-4 inline-block rounded-full bg-gold-soft px-4 py-1.5 text-sm font-semibold text-gold-foreground">
                BMBE eligible · capital under ₱3M
              </p>
            )}
          </section>

          <section>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              What&apos;s next
            </p>
            <ol className="mt-3 space-y-3">
              {NEXT_STEPS.map((step, i) => (
                <li key={step} className="flex gap-3">
                  <span className="font-semibold text-flag-red">{i + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <footer className="mt-10 border-t border-border pt-4 text-sm text-muted-foreground print:mt-6">
          Printed from Sellyo · Not an official government document
        </footer>
      </article>

      <div className="mt-6 flex flex-wrap items-center gap-3 print:hidden">
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex h-12 items-center gap-2 rounded-full bg-primary px-6 font-semibold text-primary-foreground hover:bg-primary/90"
        >
          <Download className="size-4" /> Download PDF
        </button>
        <button
          type="button"
          onClick={share}
          className="inline-flex h-12 items-center gap-2 rounded-full border border-input bg-card px-6 font-semibold hover:border-primary/40"
        >
          <Share2 className="size-4" /> Share
        </button>
        <button
          type="button"
          onClick={() => setConfirmRestart(true)}
          className="inline-flex h-12 items-center gap-2 rounded-full border border-input bg-card px-6 font-semibold hover:border-primary/40"
        >
          <RotateCcw className="size-4" /> Start a new business
        </button>
        <button
          type="button"
          onClick={onViewRoadmap}
          className="ml-auto text-sm font-medium text-muted-foreground hover:text-foreground hover:underline"
        >
          View the roadmap stages
        </button>
      </div>

      <AlertDialog open={confirmRestart} onOpenChange={setConfirmRestart}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display text-2xl">Start a new business?</AlertDialogTitle>
            <AlertDialogDescription>
              This clears {name}&apos;s progress and summary from this app. Download the PDF
              first if you want to keep it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="rounded-full"
              onClick={() => {
                restartOnboarding();
                setProfile({ ...DEFAULT_PROFILE, businessName: "" });
                router.push("/onboarding");
              }}
            >
              Start over
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
