// Screenshots of every screen at 1440, 1024, 768 and 375 px in light and dark, plus axe-core
// checks (TESTING.md section 6). Needs a running local daemon and/or cloud server:
//   LOCAL_URL=http://127.0.0.1:8765 LOCAL_TOKEN=... CLOUD_URL=http://localhost:8000 \
//   CLOUD_EMAIL=... CLOUD_PASSWORD=... node e2e/screens.mjs [--quick]
// Exit code 1 when axe finds serious or critical violations.
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "test-results", "screens");
mkdirSync(out, { recursive: true });
const axeSource = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const quick = process.argv.includes("--quick");
const WIDTHS = quick ? [1440, 375] : [1440, 1024, 768, 375];
const THEMES = quick ? ["light", "dark"] : ["light", "dark"];
const problems = [];

async function check(page, name) {
  await page.addScriptTag({ content: axeSource });
  const res = await page.evaluate(async () => await window.axe.run(document, { resultTypes: ["violations"] }));
  for (const v of res.violations.filter((x) => ["serious", "critical"].includes(x.impact))) {
    problems.push(`${name}: ${v.id} (${v.impact}) ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")}`);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (overflow) problems.push(`${name}: horizontal page scroll`);
}

async function shoot(context, base, screens, prefix) {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const page = await context.newPage();
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((t) => localStorage.setItem("faultsage-theme", t), theme);
      for (const [name, path, wait] of screens) {
        await page.goto(base + path, { waitUntil: "networkidle" });
        if (wait) await page.waitForSelector(wait, { timeout: 10000 }).catch(() => problems.push(`${prefix}-${name}: missing ${wait}`));
        await page.waitForTimeout(300);
        const file = `${prefix}-${name}-${width}-${theme}.png`;
        await page.screenshot({ path: join(out, file), fullPage: true });
        if (width === 1440 || width === 375) await check(page, `${prefix}-${name}@${width}/${theme}`);
      }
      await page.close();
    }
  }
}

const browser = await chromium.launch();
try {
  if (process.env.LOCAL_URL && process.env.LOCAL_TOKEN) {
    const ctx = await browser.newContext({ deviceScaleFactor: 1, bypassCSP: true });
    const p = await ctx.newPage();
    await p.goto(`${process.env.LOCAL_URL}/#t=${process.env.LOCAL_TOKEN}`, { waitUntil: "networkidle" });
    await p.waitForSelector("main h1");
    await p.close();
    await shoot(ctx, process.env.LOCAL_URL, [
      ["overview", "/", "main h1"],
      ["incidents", "/incidents", "table"],
      ["case-file", "/incidents/1", "#causes"],
      ["pipeline", "/pipeline", "main h1"],
      ["scan", "/scan", "main h1"],
      ["evaluation", "/evaluation", "main h1"],
      ["settings", "/settings", "main h1"],
    ], "local");
    await ctx.close();
  }
  if (process.env.CLOUD_URL) {
    const pub = await browser.newContext({ deviceScaleFactor: 1, bypassCSP: true });
    await shoot(pub, process.env.CLOUD_URL, [
      ["landing", "/", "#hero"],
      ["how-it-works", "/how-it-works", "main h1"],
      ["pricing", "/pricing", "main h1"],
      ["docs", "/docs", "main h1"],
      ["login", "/login", "form"],
      ["signup", "/signup", "form"],
    ], "cloud-public");
    await pub.close();
    if (process.env.CLOUD_EMAIL) {
      const app = await browser.newContext({ deviceScaleFactor: 1, bypassCSP: true });
      const p = await app.newPage();
      await p.goto(`${process.env.CLOUD_URL}/login`);
      await p.getByLabel("Email").fill(process.env.CLOUD_EMAIL);
      await p.getByLabel("Password").fill(process.env.CLOUD_PASSWORD ?? "");
      await p.getByRole("button", { name: "Sign in" }).click();
      await p.waitForURL("**/app");
      await p.close();
      await shoot(app, process.env.CLOUD_URL, [
        ["home", "/app", "table"],
        ["issues", "/app/projects/1", "table"],
        ["issue", "/app/projects/1/issues/1", "main h1"],
        ["setup", "/app/projects/1?tab=setup", "main h1"],
        ["case-file", "/app/projects/2/case-files/1", "#causes"],
        ["settings", "/app/settings", "main h1"],
      ], "cloud-app");
      await app.close();
    }
  }
} finally {
  await browser.close();
}
console.log(`Screens written to ${out}`);
if (problems.length) {
  console.log(`\n${problems.length} problem(s):\n${problems.join("\n")}`);
  process.exit(1);
}
console.log("axe: no serious or critical violations; no horizontal page scroll");
