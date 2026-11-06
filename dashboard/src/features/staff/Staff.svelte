<script lang="ts">
  import { ApiError, grantStaff, setOnDuty, type StaffRole } from "../../services/api";
  import Icon from "../../ui/Icon.svelte";
  import { initials } from "../../utils/incidents";
  import { formatPhone, toE164 } from "../../utils/phone";
  import { getLive } from "../shell/live.svelte";
  import PageHeader from "../shell/PageHeader.svelte";

  const ROLE_LABELS: Record<StaffRole, string> = { das: "Dispecer DAS", medic: "Medic" };

  function refusalMessage(e: unknown): string {
    if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
    if (e.reason === "already_done") return "Numărul are deja acest rol.";
    if (e.reason === "not_allowed") return "Nu aveți dreptul să adăugați personal.";
    if (e.status === 422)
      return "Date invalide. Numărul trebuie să fie de mobil, iar un medic are nevoie de cabinet.";
    return `Nu am putut trimite (${e.message}).`;
  }

  const live = getLive();
  const staff = live.staff;

  let name = $state("");
  let phone = $state("");
  let role = $state<StaffRole>("medic");
  let practice = $state("");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let added = $state<string | null>(null);

  // Whose switch is on its way, and why the last one failed
  let switching = $state<string | null>(null);
  let dutyError = $state<string | null>(null);

  function putOnDuty(id: string) {
    switching = id;
    dutyError = null;
    setOnDuty(id)
      .then(() => staff.reload())
      .catch((e: unknown) => {
        dutyError =
          e instanceof ApiError && e.reason === "not_allowed"
            ? "Doar un dispecer DAS poate fi de serviciu."
            : `Nu am putut schimba dispecerul de serviciu (${e instanceof Error ? e.message : String(e)}).`;
      })
      .finally(() => {
        switching = null;
      });
  }

  const canAdd = $derived(
    name.trim() !== "" && phone.trim() !== "" && (role === "das" || practice.trim() !== ""),
  );

  function add(e: SubmitEvent) {
    e.preventDefault();
    if (!canAdd) return;
    busy = true;
    error = null;
    added = null;
    grantStaff({
      display_name: name.trim(),
      phone: toE164(phone),
      role,
      ...(role === "medic" ? { practice: practice.trim() } : {}),
    })
      .then(() => {
        added = `Adăugat: ${name.trim()}, ${ROLE_LABELS[role].toLowerCase()}.`;
        name = "";
        phone = "";
        practice = "";
        staff.reload();
      })
      .catch((err: unknown) => {
        error = refusalMessage(err);
      })
      .finally(() => {
        busy = false;
      });
  }
</script>

{#if live.onDuty === 0}
  <div
    role="alert"
    class="flex flex-wrap items-center gap-2.5 border-b-2 border-rosu bg-rosu-strong/20 px-5 py-2.5"
  >
    <Icon name="alert" class="text-rosu" />
    <span class="font-extrabold tracking-[0.06em] text-rosu-fg">ATENȚIE:</span>
    <span class="font-semibold">
      Niciun dispecer nu este de serviciu! Apelurile de urgență nu pot fi transferate.
    </span>
  </div>
{/if}

<PageHeader title="Personal" />

<div class="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1fr)_360px]">
  <section class="flex min-h-0 flex-col border-line md:border-r-2" aria-labelledby="staff-title">
    <div class="flex flex-col gap-1 px-5 pt-4 pb-3">
      <h2 id="staff-title" class="text-[15px] font-extrabold">Dispeceri și medici</h2>
      <span class="text-xs text-fg-muted">
        Apelurile Cod Roșu se transferă doar către dispecerul de serviciu.
      </span>
    </div>
    <div class="min-h-0 flex-1 overflow-auto border-t border-line">
      {#if staff.load.kind === "loading"}
        <div role="status" class="loading-delay flex items-center gap-2 p-5 text-fg-muted">
          <span class="loading loading-sm loading-spinner"></span>Se încarcă lista…
        </div>
      {:else if staff.load.kind === "error"}
        <p role="alert" class="m-4 border border-rosu bg-rosu/15 px-4 py-3 text-rosu-fg">
          {staff.load.message}
        </p>
      {:else}
        {#if staff.load.error}
          <p role="alert" class="m-4 border border-galben bg-galben/15 px-4 py-2 text-galben-fg">
            {staff.load.error}
          </p>
        {/if}
        {#if dutyError}
          <p role="alert" class="m-4 border border-rosu bg-rosu/15 px-4 py-2 text-rosu-fg">
            {dutyError}
          </p>
        {/if}
        {#each staff.load.data as s (s.id)}
          <div
            class="grid grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 border-b border-line px-5 py-3"
          >
            <span class="grid size-[34px] place-items-center bg-line text-xs font-extrabold">
              {initials(s.display_name)}
            </span>
            <span class="flex min-w-0 flex-col gap-0.5 leading-tight">
              <span class="text-sm font-semibold">{s.display_name}</span>
              <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="font-mono text-xs text-fg-muted">{formatPhone(s.phone_e164)}</span>
                {#each s.roles as r (r)}
                  <span class="bg-line px-1.5 text-[11px] font-semibold text-fg-soft">
                    {ROLE_LABELS[r] ?? r}
                  </span>
                {/each}
                {#if s.practice}
                  <span class="text-xs text-fg-muted">{s.practice}</span>
                {/if}
              </span>
            </span>
            {#if s.roles.includes("das")}
              <span class="flex items-center gap-2.5">
                <span
                  class={[
                    "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-semibold tracking-[0.06em] uppercase",
                    s.on_duty ? "bg-verde/15 text-verde-fg" : "text-fg-muted",
                  ]}
                >
                  <span class={["size-1.5", s.on_duty ? "bg-verde" : "bg-off"]}></span>
                  {s.on_duty ? "De serviciu" : "Liber"}
                </span>
                {#if !s.on_duty}
                  <button
                    type="button"
                    class="sn-btn sn-btn-link px-2.5 py-[5px] text-xs"
                    disabled={switching !== null}
                    aria-label={`Pune de serviciu pe ${s.display_name}`}
                    onclick={() => putOnDuty(s.id)}
                  >
                    {switching === s.id ? "Se schimbă…" : "Pune de serviciu"}
                  </button>
                {/if}
              </span>
            {/if}
          </div>
        {:else}
          <p class="px-5 py-6 text-fg-muted">Niciun membru al personalului.</p>
        {/each}
      {/if}
    </div>
  </section>

  <form class="flex flex-col gap-3 px-5 pt-4 pb-5" onsubmit={add} aria-labelledby="add-title">
    <h2 id="add-title" class="text-[15px] font-extrabold">Adaugă personal</h2>
    <div class="flex border border-line" role="radiogroup" aria-label="Rol">
      {#each ["medic", "das"] as const as r (r)}
        <label
          class={[
            "flex flex-1 cursor-pointer items-center px-3 py-[7px] text-[13px] has-focus-visible:outline-2 has-focus-visible:outline-link",
            r === "das" && "border-l border-line",
            role === r ? "bg-link/15 font-semibold text-fg" : "text-fg-soft hover:bg-card",
          ]}
        >
          <input type="radio" name="role" value={r} bind:group={role} class="sr-only" />
          {ROLE_LABELS[r]}
        </label>
      {/each}
    </div>
    <label class="flex flex-col gap-1.5">
      <span class="sn-label">Nume</span>
      <input class="sn-input h-9 px-2.5" maxlength={120} bind:value={name} />
    </label>
    <label class="flex flex-col gap-1.5">
      <span class="sn-label">Telefon mobil</span>
      <input
        class="sn-input h-9 px-2.5 font-mono"
        type="tel"
        placeholder="0722 123 456"
        bind:value={phone}
      />
    </label>
    {#if role === "medic"}
      <label class="flex flex-col gap-1.5">
        <span class="sn-label">Cabinet</span>
        <input class="sn-input h-9 px-2.5" maxlength={200} bind:value={practice} />
      </label>
    {/if}
    <button class="sn-btn sn-btn-success h-9" disabled={busy || !canAdd}>Adaugă</button>
    {#if error}
      <p role="alert" class="text-rosu-fg">{error}</p>
    {/if}
    {#if added}
      <p role="status" class="text-verde-fg">{added}</p>
    {/if}
  </form>
</div>
