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
    const currentController = new AbortController();
    controller = currentController;

    try {
      const data = await read(currentController.signal);
      if (!active || currentController.signal.aborted) return;
      load = { kind: "ok", data, at: Date.now() };
    } catch (err) {
      if (
        !active ||
        currentController.signal.aborted ||
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      ) {
        return;
      }
      const message = describe(err);
      if (load.kind === "ok") {
        load = { ...load, error: message };
      } else {
        load = { kind: "error", message };
      }
    } finally {
      if (controller === currentController) controller = null;
      if (active && !currentController.signal.aborted) {
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
      // A read sent before the command would land after it and undo the change: read again
      if (controller) void execute();
    },
  };
}
