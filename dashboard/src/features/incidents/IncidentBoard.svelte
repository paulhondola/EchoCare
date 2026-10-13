<script lang="ts">
  import { ApiError, fetchIncidents, type IncidentStatus } from "../../services/api";
  import { time } from "../../utils/labels";
  import { poll } from "../../utils/poll.svelte";
  import IncidentCard from "./IncidentCard.svelte";

  const REFRESH_MS = 15_000;

  // Full class names, so Tailwind finds them in the source
  const COLUMNS: { status: IncidentStatus; title: string; border: string; badge: string }[] = [
    { status: "open", title: "Deschise", border: "border-error", badge: "badge-error" },
    { status: "in_progress", title: "În lucru", border: "border-warning", badge: "badge-warning" },
    { status: "resolved", title: "Rezolvate", border: "border-success", badge: "badge-success" },
  ];

  function describe(e: unknown): string {
    return e instanceof ApiError && e.status === 404
      ? "API-ul nu oferă încă lista de incidente."
      : `Nu am putut citi incidentele (${e instanceof Error ? e.message : String(e)}).`;
  }

  const poller = poll(fetchIncidents, REFRESH_MS, describe);
</script>

{#if poller.load.kind === "loading"}
  <div
    role="status"
    class="loading-delay flex items-center justify-center gap-2 p-12 text-base-content/60"
  >
    <span class="loading loading-spinner loading-md"></span>
    <span class="text-sm">Se încarcă incidentele…</span>
  </div>
{:else if poller.load.kind === "error"}
  <div role="alert" class="alert alert-error alert-soft">
    {poller.load.message}
  </div>
{:else if poller.load.kind === "ok"}
  <section>
    {#if poller.load.error}
      <div role="alert" class="alert alert-warning alert-soft mb-3">
        {poller.load.error}
      </div>
    {/if}
    <p class="mb-3 text-sm text-base-content/60">Actualizat la {time.format(poller.load.at)}</p>
    <div class="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] items-start gap-4">
      {#each COLUMNS as { status, title, border, badge } (status)}
        {@const items = poller.load.data.filter((i) => i.status === status)}
        <div>
          <h2 class={["mb-3 flex items-center gap-2 border-b-4 pb-1.5 font-semibold", border]}>
            {title} <span class={["badge badge-sm", badge]}>{items.length}</span>
          </h2>
          {#if items.length === 0}
            <p class="text-sm text-base-content/60">Niciun incident.</p>
          {/if}
          {#each items as i (i.id)}
            <IncidentCard
              incident={i}
              now={poller.load.at}
              {border}
              onChanged={(changed) =>
                poller.update((list) => list.map((x) => (x.id === changed.id ? changed : x)))}
              onStale={() => poller.reload()}
            />
          {/each}
        </div>
      {/each}
    </div>
  </section>
{/if}
