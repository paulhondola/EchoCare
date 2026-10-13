import { onDestroy } from "svelte";

export type Load<T> =
  | { kind: "loading" }
  // error: the last read failed; the screen keeps the last good data
  | { kind: "ok"; data: T; at: number; error?: string }
  | { kind: "error"; message: string };

/** Reads now and every `ms` until the component goes away (04 §6). Call it while the component is set up. */
export function poll<T>(
  read: (signal: AbortSignal) => Promise<T>,
  ms: number,
  describe: (e: unknown) => string,
): {
  readonly load: Load<T>;
  /** Re-reads at once: after a refused command the data is out of date */
  reload(): void;
  /** Applies a command's answer without waiting for the next read */
  update(change: (data: T) => T): void;
} {
  let load = $state<Load<T>>({ kind: "loading" });
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let active = true;

  async function execute() {
    if (timer) clearTimeout(timer);
    if (controller) controller.abort();
    controller = new AbortController();

    try {
      const data = await read(controller.signal);
      if (!active) return;
      load = { kind: "ok", data, at: Date.now() };
    } catch (err) {
      if (!active || (err instanceof DOMException && err.name === "AbortError")) return;
      const message = describe(err);
      if (load.kind === "ok") {
        load = { ...load, error: message };
      } else {
        load = { kind: "error", message };
      }
    } finally {
      if (active) {
        timer = setTimeout(execute, ms);
      }
    }
  }

  try {
    onDestroy(() => {
      active = false;
      if (timer) clearTimeout(timer);
      if (controller) controller.abort();
    });
  } catch {
    // Called outside component lifecycle (e.g. unit tests)
  }

  void execute();

  return {
    get load() {
      return load;
    },
    reload() {
      void execute();
    },
    update(change: (data: T) => T) {
      if (load.kind === "ok") {
        load = { ...load, data: change(load.data) };
      }
    },
  };
}
