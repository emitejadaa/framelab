// E2E #2/#3: right-click → head(n=3) → new node, code panel, inspector preview, table tab.
// Usage: node workbench.e2e.mjs <login_url> <screenshot_dir>
import { chromium } from "playwright-core";

const [url, shots] = process.argv.slice(2);
const browser = await chromium.launch({
  executablePath: process.env.FRAMELAB_BROWSER || "/usr/bin/chromium",
  args: process.env.CI ? ["--no-sandbox"] : [],
});
const page = await browser.newPage({ viewport: { width: 1400, height: 850 }, locale: "es-AR" });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));
const fail = async (msg) => {
  await page.screenshot({ path: `${shots}/failure.png` });
  console.error("FAIL:", msg, "\nconsole errors:", errors.join("\n"));
  await browser.close();
  process.exit(1);
};

await page.goto(url);
const root = page.locator('[data-testid="node-card"]', { hasText: "ventas" }).first();
await root.waitFor({ timeout: 15000 }).catch(() => fail("root node card never appeared"));

// inspector preview of the root
await page.locator('[data-testid="inspector"] .fl-table td').first().waitFor({ timeout: 10000 })
  .catch(() => fail("inspector preview table missing"));

// right-click → Primeras filas → n=3 → Aplicar
await root.click({ button: "right" });
await page.getByRole("button", { name: /Primeras filas/ }).click();
const n = page.locator(".fl-dialog input[type=number]").first();
await n.fill("3");
await page.locator(".fl-code-preview", { hasText: "ventas.head(n=3)" }).waitFor({ timeout: 5000 })
  .catch(() => fail("live code preview did not show ventas.head(n=3)"));
await page.getByRole("button", { name: "Aplicar" }).click();

const created = page.locator('[data-testid="node-card"]', { hasText: "ventas_head" });
await created.waitFor({ timeout: 10000 }).catch(() => fail("new node did not appear"));
await page.locator('[data-testid="code"]', { hasText: "ventas_head = ventas.head(n=3)" }).waitFor({ timeout: 5000 })
  .catch(() => fail("code panel does not show the new step"));
await page.screenshot({ path: `${shots}/workbench.png` });

// double-click → table tab with 3 rows
await created.dblclick();
await page.locator(".fl-tableview .fl-table tbody tr").nth(2).waitFor({ timeout: 10000 })
  .catch(() => fail("table view did not render rows"));
const rows = await page.locator(".fl-tableview .fl-table tbody tr").count();
if (rows !== 3) await fail(`expected 3 rows, got ${rows}`);
await page.screenshot({ path: `${shots}/table.png` });

// sort by a header (view only), then filter rows by a cell: a new node
await page.locator(".fl-tableview th", { hasText: "monto" }).click();
await page.locator('[data-testid="sort-note"]').waitFor({ timeout: 5000 }).catch(() => fail("header click did not sort"));
await page.locator(".fl-tableview tbody tr").first().locator("td").nth(1).click({ button: "right" });
await page.locator('[data-testid="table-menu"] .fl-menu-item').first().click();
await page.locator('[data-testid="created-note"]', { hasText: "ventas_head_filt" }).waitFor({ timeout: 8000 })
  .catch(() => fail("filtering by a cell did not create ventas_head_filt"));
const filtered = page.locator('[data-testid="node-card"]', { hasText: "ventas_head_filt" });

// every pandas operation: browser -> nlargest(n=2, columns="monto") with a generated form
await page.getByRole("button", { name: /← Workbench/ }).click();
// the canvas centred the node made from the table; fit the view to reach the root again
await page.locator(".react-flow__controls-fitview").click();
await page.waitForTimeout(400);
await root.click({ button: "right" });
await page.locator('[data-testid="all-pandas"]').click();
await page.locator('[data-testid="member-browser"] input').fill("nlargest");
await page.locator('[data-testid="member-nlargest"]').click();
const form = page.locator('[data-testid="member-form"]');
await form.locator(".fl-field", { hasText: /^n/ }).first().locator("input").fill("2");
await form.locator(".fl-field", { hasText: "columns" }).getByLabel(/monto/).check();
await form.locator(".fl-code-preview", { hasText: 'ventas.nlargest(n=2, columns="monto")' }).waitFor({ timeout: 5000 })
  .catch(() => fail("generated form did not preview ventas.nlargest(n=2, columns=\"monto\")"));
await form.getByRole("button", { name: "Aplicar", exact: true }).click();
await page.locator('[data-testid="node-card"]', { hasText: "ventas_nlargest" }).waitFor({ timeout: 10000 })
  .catch(() => fail("nlargest node did not appear"));

// undo / redo from the keyboard on the workbench
const nlargest = page.locator('[data-testid="node-card"]', { hasText: "ventas_nlargest" });
await page.keyboard.press("Control+z");
await nlargest.waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("Ctrl+Z did not undo nlargest"));
await page.keyboard.press("Control+z");
await filtered.waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("Ctrl+Z did not undo the cell filter"));
await page.keyboard.press("Control+z");
await created.waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("Ctrl+Z did not undo the new node"));
await page.keyboard.press("Control+y");
await created.waitFor({ timeout: 5000 }).catch(() => fail("Ctrl+Y did not redo the new node"));

if (errors.length) await fail("console errors");
console.log("OK");
await browser.close();
