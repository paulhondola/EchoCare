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

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`);
  }
}

// The dashboard asks for any status, unlike the DAS app (04 §1).
export async function fetchIncidents(signal?: AbortSignal): Promise<Incident[]> {
  const r = await apiFetch("/api/incidents?status=open,in_progress,resolved", { signal });
  if (!r.ok) throw new ApiError(r.status);
  return (await r.json()) as Incident[];
}
