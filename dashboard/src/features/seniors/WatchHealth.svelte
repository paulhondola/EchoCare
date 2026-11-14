<script lang="ts">
  import { fetchWatch, fetchWatchReadings } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { since } from "../../utils/incidents";
  import { TONE_CHIP, type Tone } from "../../utils/labels";
  import { poll } from "../../utils/poll.svelte";
  import { sparkline } from "../../utils/sparkline";

  let { id }: { id: string } = $props();

  const failed = (e: unknown) =>
    `Nu am putut citi ceasul (${e instanceof Error ? e.message : String(e)}).`;
  // A check-in lands every minute; the 24-hour line moves slower (ADR-006)
  const watch = poll((signal) => fetchWatch(id, signal), 30_000, failed);
  const readings = poll((signal) => fetchWatchReadings(id, signal), 60_000, failed);

  // UC-13's states; an unknown one shows as it is
  const STATES: Record<string, { label: string; tone: Tone }> = {
    ok: { label: "Purtat", tone: "verde" },
    not_worn: { label: "Nepurtat", tone: "galben" },
    offline: { label: "Deconectat", tone: "rosu" },
  };

  const W = 300;
  const H = 48;
  type PulseLine = { path: string; lo: number; hi: number };

  function windowLine(windowMs: number): PulseLine | null {
    if (readings.load.kind !== "ok") return null;
    const to = readings.load.at;
    const from = to - windowMs;
    const points = readings.load.data
      .map((r) => ({ t: Date.parse(r.at), v: r.pulse }))
      .filter((p) => p.t >= from && p.t <= to);
    const pulses = points.flatMap((p) => (p.v === null ? [] : [p.v]));
    if (!pulses.length) return null;
    return {
      path: sparkline(points, from, to, W, H),
      lo: Math.min(...pulses),
      hi: Math.max(...pulses),
    };
  }

  const line24h = $derived(windowLine(24 * 3_600_000));
  const line1h = $derived(windowLine(3_600_000));
  const value = (n: number | null, unit = "") => (n === null ? "—" : `${n}${unit}`);
</script>

{#snippet stat(label: string, text: string)}
  <div class="flex flex-col gap-0.5">
    <span class="sn-label">{label}</span>
    <span class="font-mono text-[15px] font-medium">{text}</span>
  </div>
{/snippet}

{#snippet pulseGraph(label: string, spanLabel: string, line: PulseLine | null, emptyText: string)}
  <div class="flex flex-col gap-1 border-t border-line pt-3">
    <span class="sn-label">{label}</span>
    {#if line}
      <svg
        viewBox="0 0 {W} {H}"
        preserveAspectRatio="none"
        class="h-12 w-full text-link"
        role="img"
        aria-label="Puls în {spanLabel}, între {line.lo} și {line.hi} bpm"
      >
        <path
          d={line.path}
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          vector-effect="non-scaling-stroke"
        />
      </svg>
      <span class="font-mono text-xs text-fg-muted">min {line.lo} · max {line.hi} bpm</span>
    {:else}
      <p class="text-fg-muted">{emptyText}</p>
    {/if}
  </div>
{/snippet}

{#if watch.load.kind === "loading"}
  <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
    <span class="loading loading-sm loading-spinner"></span>Se încarcă datele ceasului…
  </div>
{:else if watch.load.kind === "error"}
  <p role="alert" class="text-rosu-fg">{watch.load.message}</p>
{:else if !watch.load.data}
  <p class="text-fg-muted">Ceasul nu a trimis încă date.</p>
{:else}
  {@const w = watch.load.data}
  {@const s = STATES[w.state] ?? { label: w.state, tone: "muted" as Tone }}
  <section class="flex flex-col gap-3 border border-line bg-card p-4" aria-label="Date ceas">
    <div class="flex items-center gap-2">
      <Icon name="watch" />
      <span class="sn-label">Ceas</span>
      <span class={["px-2 py-0.5 text-xs font-semibold", TONE_CHIP[s.tone]]}>{s.label}</span>
      <span class="ml-auto text-xs text-fg-muted">
        Ultimul semnal {since(w.last_check_in_at, watch.load.at)}
      </span>
    </div>

    <div class="grid grid-cols-3 gap-3">
      {@render stat("Puls", value(w.last_pulse, " bpm"))}
      {@render stat("Puls în repaus", value(w.resting_pulse, " bpm"))}
      {@render stat("Baterie", value(w.battery, "%"))}
      {@render stat("Pași azi", value(w.steps_today))}
      {@render stat("Fără pași de", value(w.minutes_without_steps, " min"))}
    </div>

    {#if readings.load.kind === "error"}
      <div class="flex flex-col gap-1 border-t border-line pt-3">
        <span class="sn-label">Puls, ultimele 24 h</span>
        <p role="alert" class="text-rosu-fg">{readings.load.message}</p>
      </div>
    {:else}
      {@render pulseGraph(
        "Puls, ultimele 24 h",
        "ultimele 24 de ore",
        line24h,
        "Fără citiri de puls în ultimele 24 de ore.",
      )}
      {@render pulseGraph(
        "Puls, ultima oră",
        "ultima oră",
        line1h,
        "Fără citiri de puls în ultima oră.",
      )}
    {/if}
    {#if watch.load.error}<p role="alert" class="text-xs text-rosu-fg">{watch.load.error}</p>{/if}
  </section>
{/if}
