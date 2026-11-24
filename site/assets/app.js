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

  function show(nodes) {
    while (box.firstChild) box.removeChild(box.firstChild);
    nodes.forEach(function (node) {
      box.appendChild(node);
    });
  }

  function message(text, warn) {
    var paragraph = el("p", text, warn ? "warn" : "");
    var more = el("p");
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
    var summary = "Version " + data.version + " (" + data.channel + "), published " + Manifest.formatDate(data.issued) + ", release information valid until " + Manifest.formatDate(data.expires) + ".";
    nodes.push(el("p", summary));
    if (data.expired) {
      nodes.push(el("p", "This release information expired on " + Manifest.formatDate(data.expires) + ". The page may be out of date. Check the GitHub releases page.", "warn"));
    }
    if (data.channel !== "stable") {
      nodes.push(el("p", "This is an unstable " + data.channel + " build. It can break, and it may need a clean reinstall of the stable version.", "warn"));
    }

    var list = el("ul", "", "downloads");
    data.packages.forEach(function (item) {
      var entry = el("li");
      entry.appendChild(link("Download for " + item.label, item.url, "button"));
      list.appendChild(entry);
    });
    nodes.push(list);
    nodes.push(el("p", "Android and iOS: not available."));

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
        cell.appendChild(el("code", file.sha256));
        row.appendChild(cell);
        table.appendChild(row);
      });
      scroll.appendChild(table);
      details.appendChild(scroll);
      nodes.push(details);
    }

    var verify = el("p", "This page does not check signatures itself. ");
    verify.appendChild(link("How to verify a download", VERIFY_URL));
    verify.appendChild(document.createTextNode("."));
    nodes.push(verify);
    show(nodes);
  }

  function load(channel) {
    var mine = ++token;
    show([el("p", "Looking for the latest " + channel + " release…")]);
    firstManifest(Manifest.MANIFEST_PATHS[channel])
      .then(function (text) {
        if (mine !== token) return;
        if (text === null) {
          message("No " + channel + " release has been published yet.");
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
