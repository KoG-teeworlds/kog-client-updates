(function () {
  "use strict";

  var Manifest = window.KogManifest;
  var box = document.getElementById("release");
  if (!Manifest || !box) return;

  var RELEASES_URL = "https://github.com/KoG-teeworlds/kog-client/releases";
  var VERIFY_URL = "verify/";
  var select = document.getElementById("channel");
  var unstable = document.getElementById("unstable");
  var token = 0;

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function link(text, href, className) {
    var node = el("a", text, className);
    node.setAttribute("href", href);
    node.setAttribute("rel", "noopener");
    return node;
  }

  function detectOs() {
    if (typeof navigator === "undefined") return "";
    var ua = String((navigator.userAgentData && navigator.userAgentData.platform) || "") + " " + String(navigator.userAgent || "");
    if (/android|iphone|ipad|ipod|cros/i.test(ua)) return "";
    if (/windows|win32|win64/i.test(ua)) return "windows";
    if (/macintosh|mac os|macintel|macos/i.test(ua)) return "macos";
    if (/linux|x11/i.test(ua)) return "linux";
    return "";
  }

  var CHECKS = {
    windows: function (file, sha) {
      return '(Get-FileHash .\\' + file + ' -Algorithm SHA256).Hash -eq "' + sha + '"';
    },
    macos: function (file, sha) {
      return 'echo "' + sha + '  ' + file + '" | shasum -a 256 -c';
    },
    linux: function (file, sha) {
      return 'echo "' + sha + '  ' + file + '" | sha256sum -c';
    },
  };

  function card(item, os, anyMatch) {
    var mine = item.id === os;
    var entry = el("li", "", "platform" + (mine ? " recommended" : ""));
    var head = el("div", "", "platform-head");
    head.appendChild(el("h3", item.label));
    if (mine) head.appendChild(el("span", "Your system", "badge"));
    entry.appendChild(head);
    var meta = item.file + (item.size ? " \u00b7 " + Manifest.formatSize(item.size) : "");
    entry.appendChild(el("p", meta, "file"));
    var primary = mine || !anyMatch;
    entry.appendChild(link("Download for " + item.label, item.url, "button" + (primary ? "" : " secondary")));
    if (item.sha256) {
      var details = el("details", "", "check");
      details.appendChild(el("summary", "SHA-256 and check command"));
      var hash = el("p");
      hash.appendChild(el("code", item.sha256, "hash"));
      details.appendChild(hash);
      details.appendChild(el("p", "Run this in the folder of the download. It prints True (PowerShell) or OK if the file matches:", "small"));
      var pre = el("pre");
      pre.appendChild(el("code", CHECKS[item.id](item.file, item.sha256)));
      details.appendChild(pre);
      entry.appendChild(details);
    } else {
      entry.appendChild(el("p", "This release lists no hash for this file. Verify it with the GitHub attestation.", "small"));
    }
    return entry;
  }

  function show(nodes) {
    while (box.firstChild) box.removeChild(box.firstChild);
    nodes.forEach(function (node) {
      box.appendChild(node);
    });
  }

  function message(text, warn, offerCanary) {
    var paragraph = el("p", text, warn ? "warn" : "empty");
    var more = el("p");
    if (offerCanary) {
      var button = el("button", "Show canary builds", "button");
      button.setAttribute("type", "button");
      button.addEventListener("click", function () {
        if (select) select.value = "canary";
        load("canary");
      });
      more.appendChild(button);
    }
    more.appendChild(link("Releases on GitHub", RELEASES_URL, "button secondary"));
    show([paragraph, more]);
  }

  function fetchText(path) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, 10000);
    return fetch(path, { cache: "no-cache", credentials: "omit", referrerPolicy: "no-referrer", signal: controller.signal })
      .then(function (response) {
        clearTimeout(timer);
        if (response.status === 404) return null;
        if (!response.ok) throw new Error("http");
        return response.text();
      })
      .catch(function (error) {
        clearTimeout(timer);
        throw error;
      });
  }

  function firstManifest(paths) {
    var index = 0;
    function next() {
      if (index >= paths.length) return Promise.resolve(null);
      return fetchText(paths[index++]).then(function (text) {
        return text === null ? next() : text;
      });
    }
    return next();
  }

  function render(data) {
    var nodes = [];
    var summary = el("p", "", "release-line");
    summary.appendChild(el("strong", "Version " + data.version));
    summary.appendChild(document.createTextNode(" (" + data.channel + "), published " + Manifest.formatDate(data.issued) + ", release information valid until " + Manifest.formatDate(data.expires) + "."));
    nodes.push(summary);
    if (data.expired) {
      nodes.push(el("p", "This release information expired on " + Manifest.formatDate(data.expires) + ". The page may be out of date. Check the GitHub releases page.", "warn"));
    }
    if (data.channel !== "stable") {
      nodes.push(el("p", "This is an unstable " + data.channel + " build. It can break, and it may need a clean reinstall of the stable version.", "warn"));
    }

    var os = detectOs();
    var anyMatch = data.packages.some(function (item) {
      return item.id === os;
    });
    var list = el("ul", "", "platforms");
    data.packages.forEach(function (item) {
      list.appendChild(card(item, os, anyMatch));
    });
    nodes.push(list);
    nodes.push(el("p", "Android and iOS: not available.", "small"));

    var signed = el("p", "", "small");
    signed.appendChild(document.createTextNode("Signed manifest of this channel: "));
    signed.appendChild(link("update.json", data.channel + "/update.json"));
    signed.appendChild(document.createTextNode(" and "));
    signed.appendChild(link("update.json.sig", data.channel + "/update.json.sig"));
    signed.appendChild(document.createTextNode(". "));
    signed.appendChild(link("How to verify a download", VERIFY_URL));
    signed.appendChild(document.createTextNode(". This page does not check signatures itself."));
    nodes.push(signed);

    if (data.files.length > 0) {
      var details = el("details");
      details.appendChild(el("summary", "Signed file hashes (what the in-app updater downloads)"));
      var scroll = el("div", "", "table-scroll");
      var table = el("table");
      var head = el("tr");
      ["Platform", "Size", "SHA-256"].forEach(function (name) {
        head.appendChild(el("th", name));
      });
      table.appendChild(head);
      data.files.forEach(function (file) {
        var row = el("tr");
        row.appendChild(el("td", file.label));
        row.appendChild(el("td", Manifest.formatSize(file.size)));
        var cell = el("td");
        cell.appendChild(el("code", file.sha256, "hash"));
        row.appendChild(cell);
        table.appendChild(row);
      });
      scroll.appendChild(table);
      details.appendChild(scroll);
      nodes.push(details);
    }
    show(nodes);
  }

  function load(channel) {
    var mine = ++token;
    show([el("p", "Looking for the latest " + channel + " release…")]);
    firstManifest(Manifest.MANIFEST_PATHS[channel])
      .then(function (text) {
        if (mine !== token) return;
        if (text === null) {
          if (channel === "stable") message("No stable release has been published yet. The first one will appear here. Until then, testers can try the canary channel.", false, true);
          else message("No " + channel + " release has been published yet.");
          return;
        }
        var result = Manifest.parse(text, channel, Math.floor(Date.now() / 1000));
        if (!result.ok) {
          message(result.reason === "clock" ? "The release information looks newer than your device clock. Check your clock, or use the GitHub releases page." : "The release information could not be validated, so it is not shown. Use the GitHub releases page and verify what you download.", true);
          return;
        }
        render(result.data);
      })
      .catch(function () {
        if (mine === token) message("Could not load the release information. Try again later or use the GitHub releases page.", true);
      });
  }

  if (unstable) unstable.hidden = false;
  if (select) {
    select.addEventListener("change", function () {
      var channel = select.value;
      if (Manifest.CHANNELS.indexOf(channel) >= 0) load(channel);
    });
  }
  load("stable");
})();
