const state = {
  tenants: [],
  sites: [],
  contracts: [],
  invoices: [],
  hardware: [],
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  return res.json();
}

function setView(name) {
  document.querySelectorAll(".nav").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((el) => {
    el.classList.toggle("active", el.id === `view-${name}`);
  });
}

function renderSummary(summary) {
  const wrap = document.getElementById("summary-cards");
  wrap.innerHTML = "";
  Object.entries(summary).forEach(([k, v]) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    wrap.appendChild(card);
  });
}

function renderCustomers() {
  const wrap = document.getElementById("customers-list");
  const rows = state.tenants
    .map(
      (t) => `<tr>
      <td>${t.id}</td>
      <td>${t.name ?? ""}</td>
      <td>${t.slug ?? ""}</td>
      <td>${t.description ?? ""}</td>
      <td><button data-tenant="${t.id}" class="edit-tenant">Edit</button></td>
    </tr>`
    )
    .join("");
  wrap.innerHTML = `<table><thead><tr><th>ID</th><th>Name</th><th>Slug</th><th>Description</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;

  wrap.querySelectorAll(".edit-tenant").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.tenant);
      const current = state.tenants.find((t) => t.id === id);
      const name = prompt("Customer name", current?.name || "");
      if (name === null) return;
      const description = prompt("Description", current?.description || "");
      if (description === null) return;
      await api(`/api/app/customers/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name, description }),
      });
      await refreshCustomers();
    });
  });
}

function badge(text) {
  return `<span class="badge">${text ?? "-"}</span>`;
}

function renderInvoices() {
  const wrap = document.getElementById("invoices-list");
  const rows = state.invoices
    .slice(0, 300)
    .map((i) => {
      const contracts = (i.contracts || []).map((c) => c.name).join(", ");
      return `<tr>
        <td>${i.id}</td>
        <td>${i.number}</td>
        <td>${badge(i.status)}</td>
        <td>${i.date ?? ""}</td>
        <td>${i.amount ?? ""} ${i.currency ?? ""}</td>
        <td>${contracts}</td>
      </tr>`;
    })
    .join("");
  wrap.innerHTML = `<table><thead><tr><th>ID</th><th>Number</th><th>Status</th><th>Date</th><th>Amount</th><th>Contracts</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function fillSelects() {
  const tenantSelect = document.getElementById("tenant-select");
  const siteSelect = document.getElementById("site-select");
  tenantSelect.innerHTML = `<option value="">Unassigned</option>` + state.tenants.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
  siteSelect.innerHTML = `<option value="">Keep current</option>` + state.sites.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
}

function renderHardware() {
  const wrap = document.getElementById("hardware-list");
  const rows = state.hardware
    .slice(0, 300)
    .map((d) => `<tr>
      <td>${d.id}</td>
      <td>${d.name ?? ""}</td>
      <td>${d.serial ?? ""}</td>
      <td>${d.tenant?.name ?? "-"}</td>
      <td>${d.site?.name ?? "-"}</td>
      <td>${badge(d.status?.label || d.status?.value || "-")}</td>
    </tr>`)
    .join("");
  wrap.innerHTML = `<table><thead><tr><th>ID</th><th>Name</th><th>Serial</th><th>Customer</th><th>Site</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function refreshCustomers() {
  state.tenants = await api("/api/app/customers");
  renderCustomers();
  fillSelects();
}

async function refreshHardware(search = "") {
  const q = search ? `?search=${encodeURIComponent(search)}` : "";
  state.hardware = await api(`/api/app/hardware${q}`);
  renderHardware();
}

async function init() {
  document.querySelectorAll(".nav").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });

  const bootstrap = await api("/api/app/bootstrap");
  state.tenants = bootstrap.tenants || [];
  state.sites = bootstrap.sites || [];
  state.contracts = bootstrap.contracts || [];
  state.invoices = bootstrap.invoices || [];

  renderSummary(bootstrap.summary || {});
  renderCustomers();
  renderInvoices();
  fillSelects();
  await refreshHardware();

  document.getElementById("checkout-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const payload = {
      device_id: Number(fd.get("device_id")),
      tenant_id: fd.get("tenant_id") ? Number(fd.get("tenant_id")) : null,
      site_id: fd.get("site_id") ? Number(fd.get("site_id")) : null,
      note: String(fd.get("note") || ""),
    };
    await api("/api/app/hardware/checkout", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    alert("Hardware updated");
    await refreshHardware();
  });

  document.getElementById("device-search").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    await refreshHardware(String(fd.get("search") || ""));
  });
}

init().catch((err) => {
  console.error(err);
  alert(`Failed to load app: ${err.message}`);
});
