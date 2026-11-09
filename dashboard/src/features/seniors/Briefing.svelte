<script lang="ts">
  import type { SummaryVersion } from "../../services/api";
  import { citedOn, DIRECTION } from "../../utils/briefing";
  import { time } from "../../utils/labels";

  let {
    summary,
    calls = [],
  }: { summary: SummaryVersion | null; calls?: { id: string; started_at: string | null }[] } =
    $props();
  // The date of the call the version follows; the version's own time until the calls arrive
  const after = $derived(
    calls.find((c) => c.id === summary?.call_id)?.started_at ?? summary?.created_at ?? "",
  );
</script>

{#snippet quote(text: string, callId: string)}
  <blockquote class="border-l-2 border-line pl-3 text-[13px] text-fg-muted">
    „{text}” <span class="font-mono text-xs">· {citedOn(callId, calls)}</span>
  </blockquote>
{/snippet}

{#if !summary}
  <p class="text-fg-muted">Niciun rezumat încă.</p>
{:else}
  {@const c = summary.content}
  <section class="flex flex-col gap-3 border border-line bg-card p-4" aria-label="Rezumat">
    <div class="sn-label">Pe scurt</div>
    <p>{c.narrative}</p>

    {#if c.follow_ups.length}
      <div class="sn-label pt-2">Subiecte deschise</div>
      {#each c.follow_ups as f, i (i)}
        <div class="flex flex-col gap-1">
          <span class="font-semibold">{f.topic}</span>
          {@render quote(f.quote, f.call_id)}
        </div>
      {/each}
    {/if}

    {#if c.how_to_talk.length}
      <div class="sn-label pt-2">Cum vorbim</div>
      <ul class="list-disc pl-5">
        {#each c.how_to_talk as note, i (i)}<li>{note}</li>{/each}
      </ul>
    {/if}

    {#if c.trends.length}
      <div class="sn-label pt-2">Observații</div>
      {#each c.trends as t, i (i)}
        <div class="flex flex-col gap-1">
          <span>
            {t.note}
            <span class="text-xs font-semibold text-fg-muted">· {DIRECTION[t.direction]}</span>
          </span>
          {#each t.evidence as e, j (j)}{@render quote(e.quote, e.call_id)}{/each}
        </div>
      {/each}
    {/if}

    <p class="border-t border-line pt-2 text-xs text-fg-muted">
      Rezumat după apelul din {time.format(Date.parse(after))}
    </p>
  </section>
{/if}
