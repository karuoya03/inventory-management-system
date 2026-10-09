/* Shared helpers: API fetch wrapper, CSRF handling, header behavior. */
(function () {
  "use strict";

  function getCookie(name) {
    const match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/[-.+*]/g, "\\$&") + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : null;
  }

  async function apiFetch(path, options) {
    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    headers.set("Accept", "application/json");

    const method = (opts.method || "GET").toUpperCase();

    if (opts.body && !headers.has("Content-Type") && typeof opts.body === "string") {
      headers.set("Content-Type", "application/json");
    }

    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrf = getCookie("ims_csrf");
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }

    return fetch(path, {
      method: method,
      headers: headers,
      body: opts.body,
      credentials: "same-origin",
    });
  }

  async function parseJson(response) {
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (err) {
      return null;
    }
  }

  function errorMessage(response, body) {
    if (body && Array.isArray(body.errors) && body.errors.length) {
      return body.errors.join(" ");
    }
    if (body && typeof body.detail === "string" && body.detail !== "Validation failed.") {
      return body.detail;
    }
    if (response.status === 401) return "You are signed out. Please sign in again.";
    if (response.status === 403) return "You do not have permission to do that.";
    if (response.status === 409) return "That username or email is already in use.";
    if (response.status === 429) return "Too many requests. Please wait a moment and try again.";
    if (response.status >= 500) return "Something went wrong on the server. Try again shortly.";
    return "Request failed (" + response.status + ").";
  }

  async function logout() {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (err) {
      /* Ignore — we are leaving anyway. */
    }
    window.location.href = "/login";
  }

  async function loadCurrentUser() {
    // Never run the auth check on the sign-in page itself. A 401 here would
    // redirect to /login while already on /login — an infinite reload loop.
    if (window.location.pathname === "/login") {
      return;
    }

    const el = document.querySelector("[data-user-name]");

    try {
      const res = await apiFetch("/api/auth/me");

      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) return;

      const user = await parseJson(res);
      if (!user) return;

      if (el) el.textContent = user.full_name || user.username || "";
      document.body.dataset.userRole = user.role || "";

      if (user.role === "admin") {
        document.querySelectorAll("[data-admin-only]").forEach(function (node) {
          node.hidden = false;
        });
      }
    } catch (err) {
      if (el) el.textContent = "";
    }
  }

  document.addEventListener("click", function (event) {
    const logoutBtn = event.target.closest('[data-action="logout"]');
    if (logoutBtn) {
      event.preventDefault();
      logout();
      return;
    }

    const navToggle = event.target.closest('[data-action="toggle-nav"]');
    if (navToggle) {
      event.preventDefault();
      const open = document.body.classList.toggle("nav-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
  });

  window.IMS = {
    getCookie: getCookie,
    apiFetch: apiFetch,
    parseJson: parseJson,
    errorMessage: errorMessage,
    logout: logout,
    formatCurrency: function (value) {
      const n = Number(value);
      if (!isFinite(n)) return value;
      return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    formatDateTime: function (value) {
      if (!value) return "";
      const d = new Date(value);
      if (isNaN(d.getTime())) return value;
      return d.toLocaleString();
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadCurrentUser);
  } else {
    loadCurrentUser();
  }
})();