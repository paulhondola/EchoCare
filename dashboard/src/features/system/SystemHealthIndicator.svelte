<script lang="ts">
  import { fetchSystemHealth } from "../../services/api";
  import { poll } from "../../utils/poll.svelte";

  const REFRESH_MS = 30_000;

  function describe(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  const poller = poll(fetchSystemHealth, REFRESH_MS, describe);
</script>

{#if poller.load.kind === "ok"}
  {@const h = poller.load.data}
  {@const isOk = h.status === "ok" && h.database.status === "ok"}
  <span
    class="flex items-center gap-1.5 rounded-full bg-base-200 px-2.5 py-0.5 text-xs text-base-content/80 font-mono"
    title={`Mediu: ${h.env} · DB: ${h.database.status} (${h.database.latency_ms ?? "—"} ms)`}
  >
    <span
      class={["inline-block size-2 rounded-full", isOk ? "bg-success" : "bg-error animate-pulse"]}
    ></span>
    <span>{isOk ? "Sistem OK" : "Degradat"}</span>
    {#if h.database.latency_ms !== null}
      <span class="text-base-content/40 text-[10px]">{Math.round(h.database.latency_ms)}ms</span>
    {/if}
  </span>
{:else if poller.load.kind === "error"}
  <span
    class="flex items-center gap-1.5 rounded-full bg-error/10 px-2.5 py-0.5 text-xs text-error font-mono"
    title={poller.load.message}
  >
    <span class="inline-block size-2 rounded-full bg-error animate-pulse"></span>
    <span>Eroare conexiune</span>
  </span>
{/if}
