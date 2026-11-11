<script lang="ts">
  import "../styles.css";
  import { onAuthStateChanged, signOut } from "firebase/auth";
  import { onMount } from "svelte";
  import { SignIn } from "../features/auth";
  import { Landing } from "../features/landing";
  import Shell from "../features/shell/Shell.svelte";
  import { getMe } from "../services/api";
  import { auth } from "../services/firebase";
  import Brand from "../ui/Brand.svelte";

  let { children } = $props();

  const NO_ACCESS = "Acest număr nu are acces la dispecerat.";
  const NOT_REGISTERED = "Numărul nu este înregistrat. Contactați medicul de familie.";
  const UNAVAILABLE = "Autentificarea nu este disponibilă acum. Încercați din nou.";

  type View =
    | { kind: "loading" }
    | { kind: "signedOut"; notice?: string }
    | { kind: "das"; name: string }
    | { kind: "unavailable" };

  let view = $state<View>({ kind: "loading" });
  // Signed out, the landing page shows until "Intrați în cont" opens the sign-in card
  let signingIn = $state(false);

  onMount(() => {
    return onAuthStateChanged(auth, (user) => {
      if (!user) {
        view = view.kind === "signedOut" ? view : { kind: "signedOut" };
        return;
      }
      view = { kind: "loading" };
      // So any sign-out from here lands on the landing page again; a refusal's notice still
      // shows the sign-in card
      signingIn = false;
      const refuse = (notice: string) => {
        view = { kind: "signedOut", notice };
        void signOut(auth);
      };
      getMe()
        .then((me) => {
          if (me === "not_registered") refuse(NOT_REGISTERED);
          else if (me === "not_signed_in") return;
          else if (typeof me === "string") view = { kind: "unavailable" };
          else if (me.grants.some((g) => g.role === "das"))
            view = { kind: "das", name: me.display_name };
          else refuse(NO_ACCESS);
        })
        .catch((err: unknown) => {
          console.error(err);
          view = { kind: "unavailable" };
        });
    });
  });
</script>

{#if view.kind === "loading"}
  <main aria-busy="true" class="grid min-h-screen place-items-center">
    <span class="loading-delay loading loading-md loading-spinner text-fg-muted"></span>
  </main>
{:else if view.kind === "signedOut" && (signingIn || view.notice)}
  <main class="grid min-h-screen place-items-center p-4">
    <div class="flex w-full max-w-sm flex-col gap-5 border-2 border-line bg-subtle p-6">
      <Brand />
      <SignIn notice={view.notice} />
      <button
        class="sn-btn sn-btn-outline self-start"
        onclick={() => {
          signingIn = false;
          view = { kind: "signedOut" };
        }}
      >
        Înapoi
      </button>
    </div>
  </main>
{:else if view.kind === "signedOut"}
  <Landing onSignIn={() => (signingIn = true)} />
{:else if view.kind === "unavailable"}
  <main class="grid min-h-screen place-items-center p-4">
    <div class="flex w-full max-w-sm flex-col gap-4 border-2 border-line bg-subtle p-6">
      <Brand />
      <p role="alert" class="text-rosu-fg">{UNAVAILABLE}</p>
      <button class="sn-btn self-start" onclick={() => void signOut(auth)}>Ieșire</button>
    </div>
  </main>
{:else if view.kind === "das"}
  <Shell name={view.name} onSignOut={() => void signOut(auth)}>
    {@render children()}
  </Shell>
{/if}
