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

/** GET /api/profile (auth-layer §3.3). */
export type Me = {
  display_name: string;
  phone_e164: string;
  grants: { role: string; senior_id: string | null }[];
};

/** The body on a 200, otherwise the refusal's reason (auth-layer §3.2). */
export async function getMe(): Promise<Me | string> {
  const res = await apiFetch("/api/profile");
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

// GET /seniors/{id}/summary (04 §1, design §5 B). Mirrors backend/app/seniors/schemas.py.
export interface SummaryContent {
  follow_ups: { topic: string; question: string; call_id: string; quote: string }[];
  how_to_talk: string[];
  trends: {
    note: string;
    direction: "worse" | "better" | "steady";
    evidence: { call_id: string; quote: string }[];
  }[];
  narrative: string;
}

export interface SummaryVersion {
  content: SummaryContent;
  call_id: string;
  created_at: string;
}

// GET /incidents/{id} (04 §1), DAS only. Mirrors backend/app/incident_view.py.
export interface IncidentDetail {
  id: string;
  status: IncidentStatus;
  reason: string;
  opened_at: string;
  taken_by_name: string | null;
  taken_at: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  outcome: IncidentOutcome | null;
  note: string | null;
  handover_answered: boolean;
  senior: {
    id: string;
    full_name: string;
    form_of_address: string;
    phone_e164: string;
    phone_is_landline: boolean;
    street: string | null;
    street_number: string | null;
    block: string | null;
    staircase: string | null;
    floor: string | null;
    apartment: string | null;
    intercom_code: string | null;
    key_holder: string | null;
    landmark: string | null;
  };
  caregivers: { display_name: string; phone_e164: string; relation: string | null }[];
  event: {
    type: string;
    measured_at: string;
    latitude: number | null;
    longitude: number | null;
    location_accuracy_m: number | null;
    located_at: string | null;
    // A fall found by the home node: where, and the sweep from 0° to 180° in metres
    // (P24, 08-ecou.md §3.3). Absent from an older API copy, null for other events.
    source?: string | null;
    object_angle_deg?: number | null;
    object_distance_m?: number | null;
    scan?: number[] | null;
  } | null;
  calls: {
    id: string;
    trigger: string;
    attempt: number;
    state: string;
    started_at: string | null;
    ended_at: string | null;
    final_severity: string | null;
    final_certainty: string | null;
    reason: string | null;
    summary: string | null;
    handover_answered: boolean | null;
    reports: {
      source: string;
      severity: string;
      certainty: string | null;
      reason: string;
      quote: string | null;
      at: string;
    }[];
    turns: { speaker: string; kind: string; content: string; at: string }[];
  }[];
  summary?: SummaryVersion | null;
  // The home node's latest reading; absent from an older API copy (04 §1, P20)
  room?: RoomReading | null;
}

/** The home node's latest reading, on the senior and the incident (04 §1, P20) */
export type RoomReading = {
  state: string; // ok | offline
  temperature: number;
  humidity: number | null;
  reading_at: string;
  last_motion_at: string | null;
  room_state: string; // ok | cold_soon | cold | hot_soon | hot
};

/** One call as the incident page and the transcript show it */
export type IncidentCall = IncidentDetail["calls"][number];

// GET /seniors/{id}/calls (04 §1): newest first, queued ones included.
// Mirrors CallSummary in backend/app/calls/schemas.py.
export interface CallSummary {
  id: string;
  trigger: string;
  state: string;
  due_at: string;
  started_at: string | null;
  ended_at: string | null;
  final_severity: string | null;
  final_certainty: string | null;
  reason: string | null;
  summary: string | null;
}

export async function fetchCalls(seniorId: string, signal?: AbortSignal): Promise<CallSummary[]> {
  const r = await apiFetch(`/api/seniors/${seniorId}/calls`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as CallSummary[];
}

// GET /calls/{id}/transcript (04 §1): the call as on the incident page, every turn in order
export async function fetchTranscript(id: string, signal?: AbortSignal): Promise<TranscriptCall> {
  const r = await apiFetch(`/api/calls/${id}/transcript`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as TranscriptCall;
}

/** The transcript's call, plus what the model heard for each question (05 §2) */
export type TranscriptCall = IncidentCall & {
  answers: { field: string; value: string; clear: boolean; quote: string; at: string }[];
};

// GET /calls/live (04 §1, design 2026-11-14 §4), DAS only: the calls ringing or talking now
export interface LiveCall {
  id: string;
  senior_id: string;
  senior_name: string;
  trigger: string;
  state: string;
  starting_severity: "green" | "yellow" | "red";
  started_at: string | null;
  due_at: string;
}

export async function fetchLiveCalls(signal?: AbortSignal): Promise<LiveCall[]> {
  const r = await apiFetch("/api/calls/live", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as LiveCall[];
}

// 204 when the senior has no summary yet
export async function fetchSummary(
  seniorId: string,
  signal?: AbortSignal,
): Promise<SummaryVersion | null> {
  const r = await apiFetch(`/api/seniors/${seniorId}/summary`, { signal });
  if (r.status === 204) return null;
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SummaryVersion;
}

export type MedicalItem = {
  condition: string;
  question: string;
  worrying: string;
  evidence: string;
  included: boolean;
};

// For DAS, items and pdf_url are null unless state is "confirmed"
export type MedicalRecord = {
  state: string;
  uploaded_at: string;
  analyzed_at: string | null;
  confirmed_at: string | null;
  items: MedicalItem[] | null;
  pdf_url: string | null;
};

// 204 when the senior has no medical record
export async function fetchMedicalRecord(
  seniorId: string,
  signal?: AbortSignal,
): Promise<MedicalRecord | null> {
  const r = await apiFetch(`/api/seniors/${seniorId}/medical-record`, { signal });
  if (r.status === 204) return null;
  if (!r.ok) throw await refused(r);
  return (await r.json()) as MedicalRecord;
}

/** The address fields every senior view carries (G13) */
export type SeniorAddress = Pick<
  IncidentDetail["senior"],
  "street" | "street_number" | "block" | "staircase" | "floor" | "apartment"
>;

export async function fetchIncident(id: string, signal?: AbortSignal): Promise<IncidentDetail> {
  const r = await apiFetch(`/api/incidents/${id}`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as IncidentDetail;
}

export type StaffRole = "das" | "medic";

// One row of GET /staff (04 §1), DAS only. Mirrors StaffListing in backend/app/main.py.
export interface StaffMember {
  id: string;
  display_name: string;
  phone_e164: string;
  practice: string | null;
  roles: StaffRole[];
  on_duty: boolean;
}

export async function fetchStaff(signal?: AbortSignal): Promise<StaffMember[]> {
  const r = await apiFetch("/api/staff", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as StaffMember[];
}

/** POST /staff (auth-layer §3.4). A number that already has the role: 409 `already_done`. */
export async function grantStaff(grant: {
  display_name: string;
  phone: string;
  role: StaffRole;
  practice?: string;
}): Promise<void> {
  const r = await apiFetch("/api/staff", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(grant),
  });
  if (!r.ok) throw await refused(r);
}

// PUT /staff/on-duty (04 §2): this DAS employee takes the hand-overs, everyone else stops (P10)
export async function setOnDuty(userId: string): Promise<void> {
  const r = await apiFetch("/api/staff/on-duty", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!r.ok) throw await refused(r);
}

// One row of GET /seniors and GET /enrollments (04 §1). Mirrors SeniorSummary in
// backend/app/seniors/service.py. The state stays a string: the server adds states later.
export interface SeniorSummary {
  id: string;
  full_name: string;
  form_of_address: string;
  phone_e164: string;
  phone_is_landline: boolean;
  enrollment_state: string;
  // The senior's current code (04 §1); optional so an older API still type-checks
  code?: "green" | "yellow" | "red" | null;
  reason?: string | null;
  since?: string | null;
  // The home node, for every role; null without one (04 §1, P20)
  home_node_state?: string | null;
  room_temperature?: number | null;
  // An approximate point on her street, for the map; null off the street table (design 2026-11-14 §7)
  latitude?: number | null;
  longitude?: number | null;
}

// GET /seniors/{id} (04 §1). Mirrors SeniorView in backend/app/seniors/service.py.
export type SeniorView = IncidentDetail["senior"] & {
  call_window: string | null;
  enrollment_state: string;
  code?: "green" | "yellow" | "red" | null;
  reason?: string | null;
  since?: string | null;
  // True while one of her calls rings or is live (UC-12); only GET /seniors/{id} sets it
  call_in_progress?: boolean | null;
  watch_state?: string | null;
  room?: RoomReading | null;
  last_pulse?: number | null;
  medic: { display_name: string; practice: string | null };
  caregivers: {
    user_id: string;
    display_name: string;
    phone_e164: string;
    relation: string | null;
  }[];
};

/** Monitorizare seniori: for DAS every senior past `draft`, by name (04 §1). */
export async function fetchSeniors(signal?: AbortSignal): Promise<SeniorSummary[]> {
  const r = await apiFetch("/api/seniors?role=das", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SeniorSummary[];
}

/** Cereri de înrolare: the seniors in `submitted`, oldest first (04 §1), DAS only. */
export async function fetchEnrollments(signal?: AbortSignal): Promise<SeniorSummary[]> {
  const r = await apiFetch("/api/enrollments", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SeniorSummary[];
}

export async function fetchSenior(id: string, signal?: AbortSignal): Promise<SeniorView> {
  const r = await apiFetch(`/api/seniors/${id}`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SeniorView;
}

// GET /seniors/{id}/watch (04 §1, ADR-006). Mirrors WatchView in backend/app/seniors/schemas.py.
// The state stays a string: the server may add states later.
export interface WatchView {
  state: string;
  last_check_in_at: string;
  battery: number | null;
  worn: boolean | null;
  last_pulse: number | null;
  resting_pulse: number | null;
  steps_today: number | null;
  minutes_without_steps: number | null;
}

// One 5-minute bucket of GET /seniors/{id}/watch/readings (04 §1, ADR-006).
// Mirrors WatchReadingView in backend/app/seniors/schemas.py.
export interface WatchReading {
  at: string;
  pulse: number | null;
  battery: number | null;
  worn: boolean | null;
  steps_today: number | null;
}

/** The watch's latest check-in; null before the first one (204). */
export async function fetchWatch(id: string, signal?: AbortSignal): Promise<WatchView | null> {
  const r = await apiFetch(`/api/seniors/${id}/watch`, { signal });
  if (r.status === 204) return null;
  if (!r.ok) throw await refused(r);
  return (await r.json()) as WatchView;
}

/** The last 24 hours of check-ins, oldest first. */
export async function fetchWatchReadings(
  id: string,
  signal?: AbortSignal,
): Promise<WatchReading[]> {
  const r = await apiFetch(`/api/seniors/${id}/watch/readings`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as WatchReading[];
}

/** Acceptă: submitted → accepted (04 §2). A second accept: `already_done`. */
export async function acceptSenior(id: string): Promise<SeniorSummary> {
  const r = await apiFetch(`/api/seniors/${id}/accept`, { method: "POST" });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SeniorSummary;
}

/** Șterge toate datele: the senior and everything about them (04 §2, design 2026-11-14).
 * Refused with `call_live` or `incident_open`; a repeat is `not_found`, shown as erased. */
export async function eraseSenior(id: string): Promise<void> {
  const r = await apiFetch(`/api/seniors/${id}/erase`, { method: "POST" });
  if (!r.ok) throw await refused(r);
}

/** Exportă datele: the senior and everything about them as JSON (04 §1, design 2026-11-14). */
export async function exportSenior(
  id: string,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const r = await apiFetch(`/api/seniors/${id}/export`, { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as Record<string, unknown>;
}

export interface DatabaseHealth {
  status: "ok" | "unreachable";
  latency_ms: number | null;
}

export interface SystemHealth {
  status: "ok" | "degraded";
  env: string;
  database: DatabaseHealth;
  timestamp: string;
}

/** Dashboard system health telemetry (04 §1), DAS only. */
export async function fetchSystemHealth(signal?: AbortSignal): Promise<SystemHealth> {
  const r = await apiFetch("/api/system/health", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as SystemHealth;
}

export type CampaignKind = "heat" | "cold";
export type WarningLevel = "yellow" | "red";

// One row of GET /campaigns (04 §1), DAS only. Mirrors CampaignSummary in the backend.
// `total` counts every queued call, so it can exceed the buckets: a call that is ringing or in
// progress is only in `total`.
export interface Campaign {
  id: string;
  kind: CampaignKind;
  level: WarningLevel;
  started_by_name: string;
  started_at: string;
  warning_until: string;
  active: boolean;
  progress: {
    total: number;
    waiting: number;
    green: number;
    yellow: number;
    red: number;
    canceled: number;
  };
}

/** Newest first (04 §1). */
export async function fetchCampaigns(signal?: AbortSignal): Promise<Campaign[]> {
  const r = await apiFetch("/api/campaigns", { signal });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as Campaign[];
}

/** POST /campaigns (04 §2): 201 for a new campaign, 200 for the one already running. */
export async function startCampaign(
  kind: CampaignKind,
  level: WarningLevel,
): Promise<{ campaign: Campaign; created: boolean }> {
  const r = await apiFetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, level }),
  });
  if (!r.ok) throw await refused(r);
  return { campaign: (await r.json()) as Campaign, created: r.status === 201 };
}

/** Încheie: ends the warning and cancels the calls nobody answered (04 §2). */
export async function endCampaign(id: string): Promise<Campaign> {
  const r = await apiFetch(`/api/campaigns/${id}/end`, { method: "POST" });
  if (!r.ok) throw await refused(r);
  return (await r.json()) as Campaign;
}
