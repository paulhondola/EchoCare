import { useEffect, useState } from "react";
import { ApiError, fetchIncidents, type Incident, type IncidentStatus } from "./api";

// The dashboard gets no pushes and re-reads on a timer instead (04 §6).
const REFRESH_MS = 15_000;

const COLUMNS: { status: IncidentStatus; title: string }[] = [
  { status: "open", title: "Deschise" },
  { status: "in_progress", title: "În lucru" },
  { status: "resolved", title: "Rezolvate" },
];

const time = new Intl.DateTimeFormat("ro-RO", { dateStyle: "short", timeStyle: "short" });

function minutesSince(iso: string, now: number): string {
  const m = Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000));
  return m < 60 ? `acum ${m} min` : `acum ${Math.floor(m / 60)} h ${m % 60} min`;
}

type Load =
  | { kind: "loading" }
  | { kind: "ok"; incidents: Incident[]; at: number }
  | { kind: "error"; message: string };

export default function IncidentBoard() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const ctrl = new AbortController();
    const read = () =>
      fetchIncidents(ctrl.signal)
        .then((incidents) => {
          setLoad({ kind: "ok", incidents, at: Date.now() });
          setNow(Date.now());
        })
        .catch((e) => {
          if (ctrl.signal.aborted) return;
          const message =
            e instanceof ApiError && e.status === 404
              ? "API-ul nu oferă încă lista de incidente."
              : `Nu am putut citi incidentele (${e instanceof Error ? e.message : e}).`;
          setLoad({ kind: "error", message });
        });
    read();
    const timer = setInterval(read, REFRESH_MS);
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, []);

  if (load.kind === "loading") return <p className="notice">Se încarcă incidentele…</p>;
  if (load.kind === "error") return <p className="notice notice-error">{load.message}</p>;

  return (
    <section>
      <p className="refreshed">Actualizat la {time.format(load.at)}</p>
      <div className="board">
        {COLUMNS.map(({ status, title }) => {
          const items = load.incidents.filter((i) => i.status === status);
          return (
            <div key={status} className={`column column-${status}`}>
              <h2>
                {title} <span className="count">{items.length}</span>
              </h2>
              {items.length === 0 && <p className="empty">Niciun incident.</p>}
              {items.map((i) => (
                <article key={i.id} className="card">
                  <h3>{i.senior_full_name}</h3>
                  <p className="address">{i.senior_form_of_address}</p>
                  <p className="reason">{i.reason}</p>
                  <dl>
                    <dt>Deschis</dt>
                    <dd title={time.format(Date.parse(i.opened_at))}>{minutesSince(i.opened_at, now)}</dd>
                    {i.taken_by_name && (
                      <>
                        <dt>Preluat de</dt>
                        <dd>
                          {i.taken_by_name}
                          {i.taken_at && `, ${time.format(Date.parse(i.taken_at))}`}
                        </dd>
                      </>
                    )}
                    <dt>Transfer apel</dt>
                    <dd>{i.handover_answered ? "preluat" : "nepreluat"}</dd>
                  </dl>
                </article>
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
