import { createContext } from "svelte";
import {
  ApiError,
  fetchEnrollments,
  fetchIncidents,
  fetchLiveCalls,
  fetchSeniors,
  fetchStaff,
  fetchSystemHealth,
  type Incident,
} from "../../services/api";
import { columns, type DossierTab } from "../../utils/incidents";
import { poll } from "../../utils/poll.svelte";

const INCIDENTS_MS = 15_000;
const LISTS_MS = 30_000;
// The whole registry, mostly for a sidebar counter: the Seniors page reads it again on opening
const SENIORS_MS = 120_000;
// The live strip and the map's rings: a call shows within 2 s of ringing (design 2026-11-14 §4)
const LIVE_MS = 2_000;

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
    SENIORS_MS,
    describe("seniorii", "API-ul nu oferă încă lista de seniori."),
  );
  enrollments = poll(
    fetchEnrollments,
    LISTS_MS,
    describe("cererile", "API-ul nu oferă încă cererile de înrolare."),
  );
  liveCalls = poll(
    fetchLiveCalls,
    LIVE_MS,
    describe("apelurile în curs", "API-ul nu oferă încă apelurile în curs."),
  );
  staff = poll(fetchStaff, LISTS_MS, describe("lista de personal", "API-ul nu oferă încă lista."));
  health = poll(fetchSystemHealth, LISTS_MS, (e) => (e instanceof Error ? e.message : String(e)));

  /** Open incidents, the longest wait first, or null until the first read */
  open = $derived(
    this.incidents.load.kind === "ok" ? columns(this.incidents.load.data).open : null,
  );

  /** The incident dossier on screen, over whichever page is open */
  dossier = $state<{ id: string; tab: DossierTab } | null>(null);

  /** The live call open in its view, by call id */
  liveCall = $state<string | null>(null);

  /** Alerte sonore: off until the dispatcher turns it on, since browsers need a click to play sound */
  sound = $state(false);

  /** DAS employees on duty, or null until the staff list has been read */
  get onDuty(): number | null {
    const l = this.staff.load;
    return l.kind === "ok"
      ? l.data.filter((s) => s.on_duty && s.roles.includes("das")).length
      : null;
  }

  /** A command's answer, applied at once instead of waiting for the next read */
  incidentChanged = (i: Incident) => {
    this.incidents.update((list) => list.map((x) => (x.id === i.id ? i : x)));
  };
}

export const [getLive, setLive] = createContext<Live>();
