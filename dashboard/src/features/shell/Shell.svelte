<script lang="ts">
  import type { Snippet } from "svelte";
  import IncidentDetails from "../incidents/IncidentDetails.svelte";
  import RedAlert from "../incidents/RedAlert.svelte";
  import { Live, setLive } from "./live.svelte";
  import Sidebar from "./Sidebar.svelte";
  import { playSiren } from "./siren";

  let { name, onSignOut, children }: { name: string; onSignOut: () => void; children: Snippet } =
    $props();

  const live = new Live();
  setLive(live);

  const now = $derived(live.incidents.load.kind === "ok" ? live.incidents.load.at : Date.now());
  const alert = $derived(live.open?.[0]);
  const dossierIncident = $derived(
    live.dossier && live.incidents.load.kind === "ok"
      ? live.incidents.load.data.find((i) => i.id === live.dossier?.id)
      : undefined,
  );

  // A new open incident rings the siren when Alerte sonore is on (spec 07 §1, UC-11). The
  // first read only learns what is already open.
  let seen: Set<string> | null = null;
  $effect(() => {
    const open = live.open;
    if (!open) return;
    const fresh = seen !== null && open.some((i) => !seen!.has(i.id));
    seen = new Set(open.map((i) => i.id));
    if (fresh && live.sound) playSiren();
  });
</script>

<svelte:head>
  <title>{live.open?.length ? `(${live.open.length}) ` : ""}Sentinela DAS</title>
</svelte:head>

<div class="grid min-h-screen md:h-screen md:grid-cols-[240px_minmax(0,1fr)]">
  <Sidebar {name} {onSignOut} />
  <main class="relative flex min-h-0 min-w-0 flex-col">
    {#if alert}
      {#key alert.id}
        <RedAlert incident={alert} {now} />
      {/key}
    {/if}
    {@render children()}
  </main>
</div>

{#if live.dossier && dossierIncident}
  {#key live.dossier}
    <IncidentDetails
      incident={dossierIncident}
      tab={live.dossier.tab}
      {now}
      onClose={() => (live.dossier = null)}
      onChanged={live.incidentChanged}
      onStale={() => live.incidents.reload()}
    />
  {/key}
{/if}
