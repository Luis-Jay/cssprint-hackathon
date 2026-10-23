import stagesJson from "@/data/stages.json";
import feesJson from "@/data/fees.json";
import promptsJson from "@/data/agent-prompts.json";

export type SubStep = {
  id: string;
  label: string;
  detail?: string;
};

/** How a stage is filed: "both" lists the online route first. */
export type Filing = {
  mode: "online" | "in_person" | "both" | "check";
  note: string;
  links: { label: string; url: string }[];
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
  /** The document(s) the office issues when the stage is done; uploading them completes it. */
  outputs?: string[];
  filing?: Filing;
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

/**
 * Which local clearances a line-bureau stage covers. Model roadmaps often
 * split them over two stages, which used to be labelled "Line bureaus" twice.
 */
function bureauParts(stage: Stage): string[] {
  const title = stage.title.toLowerCase();
  const parts = [];
  if (/zoning|locational|occupancy/.test(title)) parts.push("Zoning");
  if (/sanitary|health/.test(title)) parts.push("Health");
  if (/fire|bfp/.test(title)) parts.push("Fire");
  return parts.length && parts.length < 3 ? parts : [];
}

export function stageShortLabel(stage: Stage): string {
  const parts = stageKind(stage) === "bureaus" ? bureauParts(stage) : [];
  if (parts.length) return parts.join(" & ");
  const short = STAGE_COPY[stageKind(stage)].short;
  if (short) return short;
  return stage.title.length > 18 ? `${stage.title.slice(0, 16)}…` : stage.title;
}

export function stageHeading(stage: Stage): string {
  const parts = stageKind(stage) === "bureaus" ? bureauParts(stage) : [];
  if (parts.length) {
    return `Get your ${parts.join(" and ").toLowerCase()} clearance${parts.length > 1 ? "s" : ""}`;
  }
  return STAGE_COPY[stageKind(stage)].heading || stage.title;
}

/** What the finished stage is called on the permit summary */
export function stageRecordTitle(stage: Stage): string {
  const parts = stageKind(stage) === "bureaus" ? bureauParts(stage) : [];
  if (parts.length) {
    const text = `${parts.join(" and ")} clearance${parts.length > 1 ? "s" : ""}`;
    return text[0] + text.slice(1).toLowerCase();
  }
  return STAGE_COPY[stageKind(stage)].record || stage.title;
}

/** Sellyo covers exactly one LGU */
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
