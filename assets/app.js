(function () {
  "use strict";

  var Manifest = window.KogManifest;
  var box = document.getElementById("build-info");
  if (!Manifest || !box) return;

  var RELEASES_URL = "https://github.com/KoG-teeworlds/kog-client/releases";
  var VERIFY_URL = "technical/verify/";
  var CHANNELS = Manifest.CHANNELS;
  var NAME = { stable: "Stable", canary: "Canary", dev: "Development" };
  var KIND = { stable: "Stable version", canary: "Testing build", dev: "Development build" };
  var badge = document.getElementById("build-badge");
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

  // The chosen channel is remembered on this device only. Storage can be blocked, so every access is guarded.
  function remembered() {
    try {
      var value = window.localStorage.getItem("kog-channel");
      return CHANNELS.indexOf(value) >= 0 ? value : "";
    } catch (error) {
      return "";
    }
  }

  function remember(channel) {
    try {
      window.localStorage.setItem("kog-channel", channel);
    } catch (error) {
      return;
    }
  }

  function choose(channel) {
    var radio = document.getElementById("ch-" + channel);
    if (radio) radio.checked = true;
    var words = document.querySelectorAll(".vchannel");
    for (var i = 0; i < words.length; i++) words[i].textContent = channel;
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

  function setBadge(text, kind) {
    if (!badge) return;
    badge.textContent = text;
    badge.className = "state " + kind;
  }

  function copyButton(text, label, className) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) return null;
    var button = el("button", "Copy", className || "copy-hash");
    button.setAttribute("type", "button");
    button.setAttribute("aria-label", label);
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(typeof text === "function" ? text() : text).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 2000);
      }, function () {
        button.textContent = "Not copied";
      });
    });
    return button;
  }

  function show(nodes) {
    while (box.firstChild) box.removeChild(box.firstChild);
    nodes.forEach(function (node) {
      box.appendChild(node);
    });
  }

  function message(channel, text, offerCanary) {
    var nodes = [el("p", text, "empty")];
    var row = el("p", "", "actions");
    if (offerCanary) {
      var button = el("button", "Show the canary build", "button");
      button.setAttribute("type", "button");
      button.addEventListener("click", function () {
        choose("canary");
        remember("canary");
        load("canary", false);
      });
      row.appendChild(button);
    }
    row.appendChild(link("All builds on GitHub", RELEASES_URL, "button secondary"));
    nodes.push(row);
    setBadge(NAME[channel], "planned");
    show(nodes);
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
    var os = detectOs();
    var mine = null;
    data.packages.forEach(function (item) {
      if (item.id === os) mine = item;
    });
    showInstallFor(os);
    setBadge(KIND[data.channel], data.channel === "stable" ? "built" : "partial");
    var nodes = [];

    var rows = el("dl", "", "facts");
    function fact(name, value) {
      rows.appendChild(el("dt", name));
      rows.appendChild(el("dd", value));
    }
    fact("Version", data.version);
    fact("Date", Manifest.formatDate(data.issued));
    if (mine && mine.size) fact("Size", Manifest.formatSize(mine.size));
    if (mine && mine.id === "macos") fact("Runs on", "Apple Silicon Macs only");
    nodes.push(rows);

    if (mine && mine.sha256) {
      var hash = el("div", "", "hashline");
      hash.appendChild(el("code", mine.sha256, "hash"));
      var copy = copyButton(mine.sha256, "Copy the SHA-256 of " + mine.file);
      if (copy) hash.appendChild(copy);
      nodes.push(el("p", "SHA-256 of " + mine.file, "small"));
      nodes.push(hash);
    }

    if (mine) {
      nodes.push(link("Download for " + mine.label, mine.url, "button big"));
      var others = data.packages.filter(function (item) {
        return item !== mine;
      });
      var row = el("p", "", "other");
      if (others.length > 0) {
        row.appendChild(document.createTextNode("Other systems: "));
        others.forEach(function (item, index) {
          if (index > 0) row.appendChild(document.createTextNode(", "));
          row.appendChild(link(item.label, item.url));
        });
        row.appendChild(document.createTextNode(". "));
      }
      row.appendChild(link("Check the download", VERIFY_URL));
      nodes.push(row);
    } else {
      nodes.push(el("p", "Choose your system:", "choose-title"));
      var list = el("ul", "", "choose");
      data.packages.forEach(function (item) {
        var entry = el("li");
        var button = link("Download for " + item.label, item.url, "button");
        button.appendChild(el("span", item.file + (item.size ? " · " + Manifest.formatSize(item.size) : ""), "file"));
        entry.appendChild(button);
        list.appendChild(entry);
      });
      nodes.push(list);
    }

    if (fellBack) nodes.push(el("p", "There is no stable version yet, so this is the newest testing build.", "small"));
    if (data.channel !== "stable") nodes.push(el("p", "Testing build: it can break and change without notice.", "small"));
    if (data.expired) {
      nodes.push(el("p", "The release information ran out on " + Manifest.formatDate(data.expires) + ", so a newer build may exist. Check the GitHub releases page.", "warn"));
    }
    show(nodes);
  }

  function load(channel, tryFallback, fellBack) {
    var mine = ++token;
    show([el("p", "Looking for the newest build…", "empty")]);
    setBadge(NAME[channel], "planned");
    firstManifest(Manifest.MANIFEST_PATHS[channel])
      .then(function (text) {
        if (mine !== token) return null;
        if (text === null) {
          if (channel === "stable" && tryFallback) {
            choose("canary");
            return load("canary", false, true);
          }
          if (channel === "stable") message(channel, "There is no stable version yet. The first one will appear here. Until then you can try the canary build.", true);
          else if (channel === "dev") message(channel, "Nothing is published on the development channel yet.", false);
          else message(channel, "No canary build has been published yet.", false);
          return null;
        }
        var result = Manifest.parse(text, channel, Math.floor(Date.now() / 1000));
        if (!result.ok) {
          message(channel, result.reason === "clock" ? "The release information looks newer than your device clock. Check your clock, or use the GitHub releases page." : "The release information could not be validated, so it is not shown. Use the GitHub releases page and check what you download.", false);
          return null;
        }
        choose(channel);
        render(result.data, fellBack === true);
        return null;
      })
      .catch(function () {
        if (mine === token) message(channel, "Could not load the release information. Try again later or use the GitHub releases page.", false);
      });
  }

  CHANNELS.forEach(function (channel) {
    var radio = document.getElementById("ch-" + channel);
    if (!radio) return;
    radio.addEventListener("change", function () {
      if (!radio.checked) return;
      remember(channel);
      choose(channel);
      load(channel, false);
    });
  });

  // Copy buttons for the commands that check a download.
  var commands = document.querySelectorAll(".vpanel pre");
  for (var c = 0; c < commands.length; c++) {
    (function (pre) {
      var button = copyButton(function () { return pre.textContent.replace(/\n$/, ""); }, "Copy the command", "copy");
      if (!button) return;
      var holder = el("div", "", "codeblock");
      pre.parentNode.insertBefore(holder, pre);
      holder.appendChild(pre);
      holder.appendChild(button);
    })(commands[c]);
  }

  showInstallFor(detectOs());
  var saved = remembered();
  if (saved) {
    choose(saved);
    load(saved, false);
  } else {
    load("stable", true);
  }
})();
