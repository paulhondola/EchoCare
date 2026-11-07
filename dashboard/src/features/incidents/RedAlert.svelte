<script lang="ts">
  import { takeIncident, type Incident } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { since } from "../../utils/incidents";
  import { getLive } from "../shell/live.svelte";
  import { refusalMessage } from "./commands";

  // The Shell keys this by incident, so a refusal never shows next to another senior's case
  let { incident, now }: { incident: Incident; now: number } = $props();

  const live = getLive();
  const others = $derived((live.open?.length ?? 1) - 1);

  let busy = $state(false);
  let error = $state<string | null>(null);

  function take() {
    busy = true;
    error = null;
    takeIncident(incident.id)
      .then(live.incidentChanged)
      .catch((e: unknown) => {
        error = refusalMessage(e, "take");
        live.incidents.reload();
      })
      .finally(() => {
        busy = false;
      });
  }
</script>

<!-- Cod Roșu: the longest-waiting open incident, above every page (UC-11, spec 07 §1) -->
<section
  aria-label="Cod Roșu"
  class="flex flex-wrap items-center gap-3 border-b-2 border-rosu bg-rosu-strong/20 px-5 py-2.5"
>
  <span class={["size-2.5 flex-none bg-rosu", live.sound && "sn-pulse"]}></span>
  <div class="flex min-w-0 flex-1 flex-wrap items-baseline gap-2">
    <span class="font-extrabold tracking-[0.06em] text-rosu-fg">COD ROȘU</span>
    <span class="font-semibold">{incident.senior_full_name} — {incident.reason}</span>
    <span class="text-fg-soft">deschis {since(incident.opened_at, now)}</span>
    {#if others > 0}
      <span class="text-fg-soft">· încă {others} deschise</span>
    {/if}
  </div>
  {#if error}
    <span role="alert" class="text-rosu-fg">{error}</span>
  {/if}
  <button type="button" class="sn-btn sn-btn-danger" disabled={busy} onclick={take}>
    <Icon name="zap" size={13} stroke={2.2} />Preiau cazul
  </button>
  <button
    type="button"
    class="sn-btn sn-btn-outline"
    onclick={() => (live.dossier = { id: incident.id, tab: "access" })}
  >
    Vezi dosar
  </button>
</section>
