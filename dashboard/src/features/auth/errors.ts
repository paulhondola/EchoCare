import { FirebaseError } from "firebase/app";

/**
 * Romanian translations for Firebase phone authentication errors.
 * auth-layer §7.1. Anything else falls back to UNAVAILABLE (auth-layer §3.2).
 */
export const AUTH_ERRORS: Record<string, string> = {
  // Core auth-layer §7.1 errors
  "auth/invalid-verification-code": "Cod greșit.",
  "auth/invalid-phone-number": "Număr de telefon invalid.",
  "auth/too-many-requests": "Prea multe încercări. Încercați mai târziu.",

  // Upstream telecom / operator / rate limit blocks (Identity Platform HTTP 503 ERROR_CODE:-39)
  "auth/error-code:-39": "Trimiterea SMS-ului a eșuat la operator. Încercați din nou mai târziu.",

  // SMS code & session lifetime
  "auth/code-expired": "Codul primit a expirat. Trimiteți alt cod.",
  "auth/session-expired": "Sesiunea de verificare a expirat. Trimiteți din nou codul.",
  "auth/invalid-verification-id": "Sesiunea de verificare este invalidă. Trimiteți din nou codul.",

  // Project quota & region policies
  "auth/quota-exceeded": "Limita zilnică de SMS-uri a fost depășită. Încercați mai târziu.",
  "auth/operation-not-allowed": "Autentificarea prin SMS nu este activată pentru această regiune.",

  // App & reCAPTCHA verification
  "auth/captcha-check-failed": "Verificarea de securitate (reCAPTCHA) a eșuat. Reîncărcați pagina.",
  "auth/invalid-app-credential": "Verificarea aplicației a eșuat. Reîncărcați pagina.",
  "auth/app-not-authorized": "Aplicația nu este autorizată pe acest domeniu.",
  "auth/unauthorized-domain": "Domeniul curent nu este autorizat pentru autentificare.",

  // Missing inputs
  "auth/missing-phone-number": "Introduceți numărul de telefon.",
  "auth/missing-verification-code": "Introduceți codul primit prin SMS.",

  // Account, network & timeouts
  "auth/user-disabled": "Acest cont a fost dezactivat.",
  "auth/network-request-failed": "Eroare de rețea. Verificați conexiunea la internet.",
  "auth/timeout": "Operațiunea a expirat. Reîncercați.",
};

export const UNAVAILABLE = "Autentificarea nu este disponibilă acum. Încercați din nou.";

/** Translates Firebase Auth errors to user-facing Romanian messages. */
export function authErrorText(err: unknown): string {
  if (err instanceof FirebaseError) {
    if (err.code in AUTH_ERRORS) return AUTH_ERRORS[err.code];
    if (err.code.startsWith("auth/error-code")) return AUTH_ERRORS["auth/error-code:-39"];
  }
  console.error(err);
  return UNAVAILABLE;
}
