// A5 channel opt-outs and A9 stop().
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { Channel } from "../src/index";
import { Harness, clipboard, keyDown, keyUp, pointer } from "./harness";

const CODES: Record<Channel, number[]> = {
  keystroke: [1, 2],
  pointer: [3, 4, 5],
  interaction: [6, 7, 8, 9, 10, 11, 12, 13],
};

const KEY_TYPES = ["keydown", "keyup"];
const POINTER_TYPES = ["pointermove", "pointerdown", "pointerup"];
const INTERACTION_TYPES = ["wheel", "scroll", "focus", "blur", "copy", "cut", "paste"];

let input: HTMLInputElement;

beforeEach(() => {
  document.body.innerHTML = `<input id="i" type="text">`;
  input = document.getElementById("i") as HTMLInputElement;
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

/** Produces at least one event of every code. */
function exercise(h: Harness): void {
  input.focus();
  keyDown(input, { key: "a", code: "KeyA" });
  h.advance(50);
  keyUp(input, { key: "a", code: "KeyA" });
  pointer(input, "pointermove", 1, 1);
  pointer(input, "pointerdown", 1, 1);
  pointer(input, "pointerup", 1, 1);
  document.body.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: 10 }));
  document.dispatchEvent(new Event("scroll"));
  clipboard(input, "copy", "x", () => undefined);
  window.dispatchEvent(new FocusEvent("blur"));
  h.handle.setPage(2);
  h.handle.markAction(1);
  input.blur();
}

function registeredTypes(target: EventTarget): () => string[] {
  const spy = vi.spyOn(target, "addEventListener");
  return () => spy.mock.calls.map((c) => c[0]);
}

describe("channel opt-outs (A5)", () => {
  test("with every channel enabled, every code is produced", async () => {
    const h = new Harness();
    h.start();
    exercise(h);
    await h.handle.stop();
    const seen = new Set(h.events().map((e) => e[0]));
    for (const code of [...CODES.keystroke, ...CODES.pointer, ...CODES.interaction]) {
      expect(seen.has(code), `code ${code}`).toBe(true);
    }
  });

  test.each(["keystroke", "pointer", "interaction"] as const)(
    "an opted-out %s channel produces none of its codes",
    async (channel) => {
      const h = new Harness();
      h.start({ channels: { keystroke: true, pointer: true, interaction: true, [channel]: false } });
      exercise(h);
      await h.handle.stop();
      const codes = new Set(h.events().map((e) => e[0]));
      for (const code of CODES[channel]) expect(codes.has(code), `code ${code}`).toBe(false);
      expect(codes.size).toBeGreaterThan(0);
    },
  );

  test("a disabled channel registers no listeners for its events", async () => {
    const onDoc = registeredTypes(document);
    const onWin = registeredTypes(window);
    const h = new Harness();
    h.start({ channels: { keystroke: false, pointer: false, interaction: false } });
    const all = [...onDoc(), ...onWin()];
    for (const type of [...KEY_TYPES, ...POINTER_TYPES, ...INTERACTION_TYPES]) {
      expect(all).not.toContain(type);
    }
    await h.handle.stop();
  });
});

describe("stop (A9)", () => {
  test("stop() flushes pending events", async () => {
    const h = new Harness();
    h.start({ flushIntervalMs: 60_000 });
    h.handle.setPage(5);
    await h.handle.stop();
    expect(h.events()).toEqual([[12, 0, 5]]);
  });

  test("events after stop() are not captured or sent", async () => {
    const h = new Harness();
    h.start();
    await h.handle.stop();
    const before = h.requests.length;
    exercise(h);
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("pagehide"));
    await h.handle.flush();
    expect(h.requests.length).toBe(before);
  });

  test("stop() removes every listener it added", async () => {
    const added: Array<[EventTarget, string, unknown, boolean]> = [];
    const removed: Array<[EventTarget, string, unknown, boolean]> = [];
    const capture = (o: unknown) =>
      typeof o === "boolean" ? o : Boolean((o as AddEventListenerOptions | undefined)?.capture);
    for (const target of [document, window] as EventTarget[]) {
      const add = target.addEventListener.bind(target);
      const remove = target.removeEventListener.bind(target);
      vi.spyOn(target, "addEventListener").mockImplementation((type, fn, o) => {
        added.push([target, type, fn, capture(o)]);
        add(type, fn, o);
      });
      vi.spyOn(target, "removeEventListener").mockImplementation((type, fn, o) => {
        removed.push([target, type, fn, capture(o)]);
        remove(type, fn, o);
      });
    }
    const h = new Harness();
    h.start();
    expect(added.length).toBeGreaterThan(10);
    await h.handle.stop();
    for (const entry of added) {
      expect(
        removed.some((r) => r[0] === entry[0] && r[1] === entry[1] && r[2] === entry[2] && r[3] === entry[3]),
        `listener for ${entry[1]} removed`,
      ).toBe(true);
    }
  });
});
