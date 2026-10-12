/* Páginas legales: rellena los datos del responsable desde /api/config y gestiona la baja de publicidad. */
(function () {
  "use strict";
  var m = document.querySelector('meta[name="landa-api-base"]');
  var API = ((m && m.content) || "").replace(/\/$/, "");

  function mark(el, text) {
    el.textContent = text;
    if (/POR CONFIGURAR/.test(text)) el.classList.add("pending");
  }

  fetch(API + "/api/config", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      var p = cfg.privacy || {};
      document.querySelectorAll("[data-legal]").forEach(function (el) {
        var k = el.getAttribute("data-legal");
        if (k === "privacy_version") return mark(el, cfg.privacy_version || "");
        if (k === "transfers_text_or_none") {
          return mark(el, p.transfers_text || "Por regla general no realizamos transferencias de tus datos personales a terceros. Si en el futuro fueran necesarias, se informarán en este aviso y se solicitará el consentimiento cuando la ley lo exija.");
        }
        mark(el, p[k] || "");
      });
      var banner = document.getElementById("draft-banner");
      if (banner) banner.hidden = !!p.legal_configured;
    })
    .catch(function () { /* sin conexión: se muestran los marcadores por defecto */ });

  var form = document.getElementById("revoke-form");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var status = document.getElementById("r-status");
      var btn = document.getElementById("r-btn");
      var folio = document.getElementById("r-folio").value.trim();
      var email = document.getElementById("r-email").value.trim();
      if (!folio || !email) { status.textContent = "Escribe tu folio y tu correo electrónico."; return; }
      btn.disabled = true;
      fetch(API + "/api/marketing-revocation", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folio: folio, email: email }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (r) { status.textContent = r.ok ? r.d.message : (r.d.detail || "No pudimos procesar tu solicitud. Inténtalo más tarde."); })
        .catch(function () { status.textContent = "No hay conexión. Inténtalo de nuevo."; })
        .then(function () { btn.disabled = false; });
    });
  }
})();
