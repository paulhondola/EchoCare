import { createContext } from "svelte";
import {
  ApiError,
  fetchEnrollments,
  fetchIncidents,
  fetchSeniors,
  fetchStaff,
  fetchSystemHealth,
} from "../../services/api";
import { poll } from "../../utils/poll.svelte";

const INCIDENTS_MS = 15_000;
const LISTS_MS = 30_000;

function describe(what: string, missing: string) {
  return (e: unknown) =>
    e instanceof ApiError && e.status === 404
      ? missing
      : `Nu am putut citi ${what} (${e instanceof Error ? e.message : String(e)}).`;
}

/**
 * What the dashboard reads, polled once for the whole session (04 §6): the sidebar's
 * counters and the pages share each read instead of asking twice.
 */
export class Live {
  incidents = poll(
    fetchIncidents,
    INCIDENTS_MS,
    describe("incidentele", "API-ul nu oferă încă lista de incidente."),
  );
  seniors = poll(
    fetchSeniors,
    LISTS_MS,
    describe("seniorii", "API-ul nu oferă încă lista de seniori."),
  );
  enrollments = poll(
    fetchEnrollments,
    LISTS_MS,
    describe("cererile", "API-ul nu oferă încă cererile de înrolare."),
  );
  staff = poll(fetchStaff, LISTS_MS, describe("lista de personal", "API-ul nu oferă încă lista."));
  health = poll(fetchSystemHealth, LISTS_MS, (e) => (e instanceof Error ? e.message : String(e)));

  /** Alerte sonore: off until the dispatcher turns it on, since browsers need a click to play sound */
  sound = $state(false);

  /** DAS employees on duty, or null until the staff list has been read */
  get onDuty(): number | null {
    const l = this.staff.load;
    return l.kind === "ok"
      ? l.data.filter((s) => s.on_duty && s.roles.includes("das")).length
      : null;
  }
}

export const [getLive, setLive] = createContext<Live>();
