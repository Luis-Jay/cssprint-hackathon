import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Loader2, Send, X } from "lucide-react";
import { AGENT_PERSONAS, FEE_BREAKDOWN, FEE_DISCLAIMER, FEE_TOTAL } from "@/lib/roadmap-data";
import type { Stage } from "@/lib/roadmap-data";
import { useCompliance } from "@/lib/compliance-store";
import { sendChat, subscribeTrace, type TraceEvent, type VerificationResult } from "@/lib/api";
import { UPLOAD_ACCEPT, useDocumentUpload } from "@/lib/use-document-upload";
import { AgentTrace } from "@/components/AgentTrace";
import { MarkdownMessage } from "@/components/MarkdownMessage";
import { ASSISTANT_NAME, GabAIAvatar } from "@/components/gabai";
import { cn } from "@/lib/utils";

type Msg = {
  id: string;
  role: "user" | "agent";
  agent?: string;
  text: string;
  fees?: boolean;
  checklist?: string[];
  /** Result of a document upload, drawn as an upload check card. */
  upload?: { stageId?: string; results: VerificationResult[] };
  /** Low-level record of what the agents did to produce this reply. */
  trace?: TraceEvent[];
  traceMs?: number;
};

const AGENTS = AGENT_PERSONAS.map((a) => a.name);

/** Two upload results are the same when every requirement got the same verdict. */
function uploadKey(m: Msg): string | null {
  if (!m.upload) return null;
  return JSON.stringify([m.upload.stageId, m.upload.results.map((r) => [r.document_name, r.status, r.notes])]);
}

/** Collapse back-to-back identical upload results into one card with a count. */
function groupRepeats(messages: Msg[]): { msg: Msg; count: number }[] {
  const out: { msg: Msg; count: number }[] = [];
  for (const m of messages) {
    const prev = out[out.length - 1];
    const key = uploadKey(m);
    if (prev && key && uploadKey(prev.msg) === key) {
      // Keep the latest one, so its trace is the one shown.
      prev.msg = m;
      prev.count += 1;
    } else {
      out.push({ msg: m, count: 1 });
    }
  }
  return out;
}

const STATUS_ICON: Record<VerificationResult["status"], { icon: typeof Check; tint: string }> = {
  complete: { icon: Check, tint: "bg-emerald-100 text-emerald-700" },
  incomplete: { icon: AlertTriangle, tint: "bg-gold-soft text-amber-700" },
  unreadable: { icon: AlertTriangle, tint: "bg-gold-soft text-amber-700" },
  missing: { icon: AlertTriangle, tint: "bg-red-100 text-flag-red" },
  unverified: { icon: AlertTriangle, tint: "bg-gold-soft text-amber-700" },
};

function UploadCheck({ title, results, onReupload, busy }: {
  title: string;
  results: VerificationResult[];
  onReupload?: () => void;
  busy: boolean;
}) {
  const done = results.filter((r) => r.status === "complete").length;
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="px-5 pb-4 pt-5">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Upload check</p>
        <p className="mt-1 font-display text-lg font-bold leading-snug">{title}</p>
        <div className="mt-3 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${results.length ? (done / results.length) * 100 : 0}%` }}
            />
          </div>
          <span className="shrink-0 text-sm font-medium text-muted-foreground">
            {done}/{results.length} done
          </span>
        </div>
      </div>
      <ul className="divide-y divide-border border-t border-border">
        {[...results].sort((a, b) => Number(b.kind === "output") - Number(a.kind === "output")).map((r) => {
          const { icon: Icon, tint } = STATUS_ICON[r.status] ?? STATUS_ICON.missing;
          return (
            <li key={r.document_name} className="flex items-start gap-3 px-5 py-4">
              <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full", tint)}>
                {r.status === "missing"
                  ? <span className="text-sm font-bold leading-none">!</span>
                  : <Icon className="size-3.5" strokeWidth={3} />}
              </span>
              <div className="min-w-0 flex-1">
                {r.kind === "output" && (
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">
                    Stage document
                  </p>
                )}
                <p className="font-semibold leading-snug">{r.document_name}</p>
                {r.notes && <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{r.notes}</p>}
                {r.checks && r.checks.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {r.checks.map((c) => (
                      <li key={c.label} className="flex items-start gap-1.5 text-xs">
                        <span className={cn(
                          "font-bold",
                          c.ok === true ? "text-emerald-700" : c.ok === false ? "text-flag-red" : "text-muted-foreground",
                        )}>
                          {c.ok === true ? "✓" : c.ok === false ? "✗" : "?"}
                        </span>
                        <span><span className="font-semibold">{c.label}:</span> {c.detail}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {r.status !== "complete" && r.kind !== "requirement" && onReupload && (
                <button
                  type="button"
                  onClick={onReupload}
                  disabled={busy}
                  className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-sm font-semibold text-primary hover:border-primary/40 disabled:opacity-60"
                >
                  Re-upload
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const WELCOME: Msg = {
  id: "welcome",
  role: "agent",
  agent: "GabAI",
  text: "Hi, I'm GabAI. I answer from Manila's ordinances, the DTI, BPLS and BIR rules, and your roadmap. Ask me anything in English or Filipino, or tap a suggestion below. I'm a guide: I don't file anything for you, and the issuing office has the final say.",
};


function respond(q: string, stageId: string, stages: Stage[]): Msg {
  const t = q.toLowerCase();
  const id = crypto.randomUUID();
  if (t.includes("fee") || t.includes("cost") || t.includes("calculate") || t.includes("lbt")) {
    return {
      id,
      role: "agent",
      agent: "BIR Tax Advisor",
      text: "Here is the indicative government fee estimate. It assumes ₱150,000 capital, so yours may differ, and it excludes notarial and health-exam costs.",
      fees: true,
    };
  }
  if (t.includes("yellow") || t.includes("health card")) {
    return {
      id,
      role: "agent",
      agent: "Manila Zoning Agent",
      text: "Each food handler needs a Manila Health Department Yellow Card before the Sanitary Permit is released. Each food handler goes through this sequence:",
      checklist: [
        "Barangay-issued medical referral or company letter",
        "Chest X-Ray at Manila Health Department (Sta. Cruz)",
        "Stool and urine laboratory exams",
        "Food handler's seminar attendance",
        "Yellow Card issuance — renew annually",
      ],
    };
  }
  if (t.includes("lease")) {
    return {
      id,
      role: "agent",
      agent: "Manila Zoning Agent",
      text: "Your notarized Lease Contract bundle for the Barangay and BPLS filing should contain:",
      checklist: [
        "Notarized Contract of Lease naming the business",
        "Lessor's latest Real Property Tax (RPT) receipt",
        "Lessor's valid government ID + Tax Declaration copy",
        "Sketch / vicinity map of the leased unit",
        "Photo of the storefront and signage placement",
      ],
    };
  }
  if (t.includes("name rule") || t.includes("dti name") || t.includes("business name")) {
    return {
      id,
      role: "agent",
      agent: "DTI Compliance Bot",
      text: "BNRS will reject a business name that is generic, deceptive, or confusingly similar to a registered mark. Keep it to: [Root Word] + [Descriptor].",
      checklist: [
        'Avoid protected words: "Philippines", "National", "Bureau"',
        "Root word must not be a mere generic term (e.g. only 'Cafe')",
        "No confusing similarity to an existing registered name",
        "City Scope covers all of Manila — ₱500 + ₱30 DST",
        "Validity: 5 years from date of registration",
      ],
    };
  }
  if (t.includes("bmbe")) {
    return {
      id,
      role: "agent",
      agent: "BIR Tax Advisor",
      text: "Businesses with total assets under ₱3,000,000 can register as a Barangay Micro Business Enterprise (BMBE) under RA 9178, at a Negosyo Center. Registered BMBEs are exempt from income tax on their business income. Confirm eligibility with the Negosyo Center.",
    };
  }
  const stage = stages.find((s) => s.id === stageId) ?? stages[0];
  if (!stage) {
    return { id, role: "agent", agent: "DTI Compliance Bot", text: "Your roadmap is still loading — give me a moment." };
  }
  return {
    id,
    role: "agent",
    agent: "Manila Zoning Agent",
    text: `Focusing on Stage ${stage.index} — ${stage.title} (${stage.agency}). ${stage.summary} Work through these in order:`,
    checklist: stage.subSteps.map((s) => (s.detail ? `${s.label} — ${s.detail}` : s.label)),
  };
}

export function ChatPanel({
  stageId,
  onHide,
  ask,
}: {
  stageId: string;
  onHide?: () => void;
  /** A question typed outside the panel; sent once per new id. */
  ask?: { id: string; text: string } | null;
}) {
  const { stages, sessionId, transcript, inbox } = useCompliance();
  const stage = stages.find((s) => s.id === stageId) ?? stages[0]!;

  const [messages, setMessages] = useState<Msg[]>([WELCOME]);
  const hydratedFrom = useRef<string | null>(null);
  const consumed = useRef<Set<string>>(new Set());

  // Redraw the saved conversation when a restored session arrives
  useEffect(() => {
    if (!sessionId || hydratedFrom.current === sessionId) return;
    if (!transcript.length) return;
    hydratedFrom.current = sessionId;
    setMessages([
      WELCOME,
      ...transcript.map((m, i) => ({
        id: `history-${i}`,
        role: (m.role === "user" ? "user" : "agent") as Msg["role"],
        agent: m.role === "user" ? undefined : ASSISTANT_NAME,
        text: m.content,
      })),
    ]);
  }, [sessionId, transcript]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  // Render anything pushed in from elsewhere (document uploads) as a normal
  // agent message, complete with its findings and agent activity.
  useEffect(() => {
    const fresh = inbox.filter((m) => !consumed.current.has(m.id));
    if (!fresh.length) return;
    fresh.forEach((m) => consumed.current.add(m.id));
    setMessages((prev) => [
      ...prev,
      ...fresh.map((m) => ({
        id: m.id,
        role: "agent" as const,
        agent: m.agent,
        text: m.text,
        upload: m.verification?.length
          ? { stageId: m.stageId, results: m.verification }
          : undefined,
        trace: m.trace,
        traceMs: m.traceMs,
      })),
    ]);
  }, [inbox]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || thinking) return;
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", text: question }]);
    setInput("");
    setThinking(true);

    // No session means onboarding never reached the backend; fall back to the
    // local keyword responder rather than showing an error.
    if (!sessionId) {
      setTimeout(() => {
        setMessages((m) => [...m, respond(question, stageId, stages)]);
        setThinking(false);
        inputRef.current?.focus();
      }, 700);
      return;
    }

    // Watch the agents work while the request is in flight.
    setLiveTrace([]);
    const unsubscribe = subscribeTrace(sessionId, (event) =>
      setLiveTrace((t) => [...t, event]),
    );

    try {
      const res = await sendChat(sessionId, question);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "agent",
          agent: res.agent ?? ASSISTANT_NAME,
          text: res.response,
          checklist: res.verification?.length
            ? res.verification
                .filter((v) => v.status !== "complete")
                .map((v) => `${v.document_name}${v.notes ? ` — ${v.notes}` : ""}`)
            : undefined,
          // The response carries the authoritative trace; the live feed was
          // only for the wait.
          trace: res.trace?.events,
          traceMs: res.trace?.duration_ms,
        },
      ]);
    } catch {
      // Backend unreachable: the bundled responder still answers the common
      // questions, which beats a dead chat.
      setMessages((m) => [...m, respond(question, stageId, stages)]);
    } finally {
      unsubscribe();
      setLiveTrace([]);
      setThinking(false);
      inputRef.current?.focus();
    }
  };

  const asked = useRef<string | null>(null);
  useEffect(() => {
    if (!ask || asked.current === ask.id) return;
    asked.current = ask.id;
    send(ask.text);
    // `send` is recreated every render; only a new question should trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask]);

  // Re-upload from a card goes through the same check as the stage card.
  const [reuploadStageId, setReuploadStageId] = useState<string | null>(null);
  const reuploadStage = stages.find((s) => s.id === reuploadStageId) ?? stage;
  const { upload, busy: uploading } = useDocumentUpload(reuploadStage);
  const fileRef = useRef<HTMLInputElement>(null);
  const [agentsOpen, setAgentsOpen] = useState(false);

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="border-b border-border bg-card px-5 pb-4 pt-5">
        <div className="flex items-start gap-3">
          <GabAIAvatar className="size-12" />
          <div className="min-w-0 flex-1 pt-0.5">
            <p className="truncate font-display text-xl font-bold leading-tight">{ASSISTANT_NAME}</p>
            <p className="truncate text-sm text-muted-foreground">
              Stage {stage.index} · {stage.agency}
            </p>
          </div>
          {onHide && (
            <button
              type="button"
              onClick={onHide}
              aria-label={`Close ${ASSISTANT_NAME}`}
              className="grid size-9 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-surface hover:text-foreground"
            >
              <X className="size-5" />
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setAgentsOpen((o) => !o)}
          aria-expanded={agentsOpen}
          className="mt-3 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex size-2.5 rounded-full bg-emerald-500" />
          </span>
          {AGENTS.length} specialist agents connected
          <ChevronDown className={cn("size-3.5 transition-transform", agentsOpen && "rotate-180")} />
        </button>
        {agentsOpen && (
          <ul className="mt-2 space-y-1 pl-4.5 text-sm text-muted-foreground">
            {AGENTS.map((a) => <li key={a}>{a}</li>)}
          </ul>
        )}
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-6">
        {groupRepeats(messages).map(({ msg: m, count }) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-3 leading-relaxed text-primary-foreground">
                {m.text}
              </p>
            </div>
          ) : (
            <div key={m.id} className="flex gap-3">
              <GabAIAvatar className="mt-1 size-8" />
              <div className="min-w-0 flex-1 space-y-2">
                {m.upload ? (
                  <UploadCheck
                    title={stages.find((s) => s.id === m.upload!.stageId)?.title ?? "Your upload"}
                    results={m.upload.results}
                    busy={uploading}
                    onReupload={() => {
                      setReuploadStageId(m.upload!.stageId ?? stage.id);
                      fileRef.current?.click();
                    }}
                  />
                ) : (
                  <div className="space-y-3 rounded-2xl border border-border bg-card px-5 py-4 leading-relaxed">
                    {/* Agent replies come back as Markdown; user text is rendered
                        verbatim so nobody can style the transcript by typing "**". */}
                    <MarkdownMessage>{m.text}</MarkdownMessage>

                    {m.checklist && (
                      <ul className="space-y-1.5 border-t border-border pt-3">
                        {m.checklist.map((c) => (
                          <li key={c} className="flex gap-2 text-sm leading-relaxed">
                            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-gold" />
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {m.fees && (
                      <div className="border-t border-border pt-3 text-sm">
                        <dl className="divide-y divide-border">
                          {FEE_BREAKDOWN.map((f) => (
                            <div key={f.label} className="flex items-baseline justify-between gap-3 py-2">
                              <dt>{f.short}</dt>
                              <dd className="shrink-0 font-bold">{f.amount}</dd>
                            </div>
                          ))}
                          <div className="flex items-baseline justify-between gap-3 py-2">
                            <dt className="font-semibold">Estimated total</dt>
                            <dd className="shrink-0 font-bold text-primary">{FEE_TOTAL}</dd>
                          </div>
                        </dl>
                        <p className="mt-1 text-xs text-muted-foreground">{FEE_DISCLAIMER}</p>
                      </div>
                    )}
                  </div>
                )}
                {count > 1 && <p className="px-1 text-xs text-muted-foreground">Same result ×{count}</p>}
                {m.trace && m.trace.length > 0 && <AgentTrace events={m.trace} totalMs={m.traceMs} />}
              </div>
            </div>
          ),
        )}

        {(thinking || uploading) && (
          <div className="flex gap-3">
            <GabAIAvatar className="mt-1 size-8" />
            <div className="min-w-0 flex-1">
              {liveTrace.length > 0 ? (
                <AgentTrace events={liveTrace} live />
              ) : (
                <p className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-5 py-3 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {uploading ? "Checking your document…" : "Thinking…"}
                </p>
              )}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-border bg-card pb-3 pt-4">
        <div className="flex gap-2 overflow-x-auto px-5 pb-3 [scrollbar-width:none]">
          {stage.chips.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => send(c)}
              disabled={thinking}
              className="shrink-0 whitespace-nowrap rounded-full border border-border bg-card px-4 py-2 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-sage-soft disabled:opacity-60"
            >
              {c}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="mx-5 flex items-center gap-2 rounded-2xl border border-border bg-surface p-1.5 pl-4 focus-within:border-primary/50"
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about permits, fees, requirements…"
            aria-label={`Message ${ASSISTANT_NAME}`}
            className="h-10 min-w-0 flex-1 bg-transparent text-base placeholder:text-muted-foreground focus:outline-none"
          />
          <button
            type="submit"
            disabled={thinking || !input.trim()}
            aria-label="Send"
            className="grid size-11 shrink-0 place-items-center rounded-xl bg-gold text-gold-foreground transition-opacity hover:bg-gold/90 disabled:opacity-50"
          >
            <Send className="size-4.5" />
          </button>
        </form>
        <p className="mt-2.5 px-5 text-center text-xs text-muted-foreground">
          Guidance only. Confirm fees with the issuing office.
        </p>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => {
          upload(e.target.files?.[0]);
          // Let the same file be picked again after a failed check.
          e.target.value = "";
        }}
      />
    </div>
  );
}
