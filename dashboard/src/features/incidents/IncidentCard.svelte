<script lang="ts">
  import {
    ApiError,
    resolveIncident,
    takeIncident,
    type Incident,
    type IncidentOutcome,
  } from "../../services/api";
  import { OUTCOMES, time } from "../../utils/labels";
  import IncidentDetails from "./IncidentDetails.svelte";

  let {
    incident: i,
    now,
    border,
    onChanged,
    onStale,
  }: {
    incident: Incident;
    now: number;
    border: string;
    onChanged: (incident: Incident) => void;
    onStale: () => void;
  } = $props();

  function minutesSince(iso: string, current: number): string {
    const m = Math.max(0, Math.floor((current - Date.parse(iso)) / 60_000));
    return m < 60 ? `acum ${m} min` : `acum ${Math.floor(m / 60)} h ${m % 60} min`;
  }

  function refusalMessage(e: unknown, action: "take" | "resolve"): string {
    if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
    switch (e.reason) {
      case "already_done":
        return action === "take"
          ? `Incidentul a fost preluat deja de ${e.takenByName ?? "un alt dispecer"}.`
          : "Incidentul a fost deja rezolvat.";
      case "wrong_state":
        return "Incidentul s-a schimbat între timp.";
      case "not_allowed":
        return "Nu aveți dreptul să faceți asta.";
      case "not_found":
        return "Incidentul nu mai există.";
      default:
        return `Nu am putut trimite (${e.message}).`;
    }
  }

  let busy = $state(false);
  let error = $state<string | null>(null);
  let outcome = $state<IncidentOutcome | "">("");
  let note = $state("");
  let showDetails = $state(false);

  function send(action: "take" | "resolve", command: () => Promise<Incident>) {
    busy = true;
    error = null;
    command()
      .then(onChanged)
      .catch((e: unknown) => {
        error = refusalMessage(e, action);
        onStale();
      })
      .finally(() => {
        busy = false;
      });
  }

  const canResolve = $derived(outcome !== "" && note.trim() !== "");
</script>

<article class={["card card-sm mb-3 border-l-4 bg-base-100 shadow-sm", border]}>
  <div class="card-body gap-1">
    <div class="flex items-start justify-between gap-2">
      <h3 class="card-title text-base">{i.senior_full_name}</h3>
      <button class="btn btn-ghost btn-xs" onclick={() => (showDetails = true)}> Detalii </button>
    </div>
    <p class="text-sm text-base-content/60">{i.senior_form_of_address}</p>
    <p>{i.reason}</p>
    <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
      <dt class="text-base-content/60">Deschis</dt>
      <dd title={time.format(Date.parse(i.opened_at))}>{minutesSince(i.opened_at, now)}</dd>
      {#if i.taken_by_name}
        <dt class="text-base-content/60">Preluat de</dt>
        <dd>
          {i.taken_by_name}
          {i.taken_at ? `, ${time.format(Date.parse(i.taken_at))}` : ""}
        </dd>
      {/if}
      <dt class="text-base-content/60">Transfer apel</dt>
      <dd>
        <span
          class={[
            "badge badge-xs badge-soft",
            i.handover_answered ? "badge-success" : "badge-error",
          ]}
        >
          {i.handover_answered ? "preluat" : "nepreluat"}
        </span>
      </dd>
    </dl>

    {#if i.status === "open"}
      <div class="card-actions mt-2">
        <button
          class="btn btn-sm btn-error"
          disabled={busy}
          onclick={() => send("take", () => takeIncident(i.id))}
        >
          Preiau
        </button>
      </div>
    {/if}

    {#if i.status === "in_progress"}
      <form
        class="mt-2 flex flex-col gap-2"
        onsubmit={(e) => {
          e.preventDefault();
          const selectedOutcome = outcome;
          if (selectedOutcome === "" || !canResolve) return;
          send("resolve", () => resolveIncident(i.id, selectedOutcome, note.trim()));
        }}
      >
        <select class="select select-sm w-full" aria-label="Rezultat" bind:value={outcome}>
          <option value="" disabled> Rezultat… </option>
          {#each OUTCOMES as o (o.value)}
            <option value={o.value}>
              {o.label}
            </option>
          {/each}
        </select>
        <textarea
          class="textarea textarea-sm w-full"
          aria-label="Notă"
          placeholder="Ce s-a întâmplat, pe scurt"
          maxlength={1000}
          rows={2}
          bind:value={note}></textarea>
        <button class="btn btn-sm btn-success" disabled={busy || !canResolve}> Rezolvă </button>
      </form>
    {/if}

    {#if showDetails}
      <IncidentDetails id={i.id} onClose={() => (showDetails = false)} />
    {/if}

    {#if error}
      <p role="alert" class="mt-1 text-sm text-error">
        {error}
      </p>
    {/if}
  </div>
</article>
