<script lang="ts">
  import type { MedicalRecord } from "../../services/api";

  let { record }: { record: MedicalRecord | null } = $props();
</script>

{#if record?.state === "confirmed"}
  <section class="flex flex-col gap-3 border border-line bg-card p-4" aria-label="Fișa medicală">
    <div class="sn-label">Fișa medicală</div>
    {#each (record.items ?? []).filter((i) => i.included) as item, i (i)}
      <div class="flex flex-col gap-1">
        <span class="font-semibold">{item.condition}</span>
        <span class="text-[13px] text-fg-muted">Întrebare: {item.question}</span>
      </div>
    {/each}
    {#if record.pdf_url}
      <a
        href={record.pdf_url}
        target="_blank"
        rel="noopener noreferrer"
        class="sn-btn h-[34px] self-start px-3.5">Deschide PDF</a
      >
    {/if}
  </section>
{:else if record}
  <p class="text-fg-muted">Fișa medicală: în lucru la medic</p>
{/if}
