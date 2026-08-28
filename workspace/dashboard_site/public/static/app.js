/* {{PROJECT_NAME}} dashboard — minimal generic shell.
 *
 * Flow:
 *   1. init Telegram WebApp (if opened inside Telegram)
 *   2. fetch ./api/data through the gate (verified by initData)
 *   3. fall back to window.DEMO_DATA when the gate is unavailable (local dev)
 *   4. render stat tiles + a placeholder section
 *
 * Replace render() with your real UI. The data plumbing (gate + fallback) is
 * the reusable part — keep it.
 */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var INIT_DATA = tg ? tg.initData : "";
  if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function showApp(data) {
    document.getElementById("splash").hidden = true;
    var app = document.getElementById("app");
    app.hidden = false;
    if (data && data.period) document.getElementById("period").textContent = data.period;
    render(data || {});
  }

  function render(data) {
    var root = document.getElementById("content");
    root.innerHTML = "";

    var stats = (data && data.stats) || [];
    if (stats.length) {
      var grid = el("div", "stat-grid");
      stats.forEach(function (s) {
        var card = el("div", "stat");
        card.appendChild(el("div", "stat-value", s.value));
        card.appendChild(el("div", "stat-label", s.label));
        grid.appendChild(card);
      });
      root.appendChild(grid);
    }

    var card = el("div", "card");
    card.appendChild(el("h2", null, "Placeholder"));
    card.appendChild(el("p", "hint",
      "This is the skeleton dashboard. Wire ./api/data to your gate and build "
      + "your UI in app.js render()."));
    root.appendChild(card);
  }

  function boot() {
    fetch("./api/data", { cache: "no-store", headers: { "X-Telegram-Init-Data": INIT_DATA } })
      .then(function (r) { if (!r.ok) throw new Error("gate " + r.status); return r.json(); })
      .then(function (d) { showApp(d); })
      .catch(function () { showApp(window.DEMO_DATA || {}); });
  }

  boot();
})();
