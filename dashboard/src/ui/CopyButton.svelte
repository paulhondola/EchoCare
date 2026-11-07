<script lang="ts">
  import { onDestroy } from "svelte";
  import Icon, { type IconName } from "./Icon.svelte";

  let {
    text,
    label,
    icon,
    mono = false,
    class: className = "",
  }: { text: string; label: string; icon: IconName; mono?: boolean; class?: string } = $props();

  let result = $state<"copied" | "failed" | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  onDestroy(() => clearTimeout(timer));

  function show(r: "copied" | "failed") {
    result = r;
    clearTimeout(timer);
    timer = setTimeout(() => (result = null), r === "copied" ? 1400 : 4000);
  }

  // "Copiat" only once the browser confirms it: the dispatcher pastes this into the ambulance
  // request, and a failed copy leaves whatever was on the clipboard before.
  function copy() {
    if (!navigator.clipboard) return show("failed");
    navigator.clipboard.writeText(text).then(
      () => show("copied"),
      () => show("failed"),
    );
  }
</script>

<button
  type="button"
  class={[
    "sn-btn font-semibold hover:border-link hover:text-fg",
    result === "failed" ? "text-rosu-fg" : "text-fg-soft",
    className,
  ]}
  onclick={copy}
>
  <Icon name={icon} size={13} />
  <span class={[mono && "font-mono font-medium"]}>
    {result === "copied" ? "Copiat" : result === "failed" ? "Nu s-a copiat" : label}
  </span>
</button>
