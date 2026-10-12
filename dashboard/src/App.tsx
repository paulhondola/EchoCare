import { onAuthStateChanged, signOut } from "firebase/auth";
import { useEffect, useState } from "react";
import { getMe } from "./api";
import { auth } from "./firebase";
import Enrollments from "./Enrollments";
import IncidentBoard from "./IncidentBoard";
import SignIn from "./SignIn";
import Staff from "./Staff";

const NO_ACCESS = "Acest număr nu are acces la dispecerat.";
const NOT_REGISTERED = "Numărul nu este înregistrat. Contactați medicul de familie.";
const UNAVAILABLE = "Autentificarea nu este disponibilă acum. Încercați din nou.";

// The DAS screens, picked in the header
const SCREENS = [
  { key: "incidents", label: "Incidente" },
  { key: "enrollments", label: "Cereri de înrolare" },
  { key: "staff", label: "Personal" },
] as const;
type Screen = (typeof SCREENS)[number]["key"];

// What App shows, by state (auth-layer §7.1)
type View =
  | { kind: "loading" }
  | { kind: "signedOut"; notice?: string }
  | { kind: "das"; name: string }
  | { kind: "unavailable" };

export default function App() {
  const [view, setView] = useState<View>({ kind: "loading" });
  // No router yet (AGENTS.md): two screens, picked in the header
  const [screen, setScreen] = useState<Screen>("incidents");

  useEffect(
    () =>
      onAuthStateChanged(auth, (user) => {
        if (!user) {
          // Keeps a notice set just before signing out.
          setView((v) => (v.kind === "signedOut" ? v : { kind: "signedOut" }));
          return;
        }
        setView({ kind: "loading" });
        const refuse = (notice: string) => {
          setView({ kind: "signedOut", notice });
          void signOut(auth);
        };
        getMe()
          .then((me) => {
            if (me === "not_registered") refuse(NOT_REGISTERED);
            else if (me === "not_signed_in") return; // apiFetch has already signed out
            else if (typeof me === "string") setView({ kind: "unavailable" });
            else if (me.grants.some((g) => g.role === "das"))
              setView({ kind: "das", name: me.display_name });
            else refuse(NO_ACCESS);
          })
          .catch((err: unknown) => {
            console.error(err);
            setView({ kind: "unavailable" });
          });
      }),
    [],
  );

  const exit = (
    <button className="btn btn-sm" onClick={() => void signOut(auth)}>
      Ieșire
    </button>
  );

  switch (view.kind) {
    case "loading":
      return <main aria-busy="true" />;
    case "signedOut":
      return (
        <main>
          <SignIn notice={view.notice} />
        </main>
      );
    case "das":
      return (
        <main className="mx-auto max-w-7xl p-4">
          <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-base-300 pb-2">
            <h1 className="text-2xl font-bold">Sentinela DAS</h1>
            <nav role="tablist" className="tabs tabs-box tabs-sm">
              {SCREENS.map(({ key, label }) => (
                <button
                  key={key}
                  role="tab"
                  className={`tab ${screen === key ? "tab-active" : ""}`}
                  onClick={() => setScreen(key)}
                >
                  {label}
                </button>
              ))}
            </nav>
            <span className="flex items-center gap-2 text-sm text-base-content/60">
              Conectat ca {view.name}
              {exit}
            </span>
          </header>
          {screen === "incidents" && <IncidentBoard />}
          {screen === "enrollments" && <Enrollments />}
          {screen === "staff" && <Staff />}
        </main>
      );
    case "unavailable":
      return (
        <main>
          <p role="alert">{UNAVAILABLE}</p>
          {exit}
        </main>
      );
  }
}
