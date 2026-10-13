<script lang="ts">
  import { FirebaseError } from "firebase/app";
  import { type ConfirmationResult, RecaptchaVerifier, signInWithPhoneNumber } from "firebase/auth";
  import { onDestroy } from "svelte";
  import { auth } from "../../services/firebase";
  import { toE164 } from "../../utils/phone";

  let { notice }: { notice?: string } = $props();

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

  let phone = $state("");
  let code = $state("");
  let confirmation = $state<ConfirmationResult | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let recaptchaEl: HTMLDivElement | undefined = $state();
  let codeEl: HTMLInputElement | undefined = $state();
  let verifier: RecaptchaVerifier | null = null;

  $effect(() => {
    error = notice ?? null;
  });

  $effect(() => {
    if (confirmation && codeEl) {
      codeEl.focus();
    }
  });

  function clearVerifier() {
    verifier?.clear();
    verifier = null;
  }

  onDestroy(clearVerifier);

  async function sendCode(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    busy = true;
    try {
      if (!recaptchaEl) throw new Error("Missing recaptcha container");
      // Created on press, kept in a plain variable; .clear() on failure and in onDestroy
      verifier ??= new RecaptchaVerifier(auth, recaptchaEl, { size: "invisible" });
      confirmation = await signInWithPhoneNumber(auth, toE164(phone), verifier);
    } catch (err) {
      clearVerifier();
      error = errorText(err);
    } finally {
      busy = false;
    }
  }

  async function confirm(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    busy = true;
    try {
      await confirmation!.confirm(code);
    } catch (err) {
      error = errorText(err);
    } finally {
      busy = false;
    }
  }
</script>

<section>
  <h1>Intrați în cont</h1>
  {#if confirmation}
    <form onsubmit={confirm}>
      <label for="code">Codul primit prin SMS</label>
      <input
        bind:this={codeEl}
        id="code"
        inputmode="numeric"
        autocomplete="one-time-code"
        required
        bind:value={code}
      />
      <button disabled={busy}>Confirmă</button>
    </form>
  {:else}
    <form onsubmit={sendCode}>
      <label for="phone">Număr de telefon</label>
      <input id="phone" type="tel" autocomplete="tel" required bind:value={phone} />
      <button disabled={busy}>Trimite codul</button>
    </form>
  {/if}
  {#if error}
    <p role="alert">{error}</p>
  {/if}
  <div bind:this={recaptchaEl}></div>
</section>
