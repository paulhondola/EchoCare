<script lang="ts">
  import { TRIGGERS } from "../../utils/labels";
  import { getLive } from "../shell/live.svelte";

  // The calls ringing or talking now, one chip each, over every page (design 2026-11-14 §4)
  const live = getLive();
  const calls = $derived(live.liveCalls.load.kind === "ok" ? live.liveCalls.load.data : []);

  // A second hand for the chips' running time
  let now = $state(Date.now());
  $effect(() => {
    if (calls.length === 0) return;
    const t = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(t);
  });

  function elapsed(from: string | null): string {
    if (!from) return "sună";
    const s = Math.max(0, Math.floor((now - Date.parse(from)) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
</script>

{#if calls.length > 0}
  <div
    class="flex flex-wrap items-center gap-2 border-b-2 border-line bg-subtle px-5 py-2"
    aria-live="polite"
  >
    {#each calls as c (c.id)}
      <button
        type="button"
        class="inline-flex cursor-pointer items-center gap-2 border border-link/50 bg-link/10 px-2.5 py-1 text-xs hover:border-link"
        onclick={() => (live.liveCall = c.id)}
      >
        <span class="sn-pulse size-2 rounded-full bg-link"></span>
        <span class="font-semibold text-fg">Apel în desfășurare</span>
        <span class="text-fg-soft">· {c.senior_name} · {TRIGGERS[c.trigger] ?? c.trigger} ·</span>
        <span class="font-mono text-fg">{elapsed(c.started_at)}</span>
      </button>
    {/each}
  </div>
{/if}
