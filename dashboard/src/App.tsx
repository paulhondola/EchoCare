import { onAuthStateChanged, signOut } from "firebase/auth";
import { useEffect, useState } from "react";
import { getMe } from "./api";
import { auth } from "./firebase";
import SignIn from "./SignIn";

const NO_ACCESS = "Acest număr nu are acces la dispecerat.";
const NOT_REGISTERED = "Numărul nu este înregistrat. Contactați medicul de familie.";
const UNAVAILABLE = "Autentificarea nu este disponibilă acum. Încercați din nou.";

// What App shows, by state (auth-layer §7.1)
type View =
  | { kind: "loading" }
  | { kind: "signedOut"; notice?: string }
  | { kind: "das"; name: string }
  | { kind: "unavailable" };

export default function App() {
  const [view, setView] = useState<View>({ kind: "loading" });

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

  const exit = <button onClick={() => void signOut(auth)}>Ieșire</button>;

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
        <main>
          <p>Conectat ca {view.name}</p>
          {exit}
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
