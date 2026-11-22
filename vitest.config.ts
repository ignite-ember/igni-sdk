import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The npm SDKs' own tests, run together from the repository root. Each
// package ships its TypeScript source, and the workspaces link them under
// node_modules/@ignite-ember/, so a package imports another by the name an
// extension author writes.
export default defineConfig({
  resolve: {
    alias: [
      // The reference extension imports ./igni-ui.css, which its bundler
      // copies in beside the source (README: "ships inside your bundle").
      // The tests stand in the published stylesheet for it.
      {
        find: /^\.\/igni-ui\.css$/,
        replacement: fileURLToPath(new URL("./clients/ui/igni-ui.css", import.meta.url)),
      },
      // The release-notes panel imports ./panel.css; its stylesheet is
      // ui/panel.css, which index.html links.
      {
        find: /^\.\/panel\.css$/,
        replacement: fileURLToPath(new URL("./examples/release-notes/ui/panel.css", import.meta.url)),
      },
    ],
  },
  test: {
    include: [
      "packages/**/*.{test,spec}.{ts,tsx}",
      "clients/**/*.{test,spec}.{ts,tsx}",
      "examples/reference-extension/**/*.{test,spec}.{ts,tsx}",
      "examples/release-notes/**/*.{test,spec}.{ts,tsx}",
    ],
    exclude: ["**/node_modules/**"],
    // ``npx vitest run --coverage`` (CI's npm job). Every source file
    // counts, loaded by a test or not.
    coverage: {
      provider: "v8",
      include: ["packages/*/src/**/*.{ts,tsx}"],
      exclude: ["**/node_modules/**", "**/*.test.*", "**/*.spec.*", "**/*.generated.ts", "**/*.d.ts"],
      reporter: ["text-summary"],
      // The floor: statements / branches / functions / lines, about a point
      // below where coverage stands (91.5 / 85.2 / 94.1 / 91.5 once the
      // igni-client client and its end-to-end suite landed), so the number
      // can only go up. Raise it when coverage rises; never lower it to let
      // a change through.
      thresholds: {
        statements: 90,
        branches: 84,
        functions: 92,
        lines: 90,
      },
    },
  },
});
