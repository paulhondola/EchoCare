<script lang="ts">
  import { fade } from "svelte/transition";
  import type { IncidentCall } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { clock, code, TONE_TEXT } from "../../utils/labels";
  import { alarmWords, highlight } from "../../utils/live";

  // One call's summary, every turn in the order it was said, the codes it reported and how it ended
  // `live`: new lines fade in and a typing indicator waits under the last (design 2026-11-14 §4)
  let { call, live = false }: { call: IncidentCall; live?: boolean } = $props();
  const final = $derived(code(call.final_severity));

  // Who said each line (05 §1); `das` is the employee after a hand-over (04 §4.4)
  const SPEAKERS: Record<string, { label: string; text: string }> = {
    senior: { label: "Senior", text: "text-fg-muted" },
    agent: { label: "Sistem AI", text: "text-link" },
    das: { label: "Operator DAS", text: "text-fg" },
  };
  const SYSTEM = { label: "Sistem", text: "text-fg-muted" };

  // The senior's words behind each alarm, lit inside the turn that said them. Words found in
  // no turn light the senior's last turn before the alarm, whole.
  const marks = $derived.by(() => {
    const out = new Map<number, [string, string, string] | "whole">();
    for (const r of call.reports) {
      if (r.source !== "alarm_tier1" && r.source !== "alarm_tier2") continue;
      const words = alarmWords(r);
      const hit = words
        ? call.turns.findIndex((t) => t.speaker === "senior" && highlight(t.content, words))
        : -1;
      if (hit >= 0) {
        out.set(hit, highlight(call.turns[hit].content, words!)!);
        continue;
      }
      const before = call.turns.findLastIndex(
        (t) => t.speaker === "senior" && Date.parse(t.at) <= Date.parse(r.at),
      );
      if (before >= 0 && !out.has(before)) out.set(before, "whole");
    }
    return out;
  });
</script>

{#if call.summary}
  <p class="text-fg-soft">{call.summary}</p>
{/if}

{#each call.turns as t, n (n)}
  {@const who = SPEAKERS[t.speaker] ?? SYSTEM}
  {@const mark = marks.get(n)}
  <div
    class="grid grid-cols-[70px_minmax(0,1fr)] gap-x-3 gap-y-1"
    in:fade={{ duration: live ? 350 : 0 }}
  >
    <span class="pt-0.5 font-mono text-xs font-medium text-fg-muted">
      {clock.format(Date.parse(t.at))}
    </span>
    <div class="flex flex-col gap-0.5">
      <span class={["sn-label", who.text]}>{who.label}</span>
      {#if t.kind === "keys"}
        <span>tasta {t.content}</span>
      {:else if mark === "whole"}
        <span><mark class="bg-rosu/25 text-fg">„{t.content}”</mark></span>
      {:else if mark}
        <span
          >„{mark[0]}<mark class="bg-rosu/25 font-semibold text-fg">{mark[1]}</mark>{mark[2]}”</span
        >
      {:else}
        <span>„{t.content}”</span>
      {/if}
    </div>
  </div>
{:else}
  <p class="text-fg-muted">{live ? "Se așteaptă primul cuvânt…" : "Nicio replică înregistrată."}</p>
{/each}

{#if live}
  <div class="grid grid-cols-[70px_minmax(0,1fr)] gap-x-3" aria-hidden="true">
    <span></span>
    <span class="flex gap-1 py-1">
      <span class="sn-pulse size-1.5 rounded-full bg-fg-muted"></span>
      <span class="sn-pulse size-1.5 rounded-full bg-fg-muted [animation-delay:150ms]"></span>
      <span class="sn-pulse size-1.5 rounded-full bg-fg-muted [animation-delay:300ms]"></span>
    </span>
  </div>
{/if}

{#each call.reports as r, n (n)}
  {@const level = code(r.severity)}
  <div
    class="-mx-5 grid grid-cols-[70px_minmax(0,1fr)] gap-x-3 gap-y-1 border-y border-line bg-card px-5 py-2.5"
  >
    <span class="pt-0.5 font-mono text-xs font-medium text-fg-muted">
      {clock.format(Date.parse(r.at))}
    </span>
    <div class="flex flex-col gap-0.5">
      <span class={["sn-label", level && TONE_TEXT[level.tone]]}>
        {level?.label ?? r.severity} · semnalat
      </span>
      {#if r.quote}<span class="text-sm">„{r.quote}”</span>{/if}
      <span class="text-fg-soft">{r.reason}</span>
    </div>
  </div>
{/each}

{#if final}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-t-2 border-line pt-3.5">
    <span class="sn-label">Severitate finală</span>
    <span class={["font-semibold", TONE_TEXT[final.tone]]}>
      {final.label}
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
