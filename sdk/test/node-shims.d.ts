// Minimal declarations for the Node built-ins used by tests. The project does
// not depend on @types/node, so only what the tests call is declared here.
declare module "node:crypto" {
  interface Hmac {
    update(data: Uint8Array | string): Hmac;
    digest(encoding: "base64url" | "hex"): string;
  }
  export function createHmac(algorithm: string, key: Uint8Array): Hmac;
}
