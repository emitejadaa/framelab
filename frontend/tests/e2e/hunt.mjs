// Exploratory sweep (not part of CI): every menu operation, table, plotter, rename/delete/undo.
// Usage: node hunt.mjs <login_url> <out_dir>
import { chromium } from "playwright-core";
import { writeFileSync } from "node:fs";

const [url, out] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.FRAMELAB_BROWSER || "/usr/bin/chromium" });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "es-AR" });
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e}`));
const report = [];
const note = (area, item, outcome, detail = "") => report.push({ area, item, outcome, detail });
const card = (name) => page.locator('[data-testid="node-card"]').filter({ has: page.locator(".fl-card-name", { hasText: new RegExp(`^${name}$`) }) });

await page.goto(url);
await card("ventas").waitFor({ timeout: 20000 });

async function rightClick(name) {
  await card(name).dispatchEvent("click"); // selecting a node brings it into view
  await page.waitForTimeout(350);
  await card(name).click({ button: "right" });
}

async function menuItems(name) {
  await rightClick(name);
  await page.locator(".fl-menu").waitFor();
  const labels = await page.locator(".fl-menu-group").filter({ hasNot: page.getByText(/^Nodo$/) }).locator(".fl-menu-item").allInnerTexts();
  await page.keyboard.press("Escape");
  return labels.map((l) => l.replace(/…$/, "").trim());
}

async function fillForm() {
  const dialog = page.locator(".fl-dialog");
  for (const sel of await dialog.locator("select.fl-input").all()) {
    const options = await sel.locator("option").allInnerTexts();
    const pick = options.find((o) => o.startsWith("cantidad")) ?? options.find((o) => o.startsWith("monto"));
    if (pick) await sel.selectOption({ label: pick });
  }
  const texts = dialog.locator("input.fl-input:not([type=number])");
  for (let i = 0; i < (await texts.count()); i++) {
    const input = texts.nth(i);
    if ((await input.inputValue()) === "") await input.fill(i === 0 ? "nueva" : "3");
  }
  const formula = dialog.locator(".fl-formula-input");
  if (await formula.count()) await formula.fill("round(cantidad * 2 + 1, 1)");
  const boxes = dialog.locator(".fl-columns input[type=checkbox]");
  const nboxes = await boxes.count();
  if (nboxes && !(await boxes.first().isChecked())) {
    for (const i of [2, 4].filter((k) => k < nboxes)) await boxes.nth(i).check();
  }
}

async function sweep(owner) {
  const labels = await menuItems(owner);
  for (const label of labels) {
    await rightClick(owner);
    const item = page.locator(".fl-menu-item", { hasText: label }).first();
    const before = await page.locator('[data-testid="node-card"]').count();
    await item.click();
    const dialog = page.locator(".fl-dialog");
    if (await dialog.isVisible().catch(() => false)) {
      await fillForm();
      await page.waitForTimeout(700);
      const apply = dialog.getByRole("button", { name: "Aplicar", exact: true });
      if (!(await apply.isEnabled())) {
        const err = await dialog.locator(".fl-form-error").allInnerTexts();
        note(owner, label, "form-blocked", err.join(" | "));
        await page.keyboard.press("Escape");
        continue;
      }
      await apply.click();
      await page.waitForTimeout(300);
      if (await dialog.isVisible().catch(() => false)) {
        const err = await dialog.locator(".fl-form-error").allInnerTexts();
        note(owner, label, "apply-failed", err.join(" | "));
        await page.keyboard.press("Escape");
        continue;
      }
    } else {
      const menuErr = await page.locator(".fl-menu-error").allInnerTexts().catch(() => []);
      if (menuErr.length) { note(owner, label, "menu-error", menuErr.join(" | ")); await page.keyboard.press("Escape"); continue; }
    }
    // wait for the new node to settle
    await page.waitForFunction((n) => document.querySelectorAll('[data-testid="node-card"]').length > n, before, { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(400);
    const name = (await page.locator(".fl-inspector-name").innerText().catch(() => "?")).trim();
    const state = await card(name).getAttribute("data-state").catch(() => "?");
    const title = await card(name).getAttribute("title").catch(() => "");
    note(owner, label, state === "ready" ? "ok" : `node-${state}`, `${name} ${state === "ready" ? "" : title}`);
  }
}

// ---- operations on a DataFrame, then a Series and a GroupBy made from it
await sweep("ventas");
// make a Series and a GroupBy to sweep their menus
for (const [label, pick] of [["Una columna", "cantidad"], ["Agrupar por", "pais"]]) {
  await rightClick("ventas");
  await page.locator(".fl-menu-item", { hasText: label }).first().click();
  const sel = page.locator(".fl-dialog select.fl-input").first();
  const options = await sel.locator("option").allInnerTexts();
  await sel.selectOption({ label: options.find((o) => o.startsWith(pick)) });
  await page.waitForTimeout(300);
  await page.locator(".fl-dialog").getByRole("button", { name: "Aplicar", exact: true }).click();
  await page.waitForTimeout(800);
}
await sweep("ventas_cantidad");
await sweep("ventas_by_pais");
await page.screenshot({ path: `${out}/workbench.png` });

// ---- table view of the root: page forward
await card("ventas").dispatchEvent("click");
await page.waitForTimeout(350);
await card("ventas").dblclick();
await page.locator(".fl-tableview .fl-table tbody tr").first().waitFor({ timeout: 8000 }).catch(() => note("table", "open", "failed"));
await page.getByRole("button", { name: "›" }).click().catch(() => note("table", "next page", "failed"));
await page.waitForTimeout(600);
note("table", "rows shown", String(await page.locator(".fl-tableview .fl-table tbody tr").count()));
await page.screenshot({ path: `${out}/table.png` });
await page.getByRole("button", { name: /← Workbench/ }).click();

// ---- plotter: every kind from the gallery on ventas
await rightClick("ventas");
await page.locator(".fl-menu-item", { hasText: "Graficar" }).click();
await page.locator('[data-testid="gallery"]').waitFor({ timeout: 8000 });
const kinds = ["line", "scatter", "bar", "barh", "hist", "box", "violin", "pie", "area", "step", "hexbin", "heatmap"];
for (const kind of kinds) {
  await page.locator('[data-testid="add-layer-0"]').click();
  await page.locator(`[data-testid="kind-${kind}"]`).click();
  await page.waitForTimeout(1200);
  const errors = await page.locator(".fl-layer-error").allInnerTexts();
  note("plot", kind, errors.length ? "layer-error" : "ok", errors.join(" | "));
  // remove it again
  await page.getByRole("button", { name: "Quitar esta capa" }).click();
  await page.waitForTimeout(300);
}
await page.screenshot({ path: `${out}/plot.png` });
await page.getByRole("button", { name: /← Workbench/ }).click();

// ---- rename, delete, undo
await card("ventas_cantidad").dispatchEvent("click");
await page.waitForTimeout(350);
await page.keyboard.press("F2");
await page.locator(".fl-dialog input").fill("unidades");
await page.keyboard.press("Enter");
await card("unidades").waitFor({ timeout: 5000 }).then(() => note("rename", "F2", "ok")).catch(() => note("rename", "F2", "failed"));
await card("unidades").dispatchEvent("click");
await page.waitForTimeout(350);
await page.keyboard.press("Delete");
await page.getByRole("alertdialog").getByRole("button", { name: "Eliminar", exact: true }).click();
await card("unidades").waitFor({ state: "detached", timeout: 5000 }).then(() => note("delete", "Supr", "ok")).catch(() => note("delete", "Supr", "failed"));
await page.keyboard.press("Control+z");
await card("unidades").waitFor({ timeout: 5000 }).then(() => note("undo", "Ctrl+Z", "ok")).catch(() => note("undo", "Ctrl+Z", "failed"));

writeFileSync(`${out}/report.json`, JSON.stringify({ report, consoleErrors }, null, 1));
for (const r of report) if (r.outcome !== "ok") console.log(`${r.area} | ${r.item} | ${r.outcome} | ${r.detail}`);
console.log(`ops ok: ${report.filter((r) => r.outcome === "ok").length}/${report.length}; console errors: ${consoleErrors.length}`);
for (const e of consoleErrors.slice(0, 10)) console.log("console:", e);
await browser.close();
