/** PermitPal backend client */
import type { BusinessProfile } from "./compliance-store";
import { LGU, type Filing, type Stage } from "./roadmap-data";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** How long to wait before giving up and using bundled data. */
const TIMEOUT_MS = 15_000;

/** Roadmap generation is a live RAG + model call and can take over a minute */
const ROADMAP_TIMEOUT_MS = 180_000;

export type RoadmapStep = {
  step_number: number;
  title: string;
  description: string;
  requirements: string[];
  estimated_time?: string;
  estimated_cost?: string;
  location?: string;
  notes?: string;
  /** Added by the backend: the document that completes the step, and how it's filed. */
  outputs?: string[];
  filing?: Filing;
};

export type RoadmapResponse = {
  session_id: string;
  roadmap: RoadmapStep[];
  profile: Record<string, unknown>;
  stage: string;
  source: "cache" | "rag" | "template" | null;
  refining: boolean;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type SessionResponse = {
  session_id: string;
  stage: string;
  profile: Record<string, unknown>;
  roadmap: RoadmapStep[];
  documents: Record<string, unknown>[];
  message_count: number;
  messages: ChatMessage[];
  progress: { completed?: string[]; checked?: string[] };
  source: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Where the bearer token lives between page loads. */
const TOKEN_KEY = "permitpal-auth-token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage disabled */
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit,
                          timeoutMs: number = TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}/api${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...init?.headers,
      },
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, res.status);
    }

    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(`Backend did not respond within ${timeoutMs / 1000}s`);
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Could not reach the backend",
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Translate the onboarding wizard's profile into the field names the
 * profiling and roadmap agents expect (snake_case, different key names).
 */
export function toBackendProfile(p: BusinessProfile): Record<string, unknown> {
  const numeric = (v: string) => {
    const n = Number(String(v).replace(/[^\d.]/g, ""));
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  return {
    business_name: p.businessName || null,
    business_type: p.industry || null,
    // LGU is no longer a form field - the product only covers Manila.
    location: [p.district, LGU].filter(Boolean).join(", ") || null,
    capital: numeric(p.capital),
    employees: numeric(p.employees),
    serves_food: p.servesFood,
    has_signage: p.signage,
    is_homebased: p.physicalStatus === "Home-based",
    entity_type: p.entity || null,
    owner_age: numeric(p.ownerAge),
    notes: p.notes || null,
  };
}

/** Inverse of toBackendProfile: rebuild the wizard's profile from what the backend stored */
export function fromBackendProfile(
  raw: Record<string, unknown> | null | undefined,
  fallback: BusinessProfile,
): BusinessProfile | null {
  if (!raw || !raw.business_name) return null;

  const str = (v: unknown, dflt: string) =>
    v === null || v === undefined || v === "" ? dflt : String(v);

  // Location is stored as "District, City of Manila"; the form only holds the
  // district half.
  const location = str(raw.location, "");
  const district = location
    ? location.replace(new RegExp(`,?\\s*${LGU}\\s*$`, "i"), "").trim() || fallback.district
    : fallback.district;

  return {
    ...fallback,
    businessName: str(raw.business_name, fallback.businessName),
    industry: str(raw.business_type, fallback.industry),
    district,
    capital: str(raw.capital, fallback.capital),
    employees: str(raw.employees, fallback.employees),
    entity: str(raw.entity_type, fallback.entity),
    ownerAge: str(raw.owner_age, fallback.ownerAge),
    servesFood: raw.serves_food === undefined ? fallback.servesFood : Boolean(raw.serves_food),
    signage: raw.has_signage === undefined ? fallback.signage : Boolean(raw.has_signage),
    physicalStatus: raw.is_homebased ? "Home-based" : fallback.physicalStatus,
    notes: str(raw.notes, fallback.notes),
  };
}

/** Turn a backend roadmap into the Stage shape the timeline already renders. */
export function roadmapToStages(roadmap: RoadmapStep[]): Stage[] {
  return roadmap.map((step, i) => {
    const index = step.step_number ?? i + 1;
    const id = `step-${index}`;

    const detailBits = [step.estimated_time, step.estimated_cost].filter(Boolean);
    const summary = [
      step.description,
      detailBits.length ? `(${detailBits.join(" · ")})` : "",
      step.notes ?? "",
    ]
      .filter(Boolean)
      .join(" ");

    return {
      id,
      index,
      title: step.title,
      agency: step.location ?? "See requirements",
      summary,
      subSteps: (step.requirements ?? []).map((req, j) => ({
        id: `${id}-req-${j + 1}`,
        label: req,
        detail: "",
      })),
      uploadLabel: step.outputs?.join(" and ") ?? step.title,
      outputs: step.outputs,
      filing: step.filing,
      agencyUrl: step.filing?.links[0]?.url.replace(/^https?:\/\//, ""),
      chips: [
        `What exactly do I need for ${step.title}?`,
        step.estimated_cost ? `Why does this cost ${step.estimated_cost}?` : "How long does this take?",
        `Where do I go for ${step.title}?`,
      ],
    } as Stage;
  });
}

export type ChatResponse = {
  session_id: string;
  response: string;
  stage: string;
  agent: string | null;
  profile: Record<string, unknown> | null;
  roadmap: RoadmapStep[] | null;
  documents: Record<string, unknown>[] | null;
  verification: VerificationResult[] | null;
  /** Low-level execution record for this turn; see AgentTrace. */
  trace: Trace | null;
};

export type VerificationResult = {
  document_name: string;
  /** "unverified": only a keyword match was possible, so nothing was confirmed. */
  status: "complete" | "missing" | "incomplete" | "unreadable" | "unverified";
  notes?: string;
  evidence?: string;
  confidence?: number;
  /** "output" is the stage's own document; "requirement" is something brought to apply. */
  kind?: "output" | "requirement";
  /** Deterministic checks on the fields read off the document. ok is null when unreadable. */
  checks?: { label: string; ok: boolean | null; detail: string }[];
};

export type UploadResponse = {
  session_id: string;
  status: string;
  message: string;
  verification_results: {
    documents: VerificationResult[];
    complete: number;
    missing: number;
    unreadable: number;
    /** True only when every requirement for the stage is satisfied. */
    passed: boolean;
    /** How text was recovered: "pdf" | "text" | "image" | "empty" | "unsupported" | "unreadable". */
    extracted: string;
  } | null;
  agent: string | null;
  trace: Trace | null;
};

export type TraceEvent = {
  seq: number;
  ts: number;
  phase: "route" | "agent" | "retrieval" | "model" | "parse" | "fallback" | "done";
  label: string;
  agent: string | null;
  status: "ok" | "warn" | "error";
  duration_ms: number | null;
  detail: Record<string, unknown>;
};

export type Trace = {
  id: string;
  session_id: string;
  kind: string;
  duration_ms: number;
  events: TraceEvent[];
};

/** Subscribe to live agent activity for a session */
export function subscribeTrace(
  sessionId: string,
  onEvent: (event: TraceEvent) => void,
): () => void {
  if (typeof window === "undefined" || !("EventSource" in window)) return () => {};

  let source: EventSource | null = null;
  try {
    source = new EventSource(
      `${API_BASE}/api/trace/${encodeURIComponent(sessionId)}/stream`,
    );
    source.addEventListener("trace", (e) => {
      try {
        onEvent(JSON.parse((e as MessageEvent).data) as TraceEvent);
      } catch {
        /* malformed frame - skip it rather than kill the stream */
      }
    });
    // Browsers auto-reconnect on error; nothing to do but stay quiet.
  } catch {
    return () => {};
  }

  return () => source?.close();
}

export function fetchTraces(sessionId: string, limit = 5) {
  return request<{ session_id: string; traces: Trace[] }>(
    `/trace/${encodeURIComponent(sessionId)}?limit=${limit}`,
  );
}

export type AuthUser = { id: number; email: string; name: string };

export type AuthResponse = {
  token: string;
  user: AuthUser;
  session_id: string | null;
};

/** Create an account. Stores the returned token. */
export async function signup(email: string, password: string, name?: string) {
  const res = await request<AuthResponse>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
  setToken(res.token);
  return res;
}

/** Sign in. Stores the returned token. */
export async function login(email: string, password: string) {
  const res = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(res.token);
  return res;
}

/** Outcome of resolving the stored token */
export type MeResult =
  | { ok: true; auth: AuthResponse }
  | { ok: false; reason: "no-token" | "unauthenticated" | "unreachable" };

/** Resolve the stored token against the server. */
export async function fetchMe(): Promise<MeResult> {
  if (!getToken()) return { ok: false, reason: "no-token" };
  try {
    return { ok: true, auth: await request<AuthResponse>("/auth/me") };
  } catch (err) {
    // Only a 401 means the token is genuinely dead
    if (err instanceof ApiError && err.status === 401) {
      setToken(null);
      return { ok: false, reason: "unauthenticated" };
    }
    return { ok: false, reason: "unreachable" };
  }
}

export async function logout() {
  try {
    if (getToken()) await request<void>("/auth/logout", { method: "POST" });
  } catch {
    // Even if the server call fails, drop the local token.
  } finally {
    setToken(null);
  }
}

/** Attach an agent session to the signed-in account. */
export function linkWorkspace(sessionId: string) {
  return request<AuthResponse>("/auth/workspace", {
    method: "PUT",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function createSession() {
  return request<SessionResponse>("/session", { method: "POST" });
}

/** Full session: roadmap, profile, transcript and progress. */
export function getSession(sessionId: string) {
  return request<SessionResponse>(`/session/${encodeURIComponent(sessionId)}`);
}

/** Persist which stages and sub-steps are ticked off. */
export function saveProgress(sessionId: string, completed: string[], checked: string[]) {
  return request<SessionResponse>(
    `/session/${encodeURIComponent(sessionId)}/progress`,
    { method: "PUT", body: JSON.stringify({ completed, checked }) },
  );
}

/** Send a chat message and get the responding agent's answer. */
export function sendChat(sessionId: string, message: string) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

/** Upload a document and run the Inspection Readiness Agent over it */
export async function uploadDocument(
  sessionId: string,
  documentName: string,
  file: File,
  stepNumber?: number,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("document_name", documentName);
  form.append("file", file);
  // Scope verification to the stage this was filed under, rather than
  // checking it against every requirement in the roadmap.
  if (stepNumber !== undefined) form.append("step_number", String(stepNumber));

  const controller = new AbortController();
  // Verification can make two model calls, each of which may fall back to a
  // second model on the free tier.
  const timer = setTimeout(() => controller.abort(), 120_000);

  try {
    const res = await fetch(`${API_BASE}/api/upload-document`, {
      method: "POST",
      body: form,
      signal: controller.signal,
      // No Content-Type: the browser must set the multipart boundary itself.
      headers: authHeaders(),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, res.status);
    }
    return (await res.json()) as UploadResponse;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      err instanceof Error ? err.message : "Upload failed",
    );
  } finally {
    clearTimeout(timer);
  }
}

export function createRoadmap(sessionId: string, profile: BusinessProfile) {
  return request<RoadmapResponse>("/roadmap", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      profile: toBackendProfile(profile),
    }),
  }, ROADMAP_TIMEOUT_MS);
}

export function getRoadmap(sessionId: string) {
  return request<RoadmapResponse>(`/roadmap/${encodeURIComponent(sessionId)}`);
}

/** Run the full onboarding handshake: create a session, then generate a roadmap */
export async function startCompliance(profile: BusinessProfile) {
  const session = await createSession();
  const roadmap = await createRoadmap(session.session_id, profile);

  // Bind the workspace to the account so signing in elsewhere restores it.
  // Best-effort: a signed-out user still gets a working roadmap.
  if (getToken()) {
    try {
      await linkWorkspace(session.session_id);
    } catch {
      /* not fatal */
    }
  }

  return { sessionId: session.session_id, roadmap };
}

