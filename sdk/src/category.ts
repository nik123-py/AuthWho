// Key category codes (docs/interfaces.md section 5).
export const CATEGORY_LETTER = 1;
export const CATEGORY_DIGIT = 2;
export const CATEGORY_SPACE = 3;
export const CATEGORY_BACKSPACE = 4;
export const CATEGORY_MODIFIER = 5;
export const CATEGORY_NAVIGATION = 6;
export const CATEGORY_OTHER = 7;

const BACKSPACE_KEYS = new Set(["Backspace", "Delete"]);
const MODIFIER_KEYS = new Set(["Shift", "Control", "Alt", "AltGraph", "Meta", "CapsLock"]);
const NAVIGATION_KEYS = new Set([
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Home",
  "End",
  "PageUp",
  "PageDown",
  "Tab",
]);

const LETTER = /^\p{L}$/u;
const DIGIT = /^\p{Nd}$/u;

/**
 * Maps a keyboard event to its coarse category code (1 to 7).
 *
 * This is the only place in the SDK that reads the key identifier. The value
 * is used transiently for classification and is never stored, logged or
 * returned. The function is pure: the result depends only on the event.
 */
export function categoryOf(e: KeyboardEvent): number {
  const key = typeof e.key === "string" ? e.key : "";
  if (key === " ") return CATEGORY_SPACE;
  if (BACKSPACE_KEYS.has(key)) return CATEGORY_BACKSPACE;
  if (MODIFIER_KEYS.has(key)) return CATEGORY_MODIFIER;
  if (NAVIGATION_KEYS.has(key)) return CATEGORY_NAVIGATION;

  // A produced character may arrive decomposed (base letter plus combining
  // mark), so normalise before checking that it is a single code point.
  const produced = key.normalize("NFC");
  if (LETTER.test(produced)) return CATEGORY_LETTER;
  if (DIGIT.test(produced)) return CATEGORY_DIGIT;
  return CATEGORY_OTHER;
}
