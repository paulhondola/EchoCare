<script lang="ts">
  import {
    ApiError,
    endCampaign,
    fetchCampaigns,
    startCampaign,
    type CampaignKind,
    type WarningLevel,
  } from "../../services/api";
  import { KIND_LABELS, LEVEL_LABELS, progressParts } from "../../utils/campaigns";
  import { time, TONE_CHIP } from "../../utils/labels";
  import { poll } from "../../utils/poll.svelte";
  import PageHeader from "../shell/PageHeader.svelte";

  function refusalMessage(e: unknown): string {
    if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
    return `Nu am putut trimite (${e.message}).`;
  }

  // 04 §6: the list re-reads every few seconds while the page is open, so progress moves as calls end
  const campaigns = poll(
    fetchCampaigns,
    5_000,
    (e) => `Nu am putut citi campaniile (${e instanceof Error ? e.message : String(e)}).`,
  );

  let kind = $state<CampaignKind>("heat");
  let level = $state<WarningLevel>("yellow");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);

  // Every command ends with a re-read: a refused one means the list is out of date
  function run(command: () => Promise<string | null>) {
    busy = true;
    error = null;
    notice = null;
    command()
      .then((done) => {
        notice = done;
      })
      .catch((err: unknown) => {
        error = refusalMessage(err);
      })
      .finally(() => {
        busy = false;
        campaigns.reload();
      });
  }

  function start(e: SubmitEvent) {
    e.preventDefault();
    run(async () => {
      const { campaign, created } = await startCampaign(kind, level);
      return created
        ? `Campanie lansată: ${campaign.progress.total} seniori de sunat.`
        : "Campania rulează deja.";
    });
  }

  function end(id: string) {
    run(async () => {
      await endCampaign(id);
      return null;
    });
  }
</script>

<PageHeader title="Campanii meteo" />

<div class="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1fr)_360px]">
  <section
    class="flex min-h-0 flex-col border-line md:border-r-2"
    aria-labelledby="campaigns-title"
  >
    <div class="flex flex-col gap-1 px-5 pt-4 pb-3">
      <h2 id="campaigns-title" class="text-[15px] font-extrabold">Campanii</h2>
      <span class="text-xs text-fg-muted">Cele mai noi primele.</span>
    </div>
    <div class="min-h-0 flex-1 overflow-auto border-t border-line">
      {#if campaigns.load.kind === "loading"}
        <div role="status" class="loading-delay flex items-center gap-2 p-5 text-fg-muted">
          <span class="loading loading-sm loading-spinner"></span>Se încarcă campaniile…
        </div>
      {:else if campaigns.load.kind === "error"}
        <p role="alert" class="m-4 border border-rosu bg-rosu/15 px-4 py-3 text-rosu-fg">
          {campaigns.load.message}
        </p>
      {:else}
        {#if campaigns.load.error}
          <p role="alert" class="m-4 border border-galben bg-galben/15 px-4 py-2 text-galben-fg">
            {campaigns.load.error}
          </p>
        {/if}
        {#each campaigns.load.data as c (c.id)}
          <div class="flex flex-col gap-2 border-b border-line px-5 py-3">
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span class="text-sm font-semibold">
                {KIND_LABELS[c.kind] ?? c.kind}, {(LEVEL_LABELS[c.level] ?? c.level).toLowerCase()}
              </span>
              <span
                class={[
                  "inline-flex items-center px-2 py-0.5 text-[11px] font-semibold tracking-[0.06em] uppercase",
                  TONE_CHIP[c.active ? "verde" : "muted"],
                ]}
              >
                {c.active ? "Activă" : "Încheiată"}
              </span>
              {#if c.active}
                <button
                  type="button"
                  class="sn-btn sn-btn-danger ml-auto px-2.5 py-[5px] text-xs"
                  disabled={busy}
                  onclick={() => end(c.id)}
                >
                  Încheie
                </button>
              {/if}
            </div>
            <span class="text-xs text-fg-muted">
              pornită de {c.started_by_name},
              <span class="font-mono">{time.format(Date.parse(c.started_at))}</span>
              · Avertizare până la
              <span class="font-mono">{time.format(Date.parse(c.warning_until))}</span>
            </span>
            <!-- total is the API's own count: a ringing or in-progress call is in no bucket -->
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-fg-muted">
                Total <span class="font-mono text-fg">{c.progress.total}</span>
              </span>
              {#each progressParts(c.progress) as part (part.key)}
                <span class={["px-2 py-0.5 text-[11.5px] font-semibold", TONE_CHIP[part.tone]]}>
                  <span class="font-mono">{part.n}</span>
                  {part.label}
                </span>
              {/each}
            </div>
          </div>
        {:else}
          <p class="px-5 py-6 text-fg-muted">Nicio campanie.</p>
        {/each}
      {/if}
    </div>
  </section>

  <form class="flex flex-col gap-3 px-5 pt-4 pb-5" onsubmit={start} aria-labelledby="start-title">
    <h2 id="start-title" class="text-[15px] font-extrabold">Lansează o campanie</h2>
    <div class="flex border border-line" role="radiogroup" aria-label="Tip avertizare">
      {#each ["heat", "cold"] as const as k (k)}
        <label
          class={[
            "flex flex-1 cursor-pointer items-center px-3 py-[7px] text-[13px] has-focus-visible:outline-2 has-focus-visible:outline-link",
            k === "cold" && "border-l border-line",
            kind === k ? "bg-link/15 font-semibold text-fg" : "text-fg-soft hover:bg-card",
          ]}
        >
          <input type="radio" name="kind" value={k} bind:group={kind} class="sr-only" />
          {KIND_LABELS[k]}
        </label>
      {/each}
    </div>
    <div class="flex border border-line" role="radiogroup" aria-label="Nivel avertizare">
      {#each ["yellow", "red"] as const as l (l)}
        <label
          class={[
            "flex flex-1 cursor-pointer items-center px-3 py-[7px] text-[13px] has-focus-visible:outline-2 has-focus-visible:outline-link",
            l === "red" && "border-l border-line",
            level === l ? "bg-link/15 font-semibold text-fg" : "text-fg-soft hover:bg-card",
          ]}
        >
          <input type="radio" name="level" value={l} bind:group={level} class="sr-only" />
          {LEVEL_LABELS[l]}
        </label>
      {/each}
    </div>
    <button class="sn-btn sn-btn-success h-9" disabled={busy}>Lansează</button>
    {#if error}
      <p role="alert" class="text-rosu-fg">{error}</p>
    {/if}
    {#if notice}
      <p role="status" class="text-verde-fg">{notice}</p>
    {/if}
  </form>
</div>
