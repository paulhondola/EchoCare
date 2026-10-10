const API_URL = import.meta.env.VITE_API_URL;

export type IncidentStatus = "open" | "in_progress" | "resolved";

// One row of GET /incidents (04 §1). Names follow the incidents and seniors tables (05 §1);
// the backend does not serve this endpoint yet, so keep both in step when it lands.
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
  const r = await fetch(`${API_URL}/api/incidents?status=open,in_progress,resolved`, { signal });
  if (!r.ok) throw new ApiError(r.status);
  return r.json();
}
