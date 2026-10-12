import { useEffect, useRef, useState } from "react";
import { ApiError, fetchIncidents, type Incident, type IncidentStatus } from "./api";
import IncidentCard from "./IncidentCard";
import { time } from "./labels";

// The dashboard gets no pushes and re-reads on a timer instead (04 §6).
const REFRESH_MS = 15_000;

// Full class names, so Tailwind finds them in the source
const COLUMNS: { status: IncidentStatus; title: string; border: string; badge: string }[] = [
  { status: "open", title: "Deschise", border: "border-error", badge: "badge-error" },
  { status: "in_progress", title: "În lucru", border: "border-warning", badge: "badge-warning" },
  { status: "resolved", title: "Rezolvate", border: "border-success", badge: "badge-success" },
];

type Load =
  | { kind: "loading" }
  // error: the last read failed; the board keeps the last good list
  | { kind: "ok"; incidents: Incident[]; at: number; error?: string }
  | { kind: "error"; message: string };

export default function IncidentBoard() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [now, setNow] = useState(Date.now());
  // Re-reads at once, for a card whose command was refused
  const reload = useRef(() => {});

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
          setLoad((l) => (l.kind === "ok" ? { ...l, error: message } : { kind: "error", message }));
        });
    // read() catches its own errors
    void read();
    reload.current = () => void read();
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
      {load.error && (
        <div role="alert" className="alert alert-warning alert-soft mb-3">
          {load.error}
        </div>
      )}
      <p className="mb-3 text-sm text-base-content/60">Actualizat la {time.format(load.at)}</p>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] items-start gap-4">
        {COLUMNS.map(({ status, title, border, badge }) => {
          const items = load.incidents.filter((i) => i.status === status);
          return (
            <div key={status}>
              <h2
                className={`mb-3 flex items-center gap-2 border-b-4 pb-1.5 font-semibold ${border}`}
              >
                {title} <span className={`badge badge-sm ${badge}`}>{items.length}</span>
              </h2>
              {items.length === 0 && (
                <p className="text-sm text-base-content/60">Niciun incident.</p>
              )}
              {items.map((i) => (
                <IncidentCard
                  key={i.id}
                  incident={i}
                  now={now}
                  border={border}
                  onChanged={(changed) =>
                    setLoad((l) =>
                      l.kind === "ok"
                        ? {
                            ...l,
                            incidents: l.incidents.map((x) => (x.id === changed.id ? changed : x)),
                          }
                        : l,
                    )
                  }
                  onStale={() => reload.current()}
                />
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
