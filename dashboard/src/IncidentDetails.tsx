import { useEffect, useRef, useState, type ReactNode } from "react";
import { fetchIncident, type IncidentDetail } from "./api";
import { OUTCOMES, time } from "./labels";

// Romanian labels for the stored values (05 §1); an unknown value shows as it is
const TRIGGERS: Record<string, string> = {
  campaign: "Campanie",
  watch: "Ceas",
  manual: "Cerere „Sunați-mă”",
  welcome: "Apel de bun venit",
};
const EVENTS: Record<string, string> = {
  high_pulse_at_rest: "Puls ridicat în repaus",
  inactivity: "Inactivitate",
  sos_button: "Buton SOS",
  manual_request: "„Sunați-mă”",
};
const STATES: Record<string, string> = {
  queued: "în așteptare",
  ringing: "sună",
  in_progress: "în curs",
  unanswered: "nepreluat",
  failed: "eșuat",
  completed: "încheiat",
  handed_over: "transferat la DAS",
  dropped: "întrerupt",
};
const SPEAKERS: Record<string, string> = { senior: "Senior", agent: "Agent", system: "Sistem" };
const SEVERITY_BADGE: Record<string, string> = {
  green: "badge-success",
  yellow: "badge-warning",
  red: "badge-error",
};
const SEVERITIES: Record<string, string> = { green: "verde", yellow: "galben", red: "roșu" };

const at = (iso: string | null) => (iso ? time.format(Date.parse(iso)) : "—");

/** "Str. Florilor nr. 3, bl. A2, sc. B, et. 4, ap. 17", from what was filled in */
function address(s: IncidentDetail["senior"]): string {
  const parts = [
    [s.street, s.street_number && `nr. ${s.street_number}`].filter(Boolean).join(" "),
    s.block && `bl. ${s.block}`,
    s.staircase && `sc. ${s.staircase}`,
    s.floor && `et. ${s.floor}`,
    s.apartment && `ap. ${s.apartment}`,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "Adresă necompletată";
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-base-content/60">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

type Load =
  | { kind: "loading" }
  | { kind: "ok"; incident: IncidentDetail }
  | { kind: "error"; message: string };

/** One incident in full, for handling it (UC-11 step 1, 04 §1) */
export default function IncidentDetails({ id, onClose }: { id: string; onClose: () => void }) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const dialog = useRef<HTMLDialogElement>(null);

  // A real modal: Esc, the backdrop and ✕ all close it, and focus stays inside
  useEffect(() => {
    // StrictMode runs this twice; a second showModal() throws in older browsers
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchIncident(id, ctrl.signal)
      .then((incident) => setLoad({ kind: "ok", incident }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setLoad({
          kind: "error",
          message: `Nu am putut citi incidentul (${e instanceof Error ? e.message : String(e)}).`,
        });
      });
    return () => ctrl.abort();
  }, [id]);

  return (
    <dialog ref={dialog} className="modal" onClose={onClose}>
      <div className="modal-box max-w-3xl">
        <button
          className="btn btn-circle btn-ghost btn-sm absolute top-2 right-2"
          aria-label="Închide"
          onClick={() => dialog.current?.close()}
        >
          ✕
        </button>
        {load.kind === "loading" && (
          <div role="status" className="flex items-center gap-2">
            <span className="loading loading-spinner loading-sm" />
            Se încarcă…
          </div>
        )}
        {load.kind === "error" && (
          <div role="alert" className="alert alert-error alert-soft">
            {load.message}
          </div>
        )}
        {load.kind === "ok" && <Details incident={load.incident} />}
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>Închide</button>
      </form>
    </dialog>
  );
}

function Details({ incident: i }: { incident: IncidentDetail }) {
  const s = i.senior;
  const e = i.event;
  const outcome = OUTCOMES.find((o) => o.value === i.outcome)?.label ?? i.outcome;
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h2 className="text-xl font-bold">{s.full_name}</h2>
        <p className="text-base-content/60">
          {s.form_of_address} · {i.reason}
        </p>
      </header>

      <section>
        <h3 className="mb-1 font-semibold">Senior</h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
          <Field label="Telefon">
            <a className="link" href={`tel:${s.phone_e164}`}>
              {s.phone_e164}
            </a>{" "}
            <span className="badge badge-xs badge-ghost">
              {s.phone_is_landline ? "fix" : "mobil"}
            </span>
          </Field>
          <Field label="Adresă">{address(s)}</Field>
          {s.intercom_code && <Field label="Interfon">{s.intercom_code}</Field>}
          {s.key_holder && <Field label="Chei la">{s.key_holder}</Field>}
          {s.landmark && <Field label="Reper">{s.landmark}</Field>}
        </dl>
      </section>

      <section>
        <h3 className="mb-1 font-semibold">Aparținători</h3>
        {i.caregivers.length === 0 ? (
          <p className="text-sm text-base-content/60">Niciun aparținător înregistrat.</p>
        ) : (
          <ul className="text-sm">
            {i.caregivers.map((c) => (
              <li key={c.phone_e164}>
                {c.display_name}
                {c.relation && ` (${c.relation})`} ·{" "}
                <a className="link" href={`tel:${c.phone_e164}`}>
                  {c.phone_e164}
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {e && (
        <section>
          <h3 className="mb-1 font-semibold">Eveniment</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
            <Field label="Tip">{EVENTS[e.type] ?? e.type}</Field>
            <Field label="Măsurat la">{at(e.measured_at)}</Field>
            {e.latitude !== null && e.longitude !== null && (
              <Field label="Locație">
                <a
                  className="link"
                  target="_blank"
                  rel="noreferrer"
                  href={`https://www.openstreetmap.org/?mlat=${e.latitude}&mlon=${e.longitude}#map=18/${e.latitude}/${e.longitude}`}
                >
                  {e.latitude.toFixed(5)}, {e.longitude.toFixed(5)}
                </a>
                {e.location_accuracy_m !== null && ` (±${Math.round(e.location_accuracy_m)} m)`}
                {e.located_at && `, ${at(e.located_at)}`}
              </Field>
            )}
          </dl>
        </section>
      )}

      {i.status === "resolved" && (
        <section>
          <h3 className="mb-1 font-semibold">Rezolvare</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
            <Field label="Rezultat">{outcome}</Field>
            <Field label="De">
              {i.resolved_by_name}, {at(i.resolved_at)}
            </Field>
            {i.note && <Field label="Notă">{i.note}</Field>}
          </dl>
        </section>
      )}

      <section>
        <h3 className="mb-1 font-semibold">Apeluri</h3>
        {i.calls.length === 0 && <p className="text-sm text-base-content/60">Niciun apel.</p>}
        {i.calls.map((c) => (
          <details key={c.id} className="collapse-arrow collapse mb-2 border border-base-300">
            <summary className="collapse-title flex flex-wrap items-center gap-2 text-sm">
              <span>{at(c.started_at)}</span>
              <span>
                {TRIGGERS[c.trigger] ?? c.trigger}, încercarea {c.attempt}
              </span>
              <span className="text-base-content/60">{STATES[c.state] ?? c.state}</span>
              {c.final_severity && (
                <span className={`badge badge-sm ${SEVERITY_BADGE[c.final_severity] ?? ""}`}>
                  {SEVERITIES[c.final_severity] ?? c.final_severity}
                </span>
              )}
            </summary>
            <div className="collapse-content text-sm">
              {c.summary && <p className="mb-2">{c.summary}</p>}
              {c.reports.map((r) => (
                <p key={`${r.at}-${r.source}`} className="mb-1">
                  <span className={`badge badge-xs ${SEVERITY_BADGE[r.severity] ?? ""}`}>
                    {SEVERITIES[r.severity] ?? r.severity}
                  </span>{" "}
                  {r.reason}
                  {r.quote && <q className="ml-1 italic">{r.quote}</q>}
                </p>
              ))}
              {c.turns.length > 0 && (
                <ol className="mt-2 flex flex-col gap-1">
                  {c.turns.map((t) => (
                    <li key={`${t.at}-${t.content}`}>
                      <span className="font-semibold">{SPEAKERS[t.speaker] ?? t.speaker}:</span>{" "}
                      {t.kind === "keys" ? `tasta ${t.content}` : t.content}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </details>
        ))}
      </section>
    </div>
  );
}
