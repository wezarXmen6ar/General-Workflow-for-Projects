/* ===========================================================================
   "!" markers: every built feature shows where it comes from.

   1. Put data-trace="F-001" on the element that shows a feature
      (several IDs are fine: data-trace="F-001 F-002").
   2. Load trace.css, then chain.js, then this file.
   Markers are added when the page loads. For content added later, call
   initTraceMarkers(element).

   Hovering (or focusing) the "!" shows the item's ID, name, and every path up
   to its objectives. Click to pin, Esc to unpin. The chain data comes from
   chain.js, which workflow/tool.py build generates from the documents.
   =========================================================================== */
(function () {
  var pinned = [];

  function chain() { return window.TRACE_CHAIN || {}; }

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* Every path from an item up to an objective, home parent first. */
  function paths(id, depth) {
    var n = chain()[id];
    if (!n) return [[id + " (not pushed)"]];
    var here = id + " — " + n.name;
    if (n.type === "Objective" || !n.home || depth > 8) return [[here]];
    var out = [];
    [n.home].concat(n.also || []).forEach(function (pid, i) {
      paths(pid, depth + 1).forEach(function (p) {
        out.push([here + (i ? " (also serves)" : "")].concat(p));
      });
    });
    return out;
  }

  function tipHTML(id) {
    var n = chain()[id];
    var h = '<div class="tc-hd"><b>' + esc(id) + "</b> — " +
      (n ? esc(n.name) + ' <span class="tc-ty">(' + esc(n.type) + ")</span>" : "not a pushed item") + "</div>";
    paths(id, 0).forEach(function (p) {
      h += '<div class="tc-row">' + p.map(esc).join(" → ") + "</div>";
    });
    return h;
  }

  function initTraceMarkers(root) {
    (root || document).querySelectorAll("[data-trace]").forEach(function (host) {
      if (host.dataset.traceInit) return;
      host.dataset.traceInit = "1";
      host.classList.add("trace-anchor");

      var ids = host.dataset.trace.split(/\s+/).filter(Boolean);
      var known = ids.every(function (id) { return chain()[id]; });

      var badge = document.createElement("button");
      badge.type = "button";
      badge.className = "trace-badge" + (known ? "" : " unknown");
      badge.textContent = "!";
      badge.setAttribute("aria-label", "Show what this builds toward: " + ids.join(", "));
      host.appendChild(badge);

      var tip = document.createElement("div");
      tip.className = "trace-tip";
      tip.innerHTML = ids.map(tipHTML).join('<div class="tc-sep"></div>');
      host.appendChild(tip);

      var state = { badge: badge, tip: tip, pinned: false };
      function show() {
        tip.style.right = "";
        tip.classList.add("on");
        var over = 8 - tip.getBoundingClientRect().left;   /* keep the tip inside the window */
        if (over > 0) tip.style.right = (-8 - over) + "px";
      }
      function hide() { if (!state.pinned) tip.classList.remove("on"); }
      badge.addEventListener("mouseenter", show);
      badge.addEventListener("mouseleave", hide);
      badge.addEventListener("focus", show);
      badge.addEventListener("blur", hide);
      badge.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        state.pinned = !state.pinned;
        badge.classList.toggle("pin", state.pinned);
        if (state.pinned) { pinned.push(state); show(); } else { hide(); }
      });
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    pinned.forEach(function (s) { s.pinned = false; s.badge.classList.remove("pin"); s.tip.classList.remove("on"); });
    pinned = [];
  });

  window.initTraceMarkers = initTraceMarkers;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initTraceMarkers(document); });
  } else {
    initTraceMarkers(document);
  }
})();
