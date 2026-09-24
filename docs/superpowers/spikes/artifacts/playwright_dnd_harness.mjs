// s10 driver: playwright-core + /usr/bin/chromium headless. Real (trusted) mouse input via page.mouse.
// Usage: node tools/run-dnd.mjs [--url http://127.0.0.1:8932/] [--dpr 1] [--label dpr1] [--zooms 0.5,1,2]
import { chromium } from "playwright-core";
import { mkdirSync, writeFileSync } from "node:fs";

const argv = process.argv.slice(2);
const opt = (k, d) => (argv.includes(`--${k}`) ? argv[argv.indexOf(`--${k}`) + 1] : d);
const url = opt("url", "http://127.0.0.1:8932/");
const dpr = Number(opt("dpr", "1"));
const label = opt("label", `dpr${dpr}`);
const zooms = opt("zooms", "0.5,1,2").split(",").map(Number);
const root = new URL("..", import.meta.url).pathname;
mkdirSync(`${root}results`, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const near = (a, b, tol) => Math.abs(a - b) <= tol;

const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 760 }, deviceScaleFactor: dpr });
const page = await ctx.newPage();
const consoleMsgs = [];
page.on("console", (m) => consoleMsgs.push({ type: m.type(), text: m.text().slice(0, 400) }));
page.on("pageerror", (e) => consoleMsgs.push({ type: "pageerror", text: String(e).slice(0, 400) }));

const out = { url, label, dpr, chromium: browser.version(), zooms: {}, console: consoleMsgs };
const ev = () => page.evaluate(() => window.__events.length);
const eventsSince = (n) => page.evaluate((n) => window.__events.slice(n), n);
const rect = (sel) => page.evaluate((sel) => { const r = document.querySelector(sel)?.getBoundingClientRect(); return r && { x: r.x, y: r.y, w: r.width, h: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2 }; }, sel);
const nodeRect = (id) => rect(`.react-flow__node[data-id="${id}"]`);
const nodePos = (id) => page.evaluate((id) => ({ ...window.__rf.getNode(id).position }), id);
const viewport = () => page.evaluate(() => window.__rf.getViewport());
const setCenter = (x, y, zoom) => page.evaluate(([x, y, zoom]) => window.__rf.setCenter(x, y, { zoom, duration: 0 }), [x, y, zoom]);
const reset = async () => { await page.evaluate(() => window.__reset()); await sleep(120); };
async function drag(from, to, { steps = 20, midCheck } = {}) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 3, from.y + 3, { steps: 2 });
  await page.mouse.move(to.x, to.y, { steps });
  await sleep(60);
  const mid = midCheck ? await midCheck() : undefined;
  await page.mouse.up();
  await sleep(150);
  return mid;
}
// First point on a coarse grid inside the canvas where the pane itself (no node/controls/edge) is hit.
const emptyPanePoint = () =>
  page.evaluate(() => {
    const c = document.querySelector(".react-flow").getBoundingClientRect();
    for (let fy = 0.85; fy > 0.1; fy -= 0.05)
      for (let fx = 0.9; fx > 0.1; fx -= 0.05) {
        const x = c.x + c.width * fx, y = c.y + c.height * fy;
        const ok = [[0, 0], [100, 50], [-40, -40], [40, 40]].every(([dx, dy]) => document.elementFromPoint(x + dx, y + dy)?.classList.contains("react-flow__pane"));
        if (ok) return { x, y };
      }
    return null;
  });

try {
  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector('.react-flow__node[data-id="n6"]');
  await sleep(300);
  out.env = await page.evaluate(() => ({ ua: navigator.userAgent, dpr: devicePixelRatio, w: innerWidth, h: innerHeight, scrollH: document.documentElement.scrollHeight }));

  for (const Z of zooms) {
    const R = {};
    await page.evaluate(() => window.scrollTo(0, 0));

    // ---- pan + wheel zoom ----
    await reset();
    await setCenter(335, 100, Z);
    await sleep(100);
    const vp0 = await viewport();
    const pp = await emptyPanePoint();
    let n0 = await ev();
    await drag(pp, { x: pp.x - 90, y: pp.y - 45 }, { steps: 10 });
    const vp1 = await viewport();
    R.pan = { ok: near(vp1.x - vp0.x, -90, 1.5) && near(vp1.y - vp0.y, -45, 1.5) && Math.abs(vp1.zoom - Z) < 1e-9, dx: vp1.x - vp0.x, dy: vp1.y - vp0.y, events: await eventsSince(n0) };
    n0 = await ev();
    await page.mouse.move(pp.x - 90, pp.y - 45);
    await page.mouse.wheel(0, -120);
    await sleep(300);
    const vp2 = await viewport();
    R.wheelZoom = { ok: vp2.zoom > Z, from: Z, to: vp2.zoom, events: await eventsSince(n0) };

    // ---- (a) normal node drag inside the canvas ----
    await reset();
    await setCenter(75, 18, Z);
    await sleep(100);
    let r = await nodeRect("n1");
    let p0 = await nodePos("n1");
    n0 = await ev();
    await drag({ x: r.cx, y: r.cy }, { x: r.cx + 100, y: r.cy + 60 });
    let p1 = await nodePos("n1");
    let evs = await eventsSince(n0);
    R.a_move = {
      ok: evs.length === 1 && evs[0].type === "move" && near(p1.x - p0.x, 100 / Z, 1.5 / Z) && near(p1.y - p0.y, 60 / Z, 1.5 / Z),
      expectedFlowDelta: { x: 100 / Z, y: 60 / Z },
      flowDelta: { x: p1.x - p0.x, y: p1.y - p0.y },
      events: evs,
    };

    // ---- (b) release over drop boxes OUTSIDE the canvas and over the fake tab bar -> detect + snap back ----
    const bCases = [
      ["n2", "box:plotter", [260 + 75, 18]],
      ["n2", "box:inspector", [260 + 75, 18]],
      ["n3", "tab:ploter", [520 + 75, 18]],
      ["n5", "tab:tabla", [260 + 75, 160 + 18]],
    ];
    R.b_external = [];
    for (const [id, zone, [cx, cy]] of bCases) {
      await reset();
      await setCenter(cx, cy, Z);
      await sleep(100);
      r = await nodeRect(id);
      p0 = await nodePos(id);
      const vpBefore = await viewport();
      const zr = await rect(`[data-drop-zone="${zone}"]`);
      n0 = await ev();
      const mid = await drag({ x: r.cx, y: r.cy }, { x: zr.cx, y: zr.cy }, {
        steps: 25,
        midCheck: () => page.evaluate((zone) => document.querySelector(`[data-drop-zone="${zone}"]`).classList.contains("hover"), zone),
      });
      await sleep(100);
      p1 = await nodePos(id);
      const vpAfter = await viewport();
      evs = await eventsSince(n0);
      const e0 = evs.find((e) => e.type === "drop-external");
      R.b_external.push({
        id,
        zone,
        ok: !!e0 && e0.zone === zone && evs.length === 1 && p1.x === p0.x && p1.y === p0.y,
        highlightedWhileHovering: mid,
        snappedBack: p1.x === p0.x && p1.y === p0.y,
        start: p0,
        after: p1,
        viewportDrift: { dx: Math.round(vpAfter.x - vpBefore.x), dy: Math.round(vpAfter.y - vpBefore.y) },
        events: evs,
      });
    }

    // ---- (c) drop a node onto another node -> getIntersectingNodes ----
    await reset();
    await setCenter(205, 178, Z); // midpoint between n4 and n5 centers
    await sleep(100);
    r = await nodeRect("n4");
    const t5 = await nodeRect("n5");
    p0 = await nodePos("n4");
    n0 = await ev();
    await drag({ x: r.cx, y: r.cy }, { x: t5.cx + 10, y: t5.cy + 5 });
    p1 = await nodePos("n4");
    evs = await eventsSince(n0);
    R.c_combine = { ok: evs.length === 1 && evs[0].type === "combine" && evs[0].target === "n5" && p1.x === p0.x && p1.y === p0.y, snappedBack: p1.x === p0.x && p1.y === p0.y, events: evs };
    // partial overlap (edge of n4 just touching n5's corner) still counts as combine with partially=true
    await reset();
    await setCenter(205, 178, Z); // midpoint between n4 and n5 centers
    await sleep(100);
    r = await nodeRect("n4");
    const t5b = await nodeRect("n5");
    n0 = await ev();
    // move n4 so its right edge overlaps n5's left edge by ~10 screen px
    await drag({ x: r.cx, y: r.cy }, { x: r.cx + (t5b.x - (r.x + r.w)) + 10, y: r.cy });
    evs = await eventsSince(n0);
    R.c_combine_partial = { ok: evs.length === 1 && evs[0].type === "combine" && evs[0].target === "n5", events: evs };

    // ---- (d) custom pointer DnD from sidebar into the canvas (setPointerCapture + ghost portal + screenToFlowPosition) ----
    const dCases = [["df_sales", 0], ["df_clients", 80]]; // second one with the page scrolled by 80 px
    R.d_sidebar = [];
    for (const [item, scrollY] of dCases) {
      await reset();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.evaluate(([Z]) => window.__rf.setViewport({ x: 40, y: 40, zoom: Z }), [Z]);
      await page.evaluate((y) => window.scrollTo(0, y), scrollY);
      await sleep(120);
      const src = await rect(`[data-sidebar-item="${item}"]`);
      const pane = await rect(".react-flow");
      const target = { x: Math.round(pane.x + 430), y: Math.round(pane.y + 290) };
      n0 = await ev();
      const mid = await drag({ x: src.cx, y: src.cy }, target, {
        steps: 25,
        midCheck: () =>
          page.evaluate((item) => {
            const g = document.querySelector(".dnd-ghost");
            const gr = g?.getBoundingClientRect();
            return {
              ghostInPortal: !!g?.closest(".fl-portal"),
              ghostInFlRoot: !!g?.closest(".fl-root"),
              ghostAt: gr && { x: Math.round(gr.x), y: Math.round(gr.y) },
              pointerCaptured: document.querySelector(`[data-sidebar-item="${item}"]`).hasPointerCapture(1),
            };
          }, item),
      });
      await sleep(150);
      evs = await eventsSince(n0);
      const drop = evs.find((e) => e.type === "sidebar-drop");
      const check = evs.find((e) => e.type === "sidebar-drop-check");
      const expFlow = { x: (target.x - pane.x - 40) / Z, y: (target.y - pane.y - 40) / Z };
      const ghostGone = await page.evaluate(() => !document.querySelector(".dnd-ghost"));
      R.d_sidebar.push({
        item,
        pageScrollY: scrollY,
        ok:
          !!drop && !!check && check.found && Math.abs(check.dx) <= 1 && Math.abs(check.dy) <= 1 &&
          near(drop.flow.x, expFlow.x, 1 / Z) && near(drop.flow.y, expFlow.y, 1 / Z) &&
          mid.ghostInPortal && mid.ghostInFlRoot && mid.pointerCaptured && ghostGone,
        mid,
        ghostRemovedAfterDrop: ghostGone,
        expectedFlow: expFlow,
        events: evs,
      });
    }
    // drop outside the canvas -> cancel, no node added
    await reset();
    await page.evaluate(() => window.scrollTo(0, 0));
    const src = await rect('[data-sidebar-item="read_csv"]');
    const box = await rect('[data-drop-zone="box:inspector"]');
    const nodesBefore = await page.evaluate(() => window.__rf.getNodes().length);
    n0 = await ev();
    await drag({ x: src.cx, y: src.cy }, { x: box.cx, y: box.cy }, { steps: 25 });
    evs = await eventsSince(n0);
    const nodesAfter = await page.evaluate(() => window.__rf.getNodes().length);
    R.d_sidebar_cancel = { ok: evs.length === 1 && evs[0].type === "sidebar-cancel" && nodesAfter === nodesBefore, events: evs };

    if (Z === 2 || Z === 0.5) {
      // screenshot with a ghost mid-drag + highlighted drop box
      await reset();
      await page.evaluate(([Z]) => window.__rf.setViewport({ x: 40, y: 40, zoom: Z }), [Z]);
      const s2 = await rect('[data-sidebar-item="df_sales"]');
      const pane = await rect(".react-flow");
      await page.mouse.move(s2.cx, s2.cy);
      await page.mouse.down();
      await page.mouse.move(pane.x + 300, pane.y + 250, { steps: 15 });
      await sleep(100);
      await page.screenshot({ path: `${root}screenshot-${label}-zoom${Z}-ghost.png` });
      await page.mouse.up();
      await sleep(150);
    }

    R.allOk = [R.pan.ok, R.wheelZoom.ok, R.a_move.ok, ...R.b_external.map((x) => x.ok), R.c_combine.ok, R.c_combine_partial.ok, ...R.d_sidebar.map((x) => x.ok), R.d_sidebar_cancel.ok].every(Boolean);
    out.zooms[Z] = R;
  }
  await page.screenshot({ path: `${root}screenshot-${label}-final.png` });
  out.windowEventsTotal = await page.evaluate(() => window.__events.length);
  out.appConsoleErrors = await page.evaluate(() => window.__consoleErrors);
} catch (e) {
  out.error = String(e?.stack ?? e);
} finally {
  await page.close();
  await browser.close();
}
writeFileSync(`${root}results/${label}.json`, JSON.stringify(out, null, 2));
const brief = { label, env: out.env, error: out.error, console: consoleMsgs.filter((m) => m.type !== "info" && m.type !== "log") };
for (const [Z, R] of Object.entries(out.zooms)) {
  brief[`zoom ${Z}`] = {
    allOk: R.allOk,
    pan: [R.pan.ok, R.pan.dx, R.pan.dy],
    wheelZoom: [R.wheelZoom.ok, R.wheelZoom.to],
    a_move: [R.a_move.ok, R.a_move.flowDelta, R.a_move.expectedFlowDelta],
    b_external: R.b_external.map((x) => [x.ok, x.id, x.zone, x.events.map((e) => e.type + ":" + (e.zone ?? "")).join(","), "hl=" + x.highlightedWhileHovering, "drift=" + JSON.stringify(x.viewportDrift)]),
    c_combine: [R.c_combine.ok, R.c_combine.events.map((e) => `${e.type}:${e.target ?? ""}`)],
    c_combine_partial: [R.c_combine_partial.ok, R.c_combine_partial.events.map((e) => `${e.type}:${e.target ?? ""}`)],
    d_sidebar: R.d_sidebar.map((x) => [x.ok, x.item, "scrollY=" + x.pageScrollY, JSON.stringify(x.mid), JSON.stringify(x.events.map((e) => (e.type === "sidebar-drop" ? { flow: e.flow } : e.type === "sidebar-drop-check" ? { dx: e.dx, dy: e.dy } : e.type))), "exp=" + JSON.stringify(x.expectedFlow)]),
    d_cancel: [R.d_sidebar_cancel.ok, R.d_sidebar_cancel.events.map((e) => e.type + ":" + e.zone)],
  };
}
console.log(JSON.stringify(brief, null, 1));
