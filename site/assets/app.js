(function () {
  "use strict";

  var Manifest = window.KogManifest;
  var box = document.getElementById("release");
  if (!Manifest || !box) return;

  var RELEASES_URL = "https://github.com/KoG-teeworlds/kog-client/releases";
  var VERIFY_URL = "technical/#verify";
  var select = document.getElementById("channel");
  var unstable = document.getElementById("unstable");
  var token = 0;

  var KIND = { stable: "Stable version", canary: "Testing build", dev: "Development build" };

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

  function fileLine(item) {
    return item.file + (item.size ? " · " + Manifest.formatSize(item.size) : "");
  }

  function bigButton(item) {
    return link("Download for " + item.label, item.url, "button big");
  }

  function choice(item) {
    var entry = el("li");
    var button = link("Download for " + item.label, item.url, "button");
    button.appendChild(el("span", fileLine(item), "file"));
    entry.appendChild(button);
    return entry;
  }

  function showInstallFor(os) {
    if (!os) return;
    ["windows", "macos", "linux"].forEach(function (id) {
      var section = document.getElementById("install-" + id);
      if (section) section.open = id === os;
    });
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
      var button = el("button", "Show testing builds", "button");
      button.setAttribute("type", "button");
      button.addEventListener("click", function () {
        if (select) select.value = "canary";
        load("canary", false);
      });
      more.appendChild(button);
    }
    more.appendChild(link("All builds on GitHub", RELEASES_URL, "button secondary"));
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

  function render(data, fellBack) {
    var nodes = [];
    var os = detectOs();
    var mine = null;
    data.packages.forEach(function (item) {
      if (item.id === os) mine = item;
    });
    showInstallFor(os);

    if (mine) {
      var main = el("p", "", "main-download");
      main.appendChild(bigButton(mine));
      nodes.push(main);
      nodes.push(el("p", fileLine(mine), "file-line"));
      var others = data.packages.filter(function (item) {
        return item !== mine;
      });
      if (others.length > 0) {
        var other = el("p", "Other systems: ", "other");
        others.forEach(function (item, index) {
          if (index > 0) other.appendChild(document.createTextNode(", "));
          other.appendChild(link(item.label, item.url));
        });
        nodes.push(other);
      }
    } else {
      nodes.push(el("p", "Choose your system:", "choose-title"));
      var list = el("ul", "", "choose");
      data.packages.forEach(function (item) {
        list.appendChild(choice(item));
      });
      nodes.push(list);
    }

    var build = el("p", "", "build-line");
    build.appendChild(el("strong", KIND[data.channel] + " " + data.version));
    build.appendChild(document.createTextNode(" from " + Manifest.formatDate(data.issued) + "."));
    nodes.push(build);
    if (fellBack) nodes.push(el("p", "There is no stable version yet, so this is a testing build.", "small"));
    if (data.channel !== "stable") {
      nodes.push(el("p", "This build is for testing. It can break, and it can change without notice. You can always play with the normal DDNet client.", "warn"));
    }
    if (data.expired) {
      nodes.push(el("p", "The release information on this page ran out on " + Manifest.formatDate(data.expires) + ", so a newer build may exist. Check the GitHub releases page.", "warn"));
    }

    var checks = (mine ? [mine] : data.packages).filter(function (item) {
      return item.sha256;
    });
    var details = el("details", "", "check");
    details.appendChild(el("summary", "Check the file (optional)"));
    details.appendChild(el("p", "After the download, you can compare the file with this fingerprint (SHA-256). If it differs, do not open the file.", "small"));
    checks.forEach(function (item) {
      details.appendChild(el("p", item.file, "small"));
      var hash = el("p");
      hash.appendChild(el("code", item.sha256, "hash"));
      details.appendChild(hash);
    });
    var how = el("p", "", "small");
    how.appendChild(link("How to check a file", VERIFY_URL));
    how.appendChild(document.createTextNode(". This page does not check signatures itself."));
    details.appendChild(how);
    nodes.push(details);
    show(nodes);
  }

  function load(channel, tryFallback, fellBack) {
    var mine = ++token;
    show([el("p", "Looking for the newest build…", "empty")]);
    firstManifest(Manifest.MANIFEST_PATHS[channel])
      .then(function (text) {
        if (mine !== token) return null;
        if (text === null) {
          if (channel === "stable" && tryFallback) {
            if (select) select.value = "canary";
            return load("canary", false, true);
          }
          if (channel === "stable") message("There is no stable version yet. The first one will appear here. Until then, you can try a testing build.", false, true);
          else message("No " + KIND[channel].toLowerCase() + " has been published yet.");
          return null;
        }
        var result = Manifest.parse(text, channel, Math.floor(Date.now() / 1000));
        if (!result.ok) {
          message(result.reason === "clock" ? "The release information looks newer than your device clock. Check your clock, or use the GitHub releases page." : "The release information could not be validated, so it is not shown. Use the GitHub releases page and check what you download.", true);
          return null;
        }
        render(result.data, fellBack === true);
        return null;
      })
      .catch(function () {
        if (mine === token) message("Could not load the release information. Try again later or use the GitHub releases page.", true);
      });
  }

  if (unstable) unstable.hidden = false;
  if (select) {
    select.addEventListener("change", function () {
      var channel = select.value;
      if (Manifest.CHANNELS.indexOf(channel) >= 0) load(channel, false);
    });
  }
  load("stable", true);
})();
