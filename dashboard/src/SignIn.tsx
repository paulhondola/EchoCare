import { FirebaseError } from "firebase/app";
import { type ConfirmationResult, RecaptchaVerifier, signInWithPhoneNumber } from "firebase/auth";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { auth } from "./firebase";
import { toE164 } from "./phone";

// auth-layer §7.1. Anything else falls back to the "unavailable" text of §3.2.
const ERRORS: Record<string, string> = {
  "auth/invalid-verification-code": "Cod greșit.",
  "auth/invalid-phone-number": "Număr de telefon invalid.",
  "auth/too-many-requests": "Prea multe încercări. Încercați mai târziu.",
};
const UNAVAILABLE = "Autentificarea nu este disponibilă acum. Încercați din nou.";

function errorText(err: unknown): string {
  if (err instanceof FirebaseError && err.code in ERRORS) return ERRORS[err.code];
  console.error(err);
  return UNAVAILABLE;
}

/**
 * Phone step, then code step. On success, App takes over through onAuthStateChanged.
 * `notice` is why App just signed the person out; the next attempt clears it.
 */
export default function SignIn({ notice }: { notice?: string }) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmationResult | null>(null);
  const [error, setError] = useState<string | null>(notice ?? null);
  const [busy, setBusy] = useState(false);
  const recaptchaEl = useRef<HTMLDivElement>(null);
  const verifier = useRef<RecaptchaVerifier | null>(null);

  const clearVerifier = () => {
    verifier.current?.clear();
    verifier.current = null;
  };
  useEffect(() => clearVerifier, []);

  async function sendCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Created on press, not in an effect: StrictMode would render it twice into one element (auth-layer §7.1).
      verifier.current ??= new RecaptchaVerifier(auth, recaptchaEl.current!, { size: "invisible" });
      setConfirmation(await signInWithPhoneNumber(auth, toE164(phone), verifier.current));
    } catch (err) {
      clearVerifier();
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await confirmation!.confirm(code);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Intrați în cont</h1>
      {confirmation ? (
        <form onSubmit={confirm}>
          <label htmlFor="code">Codul primit prin SMS</label>
          <input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <button disabled={busy}>Confirmă</button>
        </form>
      ) : (
        <form onSubmit={sendCode}>
          <label htmlFor="phone">Număr de telefon</label>
          <input
            id="phone"
            type="tel"
            autoComplete="tel"
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <button disabled={busy}>Trimite codul</button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
      <div ref={recaptchaEl} />
    </section>
  );
}
