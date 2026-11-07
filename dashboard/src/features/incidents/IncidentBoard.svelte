<script lang="ts">
  import type { IncidentStatus } from "../../services/api";
  import Icon, { type IconName } from "../../ui/Icon.svelte";
  import { columns, matchesIncident, shortId, since, type DossierTab } from "../../utils/incidents";
  import { time } from "../../utils/labels";
  import { getLive } from "../shell/live.svelte";
  import PageHeader from "../shell/PageHeader.svelte";
  import IncidentCard from "./IncidentCard.svelte";

  const live = getLive();
  const incidents = live.incidents;

  // Board for triage, table for scanning everything at once (spec 07 §4.2–4.3). Full class
  // names, so Tailwind finds them in the source.
  const COLUMNS: {
    status: IncidentStatus;
    title: string;
    icon: IconName;
    top: string;
    iconColor: string;
    count: string;
    empty: string;
  }[] = [
    {
      status: "open",
      title: "Deschise",
      icon: "circle-dot",
      top: "border-t-rosu",
      iconColor: "text-rosu",
      count: "bg-rosu/15 text-rosu-fg",
      empty: "Niciun incident deschis.",
    },
    {
      status: "in_progress",
      title: "În lucru",
      icon: "clock",
      top: "border-t-galben",
      iconColor: "text-galben",
      count: "bg-galben/15 text-galben-fg",
      empty: "Niciun incident în lucru.",
    },
    {
      status: "resolved",
      title: "Rezolvate",
      icon: "circle-check",
      top: "border-t-verde",
      iconColor: "text-verde",
      count: "bg-verde/15 text-verde-fg",
      empty: "Niciun incident rezolvat în ultimele 24 de ore.",
    },
  ];

  const STATUS_CHIP: Record<IncidentStatus, { label: string; chip: string }> = {
    open: { label: "Deschis", chip: "bg-rosu/15 text-rosu-fg" },
    in_progress: { label: "În lucru", chip: "bg-galben/15 text-galben-fg" },
    resolved: { label: "Rezolvat", chip: "bg-verde/15 text-verde-fg" },
  };

  let view = $state<"board" | "table">("board");
  let query = $state("");

  const all = $derived(incidents.load.kind === "ok" ? incidents.load.data : []);
  const now = $derived(incidents.load.kind === "ok" ? incidents.load.at : Date.now());
  const byStatus = $derived(columns(all.filter((i) => matchesIncident(i, query))));
  const rows = $derived([...byStatus.open, ...byStatus.in_progress, ...byStatus.resolved]);

  // The Shell shows the dossier, as it does for the Cod Roșu banner on every page
  function open(id: string, tab: DossierTab = "access") {
    live.dossier = { id, tab };
  }
</script>

<PageHeader title="Dispecerat Incidente">
  <div class="flex gap-0.5" role="tablist" aria-label="Vizualizare">
    {#each [{ key: "board", label: "Panou", icon: "board" }, { key: "table", label: "Tabel", icon: "table" }] as const as v (v.key)}
      <button
        type="button"
        role="tab"
        aria-selected={view === v.key}
        class={[
          "-mb-0.5 flex cursor-pointer items-center gap-[7px] border-b-2 px-3 py-2 font-semibold",
          view === v.key ? "border-link text-fg" : "border-transparent text-fg-muted hover:text-fg",
        ]}
        onclick={() => (view = v.key)}
      >
        <Icon name={v.icon} size={14} />{v.label}
      </button>
    {/each}
  </div>
  <label
    class="sn-input mb-2 ml-auto flex h-8 w-full max-w-[360px] items-center gap-2 px-2.5 text-fg-muted"
  >
    <Icon name="search" size={14} />
    <input
      bind:value={query}
      aria-label="Filtrează incidente"
      placeholder="Filtrează: nume, motiv, dispecer, #id"
      class="min-w-0 flex-1 bg-transparent font-mono text-xs text-fg outline-none placeholder:text-fg-muted"
    />
  </label>
</PageHeader>

{#if incidents.load.kind === "loading"}
  <div
    role="status"
    class="loading-delay flex items-center justify-center gap-2 p-12 text-fg-muted"
  >
    <span class="loading loading-md loading-spinner"></span>
    <span>Se încarcă incidentele…</span>
  </div>
{:else if incidents.load.kind === "error"}
  <p role="alert" class="m-4 border border-rosu bg-rosu/15 px-4 py-3 text-rosu-fg">
    {incidents.load.message}
  </p>
{:else}
  {#if incidents.load.error}
    <p role="alert" class="mx-4 mt-3 border border-galben bg-galben/15 px-4 py-2 text-galben-fg">
      {incidents.load.error} Afișez datele de la {time.format(incidents.load.at)}.
    </p>
  {/if}

  {#if view === "board"}
    <div class="grid min-h-0 flex-1 gap-3 p-4 md:grid-cols-3">
      {#each COLUMNS as c (c.status)}
        {@const items = byStatus[c.status]}
        <section class="flex min-h-0 flex-col border border-line bg-subtle" aria-label={c.title}>
          <div
            class={[
              "flex items-center gap-2 border-t-[3px] border-b border-b-line px-3.5 py-[11px]",
              c.top,
            ]}
          >
            <Icon name={c.icon} stroke={2.2} class={c.iconColor} />
            <h2 class="text-sm font-extrabold">{c.title}</h2>
            <span class={["sn-count", c.count]}>{items.length}</span>
          </div>
          <div class="flex min-h-0 flex-col gap-2 overflow-auto p-2.5">
            {#each items as i (i.id)}
              <IncidentCard
                incident={i}
                {now}
                onOpen={(tab) => open(i.id, tab)}
                onChanged={live.incidentChanged}
                onStale={() => incidents.reload()}
              />
            {:else}
              <p class="px-1 py-4 text-fg-muted">{query ? "Niciun rezultat." : c.empty}</p>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {:else}
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="w-full border-collapse text-left">
        <thead class="sticky top-0 z-[1] bg-subtle">
          <tr class="sn-label border-b-2 border-line">
            <th class="border-r border-card px-3 py-[9px] font-semibold">Incident</th>
            <th class="border-r border-card px-3 py-[9px] font-semibold">Senior</th>
            <th class="border-r border-card px-3 py-[9px] font-semibold">Motiv</th>
            <th class="border-r border-card px-3 py-[9px] font-semibold">Stare</th>
            <th class="border-r border-card px-3 py-[9px] font-semibold">Preluat de</th>
            <th class="px-3 py-[9px] font-semibold">Acțiuni</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as i (i.id)}
            <tr class="border-b border-line hover:bg-subtle">
              <td class="border-r border-card px-3 py-2">
                <span class="block font-mono text-[11.5px] text-fg-soft">#{shortId(i.id)}</span>
                <span class="text-xs text-fg-muted" title={time.format(Date.parse(i.opened_at))}>
                  {since(i.opened_at, now)}
                </span>
              </td>
              <td class="border-r border-card px-3 py-2">
                <span class="block text-[13.5px] font-semibold">{i.senior_full_name}</span>
                <span class="text-xs text-fg-muted">{i.senior_form_of_address}</span>
              </td>
              <td
                class={[
                  "border-r border-card px-3 py-2",
                  i.status === "open" && "font-semibold text-rosu-fg",
                ]}
              >
                {i.reason}
              </td>
              <td class="border-r border-card px-3 py-2">
                <span
                  class={[
                    "px-2 py-0.5 text-[11.5px] font-bold whitespace-nowrap",
                    STATUS_CHIP[i.status].chip,
                  ]}
                >
                  {STATUS_CHIP[i.status].label}
                </span>
              </td>
              <td class="border-r border-card px-3 py-2 text-fg-soft">{i.taken_by_name ?? "—"}</td>
              <td class="px-3 py-2">
                <button
                  type="button"
                  class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs"
                  onclick={() => open(i.id, i.status === "in_progress" ? "resolve" : "access")}
                >
                  Vezi dosar
                </button>
              </td>
            </tr>
          {:else}
            <tr>
              <td colspan="6" class="px-5 py-6 text-fg-muted">
                {query ? "Niciun incident nu corespunde filtrului." : "Niciun incident."}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{/if}
