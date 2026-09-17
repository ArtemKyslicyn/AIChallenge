(function () {
  var loaded = {};
  var buttons = document.querySelectorAll(".app-nav [data-view]");
  var viewStatus = document.getElementById("view-status");
  var labels = {
    llm: "LLM board",
    planet: "3D planet",
    parchment: "Strategy board",
    arcs: "Conflict arcs",
    about: "Architecture",
  };
  var panels = {
    llm: document.getElementById("panel-llm"),
    planet: document.getElementById("panel-planet"),
    parchment: document.getElementById("panel-parchment"),
    arcs: document.getElementById("panel-arcs"),
    about: document.getElementById("panel-about"),
  };

  var params = new URLSearchParams(location.search);
  var embed = params.get("embed") === "1";
  if (embed) {
    document.documentElement.classList.add("conflict-embed");
    document.querySelectorAll("[data-embed-hide]").forEach(function (el) {
      el.hidden = true;
    });
  }

  function activateScripts(container) {
    container.querySelectorAll("script").forEach(function (old) {
      var s = document.createElement("script");
      if (old.src) s.src = old.src;
      else s.textContent = old.textContent;
      old.replaceWith(s);
    });
  }

  async function ensure(view) {
    var panel = panels[view];
    if (!panel || view === "about" || loaded[view]) return;
    var src = panel.getAttribute("data-src");
    if (!src) return;
    var res = await fetch(src);
    if (!res.ok) throw new Error("Failed to load " + src);
    panel.innerHTML = await res.text();
    activateScripts(panel);
    loaded[view] = true;
  }

  async function show(view) {
    if (!panels[view]) view = "llm";
    await ensure(view);
    Object.keys(panels).forEach(function (key) {
      var panel = panels[key];
      if (!panel) return;
      panel.hidden = key !== view;
    });
    buttons.forEach(function (btn) {
      var on = btn.getAttribute("data-view") === view;
      if (on) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    if (viewStatus) viewStatus.textContent = "Showing: " + (labels[view] || view);
    try {
      history.replaceState(null, "", location.pathname + location.search + "#" + view);
    } catch (_) {
      /* ignore */
    }
    var panel = panels[view];
    if (panel && typeof panel.focus === "function") {
      try {
        panel.focus({ preventScroll: true });
      } catch (_) {
        panel.focus();
      }
    }
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      show(btn.getAttribute("data-view"));
    });
  });

  window.addEventListener("message", function (ev) {
    var data = ev.data;
    if (!data || typeof data !== "object") return;
    if (data.type === "aichallenge.conflict.show" && data.view) {
      show(String(data.view));
    }
    if (data.type === "aichallenge.conflict.ping") {
      try {
        if (ev.source && typeof ev.source.postMessage === "function") {
          ev.source.postMessage({ type: "aichallenge.conflict.ready" }, ev.origin || "*");
        }
      } catch (_) {
        /* ignore */
      }
    }
  });

  window.__aichallengeConflictHost = { show: show };

  var initial = (location.hash || "#llm").slice(1);
  if (!panels[initial]) initial = "llm";
  show(initial).catch(function (err) {
    console.error(err);
    var panel = panels.llm;
    if (panel) panel.textContent = "Could not load view. Serve over http:// (not file://).";
  });
})();
