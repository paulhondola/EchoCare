import { type FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  fetchStaff,
  grantStaff,
  type StaffMember,
  type StaffRole,
} from "../../services/api";
import { toE164 } from "../../utils/phone";

const ROLE_LABELS: Record<StaffRole, string> = { das: "Dispecer DAS", medic: "Medic" };

/** What to tell the dispatcher about a refused grant (04 §0, auth-layer §3.4). */
function refusalMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
  if (e.reason === "already_done") return "Numărul are deja acest rol.";
  if (e.reason === "not_allowed") return "Nu aveți dreptul să adăugați personal.";
  // FastAPI's own 422 has no reason: the number is not a mobile, or a field is empty
  if (e.status === 422)
    return "Date invalide. Numărul trebuie să fie de mobil, iar un medic are nevoie de cabinet.";
  return `Nu am putut trimite (${e.message}).`;
}

/** „Personal": DAS employees and medics, and adding one (UC-14). */
export default function Staff() {
  const [staff, setStaff] = useState<StaffMember[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<StaffRole>("medic");
  const [practice, setPractice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  const read = (signal?: AbortSignal) =>
    fetchStaff(signal)
      .then((s) => {
        setStaff(s);
        setLoadError(null);
      })
      .catch((e) => {
        if (signal?.aborted) return;
        setLoadError(`Nu am putut citi lista (${e instanceof Error ? e.message : e}).`);
      });

  useEffect(() => {
    const ctrl = new AbortController();
    void read(ctrl.signal);
    return () => ctrl.abort();
  }, []);

  const canAdd =
    name.trim() !== "" && phone.trim() !== "" && (role === "das" || practice.trim() !== "");

  function add(e: FormEvent) {
    e.preventDefault();
    if (!canAdd) return;
    setBusy(true);
    setError(null);
    setAdded(null);
    grantStaff({
      display_name: name.trim(),
      phone: toE164(phone),
      role,
      ...(role === "medic" ? { practice: practice.trim() } : {}),
    })
      .then(() => {
        setAdded(`Adăugat: ${name.trim()}, ${ROLE_LABELS[role].toLowerCase()}.`);
        setName("");
        setPhone("");
        setPractice("");
        void read();
      })
      .catch((err: unknown) => setError(refusalMessage(err)))
      .finally(() => setBusy(false));
  }

  return (
    <section className="grid items-start gap-6 lg:grid-cols-[1fr_320px]">
      <div>
        <h2 className="mb-3 text-lg font-semibold">Personal</h2>
        {loadError && (
          <div role="alert" className="alert alert-error alert-soft mb-3">
            {loadError}
          </div>
        )}
        {staff === null && !loadError && (
          <div role="status" className="alert">
            <span className="loading loading-spinner loading-sm" />
            Se încarcă lista…
          </div>
        )}
        {staff !== null && (
          <div className="overflow-x-auto">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Nume</th>
                  <th>Telefon</th>
                  <th>Rol</th>
                  <th>Cabinet</th>
                </tr>
              </thead>
              <tbody>
                {staff.map((s) => (
                  <tr key={s.id}>
                    <td>
                      {s.display_name}
                      {s.on_duty && (
                        <span className="badge badge-xs badge-success ml-2">de serviciu</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap">{s.phone_e164}</td>
                    <td>
                      {s.roles.map((r) => (
                        <span key={r} className="badge badge-sm badge-soft mr-1">
                          {ROLE_LABELS[r] ?? r}
                        </span>
                      ))}
                    </td>
                    <td>{s.practice ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <form className="card card-sm bg-base-100 shadow-sm" onSubmit={add}>
        <div className="card-body gap-2">
          <h3 className="card-title text-base">Adaugă</h3>
          <select
            className="select select-sm w-full"
            aria-label="Rol"
            value={role}
            onChange={(e) => setRole(e.target.value as StaffRole)}
          >
            <option value="medic">{ROLE_LABELS.medic}</option>
            <option value="das">{ROLE_LABELS.das}</option>
          </select>
          <input
            className="input input-sm w-full"
            aria-label="Nume"
            placeholder="Nume"
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="input input-sm w-full"
            aria-label="Telefon mobil"
            placeholder="Telefon mobil, ex. 0722 123 456"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          {role === "medic" && (
            <input
              className="input input-sm w-full"
              aria-label="Cabinet"
              placeholder="Cabinet"
              maxLength={200}
              value={practice}
              onChange={(e) => setPractice(e.target.value)}
            />
          )}
          <button className="btn btn-sm btn-primary" disabled={busy || !canAdd}>
            Adaugă
          </button>
          {error && (
            <p role="alert" className="text-sm text-error">
              {error}
            </p>
          )}
          {added && (
            <p role="status" className="text-sm text-success">
              {added}
            </p>
          )}
        </div>
      </form>
    </section>
  );
}
