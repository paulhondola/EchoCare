<script lang="ts">
  import { page } from "$app/state";
  import Brand from "../../ui/Brand.svelte";
  import Icon, { type IconName } from "../../ui/Icon.svelte";
  import { initials } from "../../utils/incidents";
  import SystemHealthIndicator from "../system/SystemHealthIndicator.svelte";
  import { getLive } from "./live.svelte";
  import { armSiren } from "./siren";

  let { name, onSignOut }: { name: string; onSignOut: () => void } = $props();

  const live = getLive();

  const count = (l: { kind: string; data?: unknown[] }) =>
    l.kind === "ok" && l.data ? l.data.length : null;

  type Item = { href: string; label: string; icon: IconName; count: number | null; on: boolean };

  const items: Item[] = $derived([
    {
      href: "/",
      label: "Incidente",
      icon: "siren",
      count: live.open?.length ?? null,
      on: page.url.pathname === "/",
    },
    {
      href: "/seniors",
      label: "Monitorizare seniori",
      icon: "users",
      count: count(live.seniors.load),
      on: page.url.pathname.startsWith("/seniors"),
    },
    {
      href: "/enrollments",
      label: "Cereri înrolare",
      icon: "clipboard",
      count: count(live.enrollments.load),
      on: page.url.pathname.startsWith("/enrollments"),
    },
    {
      href: "/staff",
      label: "Personal",
      icon: "user-check",
      count: count(live.staff.load),
      on: page.url.pathname.startsWith("/staff"),
    },
  ]);

  function toggleSound() {
    if (!live.sound) armSiren();
    live.sound = !live.sound;
  }
</script>

<aside
  class="flex min-h-0 flex-col border-line bg-subtle max-md:border-b-2 md:sticky md:top-0 md:h-screen md:border-r-2"
>
  <div class="flex flex-col gap-1 border-b-2 border-line px-4 pt-[18px] pb-4">
    <Brand />
    <SystemHealthIndicator />
  </div>

  <nav class="flex flex-col gap-0.5 px-2 py-2.5" aria-label="Secțiuni">
    {#each items as item (item.href)}
      <a
        href={item.href}
        aria-current={item.on ? "page" : undefined}
        class={[
          "flex items-center gap-2.5 border px-2.5 py-2 no-underline",
          item.on
            ? "border-line bg-card font-semibold text-fg"
            : "border-transparent text-fg-soft hover:bg-card",
        ]}
      >
        <Icon
          name={item.icon}
          class={item.on ? (item.href === "/" ? "text-rosu" : "text-link") : "text-fg-muted"}
        />
        <span>{item.label}</span>
        {#if item.count !== null}
          <span
            class={[
              "sn-count ml-auto",
              item.href === "/" && item.count > 0
                ? "bg-rosu-strong text-white"
                : ["bg-line font-medium", item.on ? "text-fg" : "text-fg-soft"],
            ]}
          >
            {item.count}
          </span>
        {/if}
      </a>
    {/each}
  </nav>

  <div class="mt-auto flex flex-col gap-3.5 border-t-2 border-line px-4 pt-3.5 pb-4">
    <button
      type="button"
      role="switch"
      aria-checked={live.sound}
      onclick={toggleSound}
      class="flex w-full cursor-pointer items-center gap-2.5 text-left"
    >
      <Icon name="volume" />
      <span>Alerte sonore</span>
      <span class="ml-auto font-mono text-[11px] font-medium text-fg-muted">
        {live.sound ? "Active" : "Oprite"}
      </span>
      <span
        class={[
          "flex h-4 w-[30px] p-0.5",
          live.sound ? "justify-end bg-verde-strong" : "justify-start bg-off",
        ]}
      >
        <span class="size-3 bg-fg"></span>
      </span>
    </button>
    <div class="flex items-center gap-2.5">
      <span class="grid size-[30px] place-items-center bg-line text-[11px] font-extrabold">
        {initials(name)}
      </span>
      <span class="flex min-w-0 flex-col leading-tight">
        <span class="text-[11px] text-fg-muted">Dispecer</span>
        <span class="truncate font-semibold">{name}</span>
      </span>
      <button
        type="button"
        title="Ieșire"
        aria-label="Ieșire"
        onclick={onSignOut}
        class="ml-auto grid size-[30px] cursor-pointer place-items-center border border-line text-fg-muted hover:border-fg-muted hover:text-fg"
      >
        <Icon name="log-out" size={14} />
      </button>
    </div>
  </div>
</aside>
