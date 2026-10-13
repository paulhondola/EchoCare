<script lang="ts">
  import {
    acceptSenior,
    ApiError,
    fetchEnrollments,
    fetchSenior,
    type SeniorSummary,
    type SeniorView,
  } from "../../services/api";
  import { address, time } from "../../utils/labels";
  import { poll } from "../../utils/poll.svelte";

  const REFRESH_MS = 15_000;

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

  function describe(e: unknown): string {
    return e instanceof ApiError && e.status === 404
      ? "API-ul nu oferă încă cererile de înrolare."
      : `Nu am putut citi cererile (${e instanceof Error ? e.message : String(e)}).`;
  }

  type Details =
    | { kind: "loading" }
    | { kind: "ok"; senior: SeniorView }
    | { kind: "error"; message: string };

  const poller = poll(fetchEnrollments, REFRESH_MS, describe);

  let acceptedNotice = $state<string | null>(null);
  let detailsMap = $state<Record<string, Details>>({});
  let busyMap = $state<Record<string, boolean>>({});
  let errorMap = $state<Record<string, string>>({});

  function toggle(id: string) {
    if (detailsMap[id]) {
      const copy = { ...detailsMap };
      delete copy[id];
      detailsMap = copy;
      return;
    }
    detailsMap = { ...detailsMap, [id]: { kind: "loading" } };
    fetchSenior(id)
      .then((senior) => {
        detailsMap = { ...detailsMap, [id]: { kind: "ok", senior } };
      })
      .catch((e: unknown) => {
        detailsMap = {
          ...detailsMap,
          [id]: {
            kind: "error",
            message: `Nu am putut citi cererea (${e instanceof Error ? e.message : String(e)}).`,
          },
        };
      });
  }

  function accept(s: SeniorSummary) {
    busyMap = { ...busyMap, [s.id]: true };
    const nextErrors = { ...errorMap };
    delete nextErrors[s.id];
    errorMap = nextErrors;

    acceptSenior(s.id)
      .then(() => {
        acceptedNotice = `Acceptat: ${s.full_name}.`;
        poller.update((list) => list.filter((x) => x.id !== s.id));
      })
      .catch((e: unknown) => {
        errorMap = { ...errorMap, [s.id]: refusalMessage(e) };
        poller.reload();
      })
      .finally(() => {
        const nextBusy = { ...busyMap };
        delete nextBusy[s.id];
        busyMap = nextBusy;
      });
  }
</script>

{#snippet registration(s: SeniorView)}
  <div class="mt-2 flex flex-col gap-3">
    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
      <dt class="text-base-content/60">Telefon</dt>
      <dd>
        {s.phone_e164}
        <span class="badge badge-xs badge-ghost ml-1">
          {s.phone_is_landline ? "fix" : "mobil"}
        </span>
      </dd>
      <dt class="text-base-content/60">Adresă</dt>
      <dd>{address(s)}</dd>
      {#if s.intercom_code}
        <dt class="text-base-content/60">Interfon</dt>
        <dd>{s.intercom_code}</dd>
      {/if}
      {#if s.key_holder}
        <dt class="text-base-content/60">Are cheie</dt>
        <dd>{s.key_holder}</dd>
      {/if}
      {#if s.landmark}
        <dt class="text-base-content/60">Reper</dt>
        <dd>{s.landmark}</dd>
      {/if}
      {#if s.call_window}
        <dt class="text-base-content/60">Interval de apel</dt>
        <dd>{s.call_window}</dd>
      {/if}
    </dl>
    <div>
      <h4 class="mb-1 text-sm font-semibold">Aparținători</h4>
      {#if s.caregivers.length === 0}
        <p class="text-sm text-base-content/60">Niciun aparținător.</p>
      {:else}
        <ul class="text-sm">
          {#each s.caregivers as c (c.user_id)}
            <li>
              {c.display_name}
              {c.relation ? ` (${c.relation})` : ""}, {c.phone_e164}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>
{/snippet}

{#if poller.load.kind === "loading"}
  <div
    role="status"
    class="loading-delay flex items-center justify-center gap-2 p-12 text-base-content/60"
  >
    <span class="loading loading-spinner loading-md"></span>
    <span class="text-sm">Se încarcă cererile…</span>
  </div>
{:else if poller.load.kind === "error"}
  <div role="alert" class="alert alert-error alert-soft">
    {poller.load.message}
  </div>
{:else if poller.load.kind === "ok"}
  <section class="max-w-3xl">
    <h2 class="mb-1 text-lg font-semibold">
      Cereri de înrolare <span class="badge badge-sm">{poller.load.data.length}</span>
    </h2>
    <p class="mb-3 text-sm text-base-content/60">Actualizat la {time.format(poller.load.at)}</p>
    {#if poller.load.error}
      <div role="alert" class="alert alert-warning alert-soft mb-3">
        {poller.load.error}
      </div>
    {/if}
    {#if acceptedNotice}
      <div role="status" class="alert alert-success alert-soft mb-3">
        {acceptedNotice}
      </div>
    {/if}
    {#if poller.load.data.length === 0}
      <p class="text-sm text-base-content/60">Nicio cerere în așteptare.</p>
    {/if}
    {#each poller.load.data as s (s.id)}
      {@const details = detailsMap[s.id]}
      {@const busy = busyMap[s.id] ?? false}
      {@const error = errorMap[s.id]}
      <article class="card card-sm mb-3 border-l-4 border-info bg-base-100 shadow-sm">
        <div class="card-body gap-1">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h3 class="card-title text-base">{s.full_name}</h3>
              <p class="text-sm text-base-content/60">{s.form_of_address}</p>
            </div>
            <div class="flex gap-2">
              <button class="btn btn-ghost btn-sm" onclick={() => toggle(s.id)}>
                {details ? "Ascunde" : "Vezi cererea"}
              </button>
              <button class="btn btn-success btn-sm" disabled={busy} onclick={() => accept(s)}>
                Acceptă
              </button>
            </div>
          </div>
          {#if details?.kind === "loading"}
            <div role="status" class="flex items-center gap-2 text-sm">
              <span class="loading loading-spinner loading-xs"></span>
              Se încarcă…
            </div>
          {/if}
          {#if details?.kind === "error"}
            <p role="alert" class="text-sm text-error">
              {details.message}
            </p>
          {/if}
          {#if details?.kind === "ok"}
            {@render registration(details.senior)}
          {/if}
          {#if error}
            <p role="alert" class="mt-1 text-sm text-error">
              {error}
            </p>
          {/if}
        </div>
      </article>
    {/each}
  </section>
{/if}
