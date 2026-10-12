// Pointer capture: POINTER_MOVE, POINTER_DOWN and POINTER_UP.
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { Harness, pointer } from "./harness";

let h: Harness;

beforeEach(() => {
  document.body.innerHTML = `<div id="box"></div>`;
  h = new Harness();
  h.start({ flushIntervalMs: 60_000 });
});

afterEach(async () => {
  await h.handle.stop();
  document.body.innerHTML = "";
});

describe("pointer capture", () => {
  test("move, down and up carry relative time and integer viewport coordinates", async () => {
    const box = document.getElementById("box")!;
    h.advance(1.26);
    pointer(box, "pointermove", 10.6, 20.4);
    h.advance(16);
    pointer(box, "pointerdown", 11.2, 21.5);
    h.advance(90);
    pointer(box, "pointerup", 11, 21);
    await h.handle.flush();
    expect(h.events()).toEqual([
      [3, 1.3, 11, 20],
      [4, 17.3, 11, 22, 0],
      [5, 107.3, 11, 21, 0],
    ]);
  });

  test("middle and secondary buttons are recorded as 1 and 2", async () => {
    pointer(document.body, "pointerdown", 0, 0, { button: 1 });
    pointer(document.body, "pointerup", 0, 0, { button: 1 });
    pointer(document.body, "pointerdown", 0, 0, { button: 2 });
    pointer(document.body, "pointerup", 0, 0, { button: 2 });
    await h.handle.flush();
    expect(h.events().map((e) => e[4])).toEqual([1, 1, 2, 2]);
  });

  test("buttons other than primary, middle and secondary are not recorded", async () => {
    pointer(document.body, "pointerdown", 0, 0, { button: 3 });
    pointer(document.body, "pointerup", 0, 0, { button: 4 });
    await h.handle.flush();
    expect(h.events()).toEqual([]);
  });

  test("touch and pen input are not captured (desktop mouse and touchpad only)", async () => {
    pointer(document.body, "pointermove", 5, 5, { pointerType: "touch" });
    pointer(document.body, "pointerdown", 5, 5, { pointerType: "touch" });
    pointer(document.body, "pointermove", 5, 5, { pointerType: "pen" });
    await h.handle.flush();
    expect(h.events()).toEqual([]);
  });

  test("events stopped by the page before reaching the document are still captured", async () => {
    const box = document.getElementById("box")!;
    box.addEventListener("pointerdown", (e) => e.stopPropagation());
    pointer(box, "pointerdown", 1, 2);
    await h.handle.flush();
    expect(h.events()).toEqual([[4, 0, 1, 2, 0]]);
  });
});
