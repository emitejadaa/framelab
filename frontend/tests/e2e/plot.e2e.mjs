// E2E: drag a node to ▟ → gallery → chart + code → edit → export; formula column; delete a node.
// Usage: node plot.e2e.mjs <login_url> <screenshot_dir>
import { chromium } from "playwright-core";

const [url, shots] = process.argv.slice(2);
const browser = await chromium.launch({
  executablePath: process.env.FRAMELAB_BROWSER || "/usr/bin/chromium",
  args: process.env.CI ? ["--no-sandbox"] : [],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "es-AR" });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));
const fail = async (msg) => {
  await page.screenshot({ path: `${shots}/failure.png` });
  console.error("FAIL:", msg, "\nconsole errors:", errors.join("\n"));
  await browser.close();
  process.exit(1);
};
const wait = (locator, what, timeout = 10000) => locator.waitFor({ timeout }).catch(() => fail(what));

await page.goto(url);
const root = page.locator('[data-testid="node-card"]', { hasText: "ventas" }).first();
await wait(root, "root node card never appeared", 15000);

// ---- new column from a nested formula ----
await root.click({ button: "right" });
await page.getByRole("button", { name: /Columna nueva/ }).click();
await page.locator(".fl-dialog input.fl-input").first().fill("total");
await page.locator(".fl-formula-input").fill("round((monto - 10) * cantidad / 2, 1)");
await wait(
  page.locator(".fl-code-preview", { hasText: 'ventas_2["total"] = ((ventas_2["monto"] - 10) * ventas_2["cantidad"] / 2).round(1)' }),
  "formula preview code is wrong",
);
await page.getByRole("button", { name: "Aplicar" }).click();
const withTotal = page.locator('[data-testid="node-card"]', { hasText: "ventas_2" });
await wait(withTotal, "formula node did not appear");

// ---- drag the root to ▟ Gráfico ----
const box = await root.boundingBox();
const target = await page.locator('[data-testid="drop-plot"]').boundingBox();
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
await page.mouse.down();
await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2 + 10, { steps: 5 });
await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 15 });
await page.mouse.up();
await wait(page.locator('[data-testid="plot-view"]'), "plot view did not open after the drop");
await wait(page.locator('[data-testid="gallery"] .fl-suggestion').first(), "no suggestions in the gallery");
await page.locator('[data-testid="gallery"] .fl-suggestion').first().click();
await wait(page.locator('[data-testid="plot-image"]'), "no chart image");
await wait(page.locator('[data-testid="figure-code"]', { hasText: "fig_ventas, ax_ventas = plt.subplots(" }), "figure code missing");
await page.screenshot({ path: `${shots}/plot-suggestion.png` });

// ---- change the chart type and a property ----
await page.locator('[data-testid="layer-kind"]').selectOption("scatter");
await wait(page.locator('[data-testid="figure-code"]', { hasText: "ax_ventas.scatter(" }), "code did not switch to scatter");
await page.locator('[data-testid="map-hue"]').selectOption({ label: /region/ }).catch(() => undefined);
await wait(page.locator('[data-testid="figure-code"]', { hasText: 'groupby("region")' }), "split by region missing");

// ---- a second layer on the same axes: histogram of the formula node ----
await page.locator('[data-testid="add-layer-0"]').click();
await page.locator('[data-testid="gallery"] select').selectOption({ label: "ventas_2" });
await page.locator('[data-testid="kind-hist"]').click();
await wait(page.locator('[data-testid="layer-0-1"]'), "second layer missing");
await wait(page.locator('[data-testid="figure-code"]', { hasText: "ventas_2 = ventas.copy()" }), "full code lacks the source pipeline");
await page.locator('[data-testid="plot-image"]').waitFor();
await page.waitForTimeout(600);
await page.screenshot({ path: `${shots}/plot-two-layers.png` });

// ---- undo removes the second layer ----
await page.getByTitle(/Deshacer/).click();
await page.locator('[data-testid="layer-0-1"]').waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("undo did not remove the layer"));

// ---- export: Python writes the file and the code gains savefig ----
await page.locator('[data-testid="export"]').click();
await page.getByRole("button", { name: /Guardar en la carpeta/ }).click();
await wait(page.locator(".fl-ok", { hasText: "fig_ventas.png" }), "export did not report the saved path");
await page.locator(".fl-dialog").getByRole("button", { name: "Cerrar", exact: true }).click();
await wait(page.locator('[data-testid="figure-code"]', { hasText: 'fig_ventas.savefig("fig_ventas.png", dpi=100)' }), "savefig missing from the code");

// ---- back to the workbench: the figure is a node; delete the formula node ----
await page.getByRole("button", { name: /← Workbench/ }).click();
await wait(page.locator('[data-testid="figure-card"]'), "figure card missing on the canvas");
await withTotal.click();
await page.keyboard.press("Delete");
await page.getByRole("alertdialog").getByRole("button", { name: "Eliminar", exact: true }).click();
await withTotal.waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("node was not deleted"));
await page.screenshot({ path: `${shots}/workbench-after.png` });

if (errors.length) await fail("console errors");
console.log("OK");
await browser.close();
