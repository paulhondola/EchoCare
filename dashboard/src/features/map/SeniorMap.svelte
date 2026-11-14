<script lang="ts">
  import L from "leaflet";
  import "leaflet/dist/leaflet.css";
  import { onMount } from "svelte";
  import type { SeniorSummary } from "../../services/api";
  import { code } from "../../utils/labels";
  import SeniorDetails from "../seniors/SeniorDetails.svelte";
  import { getLive } from "../shell/live.svelte";

  // Every senior as a pin in her code's colour; a red one pulses, a live call rings
  // (design 2026-11-14 §7). Points are approximate, from the street table on the server.
  const live = getLive();
  const TIMISOARA: L.LatLngTuple = [45.7537, 21.2257];

  let el: HTMLDivElement | undefined = $state();
  let map: L.Map | null = $state(null);
  const pins = new Map<string, { marker: L.Marker; key: string }>();
  let selected = $state<SeniorSummary | null>(null);

  const seniors = $derived(live.seniors.load.kind === "ok" ? live.seniors.load.data : []);
  const placed = $derived(seniors.filter((s) => s.latitude != null && s.longitude != null));
  const unplaced = $derived(seniors.length - placed.length);
  const calling = $derived(
    new Set(
      live.liveCalls.load.kind === "ok" ? live.liveCalls.load.data.map((c) => c.senior_id) : [],
    ),
  );

  onMount(() => {
    if (!el) return;
    const m = L.map(el, { zoomControl: true, attributionControl: true }).setView(TIMISOARA, 13);
    // OpenStreetMap's own tiles need no key; CSS turns them dark to match the dashboard
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
      className: "sn-dark-tiles",
    }).addTo(m);
    map = m;
    return () => {
      m.remove();
      pins.clear();
      map = null;
    };
  });

  function icon(tone: string, ringing: boolean): L.DivIcon {
    return L.divIcon({
      className: "",
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      html: `<span class="sn-pin sn-pin-${tone}${ringing ? " sn-pin-live" : ""}"><i></i></span>`,
    });
  }

  // Add, recolour or drop pins as the reads change, without rebuilding the map
  $effect(() => {
    const m = map;
    if (!m) return;
    const seen = new Set<string>();
    for (const s of placed) {
      seen.add(s.id);
      const tone = code(s.code)?.tone ?? "muted";
      const ringing = calling.has(s.id);
      const key = `${tone}:${ringing}`;
      const pin = pins.get(s.id);
      if (!pin) {
        const marker = L.marker([s.latitude!, s.longitude!], { icon: icon(tone, ringing) })
          .bindTooltip(s.full_name, { direction: "top", offset: [0, -8] })
          .on("click", () => (selected = seniors.find((x) => x.id === s.id) ?? null))
          .addTo(m);
        pins.set(s.id, { marker, key });
      } else if (pin.key !== key) {
        pin.marker.setIcon(icon(tone, ringing));
        pin.key = key;
      }
    }
    for (const [id, pin] of pins) {
      if (!seen.has(id)) {
        pin.marker.remove();
        pins.delete(id);
      }
    }
  });
</script>

<div class="relative h-[70vh] min-h-0 border-t-2 border-line md:h-auto md:flex-1">
  <div bind:this={el} class="absolute inset-0 bg-canvas" aria-label="Harta seniorilor"></div>
</div>
{#if unplaced > 0}
  <p class="border-t border-line px-5 py-2 text-xs text-fg-muted">Fără locație: {unplaced}</p>
{/if}

{#if selected}
  {#key selected.id}
    <SeniorDetails
      senior={selected}
      onClose={() => (selected = null)}
      onErased={() => {
        selected = null;
        live.seniors.reload();
      }}
    />
  {/key}
{/if}

<style>
  :global(.sn-pin) {
    position: relative;
    display: block;
    width: 18px;
    height: 18px;
  }
  :global(.sn-pin > i) {
    position: absolute;
    inset: 3px;
    border: 2px solid var(--color-canvas);
    border-radius: 9999px;
    background: var(--color-fg-muted);
  }
  :global(.sn-pin-verde > i) {
    background: var(--color-verde);
  }
  :global(.sn-pin-galben > i) {
    background: var(--color-galben);
  }
  :global(.sn-pin-rosu > i) {
    background: var(--color-rosu);
  }
  /* A red senior pulses; a senior on a live call rings in the link colour */
  :global(.sn-pin-rosu::after),
  :global(.sn-pin-live::before) {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: 9999px;
    animation: sn-pin-ring 1.4s ease-out infinite;
  }
  :global(.sn-pin-rosu::after) {
    border: 2px solid var(--color-rosu);
  }
  :global(.sn-pin-live::before) {
    border: 2px solid var(--color-link);
    animation-delay: 0.7s;
  }
  @keyframes -global-sn-pin-ring {
    0% {
      transform: scale(1);
      opacity: 0.9;
    }
    100% {
      transform: scale(3);
      opacity: 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    :global(.sn-pin-rosu::after),
    :global(.sn-pin-live::before) {
      animation: none;
    }
  }
  :global(.sn-dark-tiles) {
    filter: invert(1) hue-rotate(180deg) brightness(0.85) contrast(0.9);
  }
  :global(.leaflet-container) {
    background: var(--color-canvas);
    font-family: inherit;
  }
</style>
