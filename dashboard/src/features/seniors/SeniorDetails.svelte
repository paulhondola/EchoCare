<script lang="ts">
  import { onMount } from "svelte";
  import {
    ApiError,
    eraseSenior,
    exportSenior,
    fetchCalls,
    fetchMedicalRecord,
    fetchSenior,
    fetchSummary,
    fetchTranscript,
    type CallSummary,
    type IncidentCall,
    type MedicalRecord as MedicalRecordData,
    type SeniorSummary,
    type SeniorView,
    type SummaryVersion,
  } from "../../services/api";
  import CopyButton from "../../ui/CopyButton.svelte";
  import Icon from "../../ui/Icon.svelte";
  import {
    address,
    CALL_STATES,
    callLength,
    code,
    enrollment,
    time,
    TONE_CHIP,
    TONE_DOT,
    TRIGGERS,
  } from "../../utils/labels";
  import { downloadJson, eraseRefusalText } from "../../utils/erase";
  import { formatPhone } from "../../utils/phone";
  import { tabKeydown } from "../../utils/tabs";
  import CallTranscript from "../calls/CallTranscript.svelte";
  import Briefing from "./Briefing.svelte";
  import MedicalRecord from "./MedicalRecord.svelte";
  import WatchHealth from "./WatchHealth.svelte";

  let {
    senior: summary,
    onClose,
    onErased,
  }: { senior: SeniorSummary; onClose: () => void; onErased: () => void } = $props();

  // Șterge toate datele (04 §2, design 2026-11-14): asked once more in the panel, never by confirm()
  let confirmingErase = $state(false);
  let erasing = $state(false);
  let eraseError = $state<string | null>(null);
  let exporting = $state(false);
  let exportError = $state<string | null>(null);

  async function downloadExport() {
    exporting = true;
    exportError = null;
    try {
      const data = await exportSenior(summary.id, reads.signal);
      downloadJson(`echocare-senior-${summary.id}.json`, data);
    } catch (err) {
      if (!reads.signal.aborted) exportError = failed("exportul datelor", err);
    } finally {
      exporting = false;
    }
  }

  async function erase() {
    erasing = true;
    eraseError = null;
    try {
      await eraseSenior(summary.id);
      onErased();
    } catch (err) {
      const reason = err instanceof ApiError ? err.reason : undefined;
      // Someone else erased the senior first: the outcome is the same
      if (reason === "not_found") return onErased();
      eraseError = eraseRefusalText(reason);
    } finally {
      erasing = false;
    }
  }

  type Load<T> = { kind: "loading" } | { kind: "ok"; data: T } | { kind: "error"; message: string };

  const TABS = [
    { key: "file", label: "Dosar" },
    { key: "calls", label: "Apeluri" },
  ] as const;

  let load = $state<Load<SeniorView>>({ kind: "loading" });
  let tab = $state<(typeof TABS)[number]["key"]>("file");
  const TAB_KEYS = TABS.map((t) => t.key);
  const select = (key: (typeof TABS)[number]["key"]) =>
    key === "calls" ? showCalls() : (tab = key);
  // Read again each time the tab is opened, and each transcript each time its call is,
  // so a live call or hand-over is current; the last good read shows meanwhile
  // ponytail: re-read on open, not a timer; poll() the expanded call if DAS needs it live
  let calls = $state<Load<CallSummary[]> | null>(null);
  // null until read; the briefing's citations are dated from `calls`
  let briefing = $state<Load<SummaryVersion | null>>({ kind: "loading" });
  let medical = $state<Load<MedicalRecordData | null>>({ kind: "loading" });
  let transcripts = $state<Record<string, Load<IncidentCall>>>({});
  let expanded = $state<string | null>(null);
  let dialogEl: HTMLDialogElement | undefined = $state();
  // Every read stops when the slide-over closes
  const reads = new AbortController();

  const failed = (what: string, e: unknown) =>
    `Nu am putut citi ${what} (${e instanceof Error ? e.message : String(e)}).`;

  function showCalls() {
    tab = "calls";
    if (calls?.kind === "loading") return;
    if (calls?.kind !== "ok") calls = { kind: "loading" };
    fetchCalls(summary.id, reads.signal)
      .then((data) => {
        calls = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (!reads.signal.aborted) calls = { kind: "error", message: failed("apelurile", e) };
      });
  }

  function toggle(id: string) {
    expanded = expanded === id ? null : id;
    if (expanded === null || transcripts[id]?.kind === "loading") return;
    if (transcripts[id]?.kind !== "ok") transcripts[id] = { kind: "loading" };
    fetchTranscript(id, reads.signal)
      .then((data) => {
        transcripts[id] = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (!reads.signal.aborted)
          transcripts[id] = { kind: "error", message: failed("transcrierea", e) };
      });
  }

  const stage = $derived(enrollment(summary.enrollment_state));
  // The dossier's read is newer than the list's, so its code wins once it has arrived
  const current = $derived(load.kind === "ok" ? load.data : summary);
  const codeChip = $derived(code(current.code));

  onMount(() => {
    if (dialogEl && !dialogEl.open) dialogEl.showModal();
    fetchSenior(summary.id, reads.signal)
      .then((data) => {
        load = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (!reads.signal.aborted) load = { kind: "error", message: failed("dosarul", e) };
      });
    fetchSummary(summary.id, reads.signal)
      .then((data) => {
        briefing = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (!reads.signal.aborted) briefing = { kind: "error", message: failed("rezumatul", e) };
      });
    const readMedical = () =>
      fetchMedicalRecord(summary.id, reads.signal)
        .then((data) => {
          medical = { kind: "ok", data };
        })
        .catch((e: unknown) => {
          if (!reads.signal.aborted)
            medical = { kind: "error", message: failed("fișa medicală", e) };
        });
    readMedical();
    // The PDF link is presigned for 10 minutes: read a fresh one before it lapses
    const relink = setInterval(readMedical, 9 * 60_000);
    // Dates the briefing's citations; a failure shows as the Apeluri tab's error
    calls = { kind: "loading" };
    fetchCalls(summary.id, reads.signal)
      .then((data) => {
        calls = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (!reads.signal.aborted) calls = { kind: "error", message: failed("apelurile", e) };
      });
    return () => {
      clearInterval(relink);
      reads.abort();
    };
  });
</script>

{#snippet row(label: string, value: string | null)}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-b border-line py-3.5">
    <span class="sn-label">{label}</span>
    <span>{value || "—"}</span>
  </div>
{/snippet}

<dialog
  bind:this={dialogEl}
  class="modal modal-end"
  aria-labelledby="senior-title"
  onclose={onClose}
>
  <div
    class="modal-box flex h-full w-[540px] max-w-full flex-col border-l-2 border-line bg-subtle p-0 text-fg shadow-[-24px_0_48px_rgba(1,4,9,.55)]"
  >
    <div class="flex flex-col gap-2.5 border-b-2 border-line px-5 py-4">
      <div class="flex items-center gap-2.5">
        <span
          class={[
            "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
            TONE_CHIP[stage.tone],
          ]}
        >
          <span class={["size-1.5", TONE_DOT[stage.tone]]}></span>{stage.label}
        </span>
        {#if codeChip}
          <span
            class={[
              "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
              TONE_CHIP[codeChip.tone],
            ]}
          >
            <span class={["size-1.5", TONE_DOT[codeChip.tone]]}></span>{codeChip.label}
          </span>
          {#if current.reason}
            <span class="text-[13px] text-fg-muted">{current.reason}</span>
          {/if}
        {/if}
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
      <div class="flex flex-wrap items-baseline gap-2.5">
        <h2 id="senior-title" class="text-2xl leading-[1.1] font-extrabold tracking-[-0.015em]">
          {summary.full_name}
        </h2>
        <span class="text-[13px] text-fg-muted">{summary.form_of_address}</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <a href={`tel:${summary.phone_e164}`} class="sn-btn h-[34px] px-3.5">
          <Icon name="phone" size={13} />Apelează senior
        </a>
        {#if load.kind === "ok"}
          <CopyButton
            class="h-[34px] px-3.5"
            icon="copy"
            label="Copiază adresa"
            text={address(load.data)}
          />
        {/if}
      </div>
    </div>

    <div class="flex border-b-2 border-line px-3" role="tablist" aria-label="Senior">
      {#each TABS as t (t.key)}
        <button
          type="button"
          role="tab"
          id={`senior-tab-${t.key}`}
          data-tab={t.key}
          aria-selected={tab === t.key}
          aria-controls="senior-panel"
          tabindex={tab === t.key ? 0 : -1}
          onkeydown={tabKeydown(TAB_KEYS, tab, select)}
          class={[
            "-mb-0.5 flex cursor-pointer items-center gap-1.5 border-b-2 px-2.5 py-[11px] text-[12.5px] font-semibold",
            tab === t.key
              ? "border-link text-fg"
              : "border-transparent text-fg-muted hover:text-fg",
          ]}
          onclick={() => select(t.key)}
        >
          {t.label}
        </button>
      {/each}
    </div>

    <div
      id="senior-panel"
      class="min-h-0 flex-1 overflow-auto px-5 pt-[18px] pb-6"
      role="tabpanel"
      aria-labelledby={`senior-tab-${tab}`}
    >
      {#if tab === "calls"}
        {#if !calls || calls.kind === "loading"}
          <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
            <span class="loading loading-sm loading-spinner"></span>Se încarcă apelurile…
          </div>
        {:else if calls.kind === "error"}
          <p role="alert" class="text-rosu-fg">{calls.message}</p>
        {:else}
          <ul class="flex flex-col">
            {#each calls.data as c (c.id)}
              {@const codeOf = code(c.final_severity)}
              {@const length = callLength(c.started_at, c.ended_at)}
              {@const shown = transcripts[c.id]}
              <li class="border-b border-line">
                <button
                  type="button"
                  aria-expanded={expanded === c.id}
                  class="grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-3 text-left hover:text-fg"
                  onclick={() => toggle(c.id)}
                >
                  <span class="flex min-w-0 flex-col gap-0.5">
                    <span class="font-mono text-[13px] font-medium">
                      {time.format(Date.parse(c.started_at ?? c.due_at))}
                    </span>
                    <span class="text-xs text-fg-muted">
                      {TRIGGERS[c.trigger] ?? c.trigger} · {CALL_STATES[c.state] ?? c.state}
                      {#if length}· <span class="font-mono">{length}</span>{/if}
                    </span>
                    {#if c.reason}
                      <span class="truncate text-xs text-fg-soft">{c.reason}</span>
                    {/if}
                  </span>
                  {#if codeOf}
                    <span
                      class={[
                        "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
                        TONE_CHIP[codeOf.tone],
                      ]}
                    >
                      <span class={["size-1.5", TONE_DOT[codeOf.tone]]}></span>{codeOf.label}
                    </span>
                  {:else}
                    <span></span>
                  {/if}
                  <Icon
                    name="arrow-right"
                    size={14}
                    class={expanded === c.id
                      ? "rotate-90 text-fg-muted transition-transform"
                      : "text-fg-muted transition-transform"}
                  />
                </button>
                {#if expanded === c.id}
                  <div class="flex flex-col gap-3.5 pb-5">
                    {#if !shown || shown.kind === "loading"}
                      <div role="status" class="flex items-center gap-2 text-fg-muted">
                        <span class="loading loading-sm loading-spinner"></span>Se încarcă
                        transcrierea…
                      </div>
                    {:else if shown.kind === "error"}
                      <p role="alert" class="text-rosu-fg">{shown.message}</p>
                    {:else}
                      <CallTranscript call={shown.data} />
                    {/if}
                  </div>
                {/if}
              </li>
            {:else}
              <li class="text-fg-muted">Niciun apel pentru acest senior.</li>
            {/each}
          </ul>
        {/if}
      {:else if load.kind === "loading"}
        <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
          <span class="loading loading-sm loading-spinner"></span>Se încarcă dosarul…
        </div>
      {:else if load.kind === "error"}
        <p role="alert" class="text-rosu-fg">{load.message}</p>
      {:else}
        {@const s = load.data}
        <div class="flex flex-col">
          <div
            class="grid grid-cols-[150px_minmax(0,1fr)] items-center gap-3 border-b border-line pb-3.5"
          >
            <span class="sn-label">Telefon senior</span>
            <span class="font-mono text-[13px] font-medium">
              {formatPhone(s.phone_e164)}
              <span class="font-sans text-[10px] font-semibold tracking-[0.06em] text-fg-muted">
                {s.phone_is_landline ? "FIX" : "MOBIL"}
              </span>
            </span>
          </div>
          {@render row("Adresă", address(s))}
          {@render row("Interfon", s.intercom_code)}
          {@render row("Cheie de rezervă", s.key_holder)}
          {@render row("Reper orientare", s.landmark)}
          {@render row("Interval de apel", s.call_window)}
          {@render row(
            "Medic de familie",
            [s.medic.display_name, s.medic.practice].filter(Boolean).join(" · "),
          )}

          <div class="pt-4">
            {#if briefing.kind === "loading"}
              <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
                <span class="loading loading-sm loading-spinner"></span>Se încarcă rezumatul…
              </div>
            {:else if briefing.kind === "error"}
              <p role="alert" class="text-rosu-fg">{briefing.message}</p>
            {:else}
              <Briefing summary={briefing.data} calls={calls?.kind === "ok" ? calls.data : []} />
            {/if}
          </div>

          {#if medical.kind === "error"}
            <p role="alert" class="pt-4 text-rosu-fg">{medical.message}</p>
          {:else if medical.kind === "ok"}
            <div class="pt-4"><MedicalRecord record={medical.data} /></div>
          {/if}

          <div class="pt-4">
            <WatchHealth id={s.id} />
          </div>

          <div class="sn-label pt-4 pb-2">Aparținători înregistrați</div>
          {#each s.caregivers as c (c.user_id)}
            <div
              class="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-line py-2.5"
            >
              <span>
                <span class="font-semibold">{c.display_name}</span>
                {#if c.relation}<span class="text-fg-muted">· {c.relation}</span>{/if}
              </span>
              <span class="font-mono text-[13px] font-medium">{formatPhone(c.phone_e164)}</span>
              <a href={`tel:${c.phone_e164}`} class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs">
                Apelează
              </a>
            </div>
          {:else}
            <p class="text-fg-muted">Niciun aparținător înregistrat.</p>
          {/each}

          <div class="mt-6 border-t-2 border-line pt-4">
            {#if !confirmingErase}
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  class="sn-btn sn-btn-outline px-3 py-1.5 text-xs"
                  disabled={exporting}
                  onclick={downloadExport}
                >
                  <Icon name="download" size={14} />{exporting ? "Se exportă…" : "Exportă datele"}
                </button>
                <button
                  type="button"
                  class="sn-btn sn-btn-outline px-3 py-1.5 text-xs"
                  onclick={() => (confirmingErase = true)}
                >
                  <Icon name="trash-2" size={14} />Șterge toate datele
                </button>
              </div>
              {#if exportError}<p role="alert" class="mt-3 text-rosu-fg">{exportError}</p>{/if}
            {:else}
              <div
                class="border border-rosu bg-rosu/15 p-4"
                role="group"
                aria-label="Confirmă ștergerea"
              >
                <p class="text-rosu-fg">
                  Toate datele despre {s.full_name} vor fi șterse definitiv: apeluri, transcrieri, fișa
                  medicală, consimțăminte. Acțiunea nu poate fi anulată.
                </p>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="sn-btn sn-btn-outline px-3 py-1.5 text-xs"
                    disabled={erasing}
                    onclick={() => {
                      confirmingErase = false;
                      eraseError = null;
                    }}
                  >
                    Anulează
                  </button>
                  <button
                    type="button"
                    class="sn-btn sn-btn-danger px-3 py-1.5 text-xs"
                    disabled={erasing}
                    onclick={erase}
                  >
                    {erasing ? "Se șterge…" : "Șterge definitiv"}
                  </button>
                </div>
                {#if eraseError}<p role="alert" class="mt-3 text-rosu-fg">{eraseError}</p>{/if}
              </div>
            {/if}
          </div>
        </div>
      {/if}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>Închide</button>
  </form>
</dialog>
