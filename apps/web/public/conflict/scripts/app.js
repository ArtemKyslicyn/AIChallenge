(function () {
  var loaded = {};
  var pendingLive = null;
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

  function flushLive() {
    if (!pendingLive) return;
    var board = window.__aichallengeConflictBoard;
    if (board && typeof board.applyLivePatch === "function") {
      try {
        board.applyLivePatch(pendingLive);
      } catch (err) {
        console.error(err);
      }
    }
  }

  function notifyParentReady() {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "aichallenge.conflict.ready" }, "*");
      }
    } catch (_) {
      /* ignore */
    }
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
    // Scripts register __aichallengeConflictBoard synchronously after replace
    flushLive();
    if (view === "llm") notifyParentReady();
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
    flushLive();
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
      show(String(data.view)).then(function () {
        flushLive();
        notifyParentReady();
      });
    }
    if (data.type === "aichallenge.conflict.live") {
      pendingLive = data.patch || {};
      flushLive();
    }
    if (data.type === "aichallenge.conflict.ping") {
      ensure("llm")
        .catch(function () {})
        .then(function () {
          flushLive();
          notifyParentReady();
        });
    }
  });

  window.__aichallengeConflictHost = {
    show: show,
    flushLive: flushLive,
    setPendingLive: function (p) {
      pendingLive = p;
      flushLive();
    },
  };

  window.addEventListener("aichallenge-board-ready", function () {
    flushLive();
    notifyParentReady();
  });

  var initial = (location.hash || "#llm").slice(1);
  if (!panels[initial]) initial = "llm";
  show(initial)
    .then(function () {
      flushLive();
      notifyParentReady();
    })
    .catch(function (err) {
      console.error(err);
      var panel = panels.llm;
      if (panel) panel.textContent = "Could not load view. Serve over http:// (not file://).";
    });
})();
