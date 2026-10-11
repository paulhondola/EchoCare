import { signOut } from "firebase/auth";
import { auth } from "./firebase";

const API_URL = import.meta.env.VITE_API_URL;

/** Calls the API as the signed-in person (auth-layer §3.1). */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const user = auth.currentUser;
  if (!user) throw new Error("apiFetch needs a signed-in user");
  const send = async (forceRefresh: boolean) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${await user.getIdToken(forceRefresh)}`);
    return fetch(`${API_URL}${path}`, { ...init, headers });
  };
  // A 401 retries once with a forced-fresh token; a second 401 signs out (auth-layer §3.2).
  let res = await send(false);
  if (res.status === 401) res = await send(true);
  if (res.status === 401) await signOut(auth);
  return res;
}

/** GET /api/me (auth-layer §3.3). */
export type Me = {
  display_name: string;
  phone_e164: string;
  grants: { role: string; senior_id: string | null }[];
};

/** The body on a 200, otherwise the refusal's reason (auth-layer §3.2). */
export async function getMe(): Promise<Me | string> {
  const res = await apiFetch("/api/me");
  if (res.ok) return (await res.json()) as Me;
  const body = (await res.json().catch(() => null)) as { detail?: { reason?: string } } | null;
  return body?.detail?.reason ?? `http_${res.status}`;
}

export type IncidentStatus = "open" | "in_progress" | "resolved";

// One row of GET /incidents (04 §1), DAS only. Names follow the incidents and seniors tables
// (05 §1) and IncidentSummary in backend/app/main.py; keep the three in step.
export interface Incident {
  id: string;
  senior_full_name: string;
  senior_form_of_address: string;
  status: IncidentStatus;
  reason: string;
  opened_at: string;
  taken_by_name: string | null;
  taken_at: string | null;
  handover_answered: boolean;
}

/** A refused request; `reason` and the extra fields come from the refusal body (04 §0). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly reason?: string,
    readonly takenByName?: string | null,
  ) {
    super(reason ? `HTTP ${status} ${reason}` : `HTTP ${status}`);
  }
}

type Refusal = { detail?: { reason?: string; taken_by_name?: string | null } };

async function refused(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => null)) as Refusal | null;
  return new ApiError(res.status, body?.detail?.reason, body?.detail?.taken_by_name);
}

// The dashboard asks for any status, unlike the DAS app (04 §1).
export async function fetchIncidents(signal?: AbortSignal): Promise<Incident[]> {
  const r = await apiFetch("/api/incidents?status=open,in_progress,resolved", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as Incident[];
}

export type IncidentOutcome =
  | "senior_ok"
  | "team_sent"
  | "called_112"
  | "not_reached"
  | "false_alarm";

async function incidentCommand(path: string, body?: unknown): Promise<Incident> {
  const res = await apiFetch(path, {
    method: "POST",
    ...(body === undefined
      ? {}
      : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  if (!res.ok) throw await refused(res);
  return (await res.json()) as Incident;
}

/** Preiau: open → in_progress (04 §2). Someone else's incident: `already_done`. */
export function takeIncident(id: string): Promise<Incident> {
  return incidentCommand(`/api/incidents/${id}/take`);
}

/** in_progress → resolved, with an outcome and a short note (04 §2). */
export function resolveIncident(
  id: string,
  outcome: IncidentOutcome,
  note: string,
): Promise<Incident> {
  return incidentCommand(`/api/incidents/${id}/resolve`, { outcome, note });
}
