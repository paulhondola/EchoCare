<script lang="ts">
  import { ApiError, fetchStaff, grantStaff, type StaffRole } from "../../services/api";
  import { toE164 } from "../../utils/phone";
  import { poll } from "../../utils/poll.svelte";

  const REFRESH_MS = 15_000;
  const ROLE_LABELS: Record<StaffRole, string> = { das: "Dispecer DAS", medic: "Medic" };

  function refusalMessage(e: unknown): string {
    if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
    if (e.reason === "already_done") return "Numărul are deja acest rol.";
    if (e.reason === "not_allowed") return "Nu aveți dreptul să adăugați personal.";
    if (e.status === 422)
      return "Date invalide. Numărul trebuie să fie de mobil, iar un medic are nevoie de cabinet.";
    return `Nu am putut trimite (${e.message}).`;
  }

  function describe(e: unknown): string {
    return `Nu am putut citi lista (${e instanceof Error ? e.message : String(e)}).`;
  }

  const poller = poll(fetchStaff, REFRESH_MS, describe);

  let name = $state("");
  let phone = $state("");
  let role = $state<StaffRole>("medic");
  let practice = $state("");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let added = $state<string | null>(null);

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
        poller.reload();
      })
      .catch((err: unknown) => {
        error = refusalMessage(err);
      })
      .finally(() => {
        busy = false;
      });
  }
</script>

<section class="grid items-start gap-6 lg:grid-cols-[1fr_320px]">
  <div>
    <h2 class="mb-3 text-lg font-semibold">Personal</h2>
    {#if poller.load.kind === "loading"}
      <div role="status" class="alert">
        <span class="loading loading-spinner loading-sm"></span>
        Se încarcă lista…
      </div>
    {:else if poller.load.kind === "error"}
      <div role="alert" class="alert alert-error alert-soft mb-3">
        {poller.load.message}
      </div>
    {:else if poller.load.kind === "ok"}
      {#if poller.load.error}
        <div role="alert" class="alert alert-warning alert-soft mb-3">
          {poller.load.error}
        </div>
      {/if}
      <div class="overflow-x-auto">
        <table class="table table-sm">
          <thead>
            <tr>
              <th>Nume</th>
              <th>Telefon</th>
              <th>Rol</th>
              <th>Cabinet</th>
            </tr>
          </thead>
          <tbody>
            {#each poller.load.data as s (s.id)}
              <tr>
                <td>
                  {s.display_name}
                  {#if s.on_duty}
                    <span class="badge badge-xs badge-success ml-2">de serviciu</span>
                  {/if}
                </td>
                <td class="whitespace-nowrap">{s.phone_e164}</td>
                <td>
                  {#each s.roles as r (r)}
                    <span class="badge badge-sm badge-soft mr-1">
                      {ROLE_LABELS[r] ?? r}
                    </span>
                  {/each}
                </td>
                <td>{s.practice ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>

  <form class="card card-sm bg-base-100 shadow-sm" onsubmit={add}>
    <div class="card-body gap-2">
      <h3 class="card-title text-base">Adaugă</h3>
      <select class="select select-sm w-full" aria-label="Rol" bind:value={role}>
        <option value="medic">{ROLE_LABELS.medic}</option>
        <option value="das">{ROLE_LABELS.das}</option>
      </select>
      <input
        class="input input-sm w-full"
        aria-label="Nume"
        placeholder="Nume"
        maxlength={120}
        bind:value={name}
      />
      <input
        class="input input-sm w-full"
        aria-label="Telefon mobil"
        placeholder="Telefon mobil, ex. 0722 123 456"
        type="tel"
        bind:value={phone}
      />
      {#if role === "medic"}
        <input
          class="input input-sm w-full"
          aria-label="Cabinet"
          placeholder="Cabinet"
          maxlength={200}
          bind:value={practice}
        />
      {/if}
      <button class="btn btn-sm btn-primary" disabled={busy || !canAdd}> Adaugă </button>
      {#if error}
        <p role="alert" class="text-sm text-error">
          {error}
        </p>
      {/if}
      {#if added}
        <p role="status" class="text-sm text-success">
          {added}
        </p>
      {/if}
    </div>
  </form>
</section>
