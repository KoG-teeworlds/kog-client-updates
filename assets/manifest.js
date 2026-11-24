(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.KogManifest = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var REPO_PATH = "/KoG-teeworlds/kog-client/releases/download/";
  var MAX_TEXT = 4 * 1024 * 1024;
  var MAX_VALIDITY = 90 * 86400;
  var FUTURE_SLACK = 2 * 86400;
  var MAX_SIZE = 2147483647;
  var VERSION = /^\d{1,4}\.\d{1,4}\.\d{1,4}(-(canary|dev)\.\d{1,9})?$/;
  var SHA256 = /^[0-9a-f]{64}$/;

  var CHANNELS = ["stable", "canary", "dev"];
  var MANIFEST_PATHS = {
    stable: ["update.json", "stable/update.json"],
    canary: ["canary/update.json"],
    dev: ["dev/update.json"],
  };
  var PLATFORMS = [
    { id: "win64", label: "Windows (64-bit)" },
    { id: "linux-x86_64", label: "Linux (64-bit)" },
  ];
  var PACKAGES = [
    { id: "windows", label: "Windows", file: "KoG-Client-windows.zip" },
    { id: "linux", label: "Linux", file: "KoG-Client-linux.tar.xz" },
    { id: "macos", label: "macOS", file: "KoG-Client-macOS.dmg" },
  ];

  function own(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function isInt(value, min, max) {
    return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
  }

  function allowedUrl(value) {
    if (typeof value !== "string" || value.length === 0 || value.length > 300) return null;
    if (/[\u0000- \u007f\\]/.test(value)) return null;
    var url;
    try {
      url = new URL(value);
    } catch (error) {
      return null;
    }
    if (url.protocol !== "https:" || url.username !== "" || url.password !== "") return null;
    if (url.port !== "" || url.search !== "" || url.hash !== "") return null;
    if (/%2f|%5c/i.test(url.pathname)) return null;
    var onGithub = url.hostname === "github.com" && url.pathname.indexOf(REPO_PATH) === 0 && url.pathname.length > REPO_PATH.length;
    var onSite = url.hostname === "client.kog.tw" && url.pathname.length > 1;
    return onGithub || onSite ? url.href : null;
  }

  function packageLinks(version, listed) {
    if (typeof version !== "string" || !VERSION.test(version)) return [];
    var byName = {};
    if (Array.isArray(listed)) {
      listed.forEach(function (entry) {
        if (entry !== null && typeof entry === "object" && typeof entry.name === "string" && !own(byName, entry.name)) byName[entry.name] = entry;
      });
    }
    var links = [];
    PACKAGES.forEach(function (item) {
      var entry = own(byName, item.file) ? byName[item.file] : null;
      var url = entry ? allowedUrl(entry.url) : null;
      var sha256 = null;
      var size = null;
      if (url && typeof entry.sha256 === "string" && SHA256.test(entry.sha256) && isInt(entry.size, 1, MAX_SIZE)) {
        sha256 = entry.sha256;
        size = entry.size;
      } else {
        url = allowedUrl("https://github.com" + REPO_PATH + "v" + version + "/" + item.file);
      }
      if (url) links.push({ id: item.id, label: item.label, file: item.file, url: url, sha256: sha256, size: size });
    });
    return links;
  }

  function parse(text, channel, now) {
    if (CHANNELS.indexOf(channel) < 0) return { ok: false, reason: "invalid" };
    if (typeof text !== "string" || text.length === 0 || text.length > MAX_TEXT) return { ok: false, reason: "invalid" };
    var manifest;
    try {
      manifest = JSON.parse(text);
    } catch (error) {
      return { ok: false, reason: "invalid" };
    }
    if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) return { ok: false, reason: "invalid" };
    if (manifest.format !== 2) return { ok: false, reason: "invalid" };
    if (own(manifest, "channel") && manifest.channel !== channel) return { ok: false, reason: "channel" };
    if (typeof manifest.version !== "string" || !VERSION.test(manifest.version)) return { ok: false, reason: "invalid" };
    if (!isInt(manifest.issued, 1, 4102444800) || !isInt(manifest.expires, 1, 4102444800)) return { ok: false, reason: "invalid" };
    if (manifest.issued >= manifest.expires || manifest.expires > manifest.issued + MAX_VALIDITY) return { ok: false, reason: "invalid" };
    if (manifest.issued > now + FUTURE_SLACK) return { ok: false, reason: "clock" };

    var files = [];
    var platforms = manifest.platforms;
    if (platforms !== null && typeof platforms === "object" && !Array.isArray(platforms)) {
      PLATFORMS.forEach(function (platform) {
        if (!own(platforms, platform.id)) return;
        var entry = platforms[platform.id];
        var client = entry !== null && typeof entry === "object" ? entry.client : null;
        if (client === null || typeof client !== "object") return;
        var url = allowedUrl(client.url);
        if (!url || typeof client.sha256 !== "string" || !SHA256.test(client.sha256) || !isInt(client.size, 1, MAX_SIZE)) return;
        files.push({ id: platform.id, label: platform.label, sha256: client.sha256, size: client.size, url: url });
      });
    }

    return {
      ok: true,
      data: {
        version: manifest.version,
        channel: channel,
        issued: manifest.issued,
        expires: manifest.expires,
        expired: now >= manifest.expires,
        packages: packageLinks(manifest.version, manifest.packages),
        files: files,
      },
    };
  }

  function formatDate(seconds) {
    if (!isInt(seconds, 0, 4102444800)) return "";
    return new Date(seconds * 1000).toISOString().slice(0, 10);
  }

  function formatSize(bytes) {
    if (!isInt(bytes, 0, MAX_SIZE)) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KiB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MiB";
  }

  return {
    CHANNELS: CHANNELS,
    MANIFEST_PATHS: MANIFEST_PATHS,
    MAX_TEXT: MAX_TEXT,
    allowedUrl: allowedUrl,
    packageLinks: packageLinks,
    parse: parse,
    formatDate: formatDate,
    formatSize: formatSize,
  };
});
