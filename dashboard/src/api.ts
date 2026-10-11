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
