import { describe, expect, test } from "vitest";
import { categoryOf } from "../src/index";

// A2: the key category table from docs/interfaces.md section 5.
// Expected codes are literals taken from the table, not computed.
function key(k: string): KeyboardEvent {
  return new KeyboardEvent("keydown", { key: k });
}

describe("categoryOf", () => {
  test.each([
    ["a", 1],
    ["Z", 1],
    ["é", 1],
    ["ß", 1],
    ["ж", 1],
    ["क", 1],
    ["0", 2],
    ["7", 2],
    ["٣", 2],
    [" ", 3],
    ["Backspace", 4],
    ["Delete", 4],
    ["Shift", 5],
    ["Control", 5],
    ["Alt", 5],
    ["AltGraph", 5],
    ["Meta", 5],
    ["CapsLock", 5],
    ["ArrowUp", 6],
    ["ArrowDown", 6],
    ["ArrowLeft", 6],
    ["ArrowRight", 6],
    ["Home", 6],
    ["End", 6],
    ["PageUp", 6],
    ["PageDown", 6],
    ["Tab", 6],
    ["Enter", 7],
    ["Escape", 7],
    ["!", 7],
    ["?", 7],
    [".", 7],
    ["@", 7],
    ["€", 7],
    ["F5", 7],
    ["Process", 7],
    ["Unidentified", 7],
    ["Dead", 7],
    ["", 7],
  ])("key %j is category %i", (k, expected) => {
    expect(categoryOf(key(k))).toBe(expected);
  });

  test("a decomposed letter (e plus combining acute) is a letter", () => {
    expect(categoryOf(key("é"))).toBe(1);
  });

  test("a multi-character key name that is not in the table is other", () => {
    expect(categoryOf(key("Insert"))).toBe(7);
    expect(categoryOf(key("ab"))).toBe(7);
  });

  test("an event without a key is other", () => {
    expect(categoryOf(new KeyboardEvent("keydown"))).toBe(7);
  });

  test("returns only a number and does not depend on the code field", () => {
    const e = new KeyboardEvent("keydown", { key: "a", code: "Digit1" });
    expect(categoryOf(e)).toBe(1);
  });
});
