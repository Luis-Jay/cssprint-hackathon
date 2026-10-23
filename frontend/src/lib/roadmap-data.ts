import stagesJson from "@/data/stages.json";
import feesJson from "@/data/fees.json";
import promptsJson from "@/data/agent-prompts.json";

export type SubStep = {
  id: string;
  label: string;
  detail?: string;
};

export type Stage = {
  id: string;
  index: number;
  title: string;
  agency: string;
  agencyUrl?: string;
  summary: string;
  subSteps: SubStep[];
  uploadLabel: string;
  chips: string[];
};

export type Fee = { short: string; label: string; amount: string; note: string };

export type AgentPersona = { id: string; name: string; prompt: string; triggers: string[] };

export type StageKind = "dti" | "barangay" | "bureaus" | "mayor" | "bir" | "other";

/** Short tab label, plain-language heading, and permit summary title per kind of stage */
const STAGE_COPY: Record<StageKind, { short: string; heading: string; record: string }> = {
  dti: { short: "DTI name", heading: "Register your business name", record: "DTI business name registration" },
  barangay: { short: "Barangay", heading: "Get your barangay clearance", record: "Barangay clearance" },
  bureaus: { short: "Line bureaus", heading: "Clear zoning, health and fire", record: "Special local clearances" },
  mayor: { short: "Mayor's permit", heading: "Get your mayor's permit", record: "Mayor's business permit" },
  bir: { short: "BIR", heading: "Register with the BIR", record: "BIR registration" },
  other: { short: "", heading: "", record: "" },
};

/**
 * Which permit stage this is. Backend roadmaps are written by the model, so
 * ids and titles vary; match on the words they reliably contain.
 */
export function stageKind(stage: Stage): StageKind {
  const text = `${stage.id} ${stage.title} ${stage.agency}`.toLowerCase();
  if (/\bdti\b|business name/.test(text)) return "dti";
  if (/\bbir\b|internal revenue/.test(text)) return "bir";
  if (/mayor|bpls|business permit/.test(text)) return "mayor";
  if (/barangay|brgy/.test(text)) return "barangay";
  if (/zoning|sanitary|fire|bfp|cpdo|health|line bureau|clearance/.test(text)) return "bureaus";
  return "other";
}

export function stageShortLabel(stage: Stage): string {
  const short = STAGE_COPY[stageKind(stage)].short;
  if (short) return short;
  return stage.title.length > 18 ? `${stage.title.slice(0, 16)}…` : stage.title;
}

export function stageHeading(stage: Stage): string {
  return STAGE_COPY[stageKind(stage)].heading || stage.title;
}

/** What the finished stage is called on the permit summary */
export function stageRecordTitle(stage: Stage): string {
  return STAGE_COPY[stageKind(stage)].record || stage.title;
}

/** Negosyo Copilot covers exactly one LGU */
export const LGU = "City of Manila";

/** Source of truth lives in src/data/stages.json */
export const STAGES = stagesJson.stages as Stage[];

export const TOTAL_SUBSTEPS = STAGES.reduce((n, s) => n + s.subSteps.length, 0);

/** Source of truth lives in src/data/fees.json */
export const FEE_BREAKDOWN = feesJson.items as Fee[];
export const FEE_TOTAL = feesJson.totalRange;
export const FEE_DISCLAIMER = feesJson.disclaimer;
/** The starting capital the fee estimate was worked out for */
export const FEE_BASIS_CAPITAL = feesJson.basisCapital;

/** Source of truth lives in src/data/agent-prompts.json */
export const AGENT_PERSONAS = promptsJson.agents as AgentPersona[];
export const SYSTEM_PROMPT = promptsJson.systemPrompt;
export const ROADMAP_DISCLAIMER = promptsJson.disclaimer;
