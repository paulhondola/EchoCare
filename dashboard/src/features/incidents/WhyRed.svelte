<script lang="ts">
  import { fetchTranscript, type IncidentDetail, type TranscriptCall } from "../../services/api";
  import { decidingCall } from "../../utils/incidents";
  import { code, REPORT_SOURCES, TONE_CHIP, TONE_TEXT, TRIGGERS } from "../../utils/labels";
  import { alarmWords } from "../../utils/live";

  // „De ce cod roșu?”: the chain from the senior's words to the code (design 2026-11-14 §5).
  // It only shows what the server stored; the rules decided, the model may only raise (G10).
  let { detail, events }: { detail: IncidentDetail; events: Record<string, string> } = $props();

  const call = $derived(decidingCall(detail.calls));
  let answers = $state<TranscriptCall["answers"]>([]);

  $effect(() => {
    const id = call?.id;
    if (!id) return;
    const ctrl = new AbortController();
    fetchTranscript(id, ctrl.signal)
      .then((t) => (answers = t.answers))
      .catch(() => {}); // the card shows the steps it has without them
    return () => ctrl.abort();
  });

  const QUESTIONS: Record<string, string> = {
    feeling: "Cum se simte",
    orientation: "Ce zi este",
    shelter: "Apă și adăpost",
  };
  // Stored answer values (05 §2); day names are already Romanian
  const VALUES: Record<string, string> = {
    ok: "bine",
    unwell: "rău",
    yes: "da",
    no: "nu",
    unknown: "neclar",
  };
  const LEVELS = ["green", "yellow", "red"] as const;
  const CERTAINTIES = ["high", "medium", "low"] as const;
  const CERTAINTY_LABELS: Record<string, string> = {
    high: "sigur",
    medium: "parțial",
    low: "nesigur",
  };

  const alarms = $derived(
    (call?.reports ?? [])
      .filter((r) => r.source === "alarm_tier1" || r.source === "alarm_tier2")
      .map((r) => ({ r, words: alarmWords(r) })),
  );
  const final = $derived(code(call?.final_severity));
</script>

{#if call}
  <section class="mb-5 flex flex-col gap-3 border-2 border-rosu/40 bg-rosu/5 px-4 py-3.5">
    <h3 class="text-sm font-extrabold tracking-[0.04em] text-rosu-fg uppercase">De ce cod roșu?</h3>
    <ol class="flex flex-col gap-3 text-sm">
      <li class="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
        <span class="font-mono text-fg-muted">1</span>
        <div>
          <span class="sn-label">Declanșator</span>
          <div>
            {TRIGGERS[call.trigger] ?? call.trigger}{#if detail.event}
              · {events[detail.event.type] ?? detail.event.type}{/if}
          </div>
        </div>
      </li>

      {#if answers.length > 0}
        <li class="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
          <span class="font-mono text-fg-muted">2</span>
          <div class="flex flex-col gap-1">
            <span class="sn-label">Ce a spus</span>
            {#each answers as a (a.field + a.at)}
              <div class="flex flex-wrap items-baseline gap-x-2">
                <span class="text-fg-muted">{QUESTIONS[a.field] ?? a.field}:</span>
                <span class="font-semibold">{VALUES[a.value] ?? a.value}</span>
                {#if !a.clear}
                  <span class="bg-galben/15 px-1.5 text-[11px] font-semibold text-galben-fg">
                    neclar
                  </span>
                {/if}
                {#if a.quote}<span class="text-fg-soft">„{a.quote}”</span>{/if}
              </div>
            {/each}
          </div>
        </li>
      {/if}

      {#if alarms.length > 0}
        <li class="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
          <span class="font-mono text-fg-muted">3</span>
          <div class="flex flex-col gap-1">
            <span class="sn-label">Frază de alarmă</span>
            {#each alarms as { r, words }, n (n)}
              <div>
                <span class="font-semibold text-rosu-fg">{REPORT_SOURCES[r.source]}</span>
                {#if words}
                  · <mark class="bg-rosu/25 font-semibold text-fg">„{words}”</mark>
                {:else}
                  · <span class="text-fg-soft">{r.reason}</span>
                {/if}
              </div>
            {/each}
          </div>
        </li>
      {/if}

      {#if call.final_severity}
        <li class="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
          <span class="font-mono text-fg-muted">4</span>
          <div class="flex flex-col gap-1.5">
            <span class="sn-label">Severitate × certitudine</span>
            <div
              class="grid w-fit grid-cols-[auto_repeat(3,64px)] gap-px bg-line text-center text-[11px]"
            >
              <span class="bg-subtle"></span>
              {#each CERTAINTIES as c (c)}
                <span class="bg-subtle px-1 py-1 text-fg-muted">{CERTAINTY_LABELS[c]}</span>
              {/each}
              {#each [...LEVELS].reverse() as l (l)}
                {@const tone = code(l)?.tone ?? "muted"}
                <span class={["bg-subtle px-2 py-1 text-left", TONE_TEXT[tone]]}
                  >{code(l)?.label}</span
                >
                {#each CERTAINTIES as c (c)}
                  {@const lit =
                    l === call.final_severity &&
                    (call.final_certainty === null || c === call.final_certainty)}
                  <span class={["py-1", lit ? ["font-bold", TONE_CHIP[tone]] : "bg-card"]}>
                    {lit ? "●" : ""}
                  </span>
                {/each}
              {/each}
            </div>
          </div>
        </li>
      {/if}

      {#if final}
        <li class="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
          <span class="font-mono text-fg-muted">5</span>
          <div class="flex flex-col gap-0.5">
            <span class="sn-label">Rezultat</span>
            <span>
              <span class={["font-bold", TONE_TEXT[final.tone]]}>{final.label}</span>
              {#if call.reason}<span class="text-fg-soft"> · {call.reason}</span>{/if}
            </span>
            <span class="text-xs text-fg-muted">
              Regulile fixe decid. Modelul poate doar ridica nivelul, niciodată coborî.
            </span>
          </div>
        </li>
      {/if}
    </ol>
  </section>
{/if}
