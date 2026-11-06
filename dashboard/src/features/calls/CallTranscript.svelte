<script lang="ts">
  import type { IncidentCall } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { clock } from "../../utils/labels";

  // One call's summary, every turn in the order it was said, the codes it reported and how it ended
  let { call }: { call: IncidentCall } = $props();

  const SEVERITY: Record<string, { label: string; text: string }> = {
    red: { label: "Cod Roșu", text: "text-rosu-fg" },
    yellow: { label: "Cod Galben", text: "text-galben-fg" },
    green: { label: "Cod Verde", text: "text-verde-fg" },
  };
  // Who said each line (05 §1); `das` is the employee after a hand-over (04 §4.4)
  const SPEAKERS: Record<string, { label: string; text: string }> = {
    senior: { label: "Senior", text: "text-fg-muted" },
    agent: { label: "Sistem AI", text: "text-link" },
    das: { label: "Operator DAS", text: "text-fg" },
  };
  const SYSTEM = { label: "Sistem", text: "text-fg-muted" };
</script>

{#if call.summary}
  <p class="text-fg-soft">{call.summary}</p>
{/if}

{#each call.turns as t, n (n)}
  {@const who = SPEAKERS[t.speaker] ?? SYSTEM}
  <div class="grid grid-cols-[70px_minmax(0,1fr)] gap-x-3 gap-y-1">
    <span class="pt-0.5 font-mono text-xs font-medium text-fg-muted">
      {clock.format(Date.parse(t.at))}
    </span>
    <div class="flex flex-col gap-0.5">
      <span class={["sn-label", who.text]}>{who.label}</span>
      <span>{t.kind === "keys" ? `tasta ${t.content}` : `„${t.content}”`}</span>
    </div>
  </div>
{:else}
  <p class="text-fg-muted">Nicio replică înregistrată.</p>
{/each}

{#each call.reports as r, n (n)}
  <div
    class="-mx-5 grid grid-cols-[70px_minmax(0,1fr)] gap-x-3 gap-y-1 border-y border-line bg-card px-5 py-2.5"
  >
    <span class="pt-0.5 font-mono text-xs font-medium text-fg-muted">
      {clock.format(Date.parse(r.at))}
    </span>
    <div class="flex flex-col gap-0.5">
      <span class={["sn-label", SEVERITY[r.severity]?.text ?? "text-fg-muted"]}>
        {SEVERITY[r.severity]?.label ?? r.severity} · semnalat
      </span>
      {#if r.quote}<span class="text-sm">„{r.quote}”</span>{/if}
      <span class="text-fg-soft">{r.reason}</span>
    </div>
  </div>
{/each}

{#if call.final_severity}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-t-2 border-line pt-3.5">
    <span class="sn-label">Severitate finală</span>
    <span class={["font-semibold", SEVERITY[call.final_severity]?.text]}>
      {SEVERITY[call.final_severity]?.label ?? call.final_severity}
    </span>
  </div>
{/if}
{#if call.handover_answered !== null}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3">
    <span class="sn-label">Predare audio</span>
    {#if call.handover_answered}
      <span class="inline-flex items-center gap-1.5 font-semibold text-verde-fg">
        <Icon name="check" size={13} stroke={2.4} />
        Transferat cu succes la telefonul de serviciu DAS
      </span>
    {:else}
      <span class="font-semibold text-rosu-fg">Transferul nu a fost preluat</span>
    {/if}
  </div>
{/if}
