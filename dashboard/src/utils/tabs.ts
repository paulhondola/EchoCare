/**
 * The tab a key moves to in a tab list (WAI-ARIA tabs pattern): the arrows wrap around, Home and
 * End go to the ends. Null for any other key, so the browser keeps it.
 */
export function nextTab<K>(keys: readonly K[], current: K, key: string): K | null {
  const i = keys.indexOf(current);
  const n = keys.length;
  if (key === "ArrowRight") return keys[(i + 1) % n];
  if (key === "ArrowLeft") return keys[(i - 1 + n) % n];
  if (key === "Home") return keys[0];
  if (key === "End") return keys[n - 1];
  return null;
}

/** A tab's keydown: picks the next tab with [select], then moves focus to it. */
export function tabKeydown<K extends string>(
  keys: readonly K[],
  current: K,
  select: (key: K) => void,
): (e: KeyboardEvent) => void {
  return (e) => {
    const next = nextTab(keys, current, e.key);
    if (next === null) return;
    e.preventDefault();
    select(next);
    (e.currentTarget as HTMLElement)
      .closest('[role="tablist"]')
      ?.querySelector<HTMLElement>(`[data-tab="${next}"]`)
      ?.focus();
  };
}
