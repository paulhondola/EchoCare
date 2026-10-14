<script lang="ts">
  import { onMount } from "svelte";
  import { fetchIncident, type IncidentDetail } from "../../services/api";
  import { address, OUTCOMES, time } from "../../utils/labels";

  let { id, onClose }: { id: string; onClose: () => void } = $props();

  // Romanian labels for the stored values (05 §1); an unknown value shows as it is
  const TRIGGERS: Record<string, string> = {
    campaign: "Campanie",
    watch: "Ceas",
    manual: "Cerere „Sunați-mă”",
    welcome: "Apel de bun venit",
  };
  const EVENTS: Record<string, string> = {
    high_pulse_at_rest: "Puls ridicat în repaus",
    inactivity: "Inactivitate",
    sos_button: "Buton SOS",
    manual_request: "„Sunați-mă”",
  };
  const STATES: Record<string, string> = {
    queued: "în așteptare",
    ringing: "sună",
    in_progress: "în curs",
    unanswered: "nepreluat",
    failed: "eșuat",
    completed: "încheiat",
    handed_over: "transferat la DAS",
    dropped: "întrerupt",
  };
  const SPEAKERS: Record<string, string> = { senior: "Senior", agent: "Agent", system: "Sistem" };
  const SEVERITY_BADGE: Record<string, string> = {
    green: "badge-success",
    yellow: "badge-warning",
    red: "badge-error",
  };
  const SEVERITIES: Record<string, string> = { green: "verde", yellow: "galben", red: "roșu" };

  const at = (iso: string | null) => (iso ? time.format(Date.parse(iso)) : "—");

  type Load =
    | { kind: "loading" }
    | { kind: "ok"; incident: IncidentDetail }
    | { kind: "error"; message: string };

  let load = $state<Load>({ kind: "loading" });
  let dialogEl: HTMLDialogElement | undefined = $state();

  onMount(() => {
    if (dialogEl && !dialogEl.open) dialogEl.showModal();

    const ctrl = new AbortController();
    fetchIncident(id, ctrl.signal)
      .then((incident) => {
        load = { kind: "ok", incident };
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        load = {
          kind: "error",
          message: `Nu am putut citi incidentul (${e instanceof Error ? e.message : String(e)}).`,
        };
      });

    return () => ctrl.abort();
  });
</script>

<dialog bind:this={dialogEl} class="modal" onclose={onClose}>
  <div class="modal-box max-w-3xl">
    <button
      class="btn btn-circle btn-ghost btn-sm absolute top-2 right-2"
      aria-label="Închide"
      onclick={() => dialogEl?.close()}
    >
      ✕
    </button>
    {#if load.kind === "loading"}
      <div role="status" class="flex items-center gap-2">
        <span class="loading loading-spinner loading-sm"></span>
        Se încarcă…
      </div>
    {:else if load.kind === "error"}
      <div role="alert" class="alert alert-error alert-soft">
        {load.message}
      </div>
    {:else if load.kind === "ok"}
      {@const i = load.incident}
      {@const s = i.senior}
      {@const e = i.event}
      {@const outcome = OUTCOMES.find((o) => o.value === i.outcome)?.label ?? i.outcome}

      <div class="flex flex-col gap-4">
        <header>
          <h2 class="text-xl font-bold">{s.full_name}</h2>
          <p class="text-base-content/60">
            {s.form_of_address} · {i.reason}
          </p>
        </header>

        <section>
          <h3 class="mb-1 font-semibold">Senior</h3>
          <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
            <dt class="text-base-content/60">Telefon</dt>
            <dd>
              <a class="link" href={`tel:${s.phone_e164}`}>
                {s.phone_e164}
              </a>
              <span class="badge badge-xs badge-ghost ml-1">
                {s.phone_is_landline ? "fix" : "mobil"}
              </span>
            </dd>
            <dt class="text-base-content/60">Adresă</dt>
            <dd>{address(s)}</dd>
            {#if s.intercom_code}
              <dt class="text-base-content/60">Interfon</dt>
              <dd>{s.intercom_code}</dd>
            {/if}
            {#if s.key_holder}
              <dt class="text-base-content/60">Chei la</dt>
              <dd>{s.key_holder}</dd>
            {/if}
            {#if s.landmark}
              <dt class="text-base-content/60">Reper</dt>
              <dd>{s.landmark}</dd>
            {/if}
          </dl>
        </section>

        <section>
          <h3 class="mb-1 font-semibold">Aparținători</h3>
          {#if i.caregivers.length === 0}
            <p class="text-sm text-base-content/60">Niciun aparținător înregistrat.</p>
          {:else}
            <ul class="text-sm">
              {#each i.caregivers as c (c.phone_e164)}
                <li>
                  {c.display_name}
                  {c.relation ? ` (${c.relation})` : ""} ·
                  <a class="link" href={`tel:${c.phone_e164}`}>
                    {c.phone_e164}
                  </a>
                </li>
              {/each}
            </ul>
          {/if}
        </section>

        {#if e}
          <section>
            <h3 class="mb-1 font-semibold">Eveniment</h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-base-content/60">Tip</dt>
              <dd>{EVENTS[e.type] ?? e.type}</dd>
              <dt class="text-base-content/60">Măsurat la</dt>
              <dd>{at(e.measured_at)}</dd>
              {#if e.latitude !== null && e.longitude !== null}
                <dt class="text-base-content/60">Locație</dt>
                <dd>
                  <a
                    class="link"
                    target="_blank"
                    rel="noreferrer"
                    href={`https://www.openstreetmap.org/?mlat=${e.latitude}&mlon=${e.longitude}#map=18/${e.latitude}/${e.longitude}`}
                  >
                    {e.latitude.toFixed(5)}, {e.longitude.toFixed(5)}
                  </a>
                  {e.location_accuracy_m !== null
                    ? ` (±${Math.round(e.location_accuracy_m)} m)`
                    : ""}
                  {e.located_at ? `, ${at(e.located_at)}` : ""}
                </dd>
              {/if}
            </dl>
          </section>
        {/if}

        {#if i.status === "resolved"}
          <section>
            <h3 class="mb-1 font-semibold">Rezolvare</h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-base-content/60">Rezultat</dt>
              <dd>{outcome}</dd>
              <dt class="text-base-content/60">De</dt>
              <dd>{i.resolved_by_name}, {at(i.resolved_at)}</dd>
              {#if i.note}
                <dt class="text-base-content/60">Notă</dt>
                <dd>{i.note}</dd>
              {/if}
            </dl>
          </section>
        {/if}

        <section>
          <h3 class="mb-1 font-semibold">Apeluri</h3>
          {#if i.calls.length === 0}
            <p class="text-sm text-base-content/60">Niciun apel.</p>
          {/if}
          {#each i.calls as c (c.id)}
            <details class="collapse-arrow collapse mb-2 border border-base-300">
              <summary class="collapse-title flex flex-wrap items-center gap-2 text-sm">
                <span>{at(c.started_at)}</span>
                <span>
                  {TRIGGERS[c.trigger] ?? c.trigger}, încercarea {c.attempt}
                </span>
                <span class="text-base-content/60">{STATES[c.state] ?? c.state}</span>
                {#if c.final_severity}
                  <span class={["badge badge-sm", SEVERITY_BADGE[c.final_severity]]}>
                    {SEVERITIES[c.final_severity] ?? c.final_severity}
                  </span>
                {/if}
              </summary>
              <div class="collapse-content text-sm">
                {#if c.summary}
                  <p class="mb-2">{c.summary}</p>
                {/if}
                {#each c.reports as r (`${r.at}-${r.source}`)}
                  <p class="mb-1">
                    <span class={["badge badge-xs", SEVERITY_BADGE[r.severity]]}>
                      {SEVERITIES[r.severity] ?? r.severity}
                    </span>
                    {r.reason}
                    {#if r.quote}
                      <q class="ml-1 italic">{r.quote}</q>
                    {/if}
                  </p>
                {/each}
                {#if c.turns.length > 0}
                  <ol class="mt-2 flex flex-col gap-1">
                    {#each c.turns as t (`${t.at}-${t.content}`)}
                      <li>
                        <span class="font-semibold">{SPEAKERS[t.speaker] ?? t.speaker}:</span>
                        {t.kind === "keys" ? `tasta ${t.content}` : t.content}
                      </li>
                    {/each}
                  </ol>
                {/if}
              </div>
            </details>
          {/each}
        </section>
      </div>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>Închide</button>
  </form>
</dialog>
