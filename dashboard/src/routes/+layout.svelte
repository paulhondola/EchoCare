<script lang="ts">
  import "../styles.css";
  import { page } from "$app/state";
  import { onAuthStateChanged, signOut } from "firebase/auth";
  import { onMount } from "svelte";
  import { SignIn } from "../features/auth";
  import { getMe } from "../services/api";
  import { auth } from "../services/firebase";

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

  onMount(() => {
    return onAuthStateChanged(auth, (user) => {
      if (!user) {
        view = view.kind === "signedOut" ? view : { kind: "signedOut" };
        return;
      }
      view = { kind: "loading" };
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

  const isIncidents = $derived(page.url.pathname === "/");
  const isEnrollments = $derived(page.url.pathname.startsWith("/enrollments"));
  const isStaff = $derived(page.url.pathname.startsWith("/staff"));
</script>

{#if view.kind === "loading"}
  <main aria-busy="true"></main>
{:else if view.kind === "signedOut"}
  <main>
    <SignIn notice={view.notice} />
  </main>
{:else if view.kind === "unavailable"}
  <main>
    <p role="alert">{UNAVAILABLE}</p>
    <button class="btn btn-sm" onclick={() => void signOut(auth)}>Ieșire</button>
  </main>
{:else if view.kind === "das"}
  <main class="mx-auto max-w-7xl p-4">
    <header
      class="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-base-300 pb-2"
    >
      <h1 class="text-2xl font-bold">Sentinela DAS</h1>
      <nav class="tabs tabs-box tabs-sm">
        <a
          href="/"
          class={["tab", isIncidents && "tab-active"]}
          aria-current={isIncidents ? "page" : undefined}
        >
          Incidente
        </a>
        <a
          href="/enrollments"
          class={["tab", isEnrollments && "tab-active"]}
          aria-current={isEnrollments ? "page" : undefined}
        >
          Cereri de înrolare
        </a>
        <a
          href="/staff"
          class={["tab", isStaff && "tab-active"]}
          aria-current={isStaff ? "page" : undefined}
        >
          Personal
        </a>
      </nav>
      <span class="flex items-center gap-2 text-sm text-base-content/60">
        Conectat ca {view.name}
        <button class="btn btn-sm" onclick={() => void signOut(auth)}>Ieșire</button>
      </span>
    </header>
    {@render children()}
  </main>
{/if}
