const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const Manifest = require("../site/assets/manifest.js");
const appSource = fs.readFileSync(path.join(__dirname, "../site/assets/app.js"), "utf8");

const NOW = 1790000000;
const SHA = "a".repeat(64);
const BASE = "https://github.com/KoG-teeworlds/kog-client/releases/download/v1.2.3/";

function manifest(overrides = {}) {
  return {
    format: 2,
    channel: "stable",
    sequence: 7,
    issued: NOW - 86400,
    expires: NOW + 29 * 86400,
    version: "1.2.3",
    files: [],
    platforms: {
      "linux-x86_64": { client: { sha256: SHA, size: 1234567, url: BASE + "client-linux-x86_64-1.2.3" } },
      win64: { client: { sha256: "b".repeat(64), size: 2345678, url: BASE + "client-win64-1.2.3.exe" } },
    },
    ...overrides,
  };
}

function parse(object, channel = "stable", now = NOW) {
  return Manifest.parse(typeof object === "string" ? object : JSON.stringify(object), channel, now);
}

test("a valid manifest is accepted and normalised", () => {
  const result = parse(manifest());
  assert.equal(result.ok, true);
  assert.equal(result.data.version, "1.2.3");
  assert.equal(result.data.expired, false);
  assert.deepEqual(result.data.files.map((f) => f.id), ["win64", "linux-x86_64"]);
  assert.deepEqual(result.data.packages.map((p) => p.file), ["KoG-Client-windows.zip", "KoG-Client-linux.tar.xz", "KoG-Client-macOS.dmg"]);
  for (const item of result.data.packages) assert.ok(item.url.startsWith(BASE));
});

test("an expired manifest is flagged, not hidden", () => {
  const result = parse(manifest(), "stable", NOW + 40 * 86400);
  assert.equal(result.ok, true);
  assert.equal(result.data.expired, true);
});

test("a manifest issued in the future is refused as a clock problem", () => {
  const result = parse(manifest({ issued: NOW + 5 * 86400, expires: NOW + 30 * 86400 }));
  assert.deepEqual(result, { ok: false, reason: "clock" });
});

test("a manifest for another channel is refused", () => {
  assert.deepEqual(parse(manifest({ channel: "dev", version: "1.2.3-dev.4" })), { ok: false, reason: "channel" });
  assert.equal(parse(manifest({ channel: "canary", version: "1.2.3-canary.4" }), "canary").ok, true);
});

test("a missing channel field is accepted for the channel that was asked", () => {
  const m = manifest();
  delete m.channel;
  assert.equal(parse(m).ok, true);
});

test("things that are not a manifest are refused", () => {
  for (const value of ["", "null", "[]", "42", '"text"', "{", "<html></html>", "{}", "true"]) {
    assert.equal(parse(value).ok, false, value);
  }
  assert.equal(Manifest.parse(undefined, "stable", NOW).ok, false);
  assert.equal(Manifest.parse("{}", "nightly", NOW).ok, false);
});

test("HTML or script in the version is refused and never shown", () => {
  for (const version of ['1.2.3"><script>alert(1)</script>', "<img src=x onerror=alert(1)>", "1.2.3\n", "1.2", "v1.2.3", "1.2.3-beta.1", "1.2.3-dev", "1.2.3-canary.x", "99999.1.1", "1.2.3 ", "javascript:alert(1)"]) {
    assert.equal(parse(manifest({ version })).ok, false, version);
  }
});

test("huge strings and huge documents are refused", () => {
  assert.equal(parse(manifest({ version: "1".repeat(100000) })).ok, false);
  assert.equal(Manifest.parse(" ".repeat(Manifest.MAX_TEXT + 1) + "{}", "stable", NOW).ok, false);
  const big = manifest();
  big.platforms.win64.client.url = BASE + "x".repeat(10000);
  const result = parse(big);
  assert.equal(result.ok, true);
  assert.deepEqual(result.data.files.map((f) => f.id), ["linux-x86_64"]);
});

test("bad dates and validity windows are refused", () => {
  for (const change of [{ issued: "1790000000" }, { expires: null }, { issued: NOW, expires: NOW }, { issued: NOW, expires: NOW - 1 }, { issued: NOW - 86400, expires: NOW + 91 * 86400 }, { issued: 1.5 }, { issued: -5 }, { expires: 99999999999 }, { issued: Number.MAX_SAFE_INTEGER + 2 }]) {
    assert.equal(parse(manifest(change)).ok, false, JSON.stringify(change));
  }
});

test("wrong format numbers are refused", () => {
  for (const format of [1, 3, "2", null, undefined]) assert.equal(parse(manifest({ format })).ok, false, String(format));
});

test("URLs outside the allowed places are dropped", () => {
  const bad = [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "http://github.com/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://evil.example/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://github.com.evil.example/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://client.kog.tw.evil.example/update",
    "https://user@github.com/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://user:pass@client.kog.tw/x",
    "https://github.com:444/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/v1/x?a=b",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/v1/x#frag",
    "https://github.com/KoG-teeworlds/other/releases/download/v1/x",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/../../../../evil/x",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/%2e%2e/%2e%2e/x",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/v1%2fx",
    "https://github.com\\@evil.example/x",
    "https://github.com/KoG-teeworlds/kog-client/releases/download/v1/x y",
    "//github.com/KoG-teeworlds/kog-client/releases/download/v1/x",
    "/KoG-teeworlds/kog-client/releases/download/v1/x",
    "https://client.kog.tw",
    "",
    null,
    42,
    {},
    ["https://client.kog.tw/x"],
  ];
  for (const url of bad) assert.equal(Manifest.allowedUrl(url), null, String(url));
  for (const url of [BASE + "file", "https://client.kog.tw/notes/1.2.3", "https://client.kog.tw/update.json"]) assert.equal(Manifest.allowedUrl(url), url);
});

test("a platform entry with any bad field is dropped, the others stay", () => {
  const m = manifest();
  m.platforms.win64.client.sha256 = "B".repeat(64);
  assert.deepEqual(parse(m).data.files.map((f) => f.id), ["linux-x86_64"]);
  for (const change of [{ sha256: "abc" }, { sha256: 12 }, { size: -1 }, { size: 0 }, { size: 1.5 }, { size: "10" }, { size: 2147483648 }, { url: "https://evil.example/x" }]) {
    const n = manifest();
    Object.assign(n.platforms["linux-x86_64"].client, change);
    assert.deepEqual(parse(n).data.files.map((f) => f.id), ["win64"], JSON.stringify(change));
  }
});

test("unknown platforms, odd shapes and prototype keys are ignored", () => {
  const text = JSON.stringify(manifest()).replace('"platforms":{', '"platforms":{"__proto__":{"client":{"sha256":"' + SHA + '","size":5,"url":"' + BASE + 'x"}},"android":{"client":{}},');
  const result = parse(text);
  assert.equal(result.ok, true);
  assert.deepEqual(result.data.files.map((f) => f.id).sort(), ["linux-x86_64", "win64"]);
  assert.equal({}.client, undefined);
  for (const platforms of [null, [], "x", 5, { win64: null }, { win64: { client: null } }, { win64: { client: "x" } }]) {
    const result2 = parse(manifest({ platforms }));
    assert.equal(result2.ok, true);
    assert.deepEqual(result2.data.files, []);
  }
});

test("package links need a valid version", () => {
  assert.equal(Manifest.packageLinks("1.2.3").length, 3);
  assert.equal(Manifest.packageLinks("1.2.3-canary.57").length, 3);
  for (const version of ["", "1.2", '1.2.3"/><script>', null, undefined, 5, "../1.2.3"]) assert.deepEqual(Manifest.packageLinks(version), []);
});

test("dates and sizes are formatted in a fixed way", () => {
  assert.equal(Manifest.formatDate(0), "1970-01-01");
  assert.equal(Manifest.formatDate(1767225600), "2026-01-01");
  assert.equal(Manifest.formatDate("x"), "");
  assert.equal(Manifest.formatDate(-1), "");
  assert.equal(Manifest.formatSize(512), "512 B");
  assert.equal(Manifest.formatSize(1536), "1.5 KiB");
  assert.equal(Manifest.formatSize(5 * 1024 * 1024), "5.0 MiB");
  assert.equal(Manifest.formatSize(-1), "");
  assert.equal(Manifest.formatSize(1.5), "");
});

function fakeDom() {
  const calls = { innerHTML: 0, attrs: [], texts: [] };
  class Node {
    constructor(tag) {
      this.tag = tag;
      this.children = [];
      this.attrs = {};
      this.className = "";
      this.hidden = false;
      this._text = "";
      this.listeners = {};
    }
    set textContent(value) {
      calls.texts.push(String(value));
      this._text = String(value);
    }
    get textContent() {
      return this._text + this.children.map((c) => c.textContent).join("");
    }
    set innerHTML(value) {
      calls.innerHTML++;
      throw new Error("innerHTML must not be used");
    }
    setAttribute(name, value) {
      calls.attrs.push([this.tag, name, value]);
      this.attrs[name] = value;
    }
    appendChild(child) {
      this.children.push(child);
      return child;
    }
    removeChild(child) {
      this.children.splice(this.children.indexOf(child), 1);
    }
    get firstChild() {
      return this.children[0] || null;
    }
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    }
    find(tag, out = []) {
      if (this.tag === tag) out.push(this);
      this.children.forEach((c) => c.find && c.find(tag, out));
      return out;
    }
  }
  const nodes = { release: new Node("div"), channel: new Node("select"), unstable: new Node("details") };
  nodes.unstable.hidden = true;
  nodes.channel.value = "stable";
  const document = {
    getElementById: (id) => nodes[id] || null,
    createElement: (tag) => new Node(tag),
    createTextNode: (text) => {
      const node = new Node("#text");
      node._text = String(text);
      return node;
    },
  };
  return { document, nodes, calls };
}

async function runApp(responses) {
  const { document, nodes, calls } = fakeDom();
  const requested = [];
  const sandbox = {
    window: { KogManifest: Manifest },
    document,
    AbortController,
    setTimeout,
    clearTimeout,
    Date,
    Math,
    Promise,
    Error,
    fetch: async (url, options) => {
      requested.push([url, options]);
      const entry = responses[url];
      if (entry === undefined) return { status: 404, ok: false, text: async () => "" };
      if (entry instanceof Error) throw entry;
      return { status: entry.status || 200, ok: (entry.status || 200) < 400, text: async () => entry.body };
    },
  };
  vm.runInNewContext(appSource, sandbox);
  await new Promise((resolve) => setTimeout(resolve, 30));
  return { nodes, calls, requested, sandbox };
}

function liveManifest(overrides) {
  const now = Math.floor(Date.now() / 1000);
  return JSON.stringify(manifest({ issued: now - 86400, expires: now + 29 * 86400, ...overrides }));
}

test("the page shows a valid manifest through text nodes and checked links only", async () => {
  const { nodes, calls, requested } = await runApp({ "update.json": { body: liveManifest() } });
  assert.equal(calls.innerHTML, 0);
  assert.equal(nodes.unstable.hidden, false);
  const text = nodes.release.textContent;
  assert.match(text, /Version 1\.2\.3 \(stable\)/);
  assert.match(text, /Download for Windows/);
  assert.match(text, new RegExp(SHA));
  for (const [tag, name, value] of calls.attrs) {
    if (name === "href") assert.ok(Manifest.allowedUrl(value) || value === "verify/" || value === "https://github.com/KoG-teeworlds/kog-client/releases", value);
    assert.notEqual(name.slice(0, 2), "on");
  }
  assert.equal(requested[0][1].credentials, "omit");
  assert.equal(requested[0][1].referrerPolicy, "no-referrer");
});

test("a hostile manifest is shown as an error and none of its text reaches the page", async () => {
  const hostile = liveManifest({ version: '<img src=x onerror="alert(1)">' });
  const { nodes, calls } = await runApp({ "update.json": { body: hostile } });
  assert.equal(calls.innerHTML, 0);
  assert.match(nodes.release.textContent, /could not be validated/);
  assert.doesNotMatch(nodes.release.textContent, /onerror|<img|alert/);
  assert.doesNotMatch(calls.texts.join("\n"), /onerror|<img/);
});

test("a platform with a hostile URL is left out of the page", async () => {
  const m = JSON.parse(liveManifest());
  m.platforms.win64.client.url = "javascript:alert(document.domain)";
  const { nodes, calls } = await runApp({ "update.json": { body: JSON.stringify(m) } });
  assert.doesNotMatch(JSON.stringify(calls.attrs), /javascript:/);
  assert.doesNotMatch(nodes.release.textContent, /javascript:/);
  assert.match(nodes.release.textContent, /Linux \(64-bit\)/);
});

test("an expired manifest shows a warning", async () => {
  const now = Math.floor(Date.now() / 1000);
  const { nodes } = await runApp({ "update.json": { body: JSON.stringify(manifest({ issued: now - 40 * 86400, expires: now - 10 * 86400 })) } });
  assert.match(nodes.release.textContent, /expired on/);
});

test("no manifest means a calm message and a link to GitHub", async () => {
  const { nodes, calls } = await runApp({});
  assert.match(nodes.release.textContent, /No stable release has been published yet/);
  assert.ok(calls.attrs.some(([, name, value]) => name === "href" && value === "https://github.com/KoG-teeworlds/kog-client/releases"));
});

test("a network error is reported without breaking the page", async () => {
  const { nodes } = await runApp({ "update.json": new Error("offline") });
  assert.match(nodes.release.textContent, /Could not load/);
});

test("a server error is reported, a manifest at the second stable path is found", async () => {
  const broken = await runApp({ "update.json": { status: 500, body: "" } });
  assert.match(broken.nodes.release.textContent, /Could not load/);
  const second = await runApp({ "stable/update.json": { body: liveManifest() } });
  assert.match(second.nodes.release.textContent, /Version 1\.2\.3/);
  assert.deepEqual(second.requested.map((r) => r[0]), ["update.json", "stable/update.json"]);
});

test("choosing another channel loads that channel's manifest", async () => {
  const body = liveManifest({ channel: "canary", version: "1.2.3-canary.9" });
  const { nodes, requested } = await runApp({ "canary/update.json": { body } });
  nodes.channel.value = "canary";
  nodes.channel.listeners.change();
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.ok(requested.some(([url]) => url === "canary/update.json"));
  assert.match(nodes.release.textContent, /unstable canary build/);
  nodes.channel.value = "nightly";
  nodes.channel.listeners.change();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.ok(!requested.some(([url]) => /nightly/.test(url)));
});
