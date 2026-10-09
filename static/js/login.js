/* Login page behavior. */
(function () {
  "use strict";

  const form = document.getElementById("login-form");
  if (!form) return;

  const errorBox = document.querySelector("[data-login-error]");
  const submitBtn = form.querySelector('button[type="submit"]');
  const usernameField = document.getElementById("username");
  const passwordField = document.getElementById("password");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }
  function clearError() {
    errorBox.textContent = "";
    errorBox.hidden = true;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    clearError();

    const username = usernameField.value.trim();
    const password = passwordField.value;

    if (username.length < 3) {
      showError("Enter your username or email.");
      usernameField.focus();
      return;
    }
    if (password.length < 1) {
      showError("Enter your password.");
      passwordField.focus();
      return;
    }

    submitBtn.disabled = true;
    const originalLabel = submitBtn.textContent;
    submitBtn.textContent = "Signing in...";

    try {
      const res = await window.IMS.apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: username, password: password }),
      });

      if (res.ok) {
        window.location.href = "/dashboard";
        return;
      }

      const body = await window.IMS.parseJson(res);
      showError(window.IMS.errorMessage(res, body));
    } catch (err) {
      showError("Could not reach the server. Check your connection and try again.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalLabel;
    }
  });
})();