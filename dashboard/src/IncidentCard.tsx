import { useState } from "react";
import {
  ApiError,
  resolveIncident,
  takeIncident,
  type Incident,
  type IncidentOutcome,
} from "./api";

export const time = new Intl.DateTimeFormat("ro-RO", { dateStyle: "short", timeStyle: "short" });

function minutesSince(iso: string, now: number): string {
  const m = Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000));
  return m < 60 ? `acum ${m} min` : `acum ${Math.floor(m / 60)} h ${m % 60} min`;
}

// The five outcomes of 04 §2, in the order a dispatcher thinks of them
const OUTCOMES: { value: IncidentOutcome; label: string }[] = [
  { value: "senior_ok", label: "Seniorul este bine" },
  { value: "team_sent", label: "Echipă trimisă" },
  { value: "called_112", label: "Apel la 112" },
  { value: "not_reached", label: "Nu a putut fi contactat" },
  { value: "false_alarm", label: "Alarmă falsă" },
];

/** What to tell the dispatcher about a refused take or resolve (04 §0, §2). */
function refusalMessage(e: unknown, action: "take" | "resolve"): string {
  if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
  switch (e.reason) {
    case "already_done":
      return action === "take"
        ? `Incidentul a fost preluat deja de ${e.takenByName ?? "un alt dispecer"}.`
        : "Incidentul a fost deja rezolvat.";
    case "wrong_state":
      return "Incidentul s-a schimbat între timp.";
    case "not_allowed":
      return "Nu aveți dreptul să faceți asta.";
    case "not_found":
      return "Incidentul nu mai există.";
    default:
      return `Nu am putut trimite (${e.message}).`;
  }
}

type Props = {
  incident: Incident;
  now: number;
  border: string;
  /** The incident as the server answered a command */
  onChanged: (incident: Incident) => void;
  /** After a refusal: the list is out of date */
  onStale: () => void;
};

export default function IncidentCard({ incident: i, now, border, onChanged, onStale }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<IncidentOutcome | "">("");
  const [note, setNote] = useState("");

  const send = (action: "take" | "resolve", command: () => Promise<Incident>) => {
    setBusy(true);
    setError(null);
    command()
      .then(onChanged)
      .catch((e: unknown) => {
        setError(refusalMessage(e, action));
        onStale();
      })
      .finally(() => setBusy(false));
  };

  const canResolve = outcome !== "" && note.trim() !== "";

  return (
    <article className={`card card-sm mb-3 border-l-4 bg-base-100 shadow-sm ${border}`}>
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
            <span
              className={`badge badge-xs badge-soft ${i.handover_answered ? "badge-success" : "badge-error"}`}
            >
              {i.handover_answered ? "preluat" : "nepreluat"}
            </span>
          </dd>
        </dl>

        {i.status === "open" && (
          <div className="card-actions mt-2">
            <button
              className="btn btn-sm btn-error"
              disabled={busy}
              onClick={() => send("take", () => takeIncident(i.id))}
            >
              Preiau
            </button>
          </div>
        )}

        {i.status === "in_progress" && (
          <form
            className="mt-2 flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (outcome === "" || !canResolve) return;
              send("resolve", () => resolveIncident(i.id, outcome, note.trim()));
            }}
          >
            <select
              className="select select-sm w-full"
              aria-label="Rezultat"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as IncidentOutcome | "")}
            >
              <option value="" disabled>
                Rezultat…
              </option>
              {OUTCOMES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <textarea
              className="textarea textarea-sm w-full"
              aria-label="Notă"
              placeholder="Ce s-a întâmplat, pe scurt"
              maxLength={1000}
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button className="btn btn-sm btn-success" disabled={busy || !canResolve}>
              Rezolvă
            </button>
          </form>
        )}

        {error && (
          <p role="alert" className="mt-1 text-sm text-error">
            {error}
          </p>
        )}
      </div>
    </article>
  );
}
