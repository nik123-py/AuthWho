// Keystroke capture: A3 (password and ignored regions) and A4 (repeat, pairing, rollover).
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { Harness, keyDown, keyUp, pointer, typeText } from "./harness";

let h: Harness;
let text: HTMLInputElement;
let pw: HTMLInputElement;
let ignoredInput: HTMLInputElement;

beforeEach(() => {
  document.body.innerHTML = `
    <input id="text" type="text">
    <input id="pw" type="password">
    <div data-authwho="ignore"><span><input id="ignored" type="text"></span></div>
    <input id="pwupper" type="PASSWORD">`;
  text = document.getElementById("text") as HTMLInputElement;
  pw = document.getElementById("pw") as HTMLInputElement;
  ignoredInput = document.getElementById("ignored") as HTMLInputElement;
  h = new Harness();
  h.start({ flushIntervalMs: 60_000 });
});

afterEach(async () => {
  await h.handle.stop();
  document.body.innerHTML = "";
});

const keyEvents = () => h.events().filter((e) => e[0] === 1 || e[0] === 2);

describe("key events (A4)", () => {
  test("a press produces KEY_DOWN and KEY_UP with category, relative time and press_id", async () => {
    h.advance(10);
    keyDown(text, { key: "a", code: "KeyA" });
    h.advance(85.47);
    keyUp(text, { key: "a", code: "KeyA" });
    await h.handle.flush();
    expect(keyEvents()).toEqual([
      [1, 10, 1, 0],
      [2, 95.5, 1, 0],
    ]);
  });

  test("auto-repeat key-downs are dropped and do not consume a press_id", async () => {
    keyDown(text, { key: "a", code: "KeyA" });
    h.advance(500);
    keyDown(text, { key: "a", code: "KeyA", repeat: true });
    h.advance(30);
    keyDown(text, { key: "a", code: "KeyA", repeat: true });
    h.advance(30);
    keyUp(text, { key: "a", code: "KeyA" });
    h.advance(100);
    keyDown(text, { key: "b", code: "KeyB" });
    keyUp(text, { key: "b", code: "KeyB" });
    await h.handle.flush();
    expect(keyEvents().map((e) => [e[0], e[3]])).toEqual([
      [1, 0],
      [2, 0],
      [1, 1],
      [2, 1],
    ]);
  });

  test("rollover (down A, down B, up A, up B) keeps the pairing", async () => {
    keyDown(text, { key: "a", code: "KeyA" });
    h.advance(40);
    keyDown(text, { key: " ", code: "Space" });
    h.advance(40);
    keyUp(text, { key: "a", code: "KeyA" });
    h.advance(40);
    keyUp(text, { key: " ", code: "Space" });
    await h.handle.flush();
    expect(keyEvents()).toEqual([
      [1, 0, 1, 0],
      [1, 40, 3, 1],
      [2, 80, 1, 0],
      [2, 120, 3, 1],
    ]);
  });

  test("a key-up keeps the category of its key-down when Shift changes the produced key", async () => {
    keyDown(text, { key: "1", code: "Digit1" });
    keyDown(text, { key: "Shift", code: "ShiftLeft" });
    keyUp(text, { key: "!", code: "Digit1" });
    keyUp(text, { key: "Shift", code: "ShiftLeft" });
    await h.handle.flush();
    expect(keyEvents().map((e) => [e[0], e[2], e[3]])).toEqual([
      [1, 2, 0],
      [1, 5, 1],
      [2, 2, 0],
      [2, 5, 1],
    ]);
  });

  test("a key-up without a captured key-down is dropped", async () => {
    keyUp(text, { key: "a", code: "KeyA" });
    await h.handle.flush();
    expect(keyEvents()).toEqual([]);
  });
});

describe("password fields and ignored regions (A3)", () => {
  test("typing in a password field produces no keystroke events", async () => {
    typeText(pw, "s3cret", (ms) => h.advance(ms));
    await h.handle.flush();
    expect(keyEvents()).toEqual([]);
  });

  test("a password field declared with an upper-case type is also skipped", async () => {
    typeText(document.getElementById("pwupper") as HTMLInputElement, "abc", (ms) => h.advance(ms));
    await h.handle.flush();
    expect(keyEvents()).toEqual([]);
  });

  test('typing inside a data-authwho="ignore" region produces no keystroke events', async () => {
    typeText(ignoredInput, "hello", (ms) => h.advance(ms));
    await h.handle.flush();
    expect(keyEvents()).toEqual([]);
  });

  test("skipped keystrokes leave no gap in press_id", async () => {
    typeText(text, "ab", (ms) => h.advance(ms));
    typeText(pw, "xyz", (ms) => h.advance(ms));
    typeText(text, "c", (ms) => h.advance(ms));
    await h.handle.flush();
    expect(h.eventsOfCode(1).map((e) => e[3])).toEqual([0, 1, 2]);
  });

  test("a key-up that lands in a password field is not captured", async () => {
    keyDown(text, { key: "Tab", code: "Tab" });
    pw.focus();
    keyUp(pw, { key: "Tab", code: "Tab" });
    await h.handle.flush();
    expect(keyEvents().map((e) => e[0])).toEqual([1]);
  });

  test("pointer events over a password field and an ignored region are still captured", async () => {
    pointer(pw, "pointerdown", 10, 20);
    pointer(ignoredInput, "pointerup", 30, 40);
    await h.handle.flush();
    expect(h.events().map((e) => e[0])).toEqual([4, 5]);
  });
});
