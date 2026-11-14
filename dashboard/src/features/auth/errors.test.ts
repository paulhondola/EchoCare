import { FirebaseError } from "firebase/app";
import { expect, test, vi } from "vite-plus/test";
import { UNAVAILABLE, authErrorText } from "./errors";

test("translates core auth-layer §7.1 errors", () => {
  expect(authErrorText(new FirebaseError("auth/invalid-verification-code", ""))).toBe(
    "Cod greșit.",
  );
  expect(authErrorText(new FirebaseError("auth/invalid-phone-number", ""))).toBe(
    "Număr de telefon invalid.",
  );
  expect(authErrorText(new FirebaseError("auth/too-many-requests", ""))).toBe(
    "Prea multe încercări. Încercați mai târziu.",
  );
});

test("translates operator and upstream delivery errors (error-code:-39)", () => {
  expect(authErrorText(new FirebaseError("auth/error-code:-39", ""))).toBe(
    "Trimiterea SMS-ului a eșuat la operator. Încercați din nou mai târziu.",
  );
  // Handles variations of unmapped error codes from Identity Platform
  expect(authErrorText(new FirebaseError("auth/error-code", ""))).toBe(
    "Trimiterea SMS-ului a eșuat la operator. Încercați din nou mai târziu.",
  );
  expect(authErrorText(new FirebaseError("auth/error-code-other", ""))).toBe(
    "Trimiterea SMS-ului a eșuat la operator. Încercați din nou mai târziu.",
  );
});

test("translates SMS code and session lifetime errors", () => {
  expect(authErrorText(new FirebaseError("auth/code-expired", ""))).toBe(
    "Codul primit a expirat. Trimiteți alt cod.",
  );
  expect(authErrorText(new FirebaseError("auth/session-expired", ""))).toBe(
    "Sesiunea de verificare a expirat. Trimiteți din nou codul.",
  );
  expect(authErrorText(new FirebaseError("auth/invalid-verification-id", ""))).toBe(
    "Sesiunea de verificare este invalidă. Trimiteți din nou codul.",
  );
});

test("translates quota and permission errors", () => {
  expect(authErrorText(new FirebaseError("auth/quota-exceeded", ""))).toBe(
    "Limita zilnică de SMS-uri a fost depășită. Încercați mai târziu.",
  );
  expect(authErrorText(new FirebaseError("auth/operation-not-allowed", ""))).toBe(
    "Autentificarea prin SMS nu este activată pentru această regiune.",
  );
});

test("translates reCAPTCHA and domain authorization errors", () => {
  expect(authErrorText(new FirebaseError("auth/captcha-check-failed", ""))).toBe(
    "Verificarea de securitate (reCAPTCHA) a eșuat. Reîncărcați pagina.",
  );
  expect(authErrorText(new FirebaseError("auth/invalid-app-credential", ""))).toBe(
    "Verificarea aplicației a eșuat. Reîncărcați pagina.",
  );
  expect(authErrorText(new FirebaseError("auth/app-not-authorized", ""))).toBe(
    "Aplicația nu este autorizată pe acest domeniu.",
  );
  expect(authErrorText(new FirebaseError("auth/unauthorized-domain", ""))).toBe(
    "Domeniul curent nu este autorizat pentru autentificare.",
  );
});

test("translates missing input errors", () => {
  expect(authErrorText(new FirebaseError("auth/missing-phone-number", ""))).toBe(
    "Introduceți numărul de telefon.",
  );
  expect(authErrorText(new FirebaseError("auth/missing-verification-code", ""))).toBe(
    "Introduceți codul primit prin SMS.",
  );
});

test("translates account and network connectivity errors", () => {
  expect(authErrorText(new FirebaseError("auth/user-disabled", ""))).toBe(
    "Acest cont a fost dezactivat.",
  );
  expect(authErrorText(new FirebaseError("auth/network-request-failed", ""))).toBe(
    "Eroare de rețea. Verificați conexiunea la internet.",
  );
  expect(authErrorText(new FirebaseError("auth/timeout", ""))).toBe(
    "Operațiunea a expirat. Reîncercați.",
  );
});

test("falls back to UNAVAILABLE and logs unknown errors to console", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});

  const unknownFbError = new FirebaseError("auth/internal-error", "unexpected");
  expect(authErrorText(unknownFbError)).toBe(UNAVAILABLE);
  expect(spy).toHaveBeenCalledWith(unknownFbError);

  const nonFbError = new Error("something went wrong");
  expect(authErrorText(nonFbError)).toBe(UNAVAILABLE);
  expect(spy).toHaveBeenCalledWith(nonFbError);

  spy.mockRestore();
});
