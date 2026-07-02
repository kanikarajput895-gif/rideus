const state = {
  apiBase: localStorage.getItem("rideus_api_base") || "http://127.0.0.1:8000",
  loading: false,
};

const $ = (id) => document.getElementById(id);

const els = {
  apiBase: $("apiBase"),
  saveApiBtn: $("saveApiBtn"),
  refreshBtn: $("refreshBtn"),
  backendStatus: $("backendStatus"),
  dbBadge: $("dbBadge"),
  errorBox: $("errorBox"),
  metricUsers: $("metricUsers"),
  metricBookings: $("metricBookings"),
  metricActive: $("metricActive"),
  metricRevenue: $("metricRevenue"),
  metricSupport: $("metricSupport"),
  metricDrivers: $("metricDrivers"),
  metricAvailable: $("metricAvailable"),
  metricSos: $("metricSos"),
  bookingsBody: $("bookingsBody"),
  bookingCount: $("bookingCount"),
  usersGrid: $("usersGrid"),
  userCount: $("userCount"),
  contactsList: $("contactsList"),
  contactCount: $("contactCount"),
  driversGrid: $("driversGrid"),
  driverCount: $("driverCount"),
  sosList: $("sosList"),
  sosCount: $("sosCount"),
  topRideBadge: $("topRideBadge"),
  urgentSupport: $("urgentSupport"),
  avgFare: $("avgFare"),
  supportBars: $("supportBars"),
  recommendations: $("recommendations"),
};

els.apiBase.value = state.apiBase;

els.saveApiBtn.addEventListener("click", () => {
  state.apiBase = els.apiBase.value.trim().replace(/\/$/, "");
  localStorage.setItem("rideus_api_base", state.apiBase);
  loadDashboard();
});

els.refreshBtn.addEventListener("click", loadDashboard);

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-status-action]");
  if (!button) return;
  button.disabled = true;
  button.textContent = "Saving...";
  try {
    await apiPost(`/admin/bookings/${button.dataset.bookingId}/status`, {
      status: button.dataset.statusAction,
    });
    await loadDashboard();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
});

function formatMoney(value) {
  const amount = Number(value || 0);
  return `Rs ${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function safeText(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return safeText(value);
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function apiGet(path) {
  const response = await fetch(`${state.apiBase}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const json = await response.json();
      detail = json.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(`${path}: ${detail}`);
  }
  return response.json();
}

async function apiPost(path, payload) {
  const response = await fetch(`${state.apiBase}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const json = await response.json();
      detail = json.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(`${path}: ${detail}`);
  }
  return response.json();
}

async function loadDashboard() {
  if (state.loading) return;
  state.loading = true;
  els.refreshBtn.textContent = "Loading...";
  els.errorBox.classList.add("hidden");

  try {
    const [health, summary, users, bookings, contacts, insights, drivers, sos] = await Promise.all([
      apiGet("/health"),
      apiGet("/admin/summary"),
      apiGet("/admin/users"),
      apiGet("/admin/bookings"),
      apiGet("/admin/contacts"),
      apiGet("/admin/ai-insights"),
      apiGet("/admin/drivers"),
      apiGet("/admin/sos"),
    ]);

    renderHealth(health);
    renderSummary(summary);
    renderBookings(bookings);
    renderUsers(users);
    renderContacts(contacts);
    renderInsights(insights);
    renderDrivers(drivers);
    renderSos(sos);
  } catch (error) {
    showError(error);
  } finally {
    state.loading = false;
    els.refreshBtn.textContent = "Refresh Live Data";
  }
}

function renderHealth(health) {
  els.backendStatus.textContent = `Online at ${formatDate(health.time)}`;
  els.dbBadge.textContent = safeText(health.database, "DB").toUpperCase();
  els.dbBadge.className = "rounded-full bg-rideYellow px-4 py-2 text-sm font-black text-rideBlue";
}

function renderSummary(summary) {
  els.metricUsers.textContent = safeText(summary.total_users, "0");
  els.metricBookings.textContent = safeText(summary.total_bookings, "0");
  els.metricActive.textContent = safeText(summary.active_rides, "0");
  els.metricRevenue.textContent = formatMoney(summary.estimated_revenue);
  els.metricSupport.textContent = safeText(summary.support_requests, "0");
  els.metricDrivers.textContent = safeText(summary.total_drivers, "0");
  els.metricAvailable.textContent = `${safeText(summary.available_drivers, "0")} available`;
  els.metricSos.textContent = safeText(summary.open_sos, "0");
}

function renderBookings(bookings) {
  els.bookingCount.textContent = `${bookings.length} records`;
  if (!bookings.length) {
    els.bookingsBody.innerHTML = `<tr><td colspan="6"><div class="empty-state">No bookings yet. Book a ride from the Android app.</div></td></tr>`;
    return;
  }

  els.bookingsBody.innerHTML = bookings.map((booking) => {
    const route = `${safeText(booking.pickup)} -> ${safeText(booking.drop_location)}`;
    const statusClass = booking.status === "cancelled" ? "status-pill cancelled" : "status-pill";
    return `
      <tr>
        <td>#${safeText(booking.id)}</td>
        <td>
          <div class="font-black">${safeText(booking.user_mobile, "guest")}</div>
          <div class="text-xs font-bold text-muted">${formatDate(booking.created_at)}</div>
        </td>
        <td>
          <div class="max-w-[300px] truncate font-black">${route}</div>
          <div class="text-xs font-bold text-muted">${safeText(booking.distance_km, 0)} km · ${safeText(booking.distance_source, "route")}</div>
        </td>
        <td>${safeText(booking.ride_type)}</td>
        <td>${formatMoney(booking.estimated_fare)}</td>
        <td>
          <span class="${statusClass}">${safeText(booking.status)}</span>
          <div class="status-actions">
            <button class="status-action" data-booking-id="${booking.id}" data-status-action="accepted">Accept</button>
            <button class="status-action" data-booking-id="${booking.id}" data-status-action="ongoing">Start</button>
            <button class="status-action" data-booking-id="${booking.id}" data-status-action="completed">Done</button>
            <button class="status-action" data-booking-id="${booking.id}" data-status-action="cancelled">Cancel</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderUsers(users) {
  els.userCount.textContent = `${users.length} riders`;
  if (!users.length) {
    els.usersGrid.innerHTML = `<div class="empty-state md:col-span-2">No rider profiles yet. Save profile from the Android app.</div>`;
    return;
  }

  els.usersGrid.innerHTML = users.slice(0, 12).map((user) => `
    <article class="user-card">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-xl font-black text-rideBlue">${safeText(user.name, "RideUS User")}</p>
          <p class="mt-1 text-sm font-bold text-muted">${safeText(user.email)}</p>
        </div>
        <span class="rounded-full bg-rideYellow px-3 py-1 text-xs font-black text-rideBlue">#${safeText(user.id)}</span>
      </div>
      <div class="mt-5 rounded-2xl bg-[#f3fbfc] p-4">
        <p class="text-xs font-black uppercase tracking-[.14em] text-muted">Mobile</p>
        <p class="mt-1 text-lg font-black">${safeText(user.mobile)}</p>
      </div>
      <p class="mt-4 text-xs font-bold text-muted">Joined: ${formatDate(user.created_at)}</p>
    </article>
  `).join("");
}

function renderContacts(contacts) {
  els.contactCount.textContent = `${contacts.length} messages`;
  if (!contacts.length) {
    els.contactsList.innerHTML = `<div class="empty-state">No support requests yet.</div>`;
    return;
  }

  els.contactsList.innerHTML = contacts.slice(0, 10).map((contact) => `
    <article class="contact-card">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-lg font-black text-rideBlue">${safeText(contact.name)}</p>
          <p class="text-sm font-bold text-muted">${safeText(contact.mobile)} · ${safeText(contact.user_type, "Customer")}</p>
        </div>
        <span class="rounded-full bg-[#eaf6f8] px-3 py-1 text-xs font-black text-rideBlue">#${safeText(contact.id)}</span>
      </div>
      <p class="mt-4 rounded-2xl bg-[#f3fbfc] p-4 text-sm font-semibold leading-6">${safeText(contact.comment)}</p>
      <p class="mt-3 text-xs font-bold text-muted">${formatDate(contact.created_at)}</p>
    </article>
  `).join("");
}

function renderDrivers(drivers) {
  els.driverCount.textContent = `${drivers.length} drivers`;
  if (!drivers.length) {
    els.driversGrid.innerHTML = `<div class="empty-state md:col-span-2">No drivers found.</div>`;
    return;
  }
  els.driversGrid.innerHTML = drivers.map((driver) => `
    <article class="user-card">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-lg font-black text-rideBlue">${safeText(driver.name)}</p>
          <p class="text-sm font-bold text-muted">${safeText(driver.vehicle_type)} · ${safeText(driver.vehicle_number)}</p>
        </div>
        <span class="rounded-full ${Number(driver.is_available) ? "bg-rideYellow text-rideBlue" : "bg-[#eaf6f8] text-muted"} px-3 py-1 text-xs font-black">
          ${Number(driver.is_available) ? "Available" : "Busy"}
        </span>
      </div>
      <p class="mt-4 text-sm font-bold text-muted">${safeText(driver.mobile)} · Rating ${safeText(driver.rating, "4.8")}</p>
    </article>
  `).join("");
}

function renderSos(alerts) {
  els.sosCount.textContent = `${alerts.length} alerts`;
  if (!alerts.length) {
    els.sosList.innerHTML = `<div class="empty-state">No SOS alerts. Good news.</div>`;
    return;
  }
  els.sosList.innerHTML = alerts.map((alert) => `
    <article class="contact-card border-red-100">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-lg font-black text-red-700">SOS #${safeText(alert.id)}</p>
          <p class="text-sm font-bold text-muted">${safeText(alert.user_mobile)} · booking ${safeText(alert.booking_id, "-")}</p>
        </div>
        <span class="rounded-full bg-red-100 px-3 py-1 text-xs font-black text-red-700">${safeText(alert.status)}</span>
      </div>
      <p class="mt-4 rounded-2xl bg-red-50 p-4 text-sm font-semibold leading-6">${safeText(alert.message)}</p>
      <p class="mt-3 text-xs font-bold text-muted">${formatDate(alert.created_at)}</p>
    </article>
  `).join("");
}

function renderInsights(insights) {
  els.topRideBadge.textContent = safeText(insights.top_ride_type, "No rides");
  els.urgentSupport.textContent = safeText(insights.urgent_support_count, "0");
  els.avgFare.textContent = formatMoney(insights.average_fare);

  const categories = insights.support_categories || {};
  const entries = Object.entries(categories);
  const max = Math.max(...entries.map(([, value]) => Number(value)), 1);
  els.supportBars.innerHTML = entries.length
    ? entries.map(([label, count]) => {
        const width = Math.max(8, (Number(count) / max) * 100);
        return `
          <div>
            <div class="mb-2 flex items-center justify-between text-xs font-black text-muted">
              <span>${label.replaceAll("_", " ")}</span>
              <span>${count}</span>
            </div>
            <div class="progress-track"><div class="progress-fill" style="width:${width}%"></div></div>
          </div>
        `;
      }).join("")
    : `<div class="empty-state">Support AI categories will appear after user requests.</div>`;

  const recommendations = insights.recommendations || [];
  els.recommendations.innerHTML = recommendations.length
    ? recommendations.map((item) => `<li class="rounded-2xl bg-white p-3">${item}</li>`).join("")
    : `<li class="rounded-2xl bg-white p-3">No recommendations yet.</li>`;
}

function showError(error) {
  els.backendStatus.textContent = "Backend offline";
  els.dbBadge.textContent = "OFF";
  els.dbBadge.className = "rounded-full bg-red-500 px-4 py-2 text-sm font-black text-white";
  els.errorBox.textContent = `Backend is not reachable. Start it with: python -m uvicorn backend_api:app --host 0.0.0.0 --port 8000 --reload. Error: ${error.message}`;
  els.errorBox.classList.remove("hidden");
}

loadDashboard();
