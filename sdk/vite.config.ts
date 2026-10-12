import { defineConfig } from "vite";

// Library build: one ESM bundle in dist/. Workspace apps import the
// TypeScript source directly through the package "exports" field.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
      fileName: () => "authwho-sdk.js",
    },
  },
});
