// Batch signing with WebCrypto (docs/interfaces.md section 6).
//
// The stream key is imported once as a non-extractable HMAC key. Neither the
// key nor any error mentioning it is ever logged or returned.

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const LOOKUP = new Map<string, number>([...ALPHABET].map((c, i) => [c, i]));

export function base64urlEncode(bytes: Uint8Array): string {
  let out = "";
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i]! << 16) | (bytes[i + 1]! << 8) | bytes[i + 2]!;
    out += ALPHABET[(n >> 18) & 63]! + ALPHABET[(n >> 12) & 63]! + ALPHABET[(n >> 6) & 63]! + ALPHABET[n & 63]!;
  }
  const rest = bytes.length - i;
  if (rest === 1) {
    const n = bytes[i]! << 16;
    out += ALPHABET[(n >> 18) & 63]! + ALPHABET[(n >> 12) & 63]!;
  } else if (rest === 2) {
    const n = (bytes[i]! << 16) | (bytes[i + 1]! << 8);
    out += ALPHABET[(n >> 18) & 63]! + ALPHABET[(n >> 12) & 63]! + ALPHABET[(n >> 6) & 63]!;
  }
  return out;
}

export function base64urlDecode(text: string): Uint8Array<ArrayBuffer> {
  const clean = text.replace(/=+$/, "");
  if (clean.length % 4 === 1) throw new Error("AuthWho: invalid base64url length");
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let buffer = 0;
  let bits = 0;
  let o = 0;
  for (const c of clean) {
    const v = LOOKUP.get(c);
    if (v === undefined) throw new Error("AuthWho: invalid base64url character");
    buffer = (buffer << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[o++] = (buffer >> bits) & 0xff;
    }
  }
  return out;
}

/** 16 cryptographically random bytes in base64url. */
export function randomNonce(): string {
  return base64urlEncode(crypto.getRandomValues(new Uint8Array(16)));
}

export type Signer = (body: Uint8Array<ArrayBuffer>) => Promise<string>;

/** Returns a function that signs bytes with HMAC-SHA256 under the stream key. */
export function createSigner(streamKey: string): Signer {
  const raw = base64urlDecode(streamKey);
  const key = crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  // The imported key holds its own copy; clear ours once import finishes.
  void key.then(
    () => raw.fill(0),
    () => raw.fill(0),
  );
  return async (body) => {
    const mac = await crypto.subtle.sign("HMAC", await key, body);
    return base64urlEncode(new Uint8Array(mac));
  };
}
