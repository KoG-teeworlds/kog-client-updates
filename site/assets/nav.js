(function () {
  "use strict";

  // Navigation helpers for every page: the menu that folds on small screens, a search palette (press / or
  // Ctrl+K or Cmd+K) and a button that takes you back to the top. All of it is an addition: the links work without it.

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  // The menu stays open on wide screens and folds on narrow ones.
  var menu = document.querySelector("header.site .menu");
  var wide = window.matchMedia ? window.matchMedia("(min-width: 56.25rem)") : null;
  function foldMenu() {
    if (!menu) return;
    if (!wide || wide.matches) menu.setAttribute("open", "");
    else menu.removeAttribute("open");
  }
  foldMenu();
  if (wide && wide.addEventListener) wide.addEventListener("change", foldMenu);

  // Search palette
  var openers = document.querySelectorAll(".search-open");
  var index = null;
  var loading = null;
  var dialog = null;
  var input = null;
  var list = null;
  var status = null;
  var items = [];
  var selected = -1;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    if (loading) return loading;
    var path = openers.length ? openers[0].getAttribute("data-index") : "";
    loading = window.fetch(path, { credentials: "omit" })
      .then(function (response) { if (!response.ok) throw new Error("no index"); return response.json(); })
      .then(function (data) { index = data; return data; })
      .catch(function () { loading = null; index = []; return index; });
    return loading;
  }

  function matches(text, words) {
    text = text.toLowerCase();
    return words.every(function (word) { return text.indexOf(word) !== -1; });
  }

  function base() {
    return openers.length ? openers[0].getAttribute("data-index").replace("assets/search-index.json", "") : "";
  }

  function link(text, href, className) {
    var item = el("li", "", className);
    var anchor = el("a", text);
    anchor.setAttribute("href", href);
    anchor.setAttribute("role", "option");
    item.appendChild(anchor);
    return item;
  }

  function select(position) {
    if (!items.length) { selected = -1; return; }
    selected = (position + items.length) % items.length;
    items.forEach(function (anchor, i) {
      anchor.setAttribute("aria-selected", i === selected ? "true" : "false");
      anchor.parentNode.classList.toggle("on", i === selected);
    });
    items[selected].scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", items[selected].id);
  }

  function render() {
    var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    while (list.firstChild) list.removeChild(list.firstChild);
    items = [];
    var root = base();
    var shown = 0;
    (index || []).forEach(function (page) {
      var pageHit = !words.length || matches(page.t + " " + page.d, words);
      var heads = [];
      page.h.forEach(function (head) {
        if (words.length && matches(head[1], words)) heads.push(head);
      });
      if (!pageHit && !heads.length) return;
      if (shown >= 24) return;
      list.appendChild(link(page.t, root + page.u.slice(1), "page"));
      shown++;
      heads.slice(0, 5).forEach(function (head) {
        list.appendChild(link(head[1], root + page.u.slice(1) + "#" + head[0], "head"));
        shown++;
      });
    });
    var anchors = list.querySelectorAll("a");
    for (var i = 0; i < anchors.length; i++) {
      anchors[i].id = "hit-" + i;
      items.push(anchors[i]);
    }
    status.textContent = words.length ? (items.length ? items.length + (items.length === 1 ? " result" : " results") : "Nothing found") : "Type to search, or pick a page";
    select(items.length ? 0 : -1);
  }

  function build() {
    dialog = el("dialog", "", "palette");
    dialog.setAttribute("aria-label", "Search");
    var label = el("label", "Search the site", "visually-hidden");
    label.setAttribute("for", "palette-input");
    input = el("input", "");
    input.id = "palette-input";
    input.type = "search";
    input.setAttribute("placeholder", "Search pages and headings");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-controls", "palette-list");
    input.setAttribute("aria-expanded", "true");
    list = el("ul", "", "palette-list");
    list.id = "palette-list";
    list.setAttribute("role", "listbox");
    status = el("p", "", "palette-status");
    status.setAttribute("role", "status");
    var hint = el("p", "Up and down to move, Enter to open, Esc to close", "palette-hint");
    dialog.appendChild(label);
    dialog.appendChild(input);
    dialog.appendChild(list);
    dialog.appendChild(status);
    dialog.appendChild(hint);
    document.body.appendChild(dialog);

    input.addEventListener("input", render);
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); select(selected + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); select(selected - 1); }
      else if (event.key === "Enter" && items[selected]) { event.preventDefault(); window.location.href = items[selected].getAttribute("href"); }
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
  }

  function openPalette() {
    if (!window.HTMLDialogElement) return;
    if (!dialog) build();
    if (!dialog.open) dialog.showModal();
    input.value = "";
    input.focus();
    status.textContent = "Loading the index";
    loadIndex().then(render);
  }

  for (var o = 0; o < openers.length; o++) {
    if (window.HTMLDialogElement && window.fetch) {
      openers[o].hidden = false;
      openers[o].addEventListener("click", openPalette);
    }
  }

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
    var shortcut = (event.key === "k" || event.key === "K") && (event.ctrlKey || event.metaKey);
    if ((event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) || shortcut) {
      if (!window.HTMLDialogElement || !window.fetch) return;
      event.preventDefault();
      openPalette();
    }
  });

  // Back to top: only after you have scrolled. A sentinel at the top tells when it leaves the screen.
  if ("IntersectionObserver" in window) {
    var button = el("button", "", "to-top");
    button.type = "button";
    button.hidden = true;
    button.setAttribute("aria-label", "Back to the top of the page");
    button.appendChild(el("span", "↑"));
    button.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });
    document.body.appendChild(button);
    var sentinel = el("div", "", "top-sentinel");
    sentinel.setAttribute("aria-hidden", "true");
    document.body.appendChild(sentinel);
    new IntersectionObserver(function (entries) {
      button.hidden = entries[0].isIntersecting;
    }, { rootMargin: "400px 0px 0px 0px" }).observe(sentinel);
  }
})();
