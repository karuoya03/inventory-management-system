/* Products page: list, filter, create, edit, deactivate. */
(function () {
  "use strict";

  const tableBox = document.querySelector("[data-products-table]");
  const errorBox = document.querySelector("[data-products-error]");
  const successBox = document.querySelector("[data-products-success]");
  const form = document.getElementById("product-form");
  const dialog = document.getElementById("product-dialog");
  const dialogTitle = dialog.querySelector("[data-dialog-title]");
  const errorInDialog = dialog.querySelector("[data-product-error]");

  const filterForm = document.getElementById("filters");
  const filterQ = document.getElementById("filter-q");
  const filterCategory = document.getElementById("filter-category");
  const filterSupplier = document.getElementById("filter-supplier");
  const filterLow = document.getElementById("filter-low");

  let categoriesById = {};
  let suppliersById = {};

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function show(box, msg) { if (!box) return; box.textContent = msg; box.hidden = false; }
  function hide(box) { if (!box) return; box.textContent = ""; box.hidden = true; }
  function debounce(fn, ms) {
    let t;
    return function () {
      const args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  function ensureManagerUI() {
    if (document.body.dataset.userRole === "admin" ||
        document.body.dataset.userRole === "manager") {
      document.querySelectorAll("[data-manager-only]").forEach(function (n) {
        n.hidden = false;
      });
    }
  }

  function buildQuery() {
    const params = new URLSearchParams();
    if (filterQ.value.trim()) params.set("q", filterQ.value.trim());
    if (filterCategory.value) params.set("category_id", filterCategory.value);
    if (filterSupplier.value) params.set("supplier_id", filterSupplier.value);
    if (filterLow.checked) params.set("low_stock_only", "true");
    params.set("sort", "name");
    params.set("limit", "200");
    return params.toString();
  }

  function render(rows) {
    if (!rows || rows.length === 0) {
      tableBox.innerHTML = '<p class="muted">No products match these filters.</p>';
      return;
    }

    const body = rows.map(function (p) {
      const low = p.quantity_in_stock <= p.reorder_level;
      const stockCell = low
        ? '<span class="tag tag-out">' + p.quantity_in_stock + "</span>"
        : String(p.quantity_in_stock);
      const category = categoriesById[p.category_id] || "—";
      const supplier = suppliersById[p.supplier_id] || "—";

      return (
        "<tr>" +
        "<td><code>" + esc(p.sku) + "</code></td>" +
        "<td>" + esc(p.name) + "</td>" +
        "<td>" + esc(category) + "</td>" +
        "<td>" + esc(supplier) + "</td>" +
        '<td class="num">' + stockCell + "</td>" +
        '<td class="num">' + esc(p.reorder_level) + "</td>" +
        '<td class="num">' + esc(window.IMS.formatCurrency(p.unit_price)) + "</td>" +
        '<td class="actions">' +
        '<button class="button button-quiet" type="button" data-edit="' + p.id + '" data-manager-only>Edit</button> ' +
        '<button class="button button-danger" type="button" data-deactivate="' + p.id + '" data-manager-only>Deactivate</button>' +
        "</td>" +
        "</tr>"
      );
    }).join("");

    tableBox.innerHTML =
      '<div class="table-wrap"><table>' +
      "<thead><tr>" +
      "<th>SKU</th><th>Name</th><th>Category</th><th>Supplier</th>" +
      '<th class="num">In stock</th><th class="num">Reorder at</th>' +
      '<th class="num">Unit price</th><th></th>' +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";

    ensureManagerUI();
  }

  async function loadProducts() {
    hide(errorBox);
    tableBox.innerHTML = '<p class="muted">Loading...</p>';
    try {
      const res = await window.IMS.apiFetch("/api/products?" + buildQuery());
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(errorBox, window.IMS.errorMessage(res, body)); tableBox.innerHTML = ""; return; }
      render(body);
    } catch (e) {
      show(errorBox, "Could not load products.");
      tableBox.innerHTML = "";
    }
  }

  async function loadCategories() {
    try {
      const res = await window.IMS.apiFetch("/api/categories?limit=500");
      if (!res.ok) return;
      const rows = await window.IMS.parseJson(res) || [];
      categoriesById = {};
      rows.forEach(function (c) { categoriesById[c.id] = c.name; });

      const names = rows.map(function (c) { return c.name; }).sort();
      const datalist = document.getElementById("categories-list");
      if (datalist) {
        datalist.innerHTML = names
          .map(function (n) { return '<option value="' + esc(n) + '"></option>'; })
          .join("");
      }

      filterCategory.innerHTML = '<option value="">All</option>' +
        rows.map(function (c) {
          return '<option value="' + c.id + '">' + esc(c.name) + "</option>";
        }).join("");
    } catch (e) { /* silent */ }
  }

  async function loadSuppliers() {
    try {
      const res = await window.IMS.apiFetch("/api/suppliers?active_only=true&limit=500");
      if (!res.ok) return;
      const rows = await window.IMS.parseJson(res) || [];
      suppliersById = {};
      rows.forEach(function (s) { suppliersById[s.id] = s.name; });

      const names = rows.map(function (s) { return s.name; }).sort();
      const datalist = document.getElementById("suppliers-list");
      if (datalist) {
        datalist.innerHTML = names
          .map(function (n) { return '<option value="' + esc(n) + '"></option>'; })
          .join("");
      }

      filterSupplier.innerHTML = '<option value="">All</option>' +
        rows.map(function (s) {
          return '<option value="' + s.id + '">' + esc(s.name) + "</option>";
        }).join("");
    } catch (e) { /* silent */ }
  }

  function openCreate() {
    form.reset();
    form.product_id.value = "";
    document.getElementById("p-sku").readOnly = false;
    document.getElementById("p-unit").value = "pcs";
    document.getElementById("p-cost").value = "0.00";
    document.getElementById("p-price").value = "0.00";
    document.getElementById("p-reorder").value = "10";
    document.getElementById("p-category").value = "";
    document.getElementById("p-supplier").value = "";
    dialogTitle.textContent = "Add product";
    hide(errorInDialog);
    dialog.showModal();
    document.getElementById("p-sku").focus();
  }

  async function openEdit(id) {
    hide(errorInDialog);
    try {
      const res = await window.IMS.apiFetch("/api/products/" + id);
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(errorBox, window.IMS.errorMessage(res, body)); return; }

      form.product_id.value = body.id;
      form.sku.value = body.sku;
      document.getElementById("p-sku").readOnly = true;
      form.name.value = body.name;
      document.getElementById("p-category").value =
        body.category_id ? (categoriesById[body.category_id] || "") : "";
      document.getElementById("p-supplier").value =
        body.supplier_id ? (suppliersById[body.supplier_id] || "") : "";
      form.unit.value = body.unit;
      form.cost_price.value = body.cost_price;
      form.unit_price.value = body.unit_price;
      form.reorder_level.value = body.reorder_level;
      form.description.value = body.description || "";

      dialogTitle.textContent = "Edit " + body.sku;
      dialog.showModal();
    } catch (e) {
      show(errorBox, "Could not load that product.");
    }
  }

  function collectForm() {
    const categoryName = document.getElementById("p-category").value.trim();
    const supplierName = document.getElementById("p-supplier").value.trim();

    const data = {
      name: form.name.value.trim(),
      description: form.description.value.trim() || null,
      category_name: categoryName || null,
      supplier_name: supplierName || null,
      unit: form.unit.value.trim() || "pcs",
      cost_price: form.cost_price.value || "0.00",
      unit_price: form.unit_price.value || "0.00",
      reorder_level: Number(form.reorder_level.value || 0),
    };
    return data;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    hide(errorInDialog);

    const id = form.product_id.value;
    const payload = collectForm();
    if (!id) payload.sku = form.sku.value.trim();

    if (!payload.name) { show(errorInDialog, "Name is required."); return; }
    if (!id && !payload.sku) { show(errorInDialog, "SKU is required."); return; }

    const submitBtn = form.querySelector('button[type="submit"]');
    const original = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = id ? "Saving..." : "Creating...";

    try {
      const res = await window.IMS.apiFetch(
        id ? "/api/products/" + id : "/api/products",
        { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) }
      );
      const body = await window.IMS.parseJson(res);
      if (!res.ok) { show(errorInDialog, window.IMS.errorMessage(res, body)); return; }

      dialog.close();
      show(successBox, id ? "Product updated." : "Product created: " + body.sku);
      loadProducts();
    } catch (e) {
      show(errorInDialog, "Could not reach the server.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = original;
    }
  });

  async function deactivate(id) {
    if (!confirm("Deactivate this product? Stock and history are kept.")) return;
    hide(errorBox);
    try {
      const res = await window.IMS.apiFetch("/api/products/" + id, { method: "DELETE" });
      if (!res.ok && res.status !== 204) {
        const body = await window.IMS.parseJson(res);
        show(errorBox, window.IMS.errorMessage(res, body));
        return;
      }
      show(successBox, "Product deactivated.");
      loadProducts();
    } catch (e) {
      show(errorBox, "Could not deactivate that product.");
    }
  }

  document.addEventListener("click", function (event) {
    const target = event.target;

    if (target.closest('[data-action="new-product"]')) {
      event.preventDefault();
      openCreate();
      return;
    }
    if (target.closest('[data-action="close-dialog"]')) {
      dialog.close();
      return;
    }
    const editBtn = target.closest("[data-edit]");
    if (editBtn) {
      openEdit(Number(editBtn.getAttribute("data-edit")));
      return;
    }
    const deactivateBtn = target.closest("[data-deactivate]");
    if (deactivateBtn) {
      deactivate(Number(deactivateBtn.getAttribute("data-deactivate")));
    }
  });

  filterForm.addEventListener("submit", function (e) { e.preventDefault(); loadProducts(); });
  filterForm.addEventListener("reset", function () { setTimeout(loadProducts, 0); });
  filterQ.addEventListener("input", debounce(loadProducts, 350));

  (async function init() {
    await Promise.all([loadCategories(), loadSuppliers()]);
    ensureManagerUI();
    loadProducts();
  })();
})();