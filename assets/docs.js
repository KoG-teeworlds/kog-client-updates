(function () {
  "use strict";

  // Everything here is an addition: the pages work without it.

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  var live = el("p", "", "live");
  live.setAttribute("role", "status");
  document.body.appendChild(live);

  function say(text) {
    live.textContent = "";
    window.setTimeout(function () { live.textContent = text; }, 30);
  }

  function copy(text, done) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) return;
    navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
  }

  // Old links to the single technical page, such as /technical/#verify, go to the page that has the section now.
  var legacy = {
    what: "", status: "", license: "", endpoints: "update-channel/#endpoints", channels: "update-channel/#channels",
    manifest: "update-channel/#manifest", signature: "update-channel/#signature", "client-checks": "update-channel/#client-checks",
    rotation: "update-channel/#rotation", verify: "verify/", "verify-hash": "verify/#verify-hash",
    "verify-attestation": "verify/#verify-attestation", "verify-manifest": "verify/#verify-manifest", login: "login/",
    privacy: "privacy/", messages: "protocol/", repro: "build/#repro", build: "build/", signing: "release-signing/",
    security: "security/", history: "roadmap/#history"
  };
  var overview = document.body.getAttribute("data-overview");
  if (overview !== null && window.location.hash) {
    var wanted = window.location.hash.slice(1);
    if (Object.prototype.hasOwnProperty.call(legacy, wanted) && legacy[wanted]) {
      window.location.replace(overview + legacy[wanted]);
      return;
    }
  }

  // The contents and the table of the page stay open on wide screens and fold on narrow ones.
  var navWide = window.matchMedia ? window.matchMedia("(min-width: 48rem)") : null;
  var tocWide = window.matchMedia ? window.matchMedia("(min-width: 87.5rem)") : null;
  var nav = document.querySelector(".nav-toggle");
  var toc = document.querySelector(".toc-toggle");
  function setOpen(node, open) {
    if (!node) return;
    if (open) node.setAttribute("open", "");
    else node.removeAttribute("open");
  }
  function fold() {
    setOpen(nav, !navWide || navWide.matches);
    setOpen(toc, !tocWide || tocWide.matches);
  }
  fold();
  if (navWide && navWide.addEventListener) navWide.addEventListener("change", fold);
  if (tocWide && tocWide.addEventListener) tocWide.addEventListener("change", fold);

  // Copy buttons on code blocks.
  var blocks = document.querySelectorAll(".doc pre:not(.mermaid-src)");
  for (var b = 0; b < blocks.length; b++) {
    (function (pre) {
      if (!navigator.clipboard) return;
      var holder = el("div", "", "codeblock");
      pre.parentNode.insertBefore(holder, pre);
      holder.appendChild(pre);
      var button = el("button", "Copy", "copy");
      button.type = "button";
      button.setAttribute("aria-label", "Copy this code block");
      button.addEventListener("click", function () {
        copy(pre.textContent.replace(/\n$/, ""), function (ok) {
          button.textContent = ok ? "Copied" : "Not copied";
          say(ok ? "Copied to the clipboard" : "Copying was not possible");
          window.setTimeout(function () { button.textContent = "Copy"; }, 2000);
        });
      });
      holder.appendChild(button);
    })(blocks[b]);
  }

  // Heading links also copy their address.
  var anchors = document.querySelectorAll(".doc .anchor");
  for (var a = 0; a < anchors.length; a++) {
    anchors[a].addEventListener("click", function (event) {
      var url = window.location.href.split("#")[0] + event.currentTarget.getAttribute("href");
      copy(url, function (ok) { if (ok) say("Link copied"); });
    });
  }

  // Scroll spy: the heading of the table of contents that is being read. No scroll handler: the browser tells us
  // when a heading crosses the top band of the screen.
  var links = document.querySelectorAll(".docs-toc a");
  if (links.length && "IntersectionObserver" in window) {
    var byId = {};
    var heads = [];
    for (var l = 0; l < links.length; l++) {
      var id = links[l].getAttribute("href").slice(1);
      var target = document.getElementById(id);
      if (target) {
        byId[id] = links[l];
        heads.push(target);
      }
    }
    var current = null;
    var mark = function (id) {
      if (current === id) return;
      current = id;
      for (var key in byId) {
        if (key === id) {
          byId[key].classList.add("active");
          byId[key].setAttribute("aria-current", "location");
        } else {
          byId[key].classList.remove("active");
          byId[key].removeAttribute("aria-current");
        }
      }
    };
    var visible = {};
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        visible[entry.target.id] = entry.isIntersecting;
      });
      var last = null;
      var above = null;
      heads.forEach(function (head) {
        if (visible[head.id]) last = last || head.id;
        else if (head.getBoundingClientRect().top < 0) above = head.id;
      });
      mark(last || above || (heads[0] && heads[0].id));
    }, { rootMargin: "-80px 0px -70% 0px" });
    heads.forEach(function (head) { spy.observe(head); });
  }

  // Code blocks and tables that need sideways scrolling get a soft edge.
  if ("ResizeObserver" in window) {
    var scrollers = document.querySelectorAll(".doc pre, .doc .table-scroll");
    var watch = new ResizeObserver(function (entries) {
      entries.forEach(function (entry) {
        var node = entry.target;
        node.classList.toggle("is-scrollable", node.scrollWidth > node.clientWidth + 1);
      });
    });
    for (var w = 0; w < scrollers.length; w++) watch.observe(scrollers[w]);
  }

  // Search over the titles and headings of the documentation.
  var box = document.querySelector(".search");
  if (box && window.fetch) {
    var index = null;
    var input = el("input", "");
    input.type = "search";
    input.id = "docs-search";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("placeholder", "Search the documentation");
    var label = el("label", "Search the documentation", "visually-hidden");
    label.setAttribute("for", "docs-search");
    var results = el("ul", "");
    results.setAttribute("aria-label", "Search results");
    var hint = el("p", "", "hint");
    var idle = function () {
      hint.textContent = "";
      hint.appendChild(document.createTextNode("Press "));
      hint.appendChild(el("kbd", "/"));
      hint.appendChild(document.createTextNode(" to search from anywhere"));
    };
    idle();
    box.appendChild(label);
    box.appendChild(input);
    box.appendChild(hint);
    box.appendChild(results);
    box.hidden = false;

    var load = function (then) {
      if (index) return then();
      window.fetch(box.getAttribute("data-index"), { credentials: "omit" })
        .then(function (response) { if (!response.ok) throw new Error("no index"); return response.json(); })
        .then(function (data) { index = data; then(); })
        .catch(function () { box.hidden = true; });
    };

    var show = function () {
      var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      results.textContent = "";
      if (!words.length) { idle(); return; }
      hint.textContent = "";
      var found = [];
      var matches = function (text) {
        text = text.toLowerCase();
        return words.every(function (word) { return text.indexOf(word) !== -1; });
      };
      var base = box.getAttribute("data-index").replace("assets/search-index.json", "");
      for (var p = 0; p < index.length; p++) {
        var page = index[p];
        if (matches(page.t + " " + page.d)) found.push({ href: base + page.u.slice(1), text: page.t });
        for (var h = 0; h < page.h.length; h++) {
          if (matches(page.h[h][1])) found.push({ href: base + page.u.slice(1) + "#" + page.h[h][0], text: page.t + " › " + page.h[h][1] });
        }
      }
      hint.textContent = found.length ? found.length + (found.length === 1 ? " result" : " results") : "Nothing found";
      for (var r = 0; r < found.length && r < 10; r++) {
        var item = el("li", "");
        var link = el("a", found[r].text);
        link.setAttribute("href", found[r].href);
        item.appendChild(link);
        results.appendChild(item);
      }
    };

    document.addEventListener("keydown", function (event) {
      var target = event.target;
      var typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        var nav = document.querySelector(".nav-toggle");
        if (nav) nav.setAttribute("open", "");
        input.focus();
      }
    });
    input.addEventListener("focus", function () { load(function () {}); });
    input.addEventListener("input", function () { load(show); });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { input.value = ""; show(); }
      if (event.key === "Enter") {
        var first = results.querySelector("a");
        if (first) window.location.href = first.getAttribute("href");
      }
    });
  }
})();
