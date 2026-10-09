/* Reports page: valuation, stock movement by range, low stock. */
(function () {
  "use strict";

  const vGroup = document.getElementById("v-group");
  const vTable = document.querySelector("[data-valuation-table]");
  const vErr = document.querySelector("[data-valuation-error]");

  const mForm = document.getElementById("movement-form");
  const mFrom = document.getElementById("m-from");
  const mTo = document.getElementById("m-to");
  const mTable = document.querySelector("[data-movement-table]");
  const mErr = document.querySelector("[data-movement-error]");

  const lTable = document.querySelector("[data-lowstock-table]");
  const lErr = document.querySelector("[data-lowstock-error]");

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function show(box, msg) { if (!box) return; box.textContent = msg; box.hidden = false; }
  function hide(box) { if (!box) return; box.textContent = ""; box.hidden = true; }
  function currency(v) { return window.IMS.formatCurrency(v); }

  // ---- Valuation ----
  async function loadValuation() {
    hide(vErr);
    vTable.innerHTML = '<p class="muted">Loading...</p>';
    try {
      const res = await window.IMS.apiFetch("/api/reports/valuation?group_by=" + vGroup.value);
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(vErr, window.IMS.errorMessage(res, body)); vTable.innerHTML = ""; return; }

      const groups = body.groups || [];
      if (groups.length === 0) {
        vTable.innerHTML = '<p class="muted">No inventory value to report yet.</p>';
        return;
      }

      let totalUnits = 0, totalCost = 0, totalRetail = 0;
      const body_rows = groups.map(function (g) {
        totalUnits += g.units;
        totalCost += Number(g.cost_value);
        totalRetail += Number(g.retail_value);
        return (
          "<tr>" +
          "<td>" + esc(g.name || g.key) + "</td>" +
          '<td class="num">' + g.units + "</td>" +
          '<td class="num">' + currency(g.cost_value) + "</td>" +
          '<td class="num">' + currency(g.retail_value) + "</td>" +
          "</tr>"
        );
      }).join("");

      vTable.innerHTML =
        '<div class="table-wrap"><table>' +
        "<thead><tr>" +
        "<th>" + (body.group_by === "none" ? "Scope" :
          body.group_by === "category" ? "Category" : "Supplier") + "</th>" +
        '<th class="num">Units</th>' +
        '<th class="num">Cost value</th>' +
        '<th class="num">Retail value</th>' +
        "</tr></thead><tbody>" + body_rows +
        '<tr class="total-row">' +
        "<td><strong>Total</strong></td>" +
        '<td class="num"><strong>' + totalUnits + "</strong></td>" +
        '<td class="num"><strong>' + currency(totalCost.toFixed(2)) + "</strong></td>" +
        '<td class="num"><strong>' + currency(totalRetail.toFixed(2)) + "</strong></td>" +
        "</tr></tbody></table></div>";
    } catch (e) {
      show(vErr, "Could not load valuation.");
      vTable.innerHTML = "";
    }
  }

  // ---- Stock movement ----
  async function loadMovement() {
    hide(mErr);
    if (!mFrom.value || !mTo.value) {
      show(mErr, "Choose both a start and end date.");
      return;
    }
    mTable.innerHTML = '<p class="muted">Running...</p>';
    const params = new URLSearchParams({ date_from: mFrom.value, date_to: mTo.value });
    try {
      const res = await window.IMS.apiFetch("/api/reports/stock-movement?" + params.toString());
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(mErr, window.IMS.errorMessage(res, body)); mTable.innerHTML = ""; return; }

      const order = ["IN", "OUT", "ADJUSTMENT"];
      const labels = { IN: "Stock in", OUT: "Stock out", ADJUSTMENT: "Adjustments" };
      const rows = order.map(function (k) {
        const m = body.movements[k] || { quantity: 0, count: 0 };
        return (
          "<tr>" +
          "<td>" + labels[k] + "</td>" +
          '<td class="num">' + m.count + "</td>" +
          '<td class="num">' + m.quantity + "</td>" +
          "</tr>"
        );
      }).join("");

      mTable.innerHTML =
        '<p class="muted">' + esc(body.date_from) + " → " + esc(body.date_to) + "</p>" +
        '<div class="table-wrap"><table>' +
        "<thead><tr>" +
        "<th>Movement</th>" +
        '<th class="num">Transactions</th>' +
        '<th class="num">Units</th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    } catch (e) {
      show(mErr, "Could not run the movement report.");
      mTable.innerHTML = "";
    }
  }

  // ---- Low stock ----
  async function loadLowStock() {
    hide(lErr);
    lTable.innerHTML = '<p class="muted">Loading...</p>';
    try {
      const res = await window.IMS.apiFetch("/api/reports/low-stock");
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(lErr, window.IMS.errorMessage(res, body)); lTable.innerHTML = ""; return; }

      if (!body.items || body.items.length === 0) {
        lTable.innerHTML = '<p class="muted">Every product is above its reorder level.</p>';
        return;
      }

      const rows = body.items.map(function (p) {
        return (
          "<tr>" +
          "<td><code>" + esc(p.sku) + "</code></td>" +
          "<td>" + esc(p.name) + "</td>" +
          '<td class="num">' + p.quantity_in_stock + "</td>" +
          '<td class="num">' + p.reorder_level + "</td>" +
          '<td class="num">' + p.shortfall + "</td>" +
          "</tr>"
        );
      }).join("");

      lTable.innerHTML =
        '<div class="table-wrap"><table>' +
        "<thead><tr>" +
        "<th>SKU</th><th>Product</th>" +
        '<th class="num">In stock</th>' +
        '<th class="num">Reorder at</th>' +
        '<th class="num">Shortfall</th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    } catch (e) {
      show(lErr, "Could not load the low-stock report.");
      lTable.innerHTML = "";
    }
  }

  vGroup.addEventListener("change", loadValuation);
  mForm.addEventListener("submit", function (e) { e.preventDefault(); loadMovement(); });

  (function seedDates() {
    const today = new Date();
    const iso = today.toISOString().slice(0, 10);
    mTo.value = iso;
    const start = new Date(today);
    start.setDate(start.getDate() - 30);
    mFrom.value = start.toISOString().slice(0, 10);
  })();

  loadValuation();
  loadLowStock();

  // ---- Downloads ----
const dlErr = document.querySelector("[data-download-error]");
const dlDate = document.getElementById("dl-date");
const dlMonth = document.getElementById("dl-month");
const dlYear = document.getElementById("dl-year");

(function seedDownloadInputs() {
  const today = new Date();
  dlDate.value = today.toISOString().slice(0, 10);
  dlMonth.value = today.toISOString().slice(0, 7);
  dlYear.value = today.getFullYear();
})();

async function downloadFile(path) {
  hide(dlErr);
  try {
    const res = await window.IMS.apiFetch(path);
    if (!res.ok) {
      const body = await window.IMS.parseJson(res);
      show(dlErr, window.IMS.errorMessage(res, body));
      return;
    }
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "report.csv";

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    show(dlErr, "Could not download the report.");
  }
}

document.addEventListener("click", function (event) {
  const btn = event.target.closest("[data-download]");
  if (!btn) return;
  const kind = btn.getAttribute("data-download");

  if (kind === "daily") {
    if (!dlDate.value) { show(dlErr, "Pick a date first."); return; }
    downloadFile("/api/reports/download/daily.csv?date=" + dlDate.value);
  } else if (kind === "monthly") {
    if (!dlMonth.value) { show(dlErr, "Pick a month first."); return; }
    const [y, m] = dlMonth.value.split("-");
    downloadFile("/api/reports/download/monthly.csv?year=" + y + "&month=" + Number(m));
  } else if (kind === "yearly") {
    if (!dlYear.value) { show(dlErr, "Enter a year first."); return; }
    downloadFile("/api/reports/download/yearly.csv?year=" + dlYear.value);
  } else if (kind === "inventory") {
    downloadFile("/api/reports/download/inventory.csv");
  }
});
})();