// Customer journey against a running FaultSage Cloud, in a real browser, the way a new customer
// would use it. Works against a local server or your live site.
//
//   BASE_URL=https://your-site node e2e/journey.mjs
//
// Optional:
//   PYTHON=path/to/python   Python with faultsage installed (enables the SDK and CLI steps)
//   VERIFY_LINK_CMD="..."   Shell command that prints the server log; the newest email
//                           confirmation link is read from it (only when SMTP is not set up)
//   OUT=folder              Where screenshots go (default e2e-journey)
//   KEEP=1                  Keep the test accounts (default: delete them at the end)
//
// Exit code 0 means every step passed. Each step prints PASS or FAIL with the reason.

import { execFileSync, execSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { delimiter, dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = (process.env.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const PY = process.env.PYTHON || "";
const OUT = process.env.OUT || "e2e-journey";
const RUN = Date.now().toString(36);
const EMAIL = `journey-${RUN}@example.com`;
const OTHER = `journey-other-${RUN}@example.com`;
const PASSWORD = "journey test passphrase 4417";
mkdirSync(OUT, { recursive: true });

let failures = 0;
let shot = 0;
const results = [];
async function step(name, fn) {
  try {
    const note = await fn();
    results.push({ name, ok: true, note: note || "" });
    console.log(`PASS  ${name}${note ? `: ${note}` : ""}`);
  } catch (e) {
    failures += 1;
    results.push({ name, ok: false, note: String(e?.message || e) });
    console.log(`FAIL  ${name}: ${e?.message || e}`);
  }
}
function must(cond, msg) {
  if (!cond) throw new Error(msg);
}
async function snap(page, label) {
  shot += 1;
  await page.screenshot({ path: join(OUT, `${String(shot).padStart(2, "0")}-${label}.png`), fullPage: true });
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(String(e)));

let projectUrl = "";
let apiKey = "";

await step("Landing page loads over the public address", async () => {
  const r = await page.goto(BASE, { waitUntil: "networkidle" });
  must(r && r.ok(), `HTTP ${r?.status()}`);
  must(await page.locator("h1").count(), "no heading");
  const health = await (await ctx.request.get(`${BASE}/healthz`)).json();
  must(health.status === "ok", "healthz not ok");
  await snap(page, "landing");
  return `healthz ok, ${new URL(BASE).protocol.replace(":", "")}`;
});

await step("Security headers are present", async () => {
  const r = await ctx.request.get(BASE);
  const h = r.headers();
  for (const k of ["content-security-policy", "x-content-type-options", "referrer-policy"]) {
    must(h[k], `missing ${k}`);
  }
  if (BASE.startsWith("https://")) must(h["strict-transport-security"], "missing HSTS on https");
});

await step("Sign up with email and password", async () => {
  await page.goto(`${BASE}/signup`);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Your name").fill("Journey Tester");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByLabel("Workspace name").fill(`Journey ${RUN}`);
  await page.getByRole("button", { name: "Create free account" }).click();
  await page.waitForURL(/\/app/, { timeout: 15000 });
  await snap(page, "after-signup");
});

await step("Confirm the email address with the emailed link", async () => {
  if (!process.env.VERIFY_LINK_CMD) return "skipped (no VERIFY_LINK_CMD; check your inbox by hand)";
  const log = execSync(process.env.VERIFY_LINK_CMD, { encoding: "utf8", maxBuffer: 1 << 26 });
  const links = [...log.matchAll(/https?:\/\/\S+\/verify-email#token=[\w-]+/g)].map((m) => m[0]);
  must(links.length, "no confirmation link in the log");
  const link = links[links.length - 1].replace(/^https?:\/\/[^/]+/, BASE);
  await page.goto(link);
  await page.getByText("Your email address is confirmed").waitFor({ timeout: 10000 });
  const me = await (await ctx.request.get(`${BASE}/api/v1/me`)).json();
  must(me.user.email_verified === true, "account still unverified");
  await snap(page, "email-confirmed");
});

await step("Sign out, then sign in again", async () => {
  await page.goto(`${BASE}/app`);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/app"), { timeout: 10000 });
  const me = await ctx.request.get(`${BASE}/api/v1/me`);
  must(me.status() === 401, `still signed in after sign out (${me.status()})`);
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/app/, { timeout: 15000 });
});

await step("Wrong password is refused with a generic message", async () => {
  const other = await browser.newContext();
  const p = await other.newPage();
  await p.goto(`${BASE}/login`);
  await p.getByLabel("Email").fill(EMAIL);
  await p.getByLabel("Password").fill("not the password at all");
  await p.getByRole("button", { name: "Sign in" }).click();
  await p.waitForTimeout(1500);
  must(!p.url().includes("/app"), "signed in with a wrong password");
  await other.close();
});

await step("Free plan and its limits are shown", async () => {
  const me = await (await ctx.request.get(`${BASE}/api/v1/me`)).json();
  must(me.org.plan.id === "free", `plan is ${me.org.plan.id}`);
  return `${me.org.plan.projects} projects, ${me.org.plan.events_per_month} events/month, ${me.org.plan.retention_days} days`;
});

await step("Create a project in the dashboard", async () => {
  await page.goto(`${BASE}/app`);
  await page.getByLabel("Project name").fill("checkout-api");
  await page.getByLabel("GitHub repository").fill("https://github.com/example/checkout-api");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/app\/projects\/\d+/, { timeout: 15000 });
  projectUrl = page.url().replace(/[?#].*$/, "");
  await snap(page, "project-created");
  return projectUrl.replace(BASE, "");
});

await step("Create an API key (shown once)", async () => {
  await page.getByRole("button", { name: "Create API key" }).click();
  const code = page.locator("code", { hasText: /^fsk_/ }).first();
  await code.waitFor({ timeout: 10000 });
  apiKey = (await code.innerText()).trim();
  must(/^fsk_[\w-]{20,}$/.test(apiKey), "key has an unexpected shape");
  await snap(page, "api-key");
  return `${apiKey.slice(0, 12)}...`;
});

const work = mkdtempSync(join(tmpdir(), "fs-journey-"));

await step("A real app reports a production error through the SDK", async () => {
  if (!PY) return "skipped (set PYTHON to a Python with faultsage installed)";
  mkdirSync(join(work, "shopapp", "shop"), { recursive: true });
  writeFileSync(join(work, "shopapp", "shop", "__init__.py"), "");
  writeFileSync(
    join(work, "shopapp", "shop", "cart.py"),
    "class Cart:\n    def __init__(self, items):\n        self.items = items\n\n" +
      "    def total(self, discount):\n        return sum(self.items) * (1 - discount.rate)\n",
  );
  writeFileSync(
    join(work, "shopapp", "app.py"),
    "import faultsage.sdk as fs\nfs.init(environment='production')\nfrom shop.cart import Cart\n" +
      "try:\n    Cart([10, 20]).total(None)\nexcept Exception as e:\n" +
      "    assert fs.capture_exception(e, route='/checkout')\nfs.flush()\n" +
      "token = 'password=hunter2hunter2'\n",
  );
  for (const release of ["1.0.0", "1.0.1"]) {
    execFileSync(PY, ["app.py"], {
      cwd: join(work, "shopapp"),
      env: { ...process.env, FAULTSAGE_URL: BASE, FAULTSAGE_API_KEY: apiKey, FAULTSAGE_RELEASE: release },
      stdio: "pipe",
    });
  }
});

await step("The error appears grouped, with a triage note, and labels never say Strong", async () => {
  if (!PY) return "skipped";
  await page.goto(projectUrl);
  const row = page.getByText("AttributeError", { exact: false }).first();
  await row.waitFor({ timeout: 15000 });
  const pid = projectUrl.split("/").pop();
  const issues = await (await ctx.request.get(`${BASE}/api/v1/projects/${pid}/issues`)).json();
  must(
    issues.length === 1 && issues[0].event_count === 2,
    `expected 1 issue with 2 events, got ${JSON.stringify(issues.map((i) => i.event_count))}`,
  );
  await page.goto(`${projectUrl}/issues/${issues[0].id}`);
  await page.getByText("cart.py").first().waitFor({ timeout: 10000 });
  const text = await page.locator("main").innerText();
  must(!/\bStrong\b/.test(text), "the page shows Strong (D-024 says it is withheld)");
  must(!text.includes("hunter2"), "a secret reached the page");
  await snap(page, "issue-triage");
});

await step("The CLI pushes a local case file to the cloud", async () => {
  if (!PY) return "skipped";
  const root = new URL("../..", import.meta.url).pathname;
  const churn = join(work, "churn");
  const env = {
    ...process.env,
    PATH: `${dirname(PY)}${delimiter}${process.env.PATH}`,
    FAULTSAGE_HOME: join(work, "fshome"),
    CI: "1",
  };
  execFileSync("bash", [join(root, "tools", "make_sample_project.sh"), churn], { env, stdio: "pipe" });
  const fs = (args) =>
    execFileSync(PY, ["-m", "faultsage", ...args], { cwd: churn, env, encoding: "utf8", stdio: "pipe" });
  try {
    fs(["run", "--", PY, "-m", "pytest", "-q"]);
  } catch {
    // the sample's test fails on purpose; FaultSage records it
  }
  fs(["cloud", "login", "--url", BASE, "--api-key", apiKey]);
  const out = fs(["cloud", "push", "all"]);
  const pid = projectUrl.split("/").pop();
  const cfs = await (await ctx.request.get(`${BASE}/api/v1/projects/${pid}/case-files`)).json();
  must(cfs.length >= 1, `no case file arrived (${out.trim()})`);
  must(cfs[0].top_certainty !== "strong", "case file says Strong");
  await page.goto(`${projectUrl}/case-files/${cfs[0].id}`);
  await page.getByText("KeyError").first().waitFor({ timeout: 10000 });
  const body = await page.locator("main").innerText();
  must(!body.includes("out.append"), "source code from the user's project reached the cloud (D-030)");
  await snap(page, "case-file");
  return `${cfs.length} case file(s), top label ${cfs[0].top_certainty}`;
});

await step("Another customer cannot see this project", async () => {
  const other = await browser.newContext();
  const p = await other.newPage();
  await p.goto(`${BASE}/signup`);
  await p.getByLabel("Email").fill(OTHER);
  await p.getByLabel("Your name").fill("Other Customer");
  await p.getByLabel("Password").fill(PASSWORD);
  await p.getByRole("button", { name: "Create free account" }).click();
  await p.waitForURL(/\/app/, { timeout: 15000 });
  const pid = projectUrl.split("/").pop();
  const r = await other.request.get(`${BASE}/api/v1/projects/${pid}`);
  must(r.status() === 404, `other customer got HTTP ${r.status()}`);
  const list = await (await other.request.get(`${BASE}/api/v1/projects`)).json();
  must(list.length === 0, "other customer sees projects");
  await p.goto(projectUrl);
  await p.waitForTimeout(1000);
  must(!(await p.locator("main").innerText()).includes("checkout-api"), "project name visible");
  await snap(p, "other-customer");
  if (!process.env.KEEP) await deleteAccount(other, OTHER);
  await other.close();
});

await step("No JavaScript errors in the browser console", async () => {
  const real = consoleErrors.filter((e) => !/401|Failed to load resource/.test(e));
  must(real.length === 0, real.slice(0, 3).join(" | "));
});

async function deleteAccount(c, email) {
  const csrf = (await c.cookies()).find((k) => k.name.endsWith("csrf"))?.value || "";
  const r = await c.request.post(`${BASE}/api/v1/me/delete`, {
    data: { confirm: `delete ${email}`, password: PASSWORD },
    headers: { "X-CSRF-Token": csrf },
  });
  must(r.ok(), `delete failed: HTTP ${r.status()} ${await r.text()}`);
}

await step("Delete the test account (privacy: accounts can be erased)", async () => {
  if (process.env.KEEP) return "kept (KEEP=1)";
  await deleteAccount(ctx, EMAIL);
  const r = await ctx.request.get(`${BASE}/api/v1/me`);
  must(r.status() === 401, "still signed in after deletion");
  const login = await ctx.request.post(`${BASE}/api/v1/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  });
  must(login.status() === 401, "deleted account can still sign in");
});

await browser.close();
writeFileSync(join(OUT, "results.json"), JSON.stringify({ base: BASE, results }, null, 2));
console.log(`\n${results.length - failures} of ${results.length} steps passed. Screenshots: ${OUT}/`);
process.exit(failures ? 1 : 0);
