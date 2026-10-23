"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { LGU, STAGES } from "./roadmap-data";
import {
  fetchMe, fromBackendProfile, getSession, login as apiLogin, logout as apiLogout,
  roadmapToStages, saveProgress, signup as apiSignup, type AuthUser, type ChatMessage,
  type RoadmapStep,
} from "./api";
import type { Stage } from "./roadmap-data";
import type { TraceEvent, VerificationResult } from "./api";

/** A message pushed into the chat from outside it */
export type AgentMessage = {
  id: string;
  agent: string;
  text: string;
  /** The stage an upload was checked against, when this is an upload result. */
  stageId?: string;
  verification?: VerificationResult[];
  trace?: TraceEvent[];
  traceMs?: number;
  /** When it arrived (ms), so a closed chat can count unread replies. */
  at?: number;
};

export type BusinessProfile = {
  businessName: string;
  entity: string;
  ownerAge: string;
  ownerName: string;
  district: string;
  physicalStatus: string;
  capital: string;
  industry: string;
  employees: string;
  servesFood: boolean;
  signage: boolean;
  renovating: boolean;
  notes: string;
};

/** Re-exported for convenience; defined in roadmap-data.ts. */
export { LGU };

/** A blank form: a pre-filled sample business could be submitted unchanged by mistake. */
export const DEFAULT_PROFILE: BusinessProfile = {
  businessName: "",
  entity: "Sole Proprietorship",
  ownerAge: "",
  ownerName: "",
  district: "Sampaloc, Zone 30",
  physicalStatus: "Leased",
  capital: "",
  industry: "Small Café / Food Service",
  employees: "",
  servesFood: false,
  signage: false,
  renovating: false,
  notes: "",
};

/** Where the rendered roadmap came from. "bundled" means the backend was unreachable. */
export type RoadmapSource = "bundled" | "template" | "rag" | "cache";

type State = {
  profile: BusinessProfile;
  completed: string[];
  /** When each stage was completed (ISO date), for the permit summary. Local only. */
  completedAt: Record<string, string>;
  /** Name of the document that verified each stage, when one was uploaded. Local only. */
  uploads: Record<string, string>;
  /** What the owner says they actually paid in fees, once everything is done. */
  feesPaid: string;
  checked: string[];
  onboarded: boolean;
  /** Mirrors the server account; null when signed out. */
  user: AuthUser | null;
  /** Backend session id, null until onboarding hands off to the API. */
  sessionId: string | null;
  /** Roadmap as returned by the backend, null when running on bundled data. */
  roadmap: RoadmapStep[] | null;
  /** Chat transcript restored from the server; the panel seeds itself from this. */
  transcript: ChatMessage[];
  /** Messages pushed into the chat from elsewhere in the app (uploads). */
  inbox: AgentMessage[];
  roadmapSource: RoadmapSource;
};

const KEY = "msme-compliance-state-v1";

const initial: State = {
  profile: DEFAULT_PROFILE,
  completed: [],
  completedAt: {},
  uploads: {},
  feesPaid: "",
  checked: [],
  onboarded: false,
  user: null,
  sessionId: null,
  roadmap: null,
  transcript: [],
  inbox: [],
  roadmapSource: "bundled",
};

type Ctx = State & {
  /** The stages actually rendered: backend roadmap if present, else bundled. */
  stages: Stage[];
  totalSubSteps: number;
  setProfile: (p: BusinessProfile) => void;
  completeStage: (stageId: string) => void;
  /** Remember which file verified a stage. */
  recordUpload: (stageId: string, fileName: string) => void;
  setFeesPaid: (amount: string) => void;
  toggleSubStep: (subStepId: string) => void;
  isSubStepChecked: (subStepId: string) => boolean;
  resetProgress: () => void;
  restartOnboarding: () => void;
  /** True while the stored token is being resolved on first paint. */
  authLoading: boolean;
  signedIn: boolean;
  name: string;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name?: string) => Promise<void>;
  signOut: () => Promise<void>;
  finishOnboarding: (p: BusinessProfile) => void;
  /** Chat transcript restored from the server. */
  transcript: ChatMessage[];
  /** Push a message into the chat from outside the chat panel. */
  pushAgentMessage: (message: AgentMessage) => void;
  /** Tick sub-steps that a verified document satisfied. Idempotent - unlike
   *  toggleSubStep, re-verifying the same document cannot untick anything. */
  markSubStepsChecked: (ids: string[]) => void;
  /** Store a roadmap from the backend. Resets progress - the steps changed. */
  setBackendRoadmap: (sessionId: string, roadmap: RoadmapStep[], source: RoadmapSource) => void;
  isStageComplete: (id: string) => boolean;
  isStageUnlocked: (id: string) => boolean;
  progress: number;
  currentStageIndex: number;
};



/** Pull everything durable for a session: roadmap, profile, progress and the chat transcript */
async function restoreWorkspace(
  sessionId: string,
  fallbackProfile: BusinessProfile,
): Promise<Partial<State> | null> {
  try {
    const s = await getSession(sessionId);
    if (!s.roadmap?.length) return null;
    return {
      sessionId,
      roadmap: s.roadmap,
      roadmapSource: (s.source as RoadmapSource) ?? "template",
      profile: fromBackendProfile(s.profile, fallbackProfile) ?? fallbackProfile,
      completed: s.progress?.completed ?? [],
      checked: s.progress?.checked ?? [],
      transcript: s.messages ?? [],
      onboarded: true,
    };
  } catch {
    return null;
  }
}

const StoreContext = createContext<Ctx | null>(null);

function read(): State {
  if (typeof window === "undefined") return initial;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...initial, ...(JSON.parse(raw) as State) } : initial;
  } catch {
    return initial;
  }
}

export function ComplianceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(initial);
  const [hydrated, setHydrated] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    setState(read());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(KEY, JSON.stringify(state));
  }, [state, hydrated]);

  // Resolve the stored bearer token once on mount
  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;

    (async () => {
      try {
        const me = await fetchMe();
        if (cancelled) return;

        if (!me.ok) {
          // Sign out ONLY when the server says the token is invalid
          if (me.reason === "unauthenticated") {
            // The token was REJECTED
            setState(() => ({ ...initial }));
          } else if (me.reason === "no-token") {
            // Never signed in
            setState((s) => (s.user ? { ...s, user: null } : s));
          }
          // "unreachable": change nothing. The session is probably still fine.
          return;
        }

        setState((s) => ({ ...s, user: me.auth.user }));

        // Restore everything this account was last working on.
        if (me.auth.session_id && me.auth.session_id !== state.sessionId) {
          const restored = await restoreWorkspace(me.auth.session_id, state.profile);
          if (!cancelled && restored) setState((s) => ({ ...s, ...restored }));
        }
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // Runs once after hydration; state.sessionId is read, not tracked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  // Mirror progress to the server so it survives sign-out
  useEffect(() => {
    if (!hydrated || authLoading || !state.sessionId) return;
    const t = setTimeout(() => {
      saveProgress(state.sessionId!, state.completed, state.checked).catch(() => {
        /* progress is still in localStorage; retried on the next change */
      });
    }, 400);
    return () => clearTimeout(t);
  }, [hydrated, authLoading, state.sessionId, state.completed, state.checked]);

  const completeStage = useCallback((stageId: string) => {
    setState((s) =>
      s.completed.includes(stageId)
        ? s
        : {
            ...s,
            completed: [...s.completed, stageId],
            completedAt: { ...s.completedAt, [stageId]: new Date().toISOString() },
          },
    );
  }, []);

  const setBackendRoadmap = useCallback(
    (sessionId: string, roadmap: RoadmapStep[], source: RoadmapSource) => {
      setState((s) => ({
        ...s,
        sessionId,
        roadmap,
        roadmapSource: source,
        // Step ids change with the roadmap, so old progress no longer maps.
        completed: [],
        completedAt: {},
        uploads: {},
        feesPaid: "",
        checked: [],
      }));
    },
    [],
  );

  const value = useMemo<Ctx>(() => {
    const stages =
      state.roadmap && state.roadmap.length > 0 ? roadmapToStages(state.roadmap) : STAGES;
    const totalSubSteps = stages.reduce((n, s) => n + s.subSteps.length, 0);

    const isStageComplete = (id: string) => state.completed.includes(id);
    const isStageUnlocked = (id: string) => {
      const i = stages.findIndex((s) => s.id === id);
      if (i <= 0) return true;
      return isStageComplete(stages[i - 1]!.id);
    };
    const doneStepIds = new Set(state.checked);
    stages.filter((s) => isStageComplete(s.id)).forEach((s) =>
      s.subSteps.forEach((ss) => doneStepIds.add(ss.id)),
    );
    const currentStageIndex = Math.min(state.completed.length + 1, stages.length);

    return {
      ...state,
      stages,
      totalSubSteps,
      setProfile: (profile) => setState((s) => ({ ...s, profile })),
      completeStage,
      recordUpload: (stageId, fileName) =>
        setState((s) => ({ ...s, uploads: { ...s.uploads, [stageId]: fileName } })),
      setFeesPaid: (feesPaid) => setState((s) => ({ ...s, feesPaid })),
      setBackendRoadmap,
      toggleSubStep: (id) =>
        setState((s) => ({
          ...s,
          checked: s.checked.includes(id)
            ? s.checked.filter((x) => x !== id)
            : [...s.checked, id],
        })),
      pushAgentMessage: (message) =>
        setState((s) => ({ ...s, inbox: [...s.inbox, { ...message, at: Date.now() }] })),
      markSubStepsChecked: (ids) =>
        setState((s) => {
          const fresh = ids.filter((id) => !s.checked.includes(id));
          return fresh.length ? { ...s, checked: [...s.checked, ...fresh] } : s;
        }),
      isSubStepChecked: (id) => state.checked.includes(id),
      resetProgress: () =>
        setState((s) => ({ ...s, completed: [], completedAt: {}, uploads: {}, feesPaid: "", checked: [] })),
      restartOnboarding: () =>
        setState((s) => ({
          ...s, completed: [], completedAt: {}, uploads: {}, feesPaid: "", checked: [], onboarded: false,
        })),
      authLoading,
      signedIn: state.user !== null,
      name: state.user?.name ?? "",
      signIn: async (email, password) => {
        const res = await apiLogin(email, password);
        setState((s) => ({ ...s, user: res.user }));

        // Pull back everything this account already owns.
        if (res.session_id) {
          const restored = await restoreWorkspace(res.session_id, state.profile);
          if (restored) setState((s) => ({ ...s, ...restored }));
        }
      },
      signUp: async (email, password, name) => {
        const res = await apiSignup(email, password, name);
        setState((s) => ({ ...s, user: res.user }));
      },
      signOut: async () => {
        await apiLogout();
        // Clear the workspace too: leaving another account's roadmap on screen
        // after sign-out would be a data leak on a shared machine.
        setState(() => ({ ...initial }));
      },
      finishOnboarding: (profile) => setState((s) => ({ ...s, profile, onboarded: true })),
      isStageComplete,
      isStageUnlocked,
      progress: totalSubSteps === 0 ? 0 : Math.round((doneStepIds.size / totalSubSteps) * 100),

      currentStageIndex,
    };
  }, [state, completeStage, setBackendRoadmap, authLoading]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useCompliance() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useCompliance must be used inside ComplianceProvider");
  return ctx;
}

export function formatPeso(value: string) {
  const n = Number(String(value).replace(/[^\d.]/g, ""));
  if (!Number.isFinite(n) || n === 0) return "₱0";
  return "₱" + n.toLocaleString("en-PH");
}
