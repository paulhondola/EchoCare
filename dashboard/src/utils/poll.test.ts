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
});
