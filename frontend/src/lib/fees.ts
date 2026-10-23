import type { RoadmapStep } from "@/lib/api";
import {
  FEE_BASIS_CAPITAL,
  FEE_BREAKDOWN,
  FEE_TOTAL,
  stageShortLabel,
  type Stage,
} from "@/lib/roadmap-data";

export type FeeEstimate = {
  items: { label: string; amount: string }[];
  total: string;
  /** What the figures are based on, for the line under the card. */
  basis: string;
};

const peso = (n: number) => `₱${n.toLocaleString("en-PH")}`;

/** "₱500 - ₱1,500" -> [500, 1500]; "Free" -> [0, 0]; "Varies" -> null */
function parseRange(cost: string | undefined): [number, number] | null {
  if (!cost) return null;
  const numbers = (cost.match(/\d[\d,]*(?:\.\d+)?/g) ?? [])
    .map((n) => Number(n.replace(/,/g, "")))
    .filter((n) => n > 0 && n < 10_000_000);
  if (!numbers.length) return /free|no fee|none/i.test(cost) ? [0, 0] : null;
  return [numbers[0]!, Math.max(...numbers)];
}

function formatRange([min, max]: [number, number]) {
  return min === max ? peso(min) : `${peso(min)} – ${peso(max)}`;
}

/**
 * One fee estimate for the whole app. When the roadmap came from the model,
 * add up its own per-step estimates, so the fee card matches the stage cards
 * and what GabAI quotes. The bundled table is only for the bundled roadmap.
 */
export function feeEstimate(roadmap: RoadmapStep[] | null, stages: Stage[]): FeeEstimate {
  if (!roadmap?.length) {
    return {
      items: FEE_BREAKDOWN.map((f) => ({ label: f.short, amount: f.amount })),
      total: FEE_TOTAL,
      basis: `Estimates based on ${peso(FEE_BASIS_CAPITAL)} capital.`,
    };
  }

  let min = 0;
  let max = 0;
  let unknown = 0;
  const items = roadmap.map((step, i) => {
    const range = parseRange(step.estimated_cost);
    if (range) {
      min += range[0];
      max += range[1];
    } else {
      unknown += 1;
    }
    const stage = stages[i];
    return {
      label: stage ? stageShortLabel(stage) : step.title,
      amount: range ? formatRange(range) : "Varies",
    };
  });

  const varies = unknown ? ` ${unknown} step${unknown > 1 ? "s" : ""} vary and aren't included.` : "";
  return {
    items,
    total: formatRange([min, max]),
    basis: `From your roadmap's estimates.${varies} The assessor's final bill can differ.`,
  };
}
