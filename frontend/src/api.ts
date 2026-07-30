/**
 * API client.
 *
 * The access token lives in memory only — never localStorage. A token in
 * localStorage survives the tab and is readable by any script that gets injected;
 * for a product holding court files that is a bad trade for the convenience.
 * The refresh token is held the same way, so closing the tab signs you out. That is
 * deliberate for a single-user local build and revisits when the mobile app lands.
 */

const BASE = "/api";

let accessToken: string | null = null;
let refreshToken: string | null = null;
let pendingChallenge: string | null = null;

export function setTokens(tokens: { access_token: string; refresh_token: string }): void {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
}

export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
}

export function isSignedIn(): boolean {
  return accessToken !== null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

/** Human-readable text for an error body, which FastAPI shapes several ways. */
function readDetail(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (first?.msg) return String(first.msg);
  }
  return null;
}

async function send(path: string, init: RequestInit, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${BASE}${path}`, { ...init, headers });

  // One silent refresh attempt, so a lapsed access token does not look like a
  // random logout mid-upload.
  if (response.status === 401 && retry && refreshToken) {
    const refreshed = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (refreshed.ok) {
      setTokens(await refreshed.json());
      return send(path, init, false);
    }
    clearTokens();
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, readDetail(body) ?? "Something went wrong.", body);
  }
  return body as T;
}

function json(path: string, method: string, payload: unknown): Promise<unknown> {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface Account {
  id: string;
  email: string;
  display_name: string | null;
}

export interface CaseSummary {
  id: string;
  title: string;
  jurisdiction: string;
  court: string | null;
  case_number: string | null;
}

export interface DocumentSummary {
  id: string;
  title: string;
  kind: string;
  page_count: number;
  ocr_status: string;
  filed_at: string | null;
}

export interface Passage {
  id: string;
  start_offset: number;
  end_offset: number;
  quote: string;
}

export interface Page {
  page_number: number;
  text: string;
  /** null means "not measured" — a native PDF text layer — not a measured zero. */
  ocr_confidence: number | null;
  passages: Passage[];
}

export interface DocumentDetail extends DocumentSummary {
  pages: Page[];
}

export interface Citation {
  document_id: string;
  document_title: string;
  page_number: number;
  quote: string;
}

/** A correction recorded beside an entry. The entry itself never changes. */
export interface EventNote {
  id: string;
  body: string;
  created_at: string;
}

export interface TimelineEvent {
  id: string;
  kind: "procedural" | "alleged";
  provenance: "document_derived" | "user_asserted";
  occurred_at: string;
  date_precision: "exact" | "day" | "month" | "year";
  summary: string;
  /** Present exactly when provenance is document_derived. */
  citation: Citation | null;
  notes: EventNote[];
}

export interface NewEvent {
  summary: string;
  occurred_at: string;
  kind?: "procedural" | "alleged";
  date_precision?: TimelineEvent["date_precision"];
}

export const api = {
  register: (email: string, password: string) =>
    json("/auth/register", "POST", { email, password }) as Promise<Account>,

  /** Resolves to "mfa_required" when a second factor is owed, so callers handle both. */
  login: async (email: string, password: string): Promise<"ok" | "mfa_required"> => {
    const body = (await json("/auth/login", "POST", { email, password })) as
      | { access_token: string; refresh_token: string }
      | { mfa_required: true; challenge_token: string };
    if ("mfa_required" in body) {
      pendingChallenge = body.challenge_token;
      return "mfa_required";
    }
    setTokens(body);
    return "ok";
  },

  verifyMfa: async (code: string): Promise<void> => {
    if (!pendingChallenge) throw new ApiError(400, "No sign-in is in progress.");
    const body = (await json("/auth/mfa/verify", "POST", {
      challenge_token: pendingChallenge,
      code,
    })) as { access_token: string; refresh_token: string };
    pendingChallenge = null;
    setTokens(body);
  },

  me: () => request<Account>("/auth/me"),
  logout: async () => {
    await request<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    clearTokens();
  },

  listCases: () => request<CaseSummary[]>("/cases"),
  createCase: (title: string) => json("/cases", "POST", { title }) as Promise<CaseSummary>,
  readCase: (caseId: string) => request<CaseSummary>(`/cases/${caseId}`),

  listDocuments: (caseId: string) => request<DocumentSummary[]>(`/cases/${caseId}/documents`),
  readDocument: (caseId: string, documentId: string) =>
    request<DocumentDetail>(`/cases/${caseId}/documents/${documentId}`),

  listEvents: (caseId: string) => request<TimelineEvent[]>(`/cases/${caseId}/events`),
  createEvent: (caseId: string, event: NewEvent) =>
    json(`/cases/${caseId}/events`, "POST", event) as Promise<TimelineEvent>,
  addNote: (caseId: string, eventId: string, body: string) =>
    json(`/cases/${caseId}/events/${eventId}/notes`, "POST", { body }) as Promise<EventNote>,

  uploadDocument: async (caseId: string, file: File, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    // No Content-Type header: the browser must set the multipart boundary itself.
    return request<DocumentSummary>(`/cases/${caseId}/documents`, {
      method: "POST",
      body: form,
    });
  },
};
