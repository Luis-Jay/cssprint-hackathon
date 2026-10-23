"use client";

import { useState } from "react";
import {
  AlertTriangle, Brain, ChevronRight, CircleCheck, Cpu, FileSearch,
  GitBranch, Loader2, Rewind,
} from "lucide-react";
import type { TraceEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Low-level view of what the agents actually did for one turn */

const PHASE_META: Record<
  TraceEvent["phase"],
  { icon: typeof Brain; label: string; tint: string }
> = {
  route: { icon: GitBranch, label: "Routing", tint: "text-gold-foreground" },
  agent: { icon: Brain, label: "Agent", tint: "text-primary" },
  retrieval: { icon: FileSearch, label: "Retrieval", tint: "text-primary" },
  model: { icon: Cpu, label: "Model", tint: "text-gold-foreground" },
  parse: { icon: FileSearch, label: "Parse", tint: "text-muted-foreground" },
  fallback: { icon: Rewind, label: "Fallback", tint: "text-destructive" },
  done: { icon: CircleCheck, label: "Done", tint: "text-primary" },
};

/** Keys worth surfacing as a full block rather than an inline chip. */
const LONG_KEYS = new Set(["prompt", "system_prompt", "raw_response", "message", "question"]);

function ms(value: number | null) {
  if (value === null || value === undefined) return null;
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function Detail({ detail }: { detail: Record<string, unknown> }) {
  const entries = Object.entries(detail).filter(([, v]) => v !== null && v !== "");
  if (!entries.length) return null;

  const chips = entries.filter(([k, v]) => !LONG_KEYS.has(k) && typeof v !== "object");
  const blocks = entries.filter(([k, v]) => LONG_KEYS.has(k) || typeof v === "object");

  return (
    <div className="mt-2 space-y-2">
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {chips.map(([k, v]) => (
            <span
              key={k}
              className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
            >
              {k}=<span className="text-foreground">{String(v)}</span>
            </span>
          ))}
        </div>
      )}
      {blocks.map(([k, v]) => (
        <div key={k}>
          <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
            {k.replace(/_/g, " ")}
          </p>
          <pre className="mt-0.5 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-secondary/70 p-2 font-mono text-[10px] leading-relaxed">
            {typeof v === "string" ? v : JSON.stringify(v, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
}

function Row({ event }: { event: TraceEvent }) {
  const [open, setOpen] = useState(false);
  const meta = PHASE_META[event.phase] ?? PHASE_META.agent;
  const Icon = meta.icon;
  const duration = ms(event.duration_ms);
  const hasDetail = Object.keys(event.detail || {}).length > 0;

  return (
    <li className="relative pl-6">
      <span
        className={cn(
          "absolute left-0 top-1 grid size-4 place-items-center rounded-full bg-card",
          event.status === "error"
            ? "text-destructive"
            : event.status === "warn"
              ? "text-gold-foreground"
              : meta.tint,
        )}
      >
        {event.status === "error" || event.status === "warn" ? (
          <AlertTriangle className="size-3" />
        ) : (
          <Icon className="size-3" />
        )}
      </span>

      <button
        type="button"
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={cn(
          "flex w-full items-start gap-1.5 text-left",
          hasDetail && "cursor-pointer",
        )}
      >
        <span className="min-w-0 flex-1">
          <span className="text-[11px] font-semibold leading-snug">{event.label}</span>
          {event.agent && (
            <span className="ml-1.5 text-[10px] text-muted-foreground">{event.agent}</span>
          )}
        </span>
        {duration && (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {duration}
          </span>
        )}
        {hasDetail && (
          <ChevronRight
            className={cn(
              "mt-0.5 size-3 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
        )}
      </button>

      {open && <Detail detail={event.detail} />}
    </li>
  );
}

export function AgentTrace({
  events,
  live = false,
  totalMs,
  defaultOpen = false,
}: {
  events: TraceEvent[];
  /** True while the turn is still running - shows a spinner and auto-expands. */
  live?: boolean;
  totalMs?: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const expanded = open || live;

  if (!events.length && !live) return null;

  const steps = events.filter((e) => e.phase !== "done");
  const problems = events.filter((e) => e.status !== "ok").length;

  return (
    <div className="mt-1.5 overflow-hidden rounded-xl border border-border bg-card/60">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left"
        aria-expanded={expanded}
      >
        {live ? (
          <Loader2 className="size-3 shrink-0 animate-spin text-primary" />
        ) : (
          <Brain className="size-3 shrink-0 text-muted-foreground" />
        )}
        <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
          {live ? "Agents deliberating" : "Agent activity"}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {steps.length} step{steps.length === 1 ? "" : "s"}
          {totalMs ? ` · ${ms(totalMs)}` : ""}
          {problems ? ` · ${problems} warning${problems === 1 ? "" : "s"}` : ""}
        </span>
        <ChevronRight
          className={cn(
            "ml-auto size-3 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
        />
      </button>

      {expanded && (
        <ol className="space-y-2 border-t border-border px-2.5 py-2">
          {events.map((e) => (
            <Row key={`${e.seq}-${e.ts}`} event={e} />
          ))}
          {live && !events.length && (
            <li className="pl-6 text-[11px] text-muted-foreground">Waiting for the first step…</li>
          )}
        </ol>
      )}
    </div>
  );
}
