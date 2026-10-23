import { useRef, useState } from "react";
import { ArrowUpRight, Check, CheckCircle2, Loader2, Lock } from "lucide-react";
import { stageHeading, type Stage } from "@/lib/roadmap-data";
import { useCompliance } from "@/lib/compliance-store";
import { UPLOAD_ACCEPT, useDocumentUpload } from "@/lib/use-document-upload";
import { cn } from "@/lib/utils";
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
import { toast } from "sonner";

function UploadZone({ stage, isLast }: { stage: Stage; isLast: boolean }) {
  const [drag, setDrag] = useState(false);
  const { upload: handle, busy, fileName } = useDocumentUpload(stage);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        handle(e.dataTransfer.files?.[0]);
      }}
      className={cn(
        "rounded-2xl border-2 border-dashed border-input bg-surface px-6 py-6 transition-colors",
        drag && "border-primary bg-sage-soft",
      )}
    >
      <p className="font-semibold">
        {isLast ? "Upload your certificate to finish" : `Upload your certificate to unlock Stage ${stage.index + 1}`}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => handle(e.target.files?.[0])}
      />
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          className="rounded-lg border border-input bg-card px-3 py-1.5 font-medium hover:border-primary/50 disabled:opacity-60"
        >
          Choose file
        </button>
        {busy ? (
          <span className="flex items-center gap-2 font-medium text-primary">
            <Loader2 className="size-4 animate-spin" /> Checking {fileName ?? "your document"}…
          </span>
        ) : (
          <span className="text-muted-foreground">
            {fileName ?? "No file chosen"} · or drop it here
          </span>
        )}
      </div>
    </div>
  );
}

export function StageCard({ stage }: { stage: Stage }) {
  const {
    isStageComplete, isStageUnlocked, completeStage, toggleSubStep, isSubStepChecked, stages,
  } = useCompliance();
  const [confirming, setConfirming] = useState(false);

  const done = isStageComplete(stage.id);
  const unlocked = isStageUnlocked(stage.id);
  const isLast = stage.index === stages.length;
  const status = done ? "Done" : unlocked ? "Now" : "Locked";

  return (
    <div className="rounded-[2rem] bg-card p-6 shadow-soft sm:p-10">
      <p className={cn(
        "text-sm font-semibold uppercase tracking-[0.14em]",
        done ? "text-primary" : unlocked ? "text-flag-red" : "text-muted-foreground",
      )}>
        {status} · Stage {stage.index}
      </p>
      <h2 className="mt-2 text-3xl font-extrabold sm:text-4xl">{stageHeading(stage)}</h2>
      <p className="mt-3 text-lg text-muted-foreground">{stage.summary}</p>

      <ol className="mt-7 divide-y divide-border border-y border-border">
        {stage.subSteps.map((s, idx) => {
          const checked = done || isSubStepChecked(s.id);
          return (
            <li key={s.id}>
              <button
                type="button"
                disabled={done || !unlocked}
                onClick={() => toggleSubStep(s.id)}
                aria-pressed={checked}
                className="flex w-full items-start gap-5 py-5 text-left disabled:cursor-default"
              >
                <span className={cn(
                  "mt-0.5 grid size-9 shrink-0 place-items-center rounded-full text-sm font-semibold transition-colors",
                  checked ? "bg-primary text-primary-foreground" : "bg-sage-soft text-primary",
                )}>
                  {checked ? <Check className="size-4" strokeWidth={3} /> : idx + 1}
                </span>
                <span className="min-w-0">
                  <span className={cn("block text-lg font-semibold", checked && "text-muted-foreground line-through")}>
                    {s.label}
                  </span>
                  {s.detail && <span className="block text-muted-foreground">{s.detail}</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {stage.agencyUrl && (
        <a
          href={`https://${stage.agencyUrl}`}
          target="_blank"
          rel="noreferrer"
          className="mt-6 inline-flex items-center gap-1 font-semibold text-primary hover:underline"
        >
          Open {stage.agencyUrl} <ArrowUpRight className="size-4" />
        </a>
      )}

      <div className="mt-6">
        {done ? (
          <div className="flex items-center gap-2 rounded-2xl bg-sage-soft px-5 py-4 font-semibold text-primary">
            <CheckCircle2 className="size-5" /> Stage {stage.index} is complete
          </div>
        ) : unlocked ? (
          <>
            <UploadZone stage={stage} isLast={isLast} />
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="mt-3 text-sm font-medium text-muted-foreground hover:text-foreground hover:underline"
            >
              Already done? Mark this stage complete without uploading
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2 rounded-2xl border-2 border-dashed border-input px-5 py-4 text-muted-foreground">
            <Lock className="size-4" /> Finish Stage {stage.index - 1} first to unlock this one.
          </div>
        )}
      </div>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display text-2xl">
              Is Stage {stage.index} really complete?
            </AlertDialogTitle>
            <AlertDialogDescription>
              You haven&apos;t uploaded {stage.uploadLabel}. Make sure you already have every
              document for “{stage.title}” before moving on. Agencies may ask for them again later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full">Not yet</AlertDialogCancel>
            <AlertDialogAction
              className="rounded-full"
              onClick={() => {
                completeStage(stage.id);
                toast.success(`Stage ${stage.index} marked complete`, {
                  description: isLast ? "That was the last stage." : "Next stage unlocked.",
                });
              }}
            >
              Yes, mark complete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
