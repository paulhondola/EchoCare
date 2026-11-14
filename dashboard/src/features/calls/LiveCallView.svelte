<script lang="ts">
  import { onMount, tick } from "svelte";
  import { fetchTranscript, type IncidentCall, type LiveCall } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { code, TONE_TEXT, TRIGGERS } from "../../utils/labels";
  import { currentCode, liveCallDone } from "../../utils/live";
  import { getLive } from "../shell/live.svelte";
  import CallTranscript from "./CallTranscript.svelte";

  // One call as it happens: its lines every second until it leaves the live list
  // (design 2026-11-14 §4)
  let { id, onClose }: { id: string; onClose: () => void } = $props();
  const live = getLive();

  let dialogEl: HTMLDialogElement | undefined = $state();
  let scroller: HTMLDivElement | undefined = $state();
  let call = $state<IncidentCall | null>(null);
  let error = $state<string | null>(null);

  const liveList = $derived(live.liveCalls.load.kind === "ok" ? live.liveCalls.load.data : null);
  // The strip's row, kept once the call ends so the header still names her
  let row = $state<LiveCall | null>(null);
  $effect(() => {
    const found = liveList?.find((c) => c.id === id);
    if (found) row = found;
  });
  const done = $derived(liveList !== null && liveCallDone(id, liveList));
  const level = $derived(call ? currentCode(call, row?.starting_severity ?? "green") : null);
  const chip = $derived(code(level));
  // Her open incident, once a red opened one; the incident list names seniors, not ids
  const incident = $derived(
    level === "red" && row && live.incidents.load.kind === "ok"
      ? live.incidents.load.data.find(
          (i) => i.status !== "resolved" && i.senior_full_name === row?.senior_name,
        )
      : undefined,
  );

  onMount(() => {
    if (dialogEl && !dialogEl.open) dialogEl.showModal();
  });

  // Every second while live, then one last read once it has ended
  $effect(() => {
    const ended = done;
    let stop = false;
    const ctrl = new AbortController();
    async function read() {
      try {
        call = await fetchTranscript(id, ctrl.signal);
        error = null;
      } catch (e) {
        if (!ctrl.signal.aborted) error = e instanceof Error ? e.message : String(e);
      }
      if (!stop && !ended) timer = setTimeout(read, 1000);
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    void read();
    return () => {
      stop = true;
      ctrl.abort();
      clearTimeout(timer);
    };
  });

  // Keep the newest line in view
  $effect(() => {
    void call?.turns.length;
    void tick().then(() => scroller?.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" }));
  });

  function openIncident() {
    if (!incident) return;
    live.dossier = { id: incident.id, tab: "access" };
    dialogEl?.close();
  }
</script>

<dialog bind:this={dialogEl} class="modal modal-end" aria-labelledby="live-title" onclose={onClose}>
  <div
    class="modal-box flex h-full w-[540px] max-w-full flex-col border-l-2 border-line bg-subtle p-0 text-fg shadow-[-24px_0_48px_rgba(1,4,9,.55)]"
  >
    <div class="flex flex-col gap-2.5 border-b-2 border-line px-5 py-4">
      <div class="flex items-center gap-2.5 text-xs text-fg-muted">
        {#if done}
          <span>Apel încheiat</span>
        {:else}
          <span class="inline-flex items-center gap-1.5 font-semibold text-link">
            <span class="sn-pulse size-2 rounded-full bg-link"></span>În desfășurare
          </span>
        {/if}
        {#if row}<span>· {TRIGGERS[row.trigger] ?? row.trigger}</span>{/if}
        <button
          type="button"
          title="Închide"
          aria-label="Închide"
          class="ml-auto grid size-[30px] cursor-pointer place-items-center border border-line text-fg-soft hover:border-fg-muted hover:text-fg"
          onclick={() => dialogEl?.close()}
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <h2 id="live-title" class="text-2xl leading-[1.1] font-extrabold tracking-[-0.015em]">
          {row?.senior_name ?? "Apel"}
        </h2>
        {#if chip}
          {#key chip.label}
            <span
              class={[
                "live-code border-2 px-2.5 py-0.5 text-xs font-bold tracking-[0.06em] uppercase",
                TONE_TEXT[chip.tone],
              ]}
            >
              {chip.label}
            </span>
          {/key}
        {/if}
      </div>
      {#if done && incident}
        <button
          type="button"
          class="sn-btn sn-btn-danger h-[34px] self-start px-3.5"
          onclick={openIncident}
        >
          <Icon name="arrow-right" size={13} />Deschide incidentul
        </button>
      {/if}
    </div>

    <div bind:this={scroller} class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
      {#if error && !call}
        <p role="alert" class="text-rosu-fg">Nu am putut citi apelul ({error}).</p>
      {:else if call}
        <CallTranscript {call} live={!done} />
      {:else}
        <span class="loading loading-sm loading-spinner text-fg-muted"></span>
      {/if}
    </div>
  </div>
</dialog>

<style>
  /* The code chip arrives with a short pop each time the code changes */
  .live-code {
    animation: live-code-pop 450ms ease-out;
  }
  @keyframes live-code-pop {
    0% {
      transform: scale(1.35);
      opacity: 0;
    }
    100% {
      transform: scale(1);
      opacity: 1;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-code {
      animation: none;
    }
  }
</style>
