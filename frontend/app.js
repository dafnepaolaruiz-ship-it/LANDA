/* EXPO LANDA — comportamiento de la página pública.
   Seguridad: todo contenido dinámico se inserta con textContent (sin interpretar HTML). */
(function () {
  "use strict";

  // ---- Datos del evento (editar aquí si la organizadora cambia algo) ----
  var EVENT = {
    name: "EXPO LANDA",
    start: "20261107T160000Z", // 10:00 a. m. hora de México (UTC-6)
    end: "20261108T010000Z", //  7:00 p. m. hora de México
    place: "Landa Entorno Residencial, Blvd. El Chichimeco, a un minuto del Parque Industrial, Jesús María, Aguascalientes",
    mapsUrl: "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent("Landa Entorno Residencial, Blvd. El Chichimeco, Jesús María, Aguascalientes"),
    whatsapp: "524493481867",
    phoneLabel: "449 348 1867",
  };

  var metaBase = document.querySelector('meta[name="landa-api-base"]');
  var API = ((metaBase && metaBase.content) || "").replace(/\/$/, "");

  var $ = function (id) { return document.getElementById(id); };
  var form = $("reg-form");
  var state = { config: null, token: null, tokenAt: 0, idemKey: null, busy: false, captcha: null, last: null };

  // ---------------------------------------------------------------- utilidades
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(b);
    return Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }

  function api(path, options) {
    options = options || {};
    var opts = { method: options.method || "GET", credentials: "same-origin", headers: {} };
    if (options.body) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(options.body);
    }
    return fetch(API + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }

  function campaign() {
    var p = new URLSearchParams(window.location.search);
    var out = {};
    ["utm_source", "utm_medium", "utm_campaign"].forEach(function (k) {
      var v = p.get(k);
      if (v && /^[A-Za-z0-9_\-.+ ]{1,60}$/.test(v)) out[k] = v;
    });
    return out;
  }

  // ---------------------------------------------------------------- configuración y token
  function loadConfig() {
    return api("/api/config").then(function (r) {
      if (!r.ok) throw new Error("config");
      state.config = r.data;
      var max = r.data.max_attendees || 10;
      $("attendees").max = String(max);
      $("unconfirmed").hidden = !!r.data.event_details_confirmed;
      if (r.data.turnstile_site_key) initCaptcha(r.data.turnstile_site_key);
      return r.data;
    });
  }

  function loadToken(force) {
    var fresh = state.token && Date.now() - state.tokenAt < 5 * 3600 * 1000;
    if (fresh && !force) return Promise.resolve(state.token);
    return api("/api/form-token").then(function (r) {
      if (!r.ok) throw new Error("token");
      state.token = r.data.token;
      state.tokenAt = Date.now();
      return state.token;
    });
  }

  function initCaptcha(siteKey) {
    var box = $("captcha-box");
    var s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = function () {
      box.hidden = false;
      state.captcha = window.turnstile.render(box, { sitekey: siteKey, language: "es", callback: function (t) { state.captchaToken = t; } });
    };
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------- validación (espejo de la del servidor)
  function normalizePhone(raw) {
    var s = raw.trim();
    if (!s || !/^[\d\s\-.()+]+$/.test(s)) return null;
    var d = s.replace(/\D/g, "");
    if (s.charAt(0) === "+") {
      if (d.indexOf("52") !== 0) return null;
      d = d.slice(2);
      if (d.length === 11 && d.charAt(0) === "1") d = d.slice(1);
    } else if ((d.indexOf("044") === 0 || d.indexOf("045") === 0) && d.length === 13) {
      d = d.slice(3);
    } else if (d.indexOf("52") === 0 && (d.length === 12 || d.length === 13)) {
      d = d.slice(2);
      if (d.length === 11 && d.charAt(0) === "1") d = d.slice(1);
    }
    return d.length === 10 && "01".indexOf(d.charAt(0)) === -1 ? d : null;
  }

  function validate() {
    var e = {};
    var name = $("full_name").value.replace(/\s+/g, " ").trim();
    if (name.length < 3 || !/\p{L}/u.test(name)) e.full_name = "Escribe tu nombre completo.";
    if (!normalizePhone($("phone").value)) e.phone = "Escribe un celular mexicano de 10 dígitos, por ejemplo 449 123 4567.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test($("email").value.trim())) e.email = "Escribe un correo electrónico válido, por ejemplo nombre@correo.com.";
    var n = Number($("attendees").value);
    var max = (state.config && state.config.max_attendees) || 10;
    if (!Number.isInteger(n) || n < 1) e.attendees = "Indica al menos 1 asistente (tú).";
    else if (n > max) e.attendees = "Para grupos de más de " + max + " personas, contáctanos directamente.";
    if (!$("privacy_accepted").checked) e.privacy_accepted = "Debes aceptar el Aviso de Privacidad para registrar tu asistencia.";
    return e;
  }

  var ORDER = ["full_name", "phone", "email", "attendees", "privacy_accepted"];

  function showErrors(errors) {
    ORDER.forEach(function (k) {
      var msg = errors[k] || "";
      var out = $("err-" + k);
      if (out) out.textContent = msg;
      var wrap = document.querySelector('[data-field="' + k + '"]');
      if (wrap) wrap.classList.toggle("invalid", !!msg);
      var input = $(k);
      if (input && input.type !== "checkbox") input.setAttribute("aria-invalid", msg ? "true" : "false");
      if (input && input.type === "checkbox") input.setAttribute("aria-invalid", msg ? "true" : "false");
    });
    var first = ORDER.filter(function (k) { return errors[k]; })[0];
    if (first) $(first).focus();
  }

  function setStatus(msg) { $("form-status").textContent = msg || ""; }

  // ---------------------------------------------------------------- stepper
  function clampAttendees(delta) {
    var el = $("attendees");
    var max = Number(el.max) || 10;
    var v = parseInt(el.value, 10);
    if (isNaN(v)) v = 1;
    el.value = String(Math.min(max, Math.max(1, v + delta)));
  }
  $("att-minus").addEventListener("click", function () { clampAttendees(-1); });
  $("att-plus").addEventListener("click", function () { clampAttendees(1); });

  // ---------------------------------------------------------------- envío
  function setBusy(b) {
    state.busy = b;
    $("submit-btn").disabled = b;
    $("submit-btn").setAttribute("aria-busy", b ? "true" : "false");
    $("submit-label").textContent = b ? "Enviando…" : "Confirmar mi asistencia";
  }

  function buildPayload() {
    var c = campaign();
    var marketing = $("marketing_opt_in").checked;
    var p = {
      full_name: $("full_name").value.replace(/\s+/g, " ").trim(),
      phone: $("phone").value.trim(),
      email: $("email").value.trim(),
      attendees: parseInt($("attendees").value, 10),
      arrival_window: $("arrival_window").value || null,
      privacy_accepted: $("privacy_accepted").checked,
      privacy_version: state.config.privacy_version,
      marketing_opt_in: marketing,
      marketing_text_version: marketing ? state.config.marketing_text_version : null,
      form_token: state.token,
      idempotency_key: state.idemKey,
      website: $("website").value,
      captcha_token: state.captchaToken || null,
    };
    Object.keys(c).forEach(function (k) { p[k] = c[k]; });
    return p;
  }

  var NOT_SAVED = "Tu registro todavía NO se ha confirmado. Puedes intentarlo de nuevo con el mismo botón; no se duplicará.";

  function onSubmit(ev) {
    ev.preventDefault();
    if (state.busy) return; // protección contra doble clic
    setStatus("");
    var errors = validate();
    showErrors(errors);
    if (Object.keys(errors).length) return;

    setBusy(true);
    if (!state.idemKey) state.idemKey = uuid(); // se conserva en reintentos
    Promise.resolve(state.config || loadConfig())
      .then(function () { return loadToken(false); })
      .then(function () { return api("/api/registrations", { method: "POST", body: buildPayload() }); })
      .then(function (r) {
        if (r.ok && r.data && r.data.folio) return success(r.data);
        if (r.status === 422 && r.data.errors) {
          var map = {};
          Object.keys(r.data.errors).forEach(function (k) { if (ORDER.indexOf(k) !== -1) map[k] = r.data.errors[k]; });
          showErrors(map);
          setStatus(Object.keys(map).length ? "Revisa los campos marcados." : "Algún dato no es válido. " + NOT_SAVED);
        } else if (r.status === 400 && state.token) {
          state.token = null; // token vencido o inválido: se renueva en el siguiente intento
          setStatus((r.data.detail || "La sesión del formulario expiró.") + " " + NOT_SAVED);
          if (state.captcha !== null && window.turnstile) { state.captchaToken = null; window.turnstile.reset(); }
        } else if (r.status === 409) {
          setStatus(r.data.detail + " Tus datos no se han enviado.");
        } else if (r.status === 429) {
          setStatus((r.data.detail || "Demasiados intentos.") + " " + NOT_SAVED);
          state.token = null;
        } else {
          setStatus("No pudimos guardar tu registro por un problema temporal. " + NOT_SAVED);
        }
      })
      .catch(function () {
        setStatus("No hay conexión con el servidor. " + NOT_SAVED);
      })
      .then(function () { setBusy(false); });
  }
  form.addEventListener("submit", onSubmit);

  // ---------------------------------------------------------------- confirmación
  function success(data) {
    var name = $("full_name").value.replace(/\s+/g, " ").trim();
    state.last = { folio: data.folio, attendees: data.attendees };
    $("c-folio").textContent = data.folio;
    $("c-attendees").textContent = data.attendees + (data.attendees === 1 ? " persona" : " personas");
    $("c-name").textContent = name;
    $("c-contact").textContent = $("phone").value.trim() + " · " + $("email").value.trim();
    $("c-maps").href = EVENT.mapsUrl;
    $("c-wa").href = "https://wa.me/" + EVENT.whatsapp + "?text=" + encodeURIComponent("Hola Mayte, me registré en la EXPO LANDA. Mi folio es " + data.folio + ".");
    form.hidden = true;
    $("confirm").hidden = false;
    state.idemKey = null;
    state.token = null;
    $("panel").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    $("confirm").focus({ preventScroll: true });
  }

  $("copy-folio").addEventListener("click", function () {
    var btn = this, text = $("c-folio").textContent;
    function done() { btn.textContent = "¡Folio copiado!"; setTimeout(function () { btn.textContent = "Copiar folio"; }, 2200); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else fallback();
    function fallback() {
      var r = document.createRange();
      r.selectNodeContents($("c-folio"));
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      try { document.execCommand("copy"); done(); } catch (e) { /* el folio queda seleccionado para copiar a mano */ }
    }
  });

  function icsEscape(s) { return s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n"); }

  $("add-calendar").addEventListener("click", function () {
    var folio = state.last ? state.last.folio : "";
    var inApp = /FBAN|FBAV|Instagram/i.test(navigator.userAgent); // los navegadores integrados no siempre descargan archivos
    if (inApp) {
      var g = "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + encodeURIComponent(EVENT.name) +
        "&dates=" + EVENT.start + "/" + EVENT.end + "&location=" + encodeURIComponent(EVENT.place) +
        "&details=" + encodeURIComponent("Entrada gratuita. Folio de registro: " + folio);
      window.open(g, "_blank", "noopener");
      return;
    }
    var lines = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EXPO LANDA//ES", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
      "UID:" + uuid() + "@expolanda", "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, ""),
      "DTSTART:" + EVENT.start, "DTEND:" + EVENT.end, "SUMMARY:" + icsEscape(EVENT.name),
      "LOCATION:" + icsEscape(EVENT.place),
      "DESCRIPTION:" + icsEscape("Entrada gratuita. Folio de registro: " + folio + ". Contacto: Mayte Ramírez " + EVENT.phoneLabel + "."),
      "END:VEVENT", "END:VCALENDAR",
    ];
    var blob = new Blob([lines.join("\r\n")], { type: "text/calendar;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "expo-landa.ics";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  });

  $("new-registration").addEventListener("click", function () {
    form.reset();
    $("attendees").value = "1";
    showErrors({});
    setStatus("");
    $("confirm").hidden = true;
    form.hidden = false;
    state.last = null;
    loadToken(true).catch(function () {});
    $("full_name").focus();
  });

  // limpiar el error de un campo al corregirlo
  ["full_name", "phone", "email", "attendees", "privacy_accepted"].forEach(function (k) {
    $(k).addEventListener("input", function () {
      var wrap = document.querySelector('[data-field="' + k + '"]');
      if (wrap) wrap.classList.remove("invalid");
      var out = $("err-" + k);
      if (out) out.textContent = "";
    });
  });

  // ---------------------------------------------------------------- revelado al hacer scroll
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  // ---------------------------------------------------------------- cuenta regresiva y progreso de lectura
  var cd = { d: $("cd-d"), h: $("cd-h"), m: $("cd-m"), s: $("cd-s") };
  if (cd.d) {
    var target = Date.parse("2026-11-07T10:00:00-06:00");
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var tick = function () {
      var diff = Math.max(0, target - Date.now());
      if (diff === 0 && $("countdown")) { $("countdown").hidden = true; return; }
      var s = Math.floor(diff / 1000);
      cd.d.textContent = Math.floor(s / 86400);
      cd.h.textContent = pad(Math.floor((s % 86400) / 3600));
      cd.m.textContent = pad(Math.floor((s % 3600) / 60));
      cd.s.textContent = pad(s % 60);
    };
    tick();
    setInterval(tick, 1000);
  }
  var prog = $("scroll-progress");
  if (prog) {
    var updProg = function () {
      var max = document.documentElement.scrollHeight - window.innerHeight;
      prog.style.transform = "scaleX(" + (max > 0 ? Math.min(1, window.scrollY / max) : 0) + ")";
    };
    window.addEventListener("scroll", updProg, { passive: true });
    updProg();
  }

  // ---------------------------------------------------------------- barra fija móvil y cabecera
  var sticky = $("sticky-cta");
  var panelEl = $("panel");
  if (sticky && panelEl && "IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      sticky.classList.toggle("show", !entries[0].isIntersecting);
    }, { threshold: 0.05 }).observe(panelEl);
  }
  var header = document.querySelector(".site-header");
  if (header) {
    var onScroll = function () { header.classList.toggle("is-scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ---------------------------------------------------------------- navegación suave al formulario
  document.querySelectorAll('a[href="#registro"]').forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var target = $("registro") || $("panel") || $("reg-form");
      if (target) {
        var headerHeight = 72;
        var elementPos = target.getBoundingClientRect().top + window.pageYOffset;
        window.scrollTo({
          top: Math.max(0, elementPos - headerHeight),
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
        });
        var fn = $("full_name");
        if (fn) {
          setTimeout(function () {
            try { fn.focus({ preventScroll: true }); } catch (_) {}
          }, 600);
        }
      }
    });
  });

  // ---------------------------------------------------------------- arranque
  loadConfig().catch(function () { /* se reintenta al enviar */ });
  loadToken(false).catch(function () { /* se reintenta al enviar */ });
})();
