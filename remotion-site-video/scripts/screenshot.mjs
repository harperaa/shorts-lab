// Capture a full-page screenshot + candidate section regions for a URL.
// Uses Remotion's own headless Chrome (downloaded by `remotion browser ensure`)
// via puppeteer-core — no extra browser install anywhere.
//
//   node scripts/screenshot.mjs <url> <outdir>
//
// Writes: <outdir>/screenshot.png
//         <outdir>/page.json   {url, title, pageWidth, pageHeight,
//                               sections: [{label, text, rect{x,y,w,h}}]}
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const [url, outdir] = process.argv.slice(2);
if (!url || !outdir) {
  console.error("usage: node scripts/screenshot.mjs <url> <outdir>");
  process.exit(2);
}
mkdirSync(outdir, { recursive: true });

const here = dirname(fileURLToPath(import.meta.url));

// Locate (downloading if needed) Remotion's chrome-headless-shell.
function findChrome(root) {
  if (!existsSync(root)) return null;
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      const st = statSync(p);
      if (st.isDirectory()) stack.push(p);
      else if (
        name === "chrome-headless-shell" ||
        name === "chrome-headless-shell.exe" ||
        name === "headless_shell"
      )
        return p;
    }
  }
  return null;
}

const chromeRoots = [
  join(process.env.HOME || "", ".remotion", "chrome-headless-shell"),
  join(here, "..", "node_modules", ".remotion"),
];
let executablePath = chromeRoots.map(findChrome).find(Boolean);
if (!executablePath) {
  console.error("[screenshot] downloading Remotion headless chrome…");
  execSync("npx remotion browser ensure", {
    cwd: join(here, ".."),
    stdio: "inherit",
  });
  executablePath = chromeRoots.map(findChrome).find(Boolean);
}
if (!executablePath) {
  console.error("could not locate chrome-headless-shell after ensure");
  process.exit(1);
}

const VIEW_W = 1440;
const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: VIEW_W, height: 900, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "networkidle2", timeout: 60_000 });
  // settle lazy content: scroll through, then back to top
  await page.evaluate(async () => {
    await new Promise((done) => {
      let y = 0;
      const step = () => {
        y += 700;
        window.scrollTo(0, y);
        if (y < document.body.scrollHeight) setTimeout(step, 120);
        else {
          window.scrollTo(0, 0);
          setTimeout(done, 400);
        }
      };
      step();
    });
  });

  const pageHeight = Math.min(
    await page.evaluate(() => document.body.scrollHeight),
    12_000, // cap absurd pages
  );

  // candidate sections: headers, hero, sections, footers with visible size
  const sections = await page.evaluate(() => {
    const picks = [];
    const seen = new Set();
    const sels = [
      "header", "nav", "main section", "section", "article",
      "[class*='hero']", "[class*='feature']", "[class*='pricing']",
      "[class*='testimonial']", "[class*='faq']", "[class*='cta']",
      "footer", "h1", "h2",
    ];
    for (const sel of sels) {
      for (const el of document.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect();
        const y = r.top + window.scrollY;
        if (r.width < 320 || r.height < 90) continue;
        const key = `${Math.round(y / 60)}:${Math.round(r.height / 60)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const text = (el.innerText || "").trim().replace(/\s+/g, " ").slice(0, 260);
        if (!text) continue;
        picks.push({
          label: el.tagName.toLowerCase() +
            (el.id ? `#${el.id}` : "") +
            (el.className && typeof el.className === "string"
              ? "." + el.className.split(/\s+/).slice(0, 2).join(".")
              : ""),
          text,
          rect: {
            x: Math.max(0, Math.round(r.left + window.scrollX)),
            y: Math.max(0, Math.round(y)),
            w: Math.round(r.width),
            h: Math.round(r.height),
          },
        });
        if (picks.length >= 24) return picks;
      }
    }
    return picks;
  });

  await page.screenshot({
    path: join(outdir, "screenshot.png"),
    clip: { x: 0, y: 0, width: VIEW_W, height: pageHeight },
    captureBeyondViewport: true,
  });

  const title = await page.title();
  writeFileSync(
    join(outdir, "page.json"),
    JSON.stringify(
      { url, title, pageWidth: VIEW_W, pageHeight, sections },
      null,
      1,
    ),
  );
  console.log(`[screenshot] ok: ${pageHeight}px tall, ${sections.length} sections`);
} finally {
  await browser.close();
}
