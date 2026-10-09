/* Users admin page: list accounts, create accounts, toggle active. */
(function () {
  "use strict";

  const createForm = document.getElementById("create-user-form");
  const createErr = document.querySelector("[data-create-error]");
  const createOk = document.querySelector("[data-create-success]");
  const usersContainer = document.querySelector("[data-users-table]");
  const usersErr = document.querySelector("[data-users-error]");

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function show(box, message) {
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
  }
  function hide(box) {
    if (!box) return;
    box.textContent = "";
    box.hidden = true;
  }

  function renderUsers(rows) {
    if (!rows || rows.length === 0) {
      usersContainer.innerHTML = '<p class="muted">No accounts yet.</p>';
      return;
    }

    const body = rows
      .map(function (u) {
        const status = u.is_active
          ? '<span class="tag tag-in">Active</span>'
          : '<span class="tag tag-out">Inactive</span>';
        const lastSeen = u.last_login_at
          ? esc(window.IMS.formatDateTime(u.last_login_at))
          : '<span class="muted">Never</span>';
        const action = u.is_active ? "Deactivate" : "Activate";

        return (
          "<tr>" +
          "<td>" + esc(u.full_name) + "</td>" +
          "<td><code>" + esc(u.username) + "</code></td>" +
          "<td>" + esc(u.email) + "</td>" +
          "<td>" + esc(u.role) + "</td>" +
          "<td>" + status + "</td>" +
          "<td>" + lastSeen + "</td>" +
          '<td><button class="button button-quiet" type="button" ' +
          'data-toggle-active="' + u.id + '" ' +
          'data-active="' + (u.is_active ? "1" : "0") + '">' + action + "</button></td>" +
          "</tr>"
        );
      })
      .join("");

    usersContainer.innerHTML =
      '<div class="table-wrap"><table>' +
      "<thead><tr>" +
      "<th>Name</th><th>Username</th><th>Email</th><th>Role</th>" +
      "<th>Status</th><th>Last signed in</th><th></th>" +
      "</tr></thead>" +
      "<tbody>" + body + "</tbody>" +
      "</table></div>";
  }

  async function loadUsers() {
    hide(usersErr);
    usersContainer.innerHTML = '<p class="muted">Loading...</p>';
    try {
      const res = await window.IMS.apiFetch("/api/users");
      const body = await window.IMS.parseJson(res);
      if (!res.ok) {
        show(usersErr, window.IMS.errorMessage(res, body));
        usersContainer.innerHTML = "";
        return;
      }
      renderUsers(body);
    } catch (err) {
      show(usersErr, "Could not load users.");
      usersContainer.innerHTML = "";
    }
  }

  async function toggleActive(userId, currentlyActive) {
    hide(usersErr);
    try {
      const res = await window.IMS.apiFetch("/api/users/" + userId, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !currentlyActive }),
      });
      const body = await window.IMS.parseJson(res);
      if (!res.ok) {
        show(usersErr, window.IMS.errorMessage(res, body));
        return;
      }
      loadUsers();
    } catch (err) {
      show(usersErr, "Could not update that account.");
    }
  }

  if (usersContainer) {
    usersContainer.addEventListener("click", function (event) {
      const btn = event.target.closest("[data-toggle-active]");
      if (!btn) return;
      const id = Number(btn.getAttribute("data-toggle-active"));
      const active = btn.getAttribute("data-active") === "1";
      toggleActive(id, active);
    });
  }

  if (createForm) {
    createForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      hide(createErr);
      hide(createOk);

      const data = {
        full_name: createForm.full_name.value.trim(),
        username: createForm.username.value.trim(),
        email: createForm.email.value.trim(),
        password: createForm.password.value,
        role: createForm.role.value,
      };

      if (!data.full_name || !data.username || !data.email || !data.password) {
        show(createErr, "Please fill in every field.");
        return;
      }
      if (data.password.length < 10) {
        show(createErr, "Password must be at least 10 characters.");
        return;
      }
      if (!/[A-Za-z]/.test(data.password) || !/\d/.test(data.password)) {
        show(createErr, "Password must contain at least one letter and one digit.");
        return;
      }

      const btn = createForm.querySelector('button[type="submit"]');
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Creating...";

      try {
        const res = await window.IMS.apiFetch("/api/auth/register", {
          method: "POST",
          body: JSON.stringify(data),
        });
        const body = await window.IMS.parseJson(res);

        if (!res.ok) {
          let message = window.IMS.errorMessage(res, body);
          // Unpack the errors array when the handler returned field-level details.
          if (body && Array.isArray(body.errors) && body.errors.length) {
            message = body.errors
              .map(function (e) {
                if (typeof e === "string") return e;
                const field = (e.loc || []).slice(1).join(".") || "field";
                return field + ": " + (e.msg || "invalid value");
              })
              .join(" ");
          }
          show(createErr, message);
          return;
        }

        createForm.reset();
        show(createOk, "Account created: " + body.username);
        loadUsers();
      } catch (err) {
        show(createErr, "Could not reach the server.");
      } finally {
        btn.disabled = false;
        btn.textContent = original;
      }
    });
  }

  loadUsers();
})();