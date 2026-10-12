// A1: the permanent "no characters" test. It must stay green forever.
//
// It drives realistic typing (letters, digits, punctuation, a password field
// and a paste) through the real capture and transport code, captures every
// request through the injected fetchImpl, and fails if any captured event or
// batch carries a character, a typed string, or anything but finite numbers.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { BATCH_KEYS, Harness, clipboard, keyDown, keyUp, typeText } from "./harness";

const VISIBLE_TEXT = "Hello World 123!?";
const PASSWORD = "s3cret";
const PASTED = "pasted clipboard secret";

// Every typed string, plus pieces of it, must be absent from every request.
const FORBIDDEN_STRINGS = [
  VISIBLE_TEXT,
  "Hello",
  "World",
  "123!?",
  "!?",
  PASSWORD,
  "s3c",
  PASTED,
  "clipboard",
  "KeyH",
  "Digit1",
  "ShiftLeft",
];

type Restore = () => void;

/** Wraps a property getter so any read is counted, keeping the setter. */
function trapGetter(proto: object, prop: string, onRead: () => void): Restore {
  const original = Object.getOwnPropertyDescriptor(proto, prop);
  if (!original?.get) throw new Error(`no getter for ${prop}`);
  const originalGet = original.get;
  Object.defineProperty(proto, prop, {
    ...original,
    get(this: unknown) {
      onRead();
      return originalGet.call(this);
    },
  });
  return () => Object.defineProperty(proto, prop, original);
}

describe("no characters (A1)", () => {
  let h: Harness;
  const restores: Restore[] = [];
  let sensitiveReads: string[];

  beforeEach(() => {
    document.body.innerHTML = `
      <form>
        <input id="text" type="text">
        <textarea id="area"></textarea>
        <input id="pw" type="password">
      </form>`;
    sensitiveReads = [];
    restores.push(
      trapGetter(HTMLInputElement.prototype, "value", () => sensitiveReads.push("input.value")),
      trapGetter(HTMLTextAreaElement.prototype, "value", () => sensitiveReads.push("textarea.value")),
    );
    const getSelection = vi.spyOn(window, "getSelection");
    const docGetSelection = vi.spyOn(document, "getSelection");
    restores.push(() => getSelection.mockRestore(), () => docGetSelection.mockRestore());
    h = new Harness();
  });

  afterEach(() => {
    while (restores.length) restores.pop()!();
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  test("typing, a password and a paste produce numeric events with no characters", async () => {
    const consoleSpies = (["log", "info", "warn", "error", "debug", "trace"] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => undefined),
    );
    const text = document.getElementById("text") as HTMLInputElement;
    const area = document.getElementById("area") as HTMLTextAreaElement;
    const pw = document.getElementById("pw") as HTMLInputElement;

    h.start({ maxBatchEvents: 30 });
    typeText(text, VISIBLE_TEXT, (ms) => h.advance(ms));
    typeText(area, VISIBLE_TEXT, (ms) => h.advance(ms));
    typeText(pw, PASSWORD, (ms) => h.advance(ms));

    // Paste into the text field with Ctrl+V.
    text.focus();
    keyDown(text, { key: "Control", code: "ControlLeft" });
    h.advance(50);
    keyDown(text, { key: "v", code: "KeyV" });
    clipboard(text, "paste", PASTED, () => sensitiveReads.push("clipboardData"));
    h.advance(70);
    keyUp(text, { key: "v", code: "KeyV" });
    h.advance(20);
    keyUp(text, { key: "Control", code: "ControlLeft" });
    text.blur();

    await h.handle.stop();

    // Something was actually captured and sent, so the checks below are not vacuous.
    expect(h.requests.length).toBeGreaterThan(1);
    const batches = h.sentBatches();

    for (const [i, req] of h.requests.entries()) {
      const batch = batches[i]!;
      expect(Object.keys(batch).sort()).toEqual(BATCH_KEYS);

      // Every element of every event is a finite number.
      for (const ev of batch.events) {
        expect(Array.isArray(ev)).toBe(true);
        for (const value of ev) {
          expect(typeof value).toBe("number");
          expect(Number.isFinite(value)).toBe(true);
        }
      }

      // The serialised event array uses only number syntax: no letters,
      // punctuation characters or quotes can appear in it.
      expect(JSON.stringify(batch.events)).toMatch(/^[0-9[\],.-]*$/);

      // No typed string or key name appears anywhere in the body or headers.
      const everything = req.bodyText + JSON.stringify(req.headers) + req.url;
      for (const s of FORBIDDEN_STRINGS) {
        expect(everything).not.toContain(s);
        expect(everything.toLowerCase()).not.toContain(s.toLowerCase());
      }
    }

    const events = h.events();
    // 21 key-downs per visible field (17 characters plus Shift for H, W, ! and ?),
    // two fields, plus Control and v for the paste. The password adds none.
    expect(events.filter((e) => e[0] === 1)).toHaveLength(44);
    expect(events.filter((e) => e[0] === 2)).toHaveLength(44);

    // Key events carry only a category code (1 to 7) and a press counter.
    for (const ev of events.filter((e) => e[0] === 1 || e[0] === 2)) {
      expect(ev).toHaveLength(4);
      expect(ev[2]).toBeGreaterThanOrEqual(1);
      expect(ev[2]).toBeLessThanOrEqual(7);
      expect(Number.isInteger(ev[3])).toBe(true);
    }

    // The paste is recorded as an occurrence only.
    expect(events.filter((e) => e[0] === 11).map((e) => [e[0], e[2]])).toEqual([[11, 3]]);

    // Field values, the selection and the clipboard payload were never read,
    // and nothing was written to the console.
    expect(sensitiveReads).toEqual([]);
    expect(window.getSelection).not.toHaveBeenCalled();
    expect(document.getSelection).not.toHaveBeenCalled();
    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
  });

  test("the category sequence of the visible text is coarse", async () => {
    const text = document.getElementById("text") as HTMLInputElement;
    h.start();
    typeText(text, VISIBLE_TEXT, (ms) => h.advance(ms));
    await h.handle.stop();
    const categories = h.eventsOfCode(1).map((e) => e[2]);
    // Hand-derived from "Hello World 123!?" with Shift before H, W, ! and ?.
    expect(categories).toEqual([5, 1, 1, 1, 1, 1, 3, 5, 1, 1, 1, 1, 1, 3, 2, 2, 2, 5, 7, 5, 7]);
  });
});
