// Event times come from the event's own timeStamp (performance.now() clock),
// not from the clock when the handler runs, so event-loop delay does not
// distort dwell and flight times.
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { Harness, withTimeStamp } from "./harness";

let h: Harness;
let input: HTMLInputElement;

beforeEach(() => {
  document.body.innerHTML = `<input id="i" type="text">`;
  input = document.getElementById("i") as HTMLInputElement;
  h = new Harness();
  h.clock = 1000; // stream start on the performance clock
  h.start({ flushIntervalMs: 60_000 });
});

afterEach(async () => {
  await h.handle.stop();
  document.body.innerHTML = "";
});

function key(type: "keydown" | "keyup", timeStamp: number): KeyboardEvent {
  return withTimeStamp(
    new KeyboardEvent(type, { key: "a", code: "KeyA", bubbles: true, composed: true }),
    timeStamp,
  );
}

describe("event times", () => {
  test("a key press is timed by timeStamp even when the handlers run later", async () => {
    const down = key("keydown", 1250.25);
    const up = key("keyup", 1330.1);
    h.clock = 1400; // the keydown handler runs 150 ms after the event happened
    input.dispatchEvent(down);
    h.clock = 1500;
    input.dispatchEvent(up);
    await h.handle.flush();
    expect(h.events()).toEqual([
      [1, 250.3, 1, 0],
      [2, 330.1, 1, 0],
    ]);
  });

  test.each([
    ["pointermove", () => new PointerEvent("pointermove", { bubbles: true, pointerType: "mouse" }), 3],
    ["pointerdown", () => new PointerEvent("pointerdown", { bubbles: true, pointerType: "mouse" }), 4],
    ["wheel", () => new WheelEvent("wheel", { bubbles: true, deltaY: 1 }), 6],
    ["paste", () => new Event("paste", { bubbles: true }), 11],
    ["focus", () => new FocusEvent("focus"), 8],
  ] as const)("%s uses its timeStamp", async (_name, make, code) => {
    const ev = withTimeStamp(make(), 1100.04);
    h.clock = 1900;
    input.dispatchEvent(ev);
    await h.handle.flush();
    expect(h.eventsOfCode(code).map((e) => e[1])).toEqual([100]);
  });

  test("page scroll uses its timeStamp", async () => {
    const ev = withTimeStamp(new Event("scroll"), 1100);
    h.clock = 1900;
    document.dispatchEvent(ev);
    await h.handle.flush();
    expect(h.eventsOfCode(7).map((e) => e[1])).toEqual([100]);
  });

  test.each([
    ["zero", 0],
    ["not finite", Number.NaN],
    ["later than now (not on the performance clock)", 1_791_545_674_428],
  ])("a timeStamp that is %s falls back to now()", async (_name, timeStamp) => {
    h.clock = 1400;
    input.dispatchEvent(key("keydown", timeStamp));
    await h.handle.flush();
    expect(h.events()).toEqual([[1, 400, 1, 0]]);
  });
});
