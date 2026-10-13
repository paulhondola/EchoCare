import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  acceptSenior,
  ApiError,
  fetchEnrollments,
  fetchSenior,
  type SeniorSummary,
  type SeniorView,
} from "./api";
import { address, time } from "./labels";

// Re-read like the incident board: the dashboard gets no pushes (04 §6)
const REFRESH_MS = 15_000;

/** What to tell the dispatcher about a refused accept (04 §0, §2). */
function refusalMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
  switch (e.reason) {
    case "already_done":
      return "Cererea a fost deja acceptată.";
    case "wrong_state":
      return "Cererea s-a schimbat între timp.";
    case "not_found":
      return "Cererea nu mai există.";
    case "not_allowed":
      return "Nu aveți dreptul să faceți asta.";
    default:
      return `Nu am putut trimite (${e.message}).`;
  }
}

type Load =
  | { kind: "loading" }
  // error: the last read failed; the list keeps the last good one
  | { kind: "ok"; seniors: SeniorSummary[]; at: number; error?: string }
  | { kind: "error"; message: string };

/** „Cereri de înrolare": submitted registrations to review and accept (UC-04 step 1). */
export default function Enrollments() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [accepted, setAccepted] = useState<string | null>(null);
  // Re-reads at once, after a refused accept
  const reload = useRef(() => {});

  useEffect(() => {
    const ctrl = new AbortController();
    const read = () =>
      fetchEnrollments(ctrl.signal)
        .then((seniors) => setLoad({ kind: "ok", seniors, at: Date.now() }))
        .catch((e) => {
          if (ctrl.signal.aborted) return;
          const message =
            e instanceof ApiError && e.status === 404
              ? "API-ul nu oferă încă cererile de înrolare."
              : `Nu am putut citi cererile (${e instanceof Error ? e.message : e}).`;
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
        Se încarcă cererile…
      </div>
    );
  if (load.kind === "error")
    return (
      <div role="alert" className="alert alert-error alert-soft">
        {load.message}
      </div>
    );

  return (
    <section className="max-w-3xl">
      <h2 className="mb-1 text-lg font-semibold">
        Cereri de înrolare <span className="badge badge-sm">{load.seniors.length}</span>
      </h2>
      <p className="mb-3 text-sm text-base-content/60">Actualizat la {time.format(load.at)}</p>
      {load.error && (
        <div role="alert" className="alert alert-warning alert-soft mb-3">
          {load.error}
        </div>
      )}
      {accepted && (
        <div role="status" className="alert alert-success alert-soft mb-3">
          {accepted}
        </div>
      )}
      {load.seniors.length === 0 && (
        <p className="text-sm text-base-content/60">Nicio cerere în așteptare.</p>
      )}
      {load.seniors.map((s) => (
        <EnrollmentCard
          key={s.id}
          senior={s}
          onAccepted={() => {
            setAccepted(`Acceptat: ${s.full_name}.`);
            setLoad((l) =>
              l.kind === "ok" ? { ...l, seniors: l.seniors.filter((x) => x.id !== s.id) } : l,
            );
          }}
          onStale={() => reload.current()}
        />
      ))}
    </section>
  );
}

type Details =
  | { kind: "closed" }
  | { kind: "loading" }
  | { kind: "ok"; senior: SeniorView }
  | { kind: "error"; message: string };

function EnrollmentCard({
  senior: s,
  onAccepted,
  onStale,
}: {
  senior: SeniorSummary;
  onAccepted: () => void;
  onStale: () => void;
}) {
  const [details, setDetails] = useState<Details>({ kind: "closed" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = () => {
    if (details.kind !== "closed") return setDetails({ kind: "closed" });
    setDetails({ kind: "loading" });
    fetchSenior(s.id)
      .then((senior) => setDetails({ kind: "ok", senior }))
      .catch((e: unknown) =>
        setDetails({
          kind: "error",
          message: `Nu am putut citi cererea (${e instanceof Error ? e.message : String(e)}).`,
        }),
      );
  };

  const accept = () => {
    setBusy(true);
    setError(null);
    acceptSenior(s.id)
      .then(onAccepted)
      .catch((e: unknown) => {
        setError(refusalMessage(e));
        onStale();
      })
      .finally(() => setBusy(false));
  };

  return (
    <article className="card card-sm mb-3 border-l-4 border-info bg-base-100 shadow-sm">
      <div className="card-body gap-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="card-title text-base">{s.full_name}</h3>
            <p className="text-sm text-base-content/60">{s.form_of_address}</p>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-ghost btn-sm" onClick={toggle}>
              {details.kind === "closed" ? "Vezi cererea" : "Ascunde"}
            </button>
            <button className="btn btn-success btn-sm" disabled={busy} onClick={accept}>
              Acceptă
            </button>
          </div>
        </div>
        {details.kind === "loading" && (
          <div role="status" className="flex items-center gap-2 text-sm">
            <span className="loading loading-spinner loading-xs" />
            Se încarcă…
          </div>
        )}
        {details.kind === "error" && (
          <p role="alert" className="text-sm text-error">
            {details.message}
          </p>
        )}
        {details.kind === "ok" && <Registration senior={details.senior} />}
        {error && (
          <p role="alert" className="mt-1 text-sm text-error">
            {error}
          </p>
        )}
      </div>
    </article>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-base-content/60">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

/** The registration as the medic filled it in (UC-01), for review before accepting */
function Registration({ senior: s }: { senior: SeniorView }) {
  return (
    <div className="mt-2 flex flex-col gap-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
        <Field label="Telefon">
          {s.phone_e164}{" "}
          <span className="badge badge-xs badge-ghost">
            {s.phone_is_landline ? "fix" : "mobil"}
          </span>
        </Field>
        <Field label="Adresă">{address(s)}</Field>
        {s.intercom_code && <Field label="Interfon">{s.intercom_code}</Field>}
        {s.key_holder && <Field label="Are cheie">{s.key_holder}</Field>}
        {s.landmark && <Field label="Reper">{s.landmark}</Field>}
        {s.call_window && <Field label="Interval de apel">{s.call_window}</Field>}
      </dl>
      <div>
        <h4 className="mb-1 text-sm font-semibold">Aparținători</h4>
        {s.caregivers.length === 0 ? (
          <p className="text-sm text-base-content/60">Niciun aparținător.</p>
        ) : (
          <ul className="text-sm">
            {s.caregivers.map((c) => (
              <li key={c.user_id}>
                {c.display_name}
                {c.relation && ` (${c.relation})`}, {c.phone_e164}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
