// Build the embeddable Remotion Player bundle for the dashboard.
//   node scripts/build-player.mjs
// Output: ../dashboard/dist/sv-player.js (committed artifact — the
// dashboard has no build step, so this is rebuilt manually whenever the
// composition changes).
import { buildSync } from "esbuild";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "..", "dashboard", "dist", "sv-player.js");

buildSync({
  entryPoints: [join(here, "..", "src", "player-entry.tsx")],
  outfile: out,
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "info",
});
console.log("built", out);
