<script lang="ts">
  // The home node's floor sweep as a half circle seen from above (P24, 08-ecou.md §3.3):
  // Ecou at the bottom centre, 0° to its right, 180° to its left, the room's outline from
  // the sweep, and the object it found. No image of the senior exists; only distances.
  let {
    scan,
    angleDeg,
    distanceM,
  }: { scan: number[]; angleDeg: number | null; distanceM: number | null } = $props();

  const W = 360;
  const R = 150; // the drawing's radius, in px
  const CX = W / 2;
  const CY = 170;

  // The farthest echo sets the scale, never less than 3 m, rounded up to a whole metre
  const range = $derived(Math.max(3, Math.ceil(Math.max(0, ...scan))));
  const rings = $derived(Array.from({ length: range }, (_, i) => i + 1));

  function point(deg: number, metres: number): [number, number] {
    const r = (metres / range) * R;
    const rad = (deg * Math.PI) / 180;
    return [CX + r * Math.cos(rad), CY - r * Math.sin(rad)];
  }

  const step = $derived(scan.length > 1 ? 180 / (scan.length - 1) : 0);
  const outline = $derived(
    scan
      .map((m, i) =>
        point(i * step, m)
          .map((v) => v.toFixed(1))
          .join(","),
      )
      .join(" "),
  );
  const found = $derived(
    angleDeg !== null && distanceM !== null ? point(angleDeg, distanceM) : null,
  );

  /** „la 2,1 m, în stânga”: where to look, from the robot's side of the room */
  const where = $derived.by(() => {
    if (angleDeg === null || distanceM === null) return null;
    const side = angleDeg > 112.5 ? "în stânga" : angleDeg < 67.5 ? "în dreapta" : "în față";
    return `pe jos, la ${distanceM.toLocaleString("ro-RO", { maximumFractionDigits: 1 })} m, ${side}`;
  });
</script>

<div class="flex flex-col gap-2">
  <svg
    viewBox={`0 0 ${W} 190`}
    class="w-full max-w-[420px]"
    role="img"
    aria-label={where ?? "Harta camerei"}
  >
    {#each rings as m (m)}
      <path
        d={`M ${CX - (m / range) * R} ${CY} A ${(m / range) * R} ${(m / range) * R} 0 0 1 ${CX + (m / range) * R} ${CY}`}
        class="fill-none stroke-line"
        stroke-dasharray="2 4"
      />
      <text
        x={CX + (m / range) * R - 2}
        y={CY + 13}
        class="fill-fg-subtle font-mono text-[9px]"
        text-anchor="end">{m} m</text
      >
    {/each}
    <line x1={CX - R} y1={CY} x2={CX + R} y2={CY} class="stroke-line" />
    {#if scan.length > 1}
      <polygon
        points={`${CX},${CY} ${outline}`}
        class="fill-link/10 stroke-link"
        stroke-width="1.5"
      />
    {/if}
    {#if found}
      <circle cx={found[0]} cy={found[1]} r="9" class="fill-rosu/25 stroke-rosu" stroke-width="2" />
      <circle cx={found[0]} cy={found[1]} r="3" class="fill-rosu" />
    {/if}
    <rect x={CX - 9} y={CY - 6} width="18" height="12" class="fill-fg" />
    <text x={CX} y={CY + 24} class="fill-fg-muted text-[10px]" text-anchor="middle">Ecou</text>
  </svg>
  {#if where}
    <span class="font-semibold text-rosu-fg">{where}</span>
  {/if}
</div>
