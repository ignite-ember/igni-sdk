import { defineConfig } from "vitest/config";

// The npm SDKs' own tests, run together from the repository root. Each
// package ships its TypeScript source, and the workspaces link them under
// node_modules/@ignite-ember/, so a package imports another by the name an
// extension author writes.
export default defineConfig({
  test: {
    include: ["packages/**/*.{test,spec}.{ts,tsx}", "clients/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["**/node_modules/**", "examples/**"],
  },
});
