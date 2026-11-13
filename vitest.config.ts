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
      // The floor: statements / branches / functions / lines when it was
      // set (81.8 / 69.0 / 78.2 / 84.1, when the SDKs moved here from
      // igni's monorepo, where the web client's floor measured them),
      // minus one point, so the number can only go up. Raise it when
      // coverage rises; never lower it to let a change through.
      thresholds: {
        statements: 80.8,
        branches: 68,
        functions: 77.2,
        lines: 83.1,
      },
    },
  },
});
