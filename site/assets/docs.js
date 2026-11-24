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
    privacy: "privacy/", messages: "architecture/#protocol", repro: "build/#repro", build: "build/", signing: "release-signing/",
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
  var navWide = window.matchMedia ? window.matchMedia("(min-width: 56.25rem)") : null;
  var tocWide = window.matchMedia ? window.matchMedia("(min-width: 87.5rem)") : null;
  var nav = document.querySelector(".nav-toggle");
  var toc = document.querySelector(".toc-toggle");
  var groupsOfNav = document.querySelectorAll(".docs-nav .group");
  function setOpen(node, open) {
    if (!node) return;
    if (open) node.setAttribute("open", "");
    else node.removeAttribute("open");
  }
  function fold() {
    var wideNav = !navWide || navWide.matches;
    setOpen(nav, wideNav);
    // wide: every group is open; narrow: only the group of the current page
    for (var g = 0; g < groupsOfNav.length; g++) {
      setOpen(groupsOfNav[g], wideNav || !!groupsOfNav[g].querySelector('[aria-current="page"]'));
    }
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
})();
