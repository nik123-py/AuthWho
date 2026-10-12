import { createHmac } from "node:crypto";
import { describe, expect, test } from "vitest";
import { base64urlDecode, base64urlEncode, createSigner, randomNonce } from "../src/signing";
import { TEST_KEY } from "./harness";

// Independent decoder for the expected values: atob over standard base64.
function referenceDecode(b64url: string): Uint8Array {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4)), (c) => c.charCodeAt(0));
}

describe("base64url", () => {
  test("encodes without padding using the url-safe alphabet", () => {
    expect(base64urlEncode(new Uint8Array([0xfb, 0xff, 0xbf]))).toBe("-_-_");
    expect(base64urlEncode(new Uint8Array([0x00]))).toBe("AA");
    expect(base64urlEncode(new Uint8Array([0x00, 0x01]))).toBe("AAE");
  });

  test("decodes the test key to bytes 0 to 31", () => {
    expect(Array.from(base64urlDecode(TEST_KEY))).toEqual(Array.from({ length: 32 }, (_, i) => i));
  });

  test("decodes input that carries padding", () => {
    expect(Array.from(base64urlDecode("AAE="))).toEqual([0, 1]);
  });

  test("rejects characters outside the alphabet", () => {
    expect(() => base64urlDecode("ab$c")).toThrow();
  });
});

describe("randomNonce", () => {
  test("is 16 random bytes in base64url", () => {
    const a = randomNonce();
    const b = randomNonce();
    expect(a).toMatch(/^[A-Za-z0-9_-]{22}$/);
    expect(referenceDecode(a)).toHaveLength(16);
    expect(a).not.toBe(b);
  });
});

describe("createSigner", () => {
  test("produces the HMAC-SHA256 that node:crypto computes over the same bytes", async () => {
    const body = new TextEncoder().encode('{"v":1,"events":[[1,0.5,1,0]]}');
    const sign = createSigner(TEST_KEY);
    const signature = await sign(body);
    const expected = createHmac("sha256", referenceDecode(TEST_KEY)).update(body).digest("base64url");
    expect(signature).toBe(expected);
  });

  test("a different key gives a different signature", async () => {
    const body = new TextEncoder().encode("x");
    const other = "HxwdHhsaGRgXFhUUExIREA8ODQwLCgkIBwYFBAMCAQA";
    expect(await createSigner(TEST_KEY)(body)).not.toBe(await createSigner(other)(body));
  });
});
