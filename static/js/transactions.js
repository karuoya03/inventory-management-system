/* Stock movements page: post transactions, view ledger. */
(function () {
  "use strict";

  const form = document.getElementById("txn-form");
  const newErr = document.querySelector("[data-new-error]");
  const newOk = document.querySelector("[data-new-success]");
  const productSelect = document.getElementById("t-product");
  const ledgerProduct = document.getElementById("l-product");
  const ledgerType = document.getElementById("l-type");
  const ledgerFilters = document.getElementById("ledger-filters");
  const ledgerTable = document.querySelector("[data-ledger-table]");
  const ledgerErr = document.querySelector("[data-ledger-error]");

  const typeSelect = document.getElementById("t-type");
  const unitCostField = document.querySelector("[data-unit-cost-field]");
  const quantityLabel = document.querySelector("[data-quantity-label]");
  const quantityHint = document.querySelector("[data-quantity-hint]");

  let productsById = {};

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function show(box, msg) { if (!box) return; box.textContent = msg; box.hidden = false; }
  function hide(box) { if (!box) return; box.textContent = ""; box.hidden = true; }

  function syncFormForType() {
    const t = typeSelect.value;
    if (t === "IN") {
      unitCostField.hidden = false;
      quantityLabel.textContent = "Quantity";
      quantityHint.textContent = "Number of units received.";
    } else if (t === "OUT") {
      unitCostField.hidden = true;
      quantityLabel.textContent = "Quantity";
      quantityHint.textContent = "Number of units removed.";
    } else {
      unitCostField.hidden = true;
      quantityLabel.textContent = "New absolute count";
      quantityHint.textContent = "The physical count after this adjustment.";
    }
  }

  async function loadProducts() {
    try {
      const res = await window.IMS.apiFetch("/api/products?active_only=true&limit=500&sort=name");
      if (!res.ok) return;
      const rows = await window.IMS.parseJson(res) || [];

      productsById = {};
      const options = rows.map(function (p) {
        productsById[p.id] = p;
        return '<option value="' + p.id + '">' +
          esc(p.sku) + " — " + esc(p.name) +
          " (in stock: " + p.quantity_in_stock + ")" +
          "</option>";
      }).join("");

      productSelect.innerHTML = '<option value="">Select a product…</option>' + options;
      ledgerProduct.innerHTML = '<option value="">All</option>' +
        rows.map(function (p) {
          return '<option value="' + p.id + '">' + esc(p.sku) + " — " + esc(p.name) + "</option>";
        }).join("");
    } catch (e) { /* silent */ }
  }

  function renderLedger(rows) {
    if (!rows || rows.length === 0) {
      ledgerTable.innerHTML = '<p class="muted">No movements recorded yet.</p>';
      return;
    }
    const body = rows.map(function (t) {
      const type = String(t.type || "").toLowerCase();
      const cls = type === "in" ? "tag-in" : type === "out" ? "tag-out" : "tag-adjust";
      const product = productsById[t.product_id];
      const label = product ? product.sku + " — " + product.name : "#" + t.product_id;

      return (
        "<tr>" +
        "<td>" + esc(window.IMS.formatDateTime(t.created_at)) + "</td>" +
        "<td>" + esc(label) + "</td>" +
        '<td><span class="tag ' + cls + '">' + esc(t.type) + "</span></td>" +
        '<td class="num">' + t.quantity + "</td>" +
        '<td class="num">' + t.balance_after + "</td>" +
        "<td>" + esc(t.reference || "") + "</td>" +
        "</tr>"
      );
    }).join("");

    ledgerTable.innerHTML =
      '<div class="table-wrap"><table>' +
      "<thead><tr>" +
      "<th>When</th><th>Product</th><th>Type</th>" +
      '<th class="num">Quantity</th><th class="num">Balance after</th>' +
      "<th>Reference</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  async function loadLedger() {
    hide(ledgerErr);
    ledgerTable.innerHTML = '<p class="muted">Loading...</p>';
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (ledgerProduct.value) params.set("product_id", ledgerProduct.value);
    if (ledgerType.value) params.set("type", ledgerType.value);

    try {
      const res = await window.IMS.apiFetch("/api/transactions?" + params.toString());
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(ledgerErr, window.IMS.errorMessage(res, body)); ledgerTable.innerHTML = ""; return; }
      renderLedger(body);
    } catch (e) {
      show(ledgerErr, "Could not load the ledger.");
      ledgerTable.innerHTML = "";
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    hide(newErr); hide(newOk);

    const productId = Number(productSelect.value);
    const type = typeSelect.value;
    const quantity = Number(document.getElementById("t-quantity").value);
    const unitCostRaw = document.getElementById("t-unit-cost").value;
    const reference = document.getElementById("t-reference").value.trim();
    const notes = document.getElementById("t-notes").value.trim();

    if (!productId) { show(newErr, "Select a product."); return; }
    if (!Number.isFinite(quantity)) { show(newErr, "Enter a quantity."); return; }
    if ((type === "IN" || type === "OUT") && quantity <= 0) {
      show(newErr, "Quantity must be greater than zero for stock in/out."); return;
    }
    if (type === "ADJUSTMENT" && quantity < 0) {
      show(newErr, "Adjustment count cannot be negative."); return;
    }

    const payload = {
      product_id: productId,
      type: type,
      quantity: quantity,
      reference: reference || null,
      notes: notes || null,
    };
    if (type === "IN" && unitCostRaw !== "") payload.unit_cost = unitCostRaw;

    const btn = form.querySelector('button[type="submit"]');
    const original = btn.textContent;
    btn.disabled = true; btn.textContent = "Posting...";

    try {
      const res = await window.IMS.apiFetch("/api/transactions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const body = await window.IMS.parseJson(res);

      if (!res.ok) { show(newErr, window.IMS.errorMessage(res, body)); return; }

      const product = productsById[productId];
      show(newOk,
        "Posted " + type + " of " + quantity +
        (product ? " for " + product.sku : "") +
        ". Balance is now " + body.balance_after + "."
      );
      form.reset();
      syncFormForType();
      await loadProducts();
      loadLedger();
    } catch (e) {
      show(newErr, "Could not reach the server.");
    } finally {
      btn.disabled = false; btn.textContent = original;
    }
  });

  typeSelect.addEventListener("change", syncFormForType);
  ledgerFilters.addEventListener("submit", function (e) { e.preventDefault(); loadLedger(); });
  ledgerProduct.addEventListener("change", loadLedger);
  ledgerType.addEventListener("change", loadLedger);

  (async function init() {
    syncFormForType();
    await loadProducts();
    loadLedger();
  })();
})();