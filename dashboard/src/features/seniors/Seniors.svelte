<script lang="ts">
  import { onMount } from "svelte";
  import type { SeniorSummary } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { download, toCsv } from "../../utils/csv";
  import { fold } from "../../utils/incidents";
  import { clock, enrollment, TONE_CHIP, TONE_DOT } from "../../utils/labels";
  import { formatPhone } from "../../utils/phone";
  import { getLive } from "../shell/live.svelte";
  import PageHeader from "../shell/PageHeader.svelte";
  import SeniorDetails from "./SeniorDetails.svelte";

  const live = getLive();
  const seniors = live.seniors;

  // The registry is polled slowly for the sidebar's counter: read it fresh when the page opens
  onMount(() => seniors.reload());

  // Tabs by enrollment state (03 §1). The API sends no codes per senior yet (04 §1, proposed),
  // so the design's Cod Roșu / Galben / Verde tabs wait for them.
  type Tab = "all" | "active" | "enrolling" | "attention";
  const TABS: { key: Tab; label: string; dot: string; states: string[] | null }[] = [
    { key: "all", label: "Toți", dot: "bg-fg-muted", states: null },
    { key: "active", label: "Activi", dot: "bg-verde", states: ["active"] },
    { key: "enrolling", label: "În înrolare", dot: "bg-link", states: ["submitted", "accepted"] },
    {
      key: "attention",
      label: "Necesită atenție",
      dot: "bg-galben",
      states: ["refused", "wrong_number", "unreachable"],
    },
  ];

  let tab = $state<Tab>("all");
  let query = $state("");
  let selected = $state<SeniorSummary | null>(null);

  const all = $derived(seniors.load.kind === "ok" ? seniors.load.data : []);
  const inTab = (s: SeniorSummary, t: (typeof TABS)[number]) =>
    t.states === null || t.states.includes(s.enrollment_state);

  function matches(s: SeniorSummary, q: string): boolean {
    const text = fold(q.trim());
    if (!text) return true;
    const digits = q.replace(/\D/g, "");
    return (
      fold(`${s.full_name} ${s.form_of_address}`).includes(text) ||
      (digits.length > 2 &&
        (s.phone_e164.includes(digits) ||
          formatPhone(s.phone_e164).replace(/\D/g, "").includes(digits)))
    );
  }

  const current = $derived(TABS.find((t) => t.key === tab) ?? TABS[0]);
  const inCurrentTab = $derived(all.filter((s) => inTab(s, current)));
  const shown = $derived(inCurrentTab.filter((s) => matches(s, query)));

  function exportCsv() {
    const rows = shown.map((s) => [
      s.full_name,
      s.form_of_address,
      formatPhone(s.phone_e164),
      s.phone_is_landline ? "fix" : "mobil",
      enrollment(s.enrollment_state).label,
    ]);
    const day = new Date().toLocaleDateString("sv-SE"); // the local date as YYYY-MM-DD
    download(
      `seniori-${day}.csv`,
      toCsv([["Nume", "Formă de adresare", "Telefon", "Tip", "Stare înrolare"], ...rows]),
    );
  }

  const COLS = "grid-cols-[40px_minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_108px]";
</script>

<PageHeader title="Monitorizare Seniori">
  {#snippet actions()}
    <button
      type="button"
      class="sn-btn h-[30px] text-[12.5px]"
      disabled={shown.length === 0}
      onclick={exportCsv}
    >
      <Icon name="download" size={13} />Exportă CSV
    </button>
    <button
      type="button"
      title="Reîmprospătează"
      aria-label="Reîmprospătează"
      class="sn-btn grid size-[30px] place-items-center p-0"
      onclick={() => seniors.reload()}
    >
      <Icon name="refresh" size={13} />
    </button>
  {/snippet}

  <div class="flex flex-wrap gap-0.5" role="tablist" aria-label="Filtru stare">
    {#each TABS as t (t.key)}
      <button
        type="button"
        role="tab"
        aria-selected={tab === t.key}
        class={[
          "-mb-0.5 flex cursor-pointer items-center gap-[7px] border-b-2 px-3 py-2 font-semibold",
          tab === t.key ? "border-link text-fg" : "border-transparent text-fg-muted hover:text-fg",
        ]}
        onclick={() => (tab = t.key)}
      >
        <span class={["size-2", t.dot]}></span>{t.label}
        <span class="bg-line px-1.5 font-mono text-[11px] leading-[1.6] font-medium text-fg-soft">
          {all.filter((s) => inTab(s, t)).length}
        </span>
      </button>
    {/each}
  </div>
  <label
    class="sn-input mb-2 ml-auto flex h-8 w-full max-w-[380px] items-center gap-2 px-2.5 text-fg-muted"
  >
    <Icon name="search" size={14} />
    <input
      bind:value={query}
      aria-label="Caută seniori"
      placeholder="Caută după nume sau telefon…"
      class="min-w-0 flex-1 bg-transparent text-[12.5px] text-fg outline-none placeholder:text-fg-muted"
    />
  </label>
</PageHeader>

{#if seniors.load.kind === "loading"}
  <div
    role="status"
    class="loading-delay flex items-center justify-center gap-2 p-12 text-fg-muted"
  >
    <span class="loading loading-md loading-spinner"></span>
    <span>Se încarcă seniorii…</span>
  </div>
{:else if seniors.load.kind === "error"}
  <p role="alert" class="m-4 border border-rosu bg-rosu/15 px-4 py-3 text-rosu-fg">
    {seniors.load.message}
  </p>
{:else}
  {#if seniors.load.error}
    <p role="alert" class="mx-4 mt-3 border border-galben bg-galben/15 px-4 py-2 text-galben-fg">
      {seniors.load.error}
    </p>
  {/if}
  <div class="flex min-h-0 flex-1 flex-col overflow-auto" role="table" aria-label="Seniori">
    <div
      role="row"
      class={["sn-label sticky top-0 z-[1] grid border-b-2 border-line bg-subtle", COLS]}
    >
      <div role="columnheader" class="border-r border-card px-3 py-[9px]"></div>
      <div role="columnheader" class="border-r border-card px-3 py-[9px]">Senior</div>
      <div role="columnheader" class="border-r border-card px-3 py-[9px]">Telefon</div>
      <div role="columnheader" class="border-r border-card px-3 py-[9px]">Stare înrolare</div>
      <div role="columnheader" class="px-3 py-[9px]">Acțiuni</div>
    </div>
    {#each shown as s, n (s.id)}
      {@const st = enrollment(s.enrollment_state)}
      <div role="row" class={["grid border-b border-line hover:bg-subtle", COLS]}>
        <div
          role="cell"
          class="border-r border-card px-3 py-2.5 font-mono text-[11px] text-fg-subtle"
        >
          {n + 1}
        </div>
        <div role="cell" class="flex min-w-0 flex-col gap-0.5 border-r border-card px-3 py-[7px]">
          <span class="text-[13.5px] leading-tight font-semibold">{s.full_name}</span>
          <span class="text-xs text-fg-muted">{s.form_of_address}</span>
        </div>
        <div role="cell" class="flex min-w-0 items-center gap-1.5 border-r border-card px-3 py-2">
          <span
            class="border border-line px-[5px] text-[9.5px] leading-[1.6] font-semibold tracking-[0.06em] text-fg-muted uppercase"
          >
            {s.phone_is_landline ? "fix" : "mobil"}
          </span>
          <a
            href={`tel:${s.phone_e164}`}
            class="font-mono text-[11.5px] text-fg-soft hover:text-link"
          >
            {formatPhone(s.phone_e164)}
          </a>
        </div>
        <div role="cell" class="flex min-w-0 items-center border-r border-card px-3 py-2">
          <span
            class={[
              "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-bold",
              TONE_CHIP[st.tone],
            ]}
          >
            <span class={["size-[7px]", TONE_DOT[st.tone]]}></span>{st.label}
          </span>
        </div>
        <div role="cell" class="flex items-center px-3 py-2">
          <button
            type="button"
            class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs"
            onclick={() => (selected = s)}
          >
            Vezi dosar
          </button>
        </div>
      </div>
    {:else}
      <p class="px-5 py-6 text-fg-muted">
        {query || tab !== "all"
          ? "Niciun senior nu corespunde căutării."
          : "Niciun senior înrolat."}
      </p>
    {/each}
  </div>
  <div
    class="flex flex-wrap items-center gap-4 border-t-2 border-line px-5 py-2.5 text-xs text-fg-muted"
  >
    <span>
      Afișez <span class="font-mono text-fg">{shown.length}</span> din {inCurrentTab.length} seniori
    </span>
    <span class="ml-auto"
      >Actualizat la <span class="font-mono">{clock.format(seniors.load.at)}</span></span
    >
  </div>
{/if}

{#if selected}
  {#key selected.id}
    <SeniorDetails senior={selected} onClose={() => (selected = null)} />
  {/key}
{/if}
