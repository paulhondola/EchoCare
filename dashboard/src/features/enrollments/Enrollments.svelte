<script lang="ts">
  import {
    acceptSenior,
    ApiError,
    fetchSenior,
    type SeniorSummary,
    type SeniorView,
  } from "../../services/api";
  import { address, clock } from "../../utils/labels";
  import { formatPhone } from "../../utils/phone";
  import { getLive } from "../shell/live.svelte";
  import PageHeader from "../shell/PageHeader.svelte";

  function refusalMessage(e: unknown): string {
    if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
    switch (e.reason) {
      case "already_done":
        return "Cererea a fost deja acceptată.";
      case "wrong_state":
        return "Cererea s-a schimbat între timp.";
      case "not_found":
        return "Cererea nu mai există.";
      case "not_allowed":
        return "Nu aveți dreptul să faceți asta.";
      default:
        return `Nu am putut trimite (${e.message}).`;
    }
  }

  type Details =
    | { kind: "loading" }
    | { kind: "ok"; senior: SeniorView }
    | { kind: "error"; message: string };

  const live = getLive();
  const enrollments = live.enrollments;

  let acceptedNotice = $state<string | null>(null);
  let detailsMap = $state<Record<string, Details>>({});
  let busyMap = $state<Record<string, boolean>>({});
  let errorMap = $state<Record<string, string>>({});

  function toggle(id: string) {
    if (detailsMap[id]) {
      const copy = { ...detailsMap };
      delete copy[id];
      detailsMap = copy;
      return;
    }
    detailsMap = { ...detailsMap, [id]: { kind: "loading" } };
    fetchSenior(id)
      .then((senior) => {
        detailsMap = { ...detailsMap, [id]: { kind: "ok", senior } };
      })
      .catch((e: unknown) => {
        detailsMap = {
          ...detailsMap,
          [id]: {
            kind: "error",
            message: `Nu am putut citi cererea (${e instanceof Error ? e.message : String(e)}).`,
          },
        };
      });
  }

  function accept(s: SeniorSummary) {
    busyMap = { ...busyMap, [s.id]: true };
    const nextErrors = { ...errorMap };
    delete nextErrors[s.id];
    errorMap = nextErrors;

    acceptSenior(s.id)
      .then(() => {
        acceptedNotice = `Acceptat: ${s.full_name}.`;
        enrollments.update((list) => list.filter((x) => x.id !== s.id));
        live.seniors.reload();
      })
      .catch((e: unknown) => {
        errorMap = { ...errorMap, [s.id]: refusalMessage(e) };
        enrollments.reload();
      })
      .finally(() => {
        const nextBusy = { ...busyMap };
        delete nextBusy[s.id];
        busyMap = nextBusy;
      });
  }
</script>

{#snippet field(label: string, value: string | null)}
  {#if value}
    <dt class="sn-label pt-0.5">{label}</dt>
    <dd>{value}</dd>
  {/if}
{/snippet}

{#snippet registration(s: SeniorView)}
  <div class="mt-2 grid gap-4 border-t border-line pt-3 md:grid-cols-2">
    <dl class="grid grid-cols-[130px_minmax(0,1fr)] gap-x-3 gap-y-2">
      <dt class="sn-label pt-0.5">Telefon</dt>
      <dd>
        <span class="font-mono">{formatPhone(s.phone_e164)}</span>
        <span class="text-[10px] font-semibold tracking-[0.06em] text-fg-muted">
          {s.phone_is_landline ? "FIX" : "MOBIL"}
        </span>
      </dd>
      <dt class="sn-label pt-0.5">Adresă</dt>
      <dd>{address(s)}</dd>
      {@render field("Interfon", s.intercom_code)}
      {@render field("Are cheie", s.key_holder)}
      {@render field("Reper", s.landmark)}
      {@render field("Interval de apel", s.call_window)}
      {@render field("Medic", [s.medic.display_name, s.medic.practice].filter(Boolean).join(" · "))}
    </dl>
    <div>
      <h4 class="sn-label mb-2">Aparținători</h4>
      {#each s.caregivers as c (c.user_id)}
        <div class="flex flex-wrap items-baseline gap-x-2 border-b border-line py-1.5">
          <span class="font-semibold">{c.display_name}</span>
          {#if c.relation}<span class="text-fg-muted">· {c.relation}</span>{/if}
          <span class="ml-auto font-mono text-xs">{formatPhone(c.phone_e164)}</span>
        </div>
      {:else}
        <p class="text-fg-muted">Niciun aparținător.</p>
      {/each}
    </div>
  </div>
{/snippet}

<PageHeader title="Cereri de înrolare" />

<div class="min-h-0 flex-1 overflow-auto p-4">
  {#if enrollments.load.kind === "loading"}
    <div
      role="status"
      class="loading-delay flex items-center justify-center gap-2 p-12 text-fg-muted"
    >
      <span class="loading loading-md loading-spinner"></span>
      <span>Se încarcă cererile…</span>
    </div>
  {:else if enrollments.load.kind === "error"}
    <p role="alert" class="border border-rosu bg-rosu/15 px-4 py-3 text-rosu-fg">
      {enrollments.load.message}
    </p>
  {:else}
    <section class="flex max-w-4xl flex-col gap-2">
      <p class="text-xs text-fg-muted">
        Cele mai vechi primele · actualizat la
        <span class="font-mono">{clock.format(enrollments.load.at)}</span>
      </p>
      {#if enrollments.load.error}
        <p role="alert" class="border border-galben bg-galben/15 px-4 py-2 text-galben-fg">
          {enrollments.load.error}
        </p>
      {/if}
      {#if acceptedNotice}
        <p role="status" class="border border-verde bg-verde/10 px-4 py-2 text-verde-fg">
          {acceptedNotice}
        </p>
      {/if}
      {#each enrollments.load.data as s (s.id)}
        {@const details = detailsMap[s.id]}
        {@const busy = busyMap[s.id] ?? false}
        {@const error = errorMap[s.id]}
        <article class="flex border border-line bg-card">
          <div class="w-[3px] flex-none bg-link"></div>
          <div class="flex min-w-0 flex-1 flex-col gap-1 px-3 py-2.5">
            <div class="flex flex-wrap items-start gap-2">
              <div class="flex min-w-0 flex-col">
                <h3 class="text-[15px] leading-tight font-semibold">{s.full_name}</h3>
                <span class="text-xs text-fg-muted">
                  {s.form_of_address} · <span class="font-mono">{formatPhone(s.phone_e164)}</span>
                </span>
              </div>
              <div class="ml-auto flex gap-2">
                <button
                  type="button"
                  class="sn-btn sn-btn-link"
                  aria-expanded={!!details}
                  onclick={() => toggle(s.id)}
                >
                  {details ? "Ascunde" : "Vezi cererea"}
                </button>
                <button
                  type="button"
                  class="sn-btn sn-btn-success"
                  disabled={busy}
                  onclick={() => accept(s)}
                >
                  Acceptă
                </button>
              </div>
            </div>
            {#if details?.kind === "loading"}
              <div role="status" class="flex items-center gap-2 text-fg-muted">
                <span class="loading loading-xs loading-spinner"></span>Se încarcă…
              </div>
            {:else if details?.kind === "error"}
              <p role="alert" class="text-rosu-fg">{details.message}</p>
            {:else if details?.kind === "ok"}
              {@render registration(details.senior)}
            {/if}
            {#if error}
              <p role="alert" class="text-rosu-fg">{error}</p>
            {/if}
          </div>
        </article>
      {:else}
        <p class="text-fg-muted">Nicio cerere în așteptare.</p>
      {/each}
    </section>
  {/if}
</div>
