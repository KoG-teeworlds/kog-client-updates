// Layout check in a real browser: no sideways scrolling at any width, the docs sidebar is a closed drawer on narrow
// screens, its rows are compact and its badges sit on the same line. Used by the Site workflow.
//
// usage: PUPPETEER_CORE=/path/to/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js CHROME_PATH=google-chrome node scripts/check_layout.mjs [BASE_URL]
// Without BASE_URL the files of site/ are served from a local port.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const puppeteer = (await import(process.env.PUPPETEER_CORE)).default;
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "site");
const types = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".xml": "application/xml" };
let base = process.argv[2];
let server = null;
if (!base) {
  server = http.createServer((req, res) => {
    let file = path.join(root, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
    res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = "http://127.0.0.1:" + server.address().port;
}

const pages = ["/", "/technical/", "/technical/release-signing/", "/technical/glossary/", "/privacy/", "/404.html"];
const widths = [320, 360, 390, 414, 480, 600, 768, 900, 1024, 1280];
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH || "google-chrome", args: ["--no-sandbox"], headless: true });
const problems = [];
for (const url of pages) {
  for (const width of widths) {
    const page = await browser.newPage();
    await page.setViewport({ width, height: 900, deviceScaleFactor: 2 });
    await page.goto(base + url, { waitUntil: "networkidle0" });
    const m = await page.evaluate(() => {
      const rect = (node) => node.getBoundingClientRect();
      const nav = document.querySelector(".docs-nav");
      const rows = nav ? [...nav.querySelectorAll(".group li > a")].filter((a) => a.offsetParent !== null) : [];
      const badgeOff = rows.map((a) => {
        const badge = a.parentElement.querySelector(":scope > .state");
        return badge ? Math.abs(rect(badge).top + rect(badge).height / 2 - (rect(a).top + rect(a).height / 2)) : 0;
      });
      const bar = document.querySelector("header.site .bar");
      return {
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
        bar: rect(bar).height,
        navHeight: nav ? rect(nav).height : 0,
        drawerOpen: nav ? nav.querySelector(".nav-toggle").open : false,
        rowMin: rows.length ? Math.min(...rows.map((a) => rect(a).height)) : 0,
        rowMax: rows.length ? Math.max(...rows.map((a) => rect(a).height)) : 0,
        badgeOff: badgeOff.length ? Math.max(...badgeOff) : 0,
      };
    });
    const where = url + " at " + width + " px";
    if (m.scroll > m.client) problems.push(where + ": the page scrolls sideways (" + m.scroll + " > " + m.client + ")");
    if (m.bar > 72) problems.push(where + ": the top bar is " + Math.round(m.bar) + " px tall, it should fit on one row");
    if (m.navHeight && width < 900 && (m.drawerOpen || m.navHeight > 80)) problems.push(where + ": the docs menu should be a closed drawer, it is " + Math.round(m.navHeight) + " px");
    if (m.rowMax && m.rowMax > 48) problems.push(where + ": a sidebar row is " + Math.round(m.rowMax) + " px tall");
    if (m.badgeOff > 6) problems.push(where + ": a status badge is not on the line of its label");
    await page.close();
  }
}
await browser.close();
if (server) server.close();
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("layout ok: " + pages.length + " pages at " + widths.length + " widths, no sideways scroll, drawer closed under 900 px, rows compact");
