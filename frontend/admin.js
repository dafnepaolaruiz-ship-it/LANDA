/* Panel administrativo. Todo dato proveniente del servidor se pinta con textContent (sin interpretar HTML). */
(function () {
  "use strict";

  var m = document.querySelector('meta[name="landa-api-base"]');
  var API = ((m && m.content) || "").replace(/\/$/, "");
  var $ = function (id) { return document.getElementById(id); };

  var S = { csrf: null, role: null, page: 1, pages: 1, filters: {}, auditPage: 1, auditPages: 1, current: null };
  var STATUS = { pending: "Pendiente", confirmed: "Confirmado", cancelled: "Cancelado" };
  var WINDOWS = { "10-12": "10:00 – 12:00", "12-15": "12:00 – 15:00", "15-17": "15:00 – 17:00", "17-19": "17:00 – 19:00", unknown: "Aún no lo sabe" };

  // ---------------------------------------------------------------- DOM helper seguro
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function td(text, cls) { return el("td", { text: text == null ? "" : String(text), "class": cls || "" }); }

  function fmt(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("es-MX", { timeZone: "America/Mexico_City", dateStyle: "medium", timeStyle: "short" });
  }

  // ---------------------------------------------------------------- API
  function api(path, method, body, raw) {
    var headers = {};
    var opts = { method: method || "GET", credentials: "same-origin", headers: headers };
    if (opts.method !== "GET" && S.csrf) headers["X-CSRF-Token"] = S.csrf;
    if (body !== undefined && body !== null) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    return fetch(API + path, opts).then(function (res) {
      if (res.status === 401 && path !== "/api/admin/login" && path !== "/api/admin/me") { showLogin("Tu sesión expiró. Inicia sesión de nuevo."); throw new Error("401"); }
      if (raw && res.ok) return res;
      return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }

  // ---------------------------------------------------------------- vistas
  function showLogin(msg) {
    S.csrf = null;
    $("app-view").hidden = true;
    $("login-view").hidden = false;
    $("login-status").textContent = msg || "";
    $("l-pass").value = "";
    if ($("detail").open) $("detail").close();
    $("l-user").focus();
  }

  function showApp(info) {
    S.csrf = info.csrf_token;
    S.role = info.role;
    $("login-view").hidden = true;
    $("app-view").hidden = false;
    $("who").textContent = info.username + " · " + (info.role === "admin" ? "administración" : "solo lectura");
    var readonly = info.role !== "admin";
    $("btn-export").hidden = readonly;
    $("d-actions").hidden = readonly;
    var b = $("banners");
    clear(b);
    if (!info.event_details_confirmed) b.appendChild(el("div", { "class": "banner", text: "Pendiente: la organizadora aún no confirma fecha, horario y datos del evento (EVENT_DETAILS_CONFIRMED=false)." }));
    if (!info.legal_configured) b.appendChild(el("div", { "class": "banner", text: "Pendiente: faltan los datos legales reales del Aviso de Privacidad (variables PRIVACY_*). No lances la campaña así." }));
    loadStats();
    loadRegistrations();
  }

  // ---------------------------------------------------------------- login
  $("login-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var btn = $("login-btn");
    btn.disabled = true;
    api("/api/admin/login", "POST", { username: $("l-user").value, password: $("l-pass").value })
      .then(function (r) {
        if (r.ok) showApp(r.data);
        else { $("login-status").textContent = r.data.detail || "No fue posible iniciar sesión."; $("l-pass").value = ""; }
      })
      .catch(function () { $("login-status").textContent = "No hay conexión con el servidor."; })
      .then(function () { btn.disabled = false; });
  });

  $("btn-logout").addEventListener("click", function () {
    api("/api/admin/logout", "POST").then(function () { showLogin("Sesión cerrada."); }).catch(function () {});
  });

  // ---------------------------------------------------------------- estadísticas
  function loadStats() {
    api("/api/admin/stats").then(function (r) {
      if (!r.ok) return;
      var d = r.data;
      $("s-total").textContent = d.total_registrations;
      $("s-att").textContent = d.total_attendees;
      $("s-pending").textContent = d.by_status.pending.registrations;
      $("s-confirmed").textContent = d.by_status.confirmed.registrations;
      $("s-cancelled").textContent = d.by_status.cancelled.registrations;
      $("s-criterion").textContent = d.attendees_criterion;
    }).catch(function () {});
  }

  // ---------------------------------------------------------------- registros
  function readFilters() {
    var f = {};
    var q = $("f-q").value.trim();
    if (q) f.q = q;
    if ($("f-status").value) f.status = $("f-status").value;
    if ($("f-from").value) f.date_from = $("f-from").value;
    if ($("f-to").value) f.date_to = $("f-to").value;
    if ($("f-min").value) f.min_attendees = parseInt($("f-min").value, 10);
    if ($("f-max").value) f.max_attendees = parseInt($("f-max").value, 10);
    if ($("f-mkt").value) f.marketing = $("f-mkt").value;
    return f;
  }

  function loadRegistrations() {
    var body = Object.assign({}, S.filters, { page: S.page, page_size: 25 });
    api("/api/admin/registrations/search", "POST", body).then(function (r) {
      if (!r.ok) { $("result-note").textContent = r.data.detail || "No se pudo cargar la lista."; return; }
      var d = r.data;
      S.pages = d.pages;
      var tb = $("tbody");
      clear(tb);
      if (!d.items.length) {
        var row = el("tr", {}, [el("td", { colspan: "9", text: "No hay registros con estos filtros." })]);
        tb.appendChild(row);
      }
      d.items.forEach(function (it) {
        var btn = el("button", { type: "button", "class": "btn btn--small btn--ghost", text: "Ver" });
        btn.addEventListener("click", function () { openDetail(it.folio); });
        var tr = el("tr", {}, [
          td(it.folio, "mono"), td(fmt(it.created_at)), td(it.anonymized ? "(anonimizado)" : it.full_name), td(it.phone || "—"), td(it.email || "—"),
          td(it.attendees, "r"),
          el("td", {}, [el("span", { "class": "pill pill--" + it.status, text: STATUS[it.status] || it.status })]),
          td(it.marketing_allowed ? "Autorizada" : "No"),
          el("td", {}, [btn]),
        ]);
        tb.appendChild(tr);
      });
      $("result-note").textContent = d.total + " registro(s) con los filtros actuales · " + d.filtered_attendees + " asistente(s) (sin cancelados).";
      $("p-info").textContent = "Página " + d.page + " de " + d.pages;
      $("p-prev").disabled = d.page <= 1;
      $("p-next").disabled = d.page >= d.pages;
    }).catch(function () {});
  }

  $("filters").addEventListener("submit", function (ev) { ev.preventDefault(); S.filters = readFilters(); S.page = 1; loadRegistrations(); });
  $("f-clear").addEventListener("click", function () { $("filters").reset(); S.filters = {}; S.page = 1; loadRegistrations(); });
  $("p-prev").addEventListener("click", function () { if (S.page > 1) { S.page--; loadRegistrations(); } });
  $("p-next").addEventListener("click", function () { if (S.page < S.pages) { S.page++; loadRegistrations(); } });

  // ---------------------------------------------------------------- exportación
  $("btn-export").addEventListener("click", function () {
    var btn = this, st = $("export-status");
    btn.disabled = true;
    st.textContent = "Generando archivo…";
    api("/api/admin/export", "POST", S.filters, true)
      .then(function (res) {
        if (res.blob) {
          return res.blob().then(function (blob) {
            var cd = res.headers.get("Content-Disposition") || "";
            var mm = /filename="([^"]+)"/.exec(cd);
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = mm ? mm[1] : "expo-landa-registros.xlsx";
            document.body.appendChild(a);
            a.click();
            setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            st.textContent = "Archivo descargado con los registros que cumplen los filtros actuales (todas las páginas). Contiene datos personales: manéjalo con cuidado y elimínalo cuando ya no lo necesites.";
          });
        }
        st.textContent = (res.data && res.data.detail) || "No se pudo exportar.";
      })
      .catch(function () { st.textContent = "No se pudo exportar."; })
      .then(function () { btn.disabled = false; });
  });

  var syncBtn = $("btn-sharepoint-sync");
  if (syncBtn) {
    syncBtn.addEventListener("click", function () {
      var btn = this, st = $("export-status");
      btn.disabled = true;
      st.textContent = "Sincronizando registros con SharePoint…";
      api("/api/admin/sharepoint/sync", "POST")
        .then(function (r) {
          if (r.ok) {
            st.textContent = "✓ Sincronización exitosa: Archivos REGISTRO_LANDA.xlsx y CSV actualizados en tiempo real para tu carpeta de SharePoint.";
          } else {
            st.textContent = (r.data && r.data.detail) || "No se pudo sincronizar a SharePoint.";
          }
        })
        .catch(function () { st.textContent = "Error de conexión al sincronizar."; })
        .then(function () { btn.disabled = false; });
    });
  }

  // ---------------------------------------------------------------- detalle
  function kv(dl, k, v) { dl.appendChild(el("dt", { text: k })); dl.appendChild(el("dd", { text: v == null || v === "" ? "—" : String(v) })); }

  function renderDetail(d) {
    S.current = d;
    $("d-title").textContent = d.folio;
    var dl = $("d-body");
    clear(dl);
    kv(dl, "Nombre", d.anonymized ? "(anonimizado)" : d.full_name);
    kv(dl, "Teléfono", d.phone); kv(dl, "Correo", d.email);
    kv(dl, "Asistentes", d.attendees);
    kv(dl, "Horario aprox.", WINDOWS[d.arrival_window] || "No indicado");
    kv(dl, "Estado", STATUS[d.status]);
    kv(dl, "Registrado", fmt(d.created_at));
    kv(dl, "Aviso de privacidad", d.privacy_version + " · aceptado " + fmt(d.privacy_accepted_at));
    kv(dl, "Publicidad", d.marketing_allowed ? "Autorizada desde " + fmt(d.marketing_consent_at) + " (texto " + d.marketing_text_version + ")" : (d.marketing_opt_in ? "Revocada " + fmt(d.marketing_revoked_at) : (d.marketing_revoked_at ? "Revocada " + fmt(d.marketing_revoked_at) : "No autorizó")));
    kv(dl, "Fuente de campaña", d.campaign_source);
    if (d.anonymized_at) kv(dl, "Anonimizado", fmt(d.anonymized_at));
    $("d-status").value = d.status;
    $("d-revoke").hidden = !d.marketing_allowed;
    $("d-confirm").value = "";
    $("d-reason").value = "";
    $("d-status-msg").textContent = "";
    $("d-anon").disabled = !!d.anonymized_at;
  }

  function openDetail(folio) {
    api("/api/admin/registrations/" + encodeURIComponent(folio)).then(function (r) {
      if (!r.ok) return;
      renderDetail(r.data);
      if (!$("detail").open) $("detail").showModal();
    }).catch(function () {});
  }
  $("d-close").addEventListener("click", function () { $("detail").close(); });

  function msg(t) { $("d-status-msg").textContent = t; }
  function refreshAll() { loadStats(); loadRegistrations(); }

  $("d-save").addEventListener("click", function () {
    api("/api/admin/registrations/" + encodeURIComponent(S.current.folio) + "/status", "PATCH", { status: $("d-status").value })
      .then(function (r) { if (r.ok) { renderDetail(r.data); msg("Estado guardado."); refreshAll(); } else msg(r.data.detail || "No se pudo guardar."); }).catch(function () {});
  });
  $("d-revoke").addEventListener("click", function () {
    api("/api/admin/registrations/" + encodeURIComponent(S.current.folio) + "/revoke-marketing", "POST")
      .then(function (r) { if (r.ok) { renderDetail(r.data); msg("Baja de publicidad registrada."); refreshAll(); } else msg(r.data.detail || "No se pudo registrar."); }).catch(function () {});
  });
  $("d-anon").addEventListener("click", function () {
    api("/api/admin/registrations/" + encodeURIComponent(S.current.folio) + "/anonymize", "POST", { confirm_folio: $("d-confirm").value, reason: $("d-reason").value || null })
      .then(function (r) { if (r.ok) { renderDetail(r.data); msg("Registro anonimizado."); refreshAll(); } else msg(r.data.detail || "No se pudo anonimizar."); }).catch(function () {});
  });
  $("d-delete").addEventListener("click", function () {
    api("/api/admin/registrations/" + encodeURIComponent(S.current.folio) + "/delete", "POST", { confirm_folio: $("d-confirm").value, reason: $("d-reason").value || null })
      .then(function (r) { if (r.ok) { $("detail").close(); refreshAll(); } else msg(r.data.detail || "No se pudo eliminar."); }).catch(function () {});
  });

  // ---------------------------------------------------------------- bitácora
  var ACTIONS = { login: "Inicio de sesión", login_failed: "Intento fallido", logout: "Cierre de sesión", account_locked: "Cuenta bloqueada", status_changed: "Cambio de estado", marketing_revoked: "Baja de publicidad", anonymized: "Anonimización", deleted: "Eliminación", export_xlsx: "Exportación Excel", password_changed: "Cambio de contraseña", admin_created: "Cuenta creada", password_reset: "Contraseña restablecida", admin_deactivated: "Cuenta desactivada" };

  function loadAudit() {
    api("/api/admin/audit?page=" + S.auditPage).then(function (r) {
      if (!r.ok) return;
      S.auditPages = r.data.pages;
      var tb = $("audit-body");
      clear(tb);
      r.data.items.forEach(function (a) {
        tb.appendChild(el("tr", {}, [td(fmt(a.created_at)), td(a.actor), td(ACTIONS[a.action] || a.action), td(a.folio || "—", "mono"), td(a.detail || "")]));
      });
      $("a-info").textContent = "Página " + r.data.page + " de " + r.data.pages;
      $("a-prev").disabled = r.data.page <= 1;
      $("a-next").disabled = r.data.page >= r.data.pages;
    }).catch(function () {});
  }
  $("a-prev").addEventListener("click", function () { if (S.auditPage > 1) { S.auditPage--; loadAudit(); } });
  $("a-next").addEventListener("click", function () { if (S.auditPage < S.auditPages) { S.auditPage++; loadAudit(); } });

  function tab(which) {
    var reg = which === "reg";
    $("view-reg").hidden = !reg;
    $("view-audit").hidden = reg;
    $("tab-reg").setAttribute("aria-pressed", String(reg));
    $("tab-audit").setAttribute("aria-pressed", String(!reg));
    if (!reg) { S.auditPage = 1; loadAudit(); }
  }
  $("tab-reg").addEventListener("click", function () { tab("reg"); });
  $("tab-audit").addEventListener("click", function () { tab("audit"); });

  // ---------------------------------------------------------------- contraseña
  $("btn-pass").addEventListener("click", function () { $("pw-status").textContent = ""; $("pass-form").reset(); $("pass-dlg").showModal(); });
  $("pw-close").addEventListener("click", function () { $("pass-dlg").close(); });
  $("pass-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    api("/api/admin/change-password", "POST", { current_password: $("pw-cur").value, new_password: $("pw-new").value }).then(function (r) {
      if (r.ok) { S.csrf = r.data.csrf_token; $("pass-form").reset(); $("pw-status").textContent = "Contraseña actualizada. Se cerraron tus otras sesiones."; }
      else $("pw-status").textContent = r.data.detail || "No se pudo cambiar.";
    }).catch(function () {});
  });

  // ---------------------------------------------------------------- arranque
  api("/api/admin/me").then(function (r) {
    if (r.ok) showApp(r.data); else showLogin("");
  }).catch(function () { showLogin(""); });
})();
