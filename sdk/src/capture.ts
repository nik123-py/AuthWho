// DOM event capture (docs/interfaces.md section 5).
//
// Every emitted event is an array of finite numbers. Nothing here reads a
// field value, the selection, clipboard contents or a key identifier, with
// two narrow exceptions required for pairing: categoryOf() classifies the key
// inside one pure function, and the physical key identifier is used as a key
// of an in-memory map that pairs key-down with key-up. Neither is stored in
// an event, serialised or logged.
import { categoryOf } from "./category";
import type { Channel } from "./types";

export const KEY_DOWN = 1;
export const KEY_UP = 2;
export const POINTER_MOVE = 3;
export const POINTER_DOWN = 4;
export const POINTER_UP = 5;
export const WHEEL = 6;
export const SCROLL = 7;
export const FIELD_FOCUS = 8;
export const FIELD_BLUR = 9;
export const VISIBILITY = 10;
export const CLIPBOARD = 11;

const SCROLL_THROTTLE_MS = 100;
const FORM_CONTROLS = "input, select, textarea, button";
const CLIPBOARD_ACTIONS: Record<string, number> = { copy: 1, cut: 2, paste: 3 };

export interface CaptureOptions {
  root: Document;
  channels: Record<Channel, boolean>;
  /** Current stream-relative time in ms, rounded to 0.1 ms. */
  clock: () => number;
  /** Stream-relative time at which an event happened, rounded to 0.1 ms. */
  timeOf: (e: Event) => number;
  emit: (event: number[]) => void;
}

export interface Capture {
  /** Emits any pending trailing event, then removes every listener added. */
  detach(): void;
}

type Listener = (e: Event) => void;

/** True when keystrokes on this target must not be captured at all. */
function isShielded(e: Event): boolean {
  let node: Node | null = (e.composedPath()[0] as Node | undefined) ?? (e.target as Node | null);
  while (node) {
    if (node.nodeType === 1) {
      const el = node as Element;
      if (el.localName === "input" && (el as HTMLInputElement).type === "password") return true;
      if (el.getAttribute("data-authwho") === "ignore") return true;
    }
    if (node.parentNode) {
      node = node.parentNode;
    } else {
      // Continue from a shadow root to its host element.
      node = (node as Partial<ShadowRoot>).host ?? null;
    }
  }
  return false;
}

/** Field kind codes: 1 text to 9 other. Reads only the element type. */
function fieldKind(el: Element): number {
  switch (el.localName) {
    case "textarea":
      return 5;
    case "select":
      return 6;
    case "button":
      return 8;
  }
  switch ((el as HTMLInputElement).type) {
    case "text":
      return 1;
    case "password":
      return 2;
    case "email":
      return 3;
    case "number":
      return 4;
    case "checkbox":
    case "radio":
      return 7;
    case "button":
    case "submit":
    case "reset":
    case "image":
      return 8;
    default:
      return 9;
  }
}

function isDesktopPointer(e: PointerEvent): boolean {
  return e.pointerType !== "touch" && e.pointerType !== "pen";
}

export function attachCapture(options: CaptureOptions): Capture {
  const { root, channels, clock, timeOf } = options;
  const view = root.defaultView;
  const registered: Array<[EventTarget, string, Listener, AddEventListenerOptions]> = [];
  // Run on detach before listeners are removed, for example to emit a pending
  // trailing scroll event.
  const beforeDetach: Array<() => void> = [];

  const listen = (
    target: EventTarget | null,
    type: string,
    fn: Listener,
    opts: AddEventListenerOptions = { capture: true, passive: true },
  ): void => {
    if (!target) return;
    target.addEventListener(type, fn, opts);
    registered.push([target, type, fn, opts]);
  };

  const emit = (event: number[]): void => {
    for (const v of event) if (!Number.isFinite(v)) return;
    options.emit(event);
  };

  if (channels.keystroke) {
    // Physical key identifier to press record. In memory only.
    const pressed = new Map<string, { pressId: number; category: number }>();
    let nextPressId = 0;
    const identity = (e: KeyboardEvent): string => e.code || e.key || "";

    listen(root, "keydown", (ev) => {
      const e = ev as KeyboardEvent;
      if (e.repeat || isShielded(e)) return;
      const category = categoryOf(e);
      const pressId = nextPressId++;
      pressed.set(identity(e), { pressId, category });
      emit([KEY_DOWN, timeOf(e), category, pressId]);
    });

    listen(root, "keyup", (ev) => {
      const e = ev as KeyboardEvent;
      const id = identity(e);
      const press = pressed.get(id);
      pressed.delete(id);
      if (!press || isShielded(e)) return;
      emit([KEY_UP, timeOf(e), press.category, press.pressId]);
    });
  }

  if (channels.pointer) {
    listen(root, "pointermove", (ev) => {
      const e = ev as PointerEvent;
      if (!isDesktopPointer(e)) return;
      emit([POINTER_MOVE, timeOf(e), Math.round(e.clientX), Math.round(e.clientY)]);
    });
    const onButton = (code: number) => (ev: Event) => {
      const e = ev as PointerEvent;
      if (!isDesktopPointer(e) || e.button < 0 || e.button > 2) return;
      emit([code, timeOf(e), Math.round(e.clientX), Math.round(e.clientY), e.button]);
    };
    listen(root, "pointerdown", onButton(POINTER_DOWN));
    listen(root, "pointerup", onButton(POINTER_UP));
  }

  if (channels.interaction) {
    listen(root, "wheel", (ev) => {
      const e = ev as WheelEvent;
      emit([WHEEL, timeOf(e), e.deltaX, e.deltaY, e.deltaMode]);
    });

    // SCROLL throttle: the first event of a 100 ms window is sent at once
    // (leading edge) and the last suppressed event of that window is sent
    // when the window closes (trailing edge), so the final position of a
    // fast scroll is always recorded.
    let windowStart: number | undefined;
    let pendingScroll: number[] | undefined;
    let scrollTimer: ReturnType<typeof setTimeout> | undefined;
    const sendTrailingScroll = (): void => {
      if (scrollTimer !== undefined) clearTimeout(scrollTimer);
      scrollTimer = undefined;
      const event = pendingScroll;
      pendingScroll = undefined;
      if (event) emit(event);
    };
    beforeDetach.push(sendTrailingScroll);
    listen(root, "scroll", (e) => {
      // Page scroll only; scrolling inside an element is a different scroller.
      if (e.target !== root && e.target !== root.documentElement && e.target !== root.scrollingElement) return;
      const t = timeOf(e);
      const event = [SCROLL, t, Math.round(view?.scrollX ?? 0), Math.round(view?.scrollY ?? 0)];
      if (windowStart !== undefined && t - windowStart < SCROLL_THROTTLE_MS) {
        pendingScroll = event;
        scrollTimer ??= setTimeout(sendTrailingScroll, Math.max(0, windowStart + SCROLL_THROTTLE_MS - clock()));
        return;
      }
      // The previous window's trailing event, if still pending, goes first.
      sendTrailingScroll();
      windowStart = t;
      emit(event);
    });

    const fieldIndex = (target: EventTarget | null): number =>
      target ? Array.prototype.indexOf.call(root.querySelectorAll(FORM_CONTROLS), target) : -1;
    listen(root, "focus", (e) => {
      const index = fieldIndex(e.target);
      if (index >= 0) emit([FIELD_FOCUS, timeOf(e), index, fieldKind(e.target as Element)]);
    });
    listen(root, "blur", (e) => {
      const index = fieldIndex(e.target);
      if (index >= 0) emit([FIELD_BLUR, timeOf(e), index]);
    });

    let lastVisibility: number | undefined;
    const visibility = (e: Event, state: number): void => {
      if (state === lastVisibility) return;
      lastVisibility = state;
      emit([VISIBILITY, timeOf(e), state]);
    };
    listen(root, "visibilitychange", (e) => {
      visibility(e, root.visibilityState === "hidden" || !root.hasFocus() ? 0 : 1);
    });
    // Non-capture listeners on the window only see events targeted at the
    // window itself, because element focus and blur do not bubble. The node
    // check is a second guard that also works across realms.
    const windowOnly = { capture: false, passive: true };
    const isWindowTarget = (e: Event): boolean => typeof (e.target as Partial<Node> | null)?.nodeType !== "number";
    listen(view, "focus", (e) => {
      if (isWindowTarget(e)) visibility(e, root.visibilityState === "hidden" ? 0 : 1);
    }, windowOnly);
    listen(view, "blur", (e) => {
      if (isWindowTarget(e)) visibility(e, 0);
    }, windowOnly);

    const onClipboard = (e: Event): void => {
      const action = CLIPBOARD_ACTIONS[e.type];
      if (action !== undefined) emit([CLIPBOARD, timeOf(e), action]);
    };
    listen(root, "copy", onClipboard);
    listen(root, "cut", onClipboard);
    listen(root, "paste", onClipboard);
  }

  return {
    detach() {
      for (const fn of beforeDetach) fn();
      for (const [target, type, fn, opts] of registered) target.removeEventListener(type, fn, opts);
      registered.length = 0;
    },
  };
}
