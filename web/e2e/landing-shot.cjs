// Regenerates web/public/screens/case-file.png (landing page image) from the real local dashboard.
// Start `faultsage watch` in the sample project (tools/make_sample_project.sh, then run pytest twice),
// then from that project folder: node web/e2e/landing-shot.cjs .faultsage/session web/public/screens/case-file.png
// (pass the dashboard port as a third argument if it is not 8765).
const { chromium } = require("playwright");
const port = process.argv[4] || "8765";
const tok = JSON.parse(require("fs").readFileSync(process.argv[2])).token;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
  await p.goto(`http://127.0.0.1:${port}/#t=${tok}`);
  await p.waitForTimeout(1500);
  await p.goto(`http://127.0.0.1:${port}/incidents/1`);
  await p.getByText("Likely causes").waitFor();
  await p.waitForTimeout(2000);
  await p.screenshot({ path: process.argv[3] });
  await b.close();
})();
