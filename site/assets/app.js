(function () {
  "use strict";

  var Manifest = window.KogManifest;
  var box = document.getElementById("release");
  var side = document.getElementById("build-info");
  if (!Manifest || !box) return;

  var RELEASES_URL = "https://github.com/KoG-teeworlds/kog-client/releases";
  var VERIFY_URL = "technical/verify/";
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
    var radio = document.getElementById("tab-" + os);
    if (radio) radio.checked = true;
    ["windows", "macos", "linux"].forEach(function (id) {
      var label = document.querySelector('.tablist label[for="tab-' + id + '"]');
      if (label) label.classList.toggle("yours", id === os);
    });
  }

  var badge = document.getElementById("build-badge");

  function setBadge(text, kind) {
    if (!badge) return;
    badge.textContent = text;
    badge.className = "state " + kind;
  }

  function copyButton(text, label) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) return null;
    var button = el("button", "Copy", "copy-hash");
    button.setAttribute("type", "button");
    button.setAttribute("aria-label", label);
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(text).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 2000);
      }, function () {
        button.textContent = "Not copied";
      });
    });
    return button;
  }

  function fill(target, nodes) {
    while (target.firstChild) target.removeChild(target.firstChild);
    nodes.forEach(function (node) {
      target.appendChild(node);
    });
  }

  function show(nodes, sideNodes) {
    fill(box, nodes);
    if (side) fill(side, sideNodes || []);
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
    setBadge(warn ? "Unavailable" : "Nothing yet", "planned");
    show([paragraph, more], [el("p", "There is nothing to show here yet. The GitHub releases page always has the newest files.", "small"), link("Open the releases page", RELEASES_URL, "button secondary")]);
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
    var info = [];
    var os = detectOs();
    var mine = null;
    data.packages.forEach(function (item) {
      if (item.id === os) mine = item;
    });
    showInstallFor(os);
    setBadge(KIND[data.channel], data.channel === "stable" ? "built" : "partial");

    if (mine) {
      var main = el("p", "", "main-download");
      main.appendChild(bigButton(mine));
      nodes.push(main);
      nodes.push(el("p", data.version + " \u00b7 " + (mine.size ? Manifest.formatSize(mine.size) : mine.file), "file-line"));
      var row = el("p", "", "other");
      var others = data.packages.filter(function (item) {
        return item !== mine;
      });
      if (others.length > 0) {
        row.appendChild(document.createTextNode("Other systems: "));
        others.forEach(function (item, index) {
          if (index > 0) row.appendChild(document.createTextNode(", "));
          row.appendChild(link(item.label, item.url));
        });
        row.appendChild(document.createTextNode(" \u00b7 "));
      }
      row.appendChild(link("Verify the download", VERIFY_URL));
      nodes.push(row);
    } else {
      nodes.push(el("p", "Choose your system:", "choose-title"));
      var list = el("ul", "", "choose");
      data.packages.forEach(function (item) {
        list.appendChild(choice(item));
      });
      nodes.push(list);
      var verify = el("p", "", "other");
      verify.appendChild(link("Verify the download", VERIFY_URL));
      nodes.push(verify);
    }

    var rows = el("dl", "", "facts");
    function fact(name, value, extra) {
      rows.appendChild(el("dt", name));
      var cell = el("dd", value);
      if (extra) cell.appendChild(extra);
      rows.appendChild(cell);
    }
    fact("Version", data.version);
    fact("Date", Manifest.formatDate(data.issued));
    if (mine) {
      fact("File", mine.file);
      if (mine.size) fact("Size", Manifest.formatSize(mine.size));
    }
    info.push(rows);
    if (mine && mine.sha256) {
      var hash = el("div", "", "hashline");
      hash.appendChild(el("code", mine.sha256, "hash"));
      var copy = copyButton(mine.sha256, "Copy the SHA-256 of " + mine.file);
      if (copy) hash.appendChild(copy);
      info.push(el("p", "SHA-256 of the file:", "small"));
      info.push(hash);
    } else {
      data.packages.filter(function (item) { return item.sha256; }).forEach(function (item) {
        var line = el("div", "", "hashline");
        line.appendChild(el("code", item.file + "  " + item.sha256, "hash"));
        var copy = copyButton(item.sha256, "Copy the SHA-256 of " + item.file);
        if (copy) line.appendChild(copy);
        info.push(line);
      });
    }
    if (fellBack) info.push(el("p", "There is no stable version yet, so this is the newest testing build.", "small"));
    if (data.channel !== "stable") {
      info.push(el("p", "This build is for testing. It can break, and it can change without notice. You can always play with the normal DDNet client.", "warn"));
    }
    if (data.expired) {
      info.push(el("p", "The release information on this page ran out on " + Manifest.formatDate(data.expires) + ", so a newer build may exist. Check the GitHub releases page.", "warn"));
    }
    var how = el("p", "", "small");
    how.appendChild(link("How to check a file", VERIFY_URL));
    how.appendChild(document.createTextNode(". This page does not check signatures itself."));
    info.push(how);
    show(nodes, info);
  }

  function load(channel, tryFallback, fellBack) {
    var mine = ++token;
    show([el("p", "Looking for the newest build…", "empty")], [el("p", "Looking for the newest build…", "small")]);
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

  var command = document.querySelector(".safe-check pre");
  if (command) {
    var copyCommand = copyButton(command.textContent.replace(/\n$/, ""), "Copy the command");
    if (copyCommand) {
      var holder = el("div", "", "codeblock");
      command.parentNode.insertBefore(holder, command);
      holder.appendChild(command);
      copyCommand.className = "copy";
      holder.appendChild(copyCommand);
    }
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
