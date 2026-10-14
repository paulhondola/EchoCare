<script lang="ts">
  import { takeIncident, type Incident } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { initials, shortId, since } from "../../utils/incidents";
  import { time } from "../../utils/labels";
  import { refusalMessage } from "./commands";
  import type { DossierTab } from "./IncidentDetails.svelte";

  let {
    incident: i,
    now,
    onOpen,
    onChanged,
    onStale,
  }: {
    incident: Incident;
    now: number;
    onOpen: (tab: DossierTab) => void;
    onChanged: (incident: Incident) => void;
    onStale: () => void;
  } = $props();

  // Full class names, so Tailwind finds them in the source
  const BAR = { open: "bg-rosu", in_progress: "bg-galben", resolved: "bg-verde" };

  let busy = $state(false);
  let error = $state<string | null>(null);

  function take() {
    busy = true;
    error = null;
    takeIncident(i.id)
      .then(onChanged)
      .catch((e: unknown) => {
        error = refusalMessage(e, "take");
        onStale();
      })
      .finally(() => {
        busy = false;
      });
  }
</script>

<article class="relative flex border border-line bg-card hover:border-link">
  <div class={["w-[3px] flex-none", BAR[i.status]]}></div>
  <div class="flex min-w-0 flex-1 flex-col gap-[5px] px-3 pt-2.5 pb-3">
    <div class="flex items-center gap-1.5 text-[11.5px] text-fg-muted">
      <span class="font-mono">#{shortId(i.id)}</span>
      <span>·</span>
      {#if i.status === "resolved"}
        <span>deschis {time.format(Date.parse(i.opened_at))}</span>
      {:else if i.status === "in_progress" && i.taken_at}
        <span title={`Deschis ${time.format(Date.parse(i.opened_at))}`}>
          preluat {since(i.taken_at, now)}
        </span>
      {:else}
        <span title={time.format(Date.parse(i.opened_at))}>{since(i.opened_at, now)}</span>
      {/if}
      {#if i.status === "open"}
        <span class="ml-auto bg-rosu/15 px-[7px] py-0.5 text-[11px] font-semibold text-rosu-fg">
          {i.handover_answered ? "Transferat la DAS" : "Nepreluat"}
        </span>
      {:else if i.status === "in_progress"}
        <span class="ml-auto bg-galben/15 px-[7px] py-0.5 text-[11px] font-semibold text-galben-fg">
          Preluat
        </span>
      {/if}
    </div>

    <h3 class="text-[15px] leading-tight font-semibold">
      <!-- The name opens the dossier; its ::after covers the card so the whole card is the target -->
      <button
        type="button"
        class="cursor-pointer text-left after:absolute after:inset-0 after:content-['']"
        onclick={() => onOpen("access")}
      >
        {i.senior_full_name}
      </button>
      <span class="font-normal text-fg-muted">· {i.senior_form_of_address}</span>
    </h3>
    <div class={["font-semibold", i.status === "open" && "text-rosu-fg"]}>{i.reason}</div>

    <div class="mt-1 flex items-center gap-2 border-t border-line pt-2">
      {#if i.status === "open"}
        <button
          type="button"
          class="sn-btn sn-btn-danger relative z-10"
          disabled={busy}
          onclick={take}
        >
          <Icon name="zap" size={13} stroke={2.2} />Preiau
        </button>
        <span class="ml-auto flex items-center gap-[5px] text-xs text-fg-muted">
          <Icon name="user" size={13} />Nealocat
        </span>
      {:else if i.status === "in_progress"}
        <button
          type="button"
          class="sn-btn sn-btn-link relative z-10"
          onclick={() => onOpen("resolve")}
        >
          Rezolvă cazul
        </button>
        <span class="ml-auto flex items-center gap-1.5 text-xs text-fg-soft">
          <span class="grid size-5 place-items-center bg-line text-[9px] font-extrabold text-fg">
            {initials(i.taken_by_name)}
          </span>
          {i.taken_by_name}
        </span>
      {:else}
        <span
          class="inline-flex items-center gap-1.5 bg-verde/15 px-2 py-[3px] text-xs font-semibold text-verde-fg"
        >
          <Icon name="check" size={12} stroke={2.6} />Rezolvat
        </span>
        {#if i.taken_by_name}
          <span class="ml-auto text-xs text-fg-muted">Preluat de {i.taken_by_name}</span>
        {/if}
      {/if}
    </div>

    {#if error}
      <p role="alert" class="text-xs text-rosu-fg">{error}</p>
    {/if}
  </div>
</article>
