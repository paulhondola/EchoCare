<script lang="ts">
  import { getLive } from "../shell/live.svelte";

  const live = getLive();

  // "2.1 ms" under ten, whole milliseconds above
  const ms = (v: number) => `${v < 10 ? v.toFixed(1) : Math.round(v)} ms`;
</script>

<!-- The sidebar's system line (04 §1 System health) -->
<div class="mt-2.5 flex items-center gap-[7px] text-xs">
  {#if live.health.load.kind === "ok"}
    {@const h = live.health.load.data}
    {@const isOk = h.status === "ok" && h.database.status === "ok"}
    <span
      class={["size-2", isOk ? "bg-verde shadow-[0_0_8px_rgba(63,185,80,.7)]" : "sn-pulse bg-rosu"]}
    ></span>
    <span title={`Mediu: ${h.env} · Bază de date: ${h.database.status}`}>
      {isOk ? "Sistem activ" : "Sistem degradat"}
    </span>
    {#if h.database.latency_ms !== null}
      <span class="ml-auto font-mono text-[11px] text-fg-muted">{ms(h.database.latency_ms)}</span>
    {/if}
  {:else if live.health.load.kind === "error"}
    <span class="sn-pulse size-2 bg-rosu"></span>
    <span title={live.health.load.message}>Fără conexiune la API</span>
  {:else}
    <span class="size-2 bg-fg-subtle"></span>
    <span class="text-fg-muted">Se verifică…</span>
  {/if}
</div>
