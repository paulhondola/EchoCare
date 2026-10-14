<script lang="ts">
  import type { Snippet } from "svelte";
  import { Live, setLive } from "./live.svelte";
  import Sidebar from "./Sidebar.svelte";
  import { playSiren } from "./siren";

  let { name, onSignOut, children }: { name: string; onSignOut: () => void; children: Snippet } =
    $props();

  const live = new Live();
  setLive(live);

  const openCount = $derived(
    live.incidents.load.kind === "ok"
      ? live.incidents.load.data.filter((i) => i.status === "open").length
      : 0,
  );

  // A new open incident rings the siren when Alerte sonore is on (spec 07 §1, UC-11). The
  // first read only learns what is already open.
  let seen: Set<string> | null = null;
  $effect(() => {
    const load = live.incidents.load;
    if (load.kind !== "ok") return;
    const open = load.data.filter((i) => i.status === "open").map((i) => i.id);
    const fresh = seen !== null && open.some((id) => !seen!.has(id));
    seen = new Set(open);
    if (fresh && live.sound) playSiren();
  });
</script>

<svelte:head>
  <title>{openCount > 0 ? `(${openCount}) ` : ""}Sentinela DAS</title>
</svelte:head>

<div class="grid min-h-screen md:h-screen md:grid-cols-[240px_minmax(0,1fr)]">
  <Sidebar {name} {onSignOut} />
  <main class="relative flex min-h-0 min-w-0 flex-col">
    {@render children()}
  </main>
</div>
