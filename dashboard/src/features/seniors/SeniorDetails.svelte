<script lang="ts">
  import { onMount } from "svelte";
  import { fetchSenior, type SeniorSummary, type SeniorView } from "../../services/api";
  import CopyButton from "../../ui/CopyButton.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { address, code, enrollment, TONE_CHIP, TONE_DOT } from "../../utils/labels";
  import { formatPhone } from "../../utils/phone";

  let { senior: summary, onClose }: { senior: SeniorSummary; onClose: () => void } = $props();

  type Load =
    | { kind: "loading" }
    | { kind: "ok"; data: SeniorView }
    | { kind: "error"; message: string };

  let load = $state<Load>({ kind: "loading" });
  let dialogEl: HTMLDialogElement | undefined = $state();

  const stage = $derived(enrollment(summary.enrollment_state));
  // The dossier's read is newer than the list's, so its code wins once it has arrived
  const current = $derived(load.kind === "ok" ? load.data : summary);
  const codeChip = $derived(code(current.code));

  onMount(() => {
    if (dialogEl && !dialogEl.open) dialogEl.showModal();
    const ctrl = new AbortController();
    fetchSenior(summary.id, ctrl.signal)
      .then((data) => {
        load = { kind: "ok", data };
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        load = {
          kind: "error",
          message: `Nu am putut citi dosarul (${e instanceof Error ? e.message : String(e)}).`,
        };
      });
    return () => ctrl.abort();
  });
</script>

{#snippet row(label: string, value: string | null)}
  <div class="grid grid-cols-[150px_minmax(0,1fr)] gap-3 border-b border-line py-3.5">
    <span class="sn-label">{label}</span>
    <span>{value || "—"}</span>
  </div>
{/snippet}

<dialog
  bind:this={dialogEl}
  class="modal modal-end"
  aria-labelledby="senior-title"
  onclose={onClose}
>
  <div
    class="modal-box flex h-full w-[540px] max-w-full flex-col border-l-2 border-line bg-subtle p-0 text-fg shadow-[-24px_0_48px_rgba(1,4,9,.55)]"
  >
    <div class="flex flex-col gap-2.5 border-b-2 border-line px-5 py-4">
      <div class="flex items-center gap-2.5">
        <span
          class={[
            "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
            TONE_CHIP[stage.tone],
          ]}
        >
          <span class={["size-1.5", TONE_DOT[stage.tone]]}></span>{stage.label}
        </span>
        {#if codeChip}
          <span
            class={[
              "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11.5px] font-semibold",
              TONE_CHIP[codeChip.tone],
            ]}
          >
            <span class={["size-1.5", TONE_DOT[codeChip.tone]]}></span>{codeChip.label}
          </span>
          {#if current.reason}
            <span class="text-[13px] text-fg-muted">{current.reason}</span>
          {/if}
        {/if}
        <button
          type="button"
          title="Închide"
          aria-label="Închide"
          class="ml-auto grid size-[30px] cursor-pointer place-items-center border border-line text-fg-soft hover:border-fg-muted hover:text-fg"
          onclick={() => dialogEl?.close()}
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <div class="flex flex-wrap items-baseline gap-2.5">
        <h2 id="senior-title" class="text-2xl leading-[1.1] font-extrabold tracking-[-0.015em]">
          {summary.full_name}
        </h2>
        <span class="text-[13px] text-fg-muted">{summary.form_of_address}</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <a href={`tel:${summary.phone_e164}`} class="sn-btn h-[34px] px-3.5">
          <Icon name="phone" size={13} />Apelează senior
        </a>
        {#if load.kind === "ok"}
          <CopyButton
            class="h-[34px] px-3.5"
            icon="copy"
            label="Copiază adresa"
            text={address(load.data)}
          />
        {/if}
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-auto px-5 pt-[18px] pb-6">
      {#if load.kind === "loading"}
        <div role="status" class="loading-delay flex items-center gap-2 text-fg-muted">
          <span class="loading loading-sm loading-spinner"></span>Se încarcă dosarul…
        </div>
      {:else if load.kind === "error"}
        <p role="alert" class="text-rosu-fg">{load.message}</p>
      {:else}
        {@const s = load.data}
        <div class="flex flex-col">
          <div
            class="grid grid-cols-[150px_minmax(0,1fr)] items-center gap-3 border-b border-line pb-3.5"
          >
            <span class="sn-label">Telefon senior</span>
            <span class="font-mono text-[13px] font-medium">
              {formatPhone(s.phone_e164)}
              <span class="font-sans text-[10px] font-semibold tracking-[0.06em] text-fg-muted">
                {s.phone_is_landline ? "FIX" : "MOBIL"}
              </span>
            </span>
          </div>
          {@render row("Adresă", address(s))}
          {@render row("Interfon", s.intercom_code)}
          {@render row("Cheie de rezervă", s.key_holder)}
          {@render row("Reper orientare", s.landmark)}
          {@render row("Interval de apel", s.call_window)}
          {@render row(
            "Medic de familie",
            [s.medic.display_name, s.medic.practice].filter(Boolean).join(" · "),
          )}

          <div class="sn-label pt-4 pb-2">Aparținători înregistrați</div>
          {#each s.caregivers as c (c.user_id)}
            <div
              class="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-line py-2.5"
            >
              <span>
                <span class="font-semibold">{c.display_name}</span>
                {#if c.relation}<span class="text-fg-muted">· {c.relation}</span>{/if}
              </span>
              <span class="font-mono text-[13px] font-medium">{formatPhone(c.phone_e164)}</span>
              <a href={`tel:${c.phone_e164}`} class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs">
                Apelează
              </a>
            </div>
          {:else}
            <p class="text-fg-muted">Niciun aparținător înregistrat.</p>
          {/each}
        </div>
      {/if}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>Închide</button>
  </form>
</dialog>
