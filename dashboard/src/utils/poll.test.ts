import { describe, expect, it, vi } from "vitest";
import { poll } from "./poll.svelte";

describe("poll", () => {
  it("initializes with loading state and transitions to ok on success", async () => {
    let callCount = 0;
    const poller = poll(
      async () => {
        callCount++;
        return ["item1", "item2"];
      },
      1000,
      (err) => String(err),
    );

    expect(poller.load.kind).toBe("loading");

    // Wait for the initial read to settle
    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
    });

    if (poller.load.kind === "ok") {
      expect(poller.load.data).toEqual(["item1", "item2"]);
      expect(typeof poller.load.at).toBe("number");
    }
    expect(callCount).toBe(1);
  });

  it("sets error state on initial failure", async () => {
    const poller = poll(
      async () => {
        throw new Error("network failed");
      },
      1000,
      (err) => (err instanceof Error ? err.message : String(err)),
    );

    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("error");
    });

    if (poller.load.kind === "error") {
      expect(poller.load.message).toBe("network failed");
    }
  });

  it("preserves good data with error field on subsequent poll failure", async () => {
    let succeed = true;
    const poller = poll(
      async () => {
        if (!succeed) throw new Error("temporary blip");
        return { count: 42 };
      },
      50,
      (err) => (err instanceof Error ? err.message : String(err)),
    );

    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
    });

    // Make next read fail
    succeed = false;
    await vi.waitFor(
      () => {
        expect(poller.load.kind).toBe("ok");
        if (poller.load.kind === "ok") {
          expect(poller.load.error).toBe("temporary blip");
          expect(poller.load.data).toEqual({ count: 42 });
        }
      },
      { timeout: 500 },
    );
  });

  it("updates data with update()", async () => {
    const poller = poll(
      async () => [1, 2],
      1000,
      (err) => String(err),
    );

    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
    });

    poller.update((items) => [...items, 3]);

    if (poller.load.kind === "ok") {
      expect(poller.load.data).toEqual([1, 2, 3]);
    }
  });

  it("triggers an immediate read with reload()", async () => {
    let count = 0;
    const poller = poll(
      async () => {
        count++;
        return count;
      },
      10000,
      (err) => String(err),
    );

    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
      if (poller.load.kind === "ok") {
        expect(poller.load.data).toBe(1);
      }
    });

    poller.reload();

    await vi.waitFor(() => {
      if (poller.load.kind === "ok") {
        expect(poller.load.data).toBe(2);
      }
    });
  });

  it("aborts in-flight read on reload() without setting error state", async () => {
    const abortedSignals: boolean[] = [];
    let callCount = 0;

    const poller = poll(
      (signal) => {
        callCount++;
        const currentCall = callCount;
        return new Promise<string[]>((resolve, reject) => {
          signal.addEventListener("abort", () => {
            abortedSignals.push(signal.aborted);
            reject(new DOMException("Aborted", "AbortError"));
          });
          if (currentCall === 1) {
            // Leave first call pending until aborted
          } else {
            resolve(["second"]);
          }
        });
      },
      10000,
      (err) => (err instanceof Error ? err.message : String(err)),
    );

    expect(poller.load.kind).toBe("loading");

    // Call reload while first is still pending
    poller.reload();

    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
    });

    if (poller.load.kind === "ok") {
      expect(poller.load.data).toEqual(["second"]);
      expect(poller.load.error).toBeUndefined();
    }
    expect(abortedSignals).toEqual([true]);
  });

  it("ignores generic Error with name AbortError without error state", async () => {
    let callCount = 0;
    const poller = poll(
      () => {
        callCount++;
        if (callCount === 1) {
          const err = new Error("This operation was aborted");
          err.name = "AbortError";
          throw err;
        }
        return Promise.resolve(["recovered"]);
      },
      50,
      (err) => (err instanceof Error ? err.message : String(err)),
    );

    // Initial read threw an AbortError - it should NOT transition load to error
    expect(poller.load.kind).toBe("loading");
    await vi.waitFor(() => {
      expect(poller.load.kind).toBe("ok");
    });
    if (poller.load.kind === "ok") {
      expect(poller.load.data).toEqual(["recovered"]);
    }
  });
});
