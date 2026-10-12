// Interaction capture: WHEEL, SCROLL, FIELD_FOCUS, FIELD_BLUR, VISIBILITY,
// CLIPBOARD, PAGE and ACTION_MARK.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { Harness, clipboard, until } from "./harness";

let h: Harness;

function setScroll(x: number, y: number): void {
  Object.defineProperty(window, "scrollX", { configurable: true, value: x });
  Object.defineProperty(window, "scrollY", { configurable: true, value: y });
}

beforeEach(() => {
  document.body.innerHTML = `
    <form>
      <input id="f0" type="text">
      <input id="f1" type="password">
      <input id="f2" type="email">
      <input id="f3" type="number">
      <textarea id="f4"></textarea>
      <select id="f5"><option>a</option></select>
      <input id="f6" type="checkbox">
      <input id="f7" type="radio">
      <button id="f8" type="button">Go</button>
      <input id="f9" type="date">
      <input id="f10" type="submit">
    </form>
    <div id="plain" tabindex="0"></div>
    <div id="scroller" style="overflow:auto"></div>`;
  setScroll(0, 0);
  h = new Harness();
  h.start({ flushIntervalMs: 60_000 });
});

afterEach(async () => {
  await h.handle.stop();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("wheel and scroll", () => {
  test("WHEEL records deltas and delta mode", async () => {
    h.advance(5);
    document.body.dispatchEvent(
      new WheelEvent("wheel", { bubbles: true, deltaX: -1.5, deltaY: 120, deltaMode: 0 }),
    );
    document.body.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: 3, deltaMode: 1 }));
    await h.handle.flush();
    expect(h.events()).toEqual([
      [6, 5, -1.5, 120, 0],
      [6, 5, 0, 3, 1],
    ]);
  });

  function scrollAt(steps: Array<[number, number]>): void {
    let last = h.clock;
    for (const [t, y] of steps) {
      h.advance(t - last);
      last = t;
      setScroll(0, y);
      document.dispatchEvent(new Event("scroll"));
    }
  }

  test("SCROLL is throttled per 100 ms window with a leading and a trailing event", async () => {
    // Windows open at 0, 100 and 210. Within each, the first event is sent at
    // once and the last suppressed one is sent as the trailing event.
    scrollAt([
      [0, 10],
      [30, 20],
      [60, 30],
      [100, 40],
      [150, 50],
      [210, 60.6],
    ]);
    await h.handle.flush();
    expect(h.eventsOfCode(7)).toEqual([
      [7, 0, 0, 10],
      [7, 60, 0, 30],
      [7, 100, 0, 40],
      [7, 150, 0, 50],
      [7, 210, 0, 61],
    ]);
  });

  test("the final position of a fast scroll is sent when the window closes", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      scrollAt([
        [0, 10],
        [30, 20],
        [60, 30],
        [90, 40],
      ]);
      await vi.advanceTimersByTimeAsync(100);
      await h.handle.flush();
      expect(h.eventsOfCode(7)).toEqual([
        [7, 0, 0, 10],
        [7, 90, 0, 40],
      ]);
    } finally {
      vi.useRealTimers();
    }
  });

  test("a single scroll event is sent once, with no trailing duplicate", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      scrollAt([[0, 10]]);
      await vi.advanceTimersByTimeAsync(300);
      await h.handle.flush();
      expect(h.eventsOfCode(7)).toEqual([[7, 0, 0, 10]]);
    } finally {
      vi.useRealTimers();
    }
  });

  test("stop() sends a pending trailing scroll", async () => {
    scrollAt([
      [0, 10],
      [40, 25],
    ]);
    await h.handle.stop();
    expect(h.eventsOfCode(7)).toEqual([
      [7, 0, 0, 10],
      [7, 40, 0, 25],
    ]);
  });

  test("scrolling inside an element is not recorded as page scroll", async () => {
    document.getElementById("scroller")!.dispatchEvent(new Event("scroll"));
    await h.handle.flush();
    expect(h.eventsOfCode(7)).toEqual([]);
  });
});

describe("field focus", () => {
  test("FIELD_FOCUS carries the document-order index and the numeric field kind", async () => {
    for (let i = 0; i <= 10; i++) (document.getElementById(`f${i}`) as HTMLElement).focus();
    (document.getElementById("f10") as HTMLElement).blur();
    await h.handle.flush();
    expect(h.eventsOfCode(8).map((e) => [e[2], e[3]])).toEqual([
      [0, 1],
      [1, 2],
      [2, 3],
      [3, 4],
      [4, 5],
      [5, 6],
      [6, 7],
      [7, 7],
      [8, 8],
      [9, 9],
      [10, 8],
    ]);
    expect(h.eventsOfCode(9).map((e) => e[2])).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  test("focus on an element that is not a form control is not recorded", async () => {
    document.getElementById("plain")!.focus();
    await h.handle.flush();
    expect(h.eventsOfCode(8)).toEqual([]);
  });
});

describe("visibility", () => {
  test("hidden and window blur give 0; visible with focus and window focus give 1", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    vi.spyOn(document, "hasFocus").mockReturnValue(true);
    window.dispatchEvent(new FocusEvent("blur"));
    h.advance(10);
    window.dispatchEvent(new FocusEvent("focus"));
    h.advance(10);
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    h.advance(10);
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await h.handle.flush();
    await until(() => h.eventsOfCode(10).length === 4);
    expect(h.eventsOfCode(10)).toEqual([
      [10, 0, 0],
      [10, 10, 1],
      [10, 20, 0],
      [10, 30, 1],
    ]);
  });

  test("repeated identical states are recorded once", async () => {
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    window.dispatchEvent(new FocusEvent("blur"));
    window.dispatchEvent(new FocusEvent("blur"));
    await h.handle.flush();
    expect(h.eventsOfCode(10)).toHaveLength(1);
  });

  test("pagehide flushes with keepalive", async () => {
    h.handle.setPage(1);
    window.dispatchEvent(new Event("pagehide"));
    await until(() => h.requests.length === 1);
    expect(h.requests[0]!.keepalive).toBe(true);
  });
});

describe("clipboard, page and action marks", () => {
  test("CLIPBOARD records copy, cut and paste as 1, 2 and 3 without reading content", async () => {
    let reads = 0;
    const onRead = () => reads++;
    clipboard(document.body, "copy", "a", onRead);
    clipboard(document.body, "cut", "b", onRead);
    clipboard(document.body, "paste", "c", onRead);
    await h.handle.flush();
    expect(h.eventsOfCode(11).map((e) => e[2])).toEqual([1, 2, 3]);
    expect(reads).toBe(0);
  });

  test("setPage and markAction record integer codes and ignore anything else", async () => {
    h.advance(3);
    h.handle.setPage(4);
    h.handle.markAction(1);
    h.handle.setPage(1.5);
    h.handle.markAction(Number.NaN);
    await h.handle.flush();
    expect(h.events()).toEqual([
      [12, 3, 4],
      [13, 3, 1],
    ]);
  });
});
