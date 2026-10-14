<script lang="ts">
  import type { Snippet } from "svelte";
  import { getLive } from "./live.svelte";

  let { title, actions, children }: { title: string; actions?: Snippet; children?: Snippet } =
    $props();

  const live = getLive();
</script>

<!-- Title row with who is on duty (P10), then the page's tabs and search, over a 2px rule -->
<header class={["flex flex-col gap-3 border-b-2 border-line px-5 pt-[18px]", !children && "pb-4"]}>
  <div class="flex flex-wrap items-center gap-3">
    <h1 class="text-[22px] leading-[1.1] font-extrabold tracking-[-0.015em] text-fg">{title}</h1>
    {#if live.onDuty !== null}
      <span
        class={[
          "inline-flex items-center gap-1.5 px-[9px] py-[3px] text-[11.5px] font-semibold",
          live.onDuty > 0 ? "bg-verde/15 text-verde-fg" : "bg-rosu/15 text-rosu-fg",
        ]}
      >
        <span class={["size-1.5", live.onDuty > 0 ? "bg-verde" : "bg-rosu"]}></span>
        {live.onDuty === 0
          ? "Nimeni de serviciu"
          : live.onDuty === 1
            ? "1 dispecer de serviciu"
            : `${live.onDuty} dispeceri de serviciu`}
      </span>
    {/if}
    {#if actions}
      <div class="ml-auto flex gap-2">{@render actions()}</div>
    {/if}
  </div>
  {#if children}
    <div class="flex flex-wrap items-end gap-4">{@render children()}</div>
  {/if}
</header>
