<script lang="ts">
  import { onMount } from "svelte";
  import {
    fetchIncident,
    fetchSenior,
    resolveIncident,
    takeIncident,
    type Incident,
    type IncidentDetail,
    type IncidentOutcome,
    type SeniorView,
  } from "../../services/api";
  import CopyButton from "../../ui/CopyButton.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { shortId, since, type DossierTab } from "../../utils/incidents";
  import {
    address,
    CALL_STATES,
    callLength,
    clock,
    OUTCOMES,
    time,
    TRIGGERS,
  } from "../../utils/labels";
  import { formatPhone } from "../../utils/phone";
  import CallTranscript from "../calls/CallTranscript.svelte";
  import { refusalMessage } from "./commands";

  let {
    incident,
    tab: initialTab,
    now,
    onClose,
    onChanged,
    onStale,
  }: {
    incident: Incident;
    tab: DossierTab;
    now: number;
    onClose: () => void;
    onChanged: (incident: Incident) => void;
    onStale: () => void;
  } = $props();

  const TABS: { key: DossierTab; n: number; label: string }[] = [
    { key: "access", n: 1, label: "Urgență & acces" },
    { key: "transcript", n: 2, label: "Transcriere apel" },
    { key: "event", n: 3, label: "Eveniment" },
    { key: "resolve", n: 4, label: "Rezolvare caz" },
  ];

  // Romanian labels for the stored values (05 §1); an unknown value shows as it is
  const EVENTS: Record<string, string> = {
    high_pulse_at_rest: "Puls ridicat în repaus",
    inactivity: "Inactivitate",
    sos_button: "Buton SOS",
    manual_request: "„Sunați-mă”",
    fall: "Cădere detectată",
  };

  type Load<T> = { kind: "loading" } | { kind: "ok"; data: T } | { kind: "error"; message: string };

  // svelte-ignore state_referenced_locally
  let tab = $state<DossierTab>(initialTab);
  let load = $state<Load<IncidentDetail>>({ kind: "loading" });
  let senior = $state<SeniorView | null>(null);
  let dialogEl: HTMLDialogElement | undefined = $state();
  let outcome = $state<IncidentOutcome | "">("");
  let note = $state("");
  let busy = $state(false);
  let error = $state<string | null>(null);

  onMount(() => {
    if (dialogEl && !dialogEl.open) dialogEl.showModal();
  });

  // Read again whenever the board sees the incident change hands or state
  const version = $derived(`${incident.id}:${incident.status}:${incident.taken_by_name ?? ""}`);
  $effect(() => {
    void version;
    const ctrl = new AbortController();
    fetchIncident(incident.id, ctrl.signal)
      .then((data) => {
        load = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        if (load.kind !== "ok")
          load = {
            kind: "error",
            message: `Nu am putut citi incidentul (${e instanceof Error ? e.message : String(e)}).`,
          };
      });
    return () => ctrl.abort();
  });

  // The senior's page adds the family doctor and the call window; the dossier works without it
  const seniorId = $derived(load.kind === "ok" ? load.data.senior.id : null);
  $effect(() => {
    if (!seniorId) return;
    const ctrl = new AbortController();
    fetchSenior(seniorId, ctrl.signal)
      .then((s) => {
        senior = s;
      })
      .catch(() => {});
    return () => ctrl.abort();
  });

  function send(action: "take" | "resolve", command: () => Promise<Incident>) {
    busy = true;
    error = null;
    command()
      .then((changed) => {
        onChanged(changed);
        if (action === "take") tab = "resolve";
      })
      .catch((e: unknown) => {
        error = refusalMessage(e, action);
        onStale();
      })
      .finally(() => {
        busy = false;
      });
  }

  const take = () => send("take", () => takeIncident(incident.id));

  const canFinish = $derived(outcome !== "" && note.trim() !== "");
  function finish(e: SubmitEvent) {
    e.preventDefault();
    const chosen = outcome;
    if (chosen === "" || !canFinish) return;
    send("resolve", () => resolveIncident(incident.id, chosen, note.trim()));
  }

  const at = (iso: string | null) => (iso ? time.format(Date.parse(iso)) : "—");
  const tel = (e164: string) => `tel:${e164}`;

  const STATUS = $derived(
    incident.status === "open"
      ? {
          label: `Deschis · ${since(incident.opened_at, now)}`,
          chip: "bg-rosu/15 text-rosu-fg",
          dot: "bg-rosu",
        }
      : incident.status === "in_progress"
        ? {
            label: `În lucru · preluat de ${incident.taken_by_name ?? "un dispecer"}`,
            chip: "bg-galben/15 text-galben-fg",
            dot: "bg-galben",
          }
        : { label: "Rezolvat", chip: "bg-verde/15 text-verde-fg", dot: "bg-verde" },
  );
</script>

{#snippet row(label: string, value: string | null)}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-b border-line py-3.5">
    <span class="sn-label">{label}</span>
    <span>{value || "—"}</span>
  </div>
{/snippet}

{#snippet callLink(e164: string)}
  <a href={tel(e164)} class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs">Apelează</a>
{/snippet}

<dialog
  bind:this={dialogEl}
  class="modal modal-end"
  aria-labelledby="dossier-title"
  onclose={onClose}
>
  <div
    class="modal-box flex h-full w-[540px] max-w-full flex-col border-l-2 border-line bg-subtle p-0 text-fg shadow-[-24px_0_48px_rgba(1,4,9,.55)]"
  >
    <!-- Who, where, and the first actions -->
    <div class="flex flex-col gap-2.5 border-b-2 border-line px-5 py-4">
      <div class="flex items-center gap-2.5 text-xs text-fg-muted">
        <span class="font-mono">#{shortId(incident.id)}</span>
        <span
          class={[
            "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
            STATUS.chip,
          ]}
        >
          <span class={["size-1.5", STATUS.dot]}></span>{STATUS.label}
        </span>
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
        <h2 id="dossier-title" class="text-2xl leading-[1.1] font-extrabold tracking-[-0.015em]">
          {incident.senior_full_name}
        </h2>
        <span class="text-[13px] text-fg-muted">{incident.senior_form_of_address}</span>
      </div>
      <div class="flex">
        <span
          class="inline-flex flex-wrap items-center gap-2 border border-rosu bg-rosu/15 px-2.5 py-1 text-xs font-bold text-rosu-fg"
        >
          <span class="tracking-[0.06em]">COD ROȘU</span>
          <span class="font-semibold text-fg">{incident.reason}</span>
        </span>
      </div>

      {#if load.kind === "ok"}
        {@const s = load.data.senior}
        {@const e = load.data.event}
        {@const line = address(s)}
        <div class="text-sm">{line}</div>
        <div class="flex flex-wrap gap-1.5">
          <CopyButton class="h-7 px-2.5 text-xs" icon="copy" label="Copiază adresa" text={line} />
          {#if s.intercom_code}
            <CopyButton
              class="h-7 px-2.5 text-xs"
              icon="key"
              mono
              label={`Interfon: ${s.intercom_code}`}
              text={s.intercom_code}
            />
          {/if}
          {#if e && e.latitude !== null && e.longitude !== null}
            {@const gps = `${e.latitude.toFixed(4)}, ${e.longitude.toFixed(4)}`}
            <CopyButton
              class="h-7 px-2.5 text-xs"
              icon="navigation"
              mono
              label={`GPS: ${gps}`}
              text={gps}
            />
          {/if}
        </div>
        {#if incident.status === "open"}
          <div class="mt-1 flex gap-2">
            <button
              type="button"
              class="sn-btn sn-btn-danger h-[34px] px-3.5"
              disabled={busy}
              onclick={take}
            >
              <Icon name="zap" size={13} stroke={2.2} />Preiau cazul
            </button>
            <a href={tel(s.phone_e164)} class="sn-btn h-[34px] px-3.5">
              <Icon name="phone" size={13} />Apelează senior
            </a>
          </div>
        {/if}
      {/if}
      {#if error}
        <p role="alert" class="text-rosu-fg">{error}</p>
      {/if}
    </div>

    <div class="flex border-b-2 border-line px-3" role="tablist" aria-label="Dosar">
      {#each TABS as t (t.key)}
        <button
          type="button"
          role="tab"
          aria-selected={tab === t.key}
          class={[
            "-mb-0.5 flex cursor-pointer items-center gap-1.5 border-b-2 px-2.5 py-[11px] text-[12.5px] font-semibold",
            tab === t.key
              ? "border-link text-fg"
              : "border-transparent text-fg-muted hover:text-fg",
          ]}
          onclick={() => (tab = t.key)}
        >
          <span class="font-mono text-[11px] font-medium text-fg-muted">{t.n}</span>{t.label}
        </button>
      {/each}
    </div>

    <div class="min-h-0 flex-1 overflow-auto px-5 pt-[18px] pb-6" role="tabpanel">
      {#if load.kind === "loading"}
        <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
          <span class="loading loading-sm loading-spinner"></span>Se încarcă dosarul…
        </div>
      {:else if load.kind === "error"}
        <p role="alert" class="text-rosu-fg">{load.message}</p>
      {:else}
        {@const d = load.data}
        {@const s = d.senior}

        {#if tab === "access"}
          <div class="flex flex-col">
            <div
              class="grid grid-cols-[150px_minmax(0,1fr)_auto] items-center gap-3 border-b border-line pb-3.5"
            >
              <span class="sn-label">Telefon senior</span>
              <span class="font-mono text-[13px] font-medium">
                {formatPhone(s.phone_e164)}
                <span class="font-sans text-[10px] font-semibold tracking-[0.06em] text-fg-muted">
                  {s.phone_is_landline ? "FIX" : "MOBIL"}
                </span>
              </span>
              {@render callLink(s.phone_e164)}
            </div>
            {@render row("Reper orientare", s.landmark)}
            {@render row("Cheie de rezervă", s.key_holder)}
            {#if senior?.call_window}
              {@render row("Interval de apel", senior.call_window)}
            {/if}

            <div class="sn-label border-t border-line pt-4 pb-2">Aparținători înregistrați</div>
            {#if d.caregivers.length === 0}
              <p class="border-b-2 border-line pb-3 text-fg-muted">
                Niciun aparținător înregistrat.
              </p>
            {:else}
              {#each d.caregivers as c, idx (c.phone_e164)}
                <div
                  class={[
                    "grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-2.5",
                    idx === d.caregivers.length - 1
                      ? "border-b-2 border-line"
                      : "border-b border-line",
                  ]}
                >
                  <span>
                    <span class="font-semibold">{c.display_name}</span>
                    {#if c.relation}<span class="text-fg-muted">· {c.relation}</span>{/if}
                  </span>
                  <span class="font-mono text-[13px] font-medium">{formatPhone(c.phone_e164)}</span>
                  {@render callLink(c.phone_e164)}
                </div>
              {/each}
            {/if}

            {#if senior}
              <div class="sn-label pt-4 pb-2">Medic de familie</div>
              <div class="py-2.5">
                <span class="font-semibold">{senior.medic.display_name}</span>
                {#if senior.medic.practice}
                  <span class="text-fg-muted">· {senior.medic.practice}</span>
                {/if}
              </div>
            {/if}
          </div>
        {:else if tab === "transcript"}
          {#if d.calls.length === 0}
            <p class="text-fg-muted">Niciun apel înregistrat pentru acest incident.</p>
          {/if}
          <div class="flex flex-col gap-8">
            {#each d.calls as c (c.id)}
              {@const length = callLength(c.started_at, c.ended_at)}
              <section class="flex flex-col gap-3.5">
                <div
                  class="flex flex-wrap gap-x-[18px] gap-y-1.5 border-b-2 border-line pb-3 text-xs text-fg-muted"
                >
                  <span>
                    Apel inițiat la
                    <span class="font-mono text-fg">
                      {c.started_at ? clock.format(Date.parse(c.started_at)) : "—"}
                    </span>
                  </span>
                  <span>{TRIGGERS[c.trigger] ?? c.trigger} · încercarea {c.attempt}</span>
                  {#if length}
                    <span>durată <span class="font-mono text-fg">{length}</span></span>
                  {/if}
                  <span>{CALL_STATES[c.state] ?? c.state}</span>
                </div>

                <CallTranscript call={c} />
              </section>
            {/each}
          </div>
        {:else if tab === "event"}
          {@const e = d.event}
          {#if !e}
            <p class="text-fg-muted">
              Incidentul nu vine de la ceas sau de la nodul ambiental; motivul este cel din apel.
            </p>
          {:else}
            <div class="flex flex-col">
              {@render row("Tip", EVENTS[e.type] ?? e.type)}
              {@render row("Măsurat la", at(e.measured_at))}
              {#if e.latitude !== null && e.longitude !== null}
                <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-b border-line py-3.5">
                  <span class="sn-label">Locație</span>
                  <span class="flex flex-col gap-1">
                    <a
                      class="font-mono text-link"
                      target="_blank"
                      rel="noreferrer"
                      href={`https://www.openstreetmap.org/?mlat=${e.latitude}&mlon=${e.longitude}#map=18/${e.latitude}/${e.longitude}`}
                    >
                      {e.latitude.toFixed(5)}, {e.longitude.toFixed(5)}
                    </a>
                    <span class="text-xs text-fg-muted">
                      {e.location_accuracy_m !== null
                        ? `±${Math.round(e.location_accuracy_m)} m`
                        : "precizie necunoscută"}{e.located_at ? ` · ${at(e.located_at)}` : ""}
                    </span>
                  </span>
                </div>
              {:else}
                {@render row("Locație", "Fără locație în eveniment")}
              {/if}
            </div>
          {/if}
        {:else if tab === "resolve"}
          {#if incident.status === "open"}
            <div class="flex flex-col items-start gap-3 border border-line bg-canvas p-4">
              <span>Preia cazul pentru a-l putea rezolva.</span>
              <button
                type="button"
                class="sn-btn sn-btn-danger h-[34px] px-3.5"
                disabled={busy}
                onclick={take}
              >
                <Icon name="zap" size={13} stroke={2.2} />Preiau cazul
              </button>
            </div>
          {:else if incident.status === "in_progress"}
            <form class="flex flex-col gap-3.5" onsubmit={finish}>
              <div class="sn-label" id="outcome-label">Rezultat</div>
              <div
                class="flex flex-col border border-line"
                role="radiogroup"
                aria-labelledby="outcome-label"
              >
                {#each OUTCOMES as o (o.value)}
                  <label
                    class={[
                      "flex cursor-pointer items-center gap-2.5 border-b border-line px-3 py-[9px] last:border-b-0 hover:bg-card",
                      outcome === o.value && "bg-link/12",
                    ]}
                  >
                    <input
                      type="radio"
                      name="outcome"
                      value={o.value}
                      bind:group={outcome}
                      class="peer sr-only"
                    />
                    <span
                      class={[
                        "size-3.5 flex-none border-2 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-link",
                        outcome === o.value ? "border-link bg-link" : "border-line-strong",
                      ]}
                    ></span>
                    {o.label}
                    <span class="ml-auto font-mono text-[11px] text-fg-muted">{o.value}</span>
                  </label>
                {/each}
              </div>
              <label class="flex flex-col gap-1.5">
                <span class="sn-label">Notă de rezolvare · obligatorie</span>
                <textarea
                  class="sn-input min-h-24 resize-y p-2.5 text-[13px] leading-normal"
                  placeholder="Descrieți pe scurt măsurile luate…"
                  maxlength={1000}
                  bind:value={note}></textarea>
              </label>
              <button
                class="sn-btn sn-btn-success h-10 w-full px-3.5 text-sm"
                disabled={busy || !canFinish}
              >
                Finalizează și arhivează incidentul<Icon name="arrow-right" size={14} />
              </button>
            </form>
          {:else}
            {@const label = OUTCOMES.find((o) => o.value === d.outcome)?.label ?? d.outcome}
            <div class="flex flex-col gap-2 border border-verde bg-verde/10 p-4">
              <span class="flex items-center gap-2 font-extrabold text-verde-fg">
                <Icon name="circle-check" size={15} />Incident arhivat · {label}
              </span>
              {#if d.note}<span class="text-fg-soft">{d.note}</span>{/if}
              <span class="text-xs text-fg-muted">
                Rezolvat de {d.resolved_by_name ?? "—"}, {at(d.resolved_at)}
              </span>
            </div>
          {/if}
        {/if}
      {/if}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>Închide</button>
  </form>
</dialog>
