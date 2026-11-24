import { chromium } from "playwright-core";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const mode = process.argv[2];
const visual = process.argv[3] === "visual";
const root = "/work";
const site = path.join(root, "site");
const types = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain", ".xml": "application/xml" };

function serve(dir) {
  const server = http.createServer((req, res) => {
    let file = path.join(dir, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(dir)) return res.writeHead(403).end();
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) {
      res.writeHead(404, { "content-type": "text/html" });
      return res.end(fs.readFileSync(path.join(dir, "404.html")));
    }
    res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function manifest(now, extra = {}) {
  const base = "https://github.com/KoG-teeworlds/kog-client/releases/download/v0.1.0/";
  return JSON.stringify({
    format: 2, channel: "stable", sequence: 1, issued: now - 86400, expires: now + 29 * 86400, version: "0.1.0", files: [],
    platforms: {
      "linux-x86_64": { client: { sha256: "9f2c1a7b4d6e8f003a5b7c9d1e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b2c4d6e8f", size: 41234567, url: base + "client-linux-x86_64-0.1.0" } },
      win64: { client: { sha256: "1a3b5c7d9e0f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a1b", size: 39876543, url: base + "client-win64-0.1.0.exe" } },
    },
    ...extra,
  });
}

if (mode === "og") {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await page.goto("file://" + path.join(root, "scripts/og/card.html"));
  await page.screenshot({ path: path.join(root, "site/assets/og.png"), clip: { x: 0, y: 0, width: 1200, height: 630 } });
  await browser.close();
  console.log("og.png written");
} else if (mode === "pages") {
  const out = "/out";
  const browser = await chromium.launch();
  const problems = [];
  const states = {
    ok: (now) => manifest(now),
    none: () => null,
    expired: (now) => manifest(now, { issued: now - 60 * 86400, expires: now - 30 * 86400 }),
  };
  const pages = ["/", "/technical/", "/privacy/", "/verify/", "/nope/"];
  for (const [state, make] of Object.entries(states)) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "site-"));
    fs.cpSync(site, dir, { recursive: true });
    const body = make(Math.floor(Date.now() / 1000));
    if (body) fs.writeFileSync(path.join(dir, "update.json"), body);
    const server = await serve(dir);
    const origin = "http://127.0.0.1:" + server.address().port;
    for (const scheme of ["light", "dark"]) {
      for (const width of [1280, 390]) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme, bypassCSP: visual });
        for (const url of state === "ok" ? pages : ["/"]) {
          const page = await context.newPage();
          const external = [];
          page.on("request", (request) => { if (!request.url().startsWith(origin) && !request.url().startsWith("data:")) external.push(request.url()); });
          page.on("console", (message) => { const expected404 = /status of 404/.test(message.text()) && (url === "/nope/" || state === "none"); if (["error", "warning"].includes(message.type()) && !expected404) problems.push(state + " " + url + " console: " + message.text()); });
          page.on("pageerror", (error) => problems.push(state + " " + url + " pageerror: " + error.message));
          await page.goto(origin + url, { waitUntil: "networkidle" });
          if (visual) await page.addStyleTag({ content: "body, select, code { font-family: Arial, Liberation Sans, sans-serif !important } code, pre { font-family: Liberation Mono, monospace !important }" });
          await page.waitForTimeout(150);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
          if (overflow) problems.push(state + " " + url + " " + width + "px: horizontal overflow");
          if (external.length) problems.push(state + " " + url + " external requests: " + external.join(", "));
          const name = (url === "/" ? "home" : url.replaceAll("/", "")) + "-" + state + "-" + width + "-" + scheme + ".png";
          await page.screenshot({ path: path.join(out, name), fullPage: true });
          await page.close();
        }
        await context.close();
      }
    }
    server.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(out, "problems.txt"), problems.join("\n"));
  console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "no problems");
  process.exit(problems.length ? 1 : 0);
}
