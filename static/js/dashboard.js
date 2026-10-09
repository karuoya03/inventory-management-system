/* Dashboard: summary stats, low-stock table, recent movements. */
(function () {
  "use strict";

  function setStat(name, value) {
    const el = document.querySelector('[data-stat="' + name + '"]');
    if (el) el.textContent = value;
  }

  function renderLowStock(payload) {
    const container = document.querySelector("[data-low-stock-table]");
    if (!container) return;

    if (!payload || !payload.items || payload.items.length === 0) {
      container.innerHTML =
        '<p class="muted">Every product is above its reorder level. Nothing to restock right now.</p>';
      return;
    }

    const rows = payload.items
      .map(function (item) {
        return (
          "<tr>" +
          "<td><code>" + escapeHtml(item.sku) + "</code></td>" +
          "<td>" + escapeHtml(item.name) + "</td>" +
          '<td class="num">' + item.quantity_in_stock + "</td>" +
          '<td class="num">' + item.reorder_level + "</td>" +
          '<td class="num">' + item.shortfall + "</td>" +
          "</tr>"
        );
      })
      .join("");

    container.innerHTML =
      '<div class="table-wrap"><table>' +
      "<thead><tr>" +
      "<th>SKU</th><th>Product</th>" +
      '<th class="num">In stock</th>' +
      '<th class="num">Reorder at</th>' +
      '<th class="num">Shortfall</th>' +
      "</tr></thead>" +
      "<tbody>" + rows + "</tbody>" +
      "</table></div>";
  }

  function renderRecent(rows) {
    const container = document.querySelector("[data-recent-table]");
    if (!container) return;

    if (!rows || rows.length === 0) {
      container.innerHTML =
        '<p class="muted">No stock movements recorded yet. Record one from the Stock page.</p>';
      return;
    }

    const body = rows
      .slice(0, 10)
      .map(function (txn) {
        const type = String(txn.type || "").toLowerCase();
        const cls = type === "in" ? "tag-in" : type === "out" ? "tag-out" : "tag-adjust";
        return (
          "<tr>" +
          '<td><span class="tag ' + cls + '">' + escapeHtml(txn.type) + "</span></td>" +
          '<td class="num">' + txn.quantity + "</td>" +
          '<td class="num">' + txn.balance_after + "</td>" +
          "<td>" + escapeHtml(txn.reference || "") + "</td>" +
          "<td>" + escapeHtml(window.IMS.formatDateTime(txn.created_at)) + "</td>" +
          "</tr>"
        );
      })
      .join("");

    container.innerHTML =
      '<div class="table-wrap"><table>' +
      "<thead><tr>" +
      "<th>Type</th>" +
      '<th class="num">Quantity</th>' +
      '<th class="num">Balance after</th>' +
      "<th>Reference</th>" +
      "<th>When</th>" +
      "</tr></thead>" +
      "<tbody>" + body + "</tbody>" +
      "</table></div>";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function loadSummary() {
    try {
      const res = await window.IMS.apiFetch("/api/reports/summary");
      if (!res.ok) return;
      const data = await window.IMS.parseJson(res);
      if (!data) return;
      setStat("total_products", data.total_products);
      setStat("total_units_in_stock", data.total_units_in_stock);
      setStat("inventory_cost_value", window.IMS.formatCurrency(data.inventory_cost_value));
      setStat("low_stock_count", data.low_stock_count);
    } catch (err) {
      /* Silent — stats show a dash. */
    }
  }

  async function loadLowStock() {
    const errBox = document.querySelector("[data-low-stock-error]");
    try {
      const res = await window.IMS.apiFetch("/api/reports/low-stock");
      const body = await window.IMS.parseJson(res);
      if (!res.ok) {
        errBox.textContent = window.IMS.errorMessage(res, body);
        errBox.hidden = false;
        return;
      }
      renderLowStock(body);
    } catch (err) {
      errBox.textContent = "Could not load low-stock data.";
      errBox.hidden = false;
    }
  }

  async function loadRecent() {
    const errBox = document.querySelector("[data-recent-error]");
    try {
      const res = await window.IMS.apiFetch("/api/transactions?limit=10");
      const body = await window.IMS.parseJson(res);
      if (!res.ok) {
        errBox.textContent = window.IMS.errorMessage(res, body);
        errBox.hidden = false;
        return;
      }
      renderRecent(body);
    } catch (err) {
      errBox.textContent = "Could not load recent movements.";
      errBox.hidden = false;
    }
  }

  loadSummary();
  loadLowStock();
  loadRecent();
})();