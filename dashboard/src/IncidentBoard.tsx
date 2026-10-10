import { useEffect, useState } from "react";
import { ApiError, fetchIncidents, type Incident, type IncidentStatus } from "./api";

// The dashboard gets no pushes and re-reads on a timer instead (04 §6).
const REFRESH_MS = 15_000;

// Full class names, so Tailwind finds them in the source
const COLUMNS: { status: IncidentStatus; title: string; border: string; badge: string }[] = [
  { status: "open", title: "Deschise", border: "border-error", badge: "badge-error" },
  { status: "in_progress", title: "În lucru", border: "border-warning", badge: "badge-warning" },
  { status: "resolved", title: "Rezolvate", border: "border-success", badge: "badge-success" },
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

  if (load.kind === "loading")
    return (
      <div role="status" className="alert">
        <span className="loading loading-spinner loading-sm" />
        Se încarcă incidentele…
      </div>
    );
  if (load.kind === "error")
    return (
      <div role="alert" className="alert alert-error alert-soft">
        {load.message}
      </div>
    );

  return (
    <section>
      <p className="mb-3 text-sm text-base-content/60">Actualizat la {time.format(load.at)}</p>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] items-start gap-4">
        {COLUMNS.map(({ status, title, border, badge }) => {
          const items = load.incidents.filter((i) => i.status === status);
          return (
            <div key={status}>
              <h2 className={`mb-3 flex items-center gap-2 border-b-4 pb-1.5 font-semibold ${border}`}>
                {title} <span className={`badge badge-sm ${badge}`}>{items.length}</span>
              </h2>
              {items.length === 0 && <p className="text-sm text-base-content/60">Niciun incident.</p>}
              {items.map((i) => (
                <article key={i.id} className={`card card-sm mb-3 border-l-4 bg-base-100 shadow-sm ${border}`}>
                  <div className="card-body gap-1">
                    <h3 className="card-title text-base">{i.senior_full_name}</h3>
                    <p className="text-sm text-base-content/60">{i.senior_form_of_address}</p>
                    <p>{i.reason}</p>
                    <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
                      <dt className="text-base-content/60">Deschis</dt>
                      <dd title={time.format(Date.parse(i.opened_at))}>{minutesSince(i.opened_at, now)}</dd>
                      {i.taken_by_name && (
                        <>
                          <dt className="text-base-content/60">Preluat de</dt>
                          <dd>
                            {i.taken_by_name}
                            {i.taken_at && `, ${time.format(Date.parse(i.taken_at))}`}
                          </dd>
                        </>
                      )}
                      <dt className="text-base-content/60">Transfer apel</dt>
                      <dd>
                        <span className={`badge badge-xs badge-soft ${i.handover_answered ? "badge-success" : "badge-error"}`}>
                          {i.handover_answered ? "preluat" : "nepreluat"}
                        </span>
                      </dd>
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
