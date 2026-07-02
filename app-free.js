/* ---- Page Switching ---- */
const pageHome       = document.getElementById('page-home');
const pageAbout      = document.getElementById('page-about');
const pageSafety     = document.getElementById('page-safety');
const pageContact    = document.getElementById('page-contact');
const homeFooter     = document.getElementById('home-footer');
const navLinks       = document.querySelectorAll('[data-nav]');

function showPage(page) {
  // Hide all pages first
  pageHome.style.display     = 'none';
  pageAbout.style.display    = 'none';
  pageSafety.style.display   = 'none';
  pageContact.style.display  = 'none';
  homeFooter.style.display   = 'none';

  // Show selected page
  if (page === 'about') {
    pageAbout.style.display = 'block';
    homeFooter.style.display = '';
  } else if (page === 'safety') {
    pageSafety.style.display = 'block';
    homeFooter.style.display = '';
  } else if (page === 'contact') {
    pageContact.style.display = 'block';
  } else {
    pageHome.style.display   = '';
    homeFooter.style.display = '';
  }

  // Update active nav link
  navLinks.forEach(link => {
    link.classList.toggle('active', link.dataset.nav === page);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Hide About Us, Safety & Contact on load (show home by default)
pageAbout.style.display    = 'none';
pageSafety.style.display   = 'none';
pageContact.style.display  = 'none';
// homeFooter shows by default on home — hide only when switching pages

navLinks.forEach(link => {
  link.addEventListener('click', (e) => {
    const target = link.dataset.nav;
    if (target === 'home' || target === 'about' || target === 'safety' || target === 'contact') {
      e.preventDefault();
      showPage(target);
    }
  });
});
/* ---- End Page Switching ---- */

const form = document.querySelector(".ride-form");
const pickupInput = document.getElementById("pickupInput");
const dropInput = document.getElementById("dropInput");
const resultPickup = document.getElementById("resultPickup");
const resultDrop = document.getElementById("resultDrop");
const resultFare = document.getElementById("resultFare");
const resultService = document.getElementById("resultService");
const resultDistance = document.getElementById("resultDistance");
const resultEta = document.getElementById("resultEta");
const resultNote = document.getElementById("resultNote");
const mapStatus = document.getElementById("mapStatus");
const serviceCards = document.querySelectorAll(".service-card");
const contactForm = document.querySelector(".contact-form");
const contactStatus = document.getElementById("contactStatus");

const SEARCH_URL = "https://nominatim.openstreetmap.org/search";
const ROUTE_URL = "https://router.project-osrm.org/route/v1/driving";
const DEFAULT_CENTER = [28.6139, 77.209];

let map;
let selectedPickup = null;
let selectedDrop = null;
let selectedService = "Bike-Taxi";

const SERVICE_RATES = {
  "Bike-Taxi": { base: 25, perKm: 9, speed: 28, bookable: true },
  Auto: { base: 35, perKm: 14, speed: 22, bookable: true },
  Cab: { base: 55, perKm: 20, speed: 26, bookable: true },
  Parcel: { base: 45, perKm: 12, speed: 24, bookable: false },
  "Travel and Stay": { base: 0, perKm: 0, speed: 0, bookable: false },
  "Metro Ticket": { base: 20, perKm: 4, speed: 34, bookable: false },
};

function titleCase(value) {
  return value
    .trim()
    .replace(/\s+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function setNote(message, kind = "info") {
  resultNote.textContent = message;
  resultNote.dataset.kind = kind;
}

function setMapMessage(message, kind = "info") {
  mapStatus.textContent = message;
  mapStatus.dataset.kind = kind;
}

function formatKm(distanceKm) {
  return `${distanceKm.toFixed(1)} km`;
}

function formatMoney(amount) {
  return `Rs ${Math.round(amount)}`;
}

function estimateFare(distanceKm) {
  const rate = SERVICE_RATES[selectedService] || SERVICE_RATES["Bike-Taxi"];
  return rate.base + Math.max(distanceKm * rate.perKm, 18);
}

function estimateEta(distanceKm) {
  const rate = SERVICE_RATES[selectedService] || SERVICE_RATES["Bike-Taxi"];
  return Math.max(8, Math.round((distanceKm / rate.speed) * 60) + 5);
}

function showEmptyState() {
  resultService.textContent = selectedService;
  resultDistance.textContent = "-- km";
  resultFare.textContent = "Rs 0";
  resultEta.textContent = "-- min";
}

function createSuggestions(input) {
  const list = document.createElement("div");
  list.className = "suggestions";
  list.hidden = true;
  input.closest(".field").appendChild(list);
  return list;
}

const pickupSuggestions = createSuggestions(pickupInput);
const dropSuggestions = createSuggestions(dropInput);

function clearSuggestions(list) {
  list.innerHTML = "";
  list.hidden = true;
}

function debounce(callback, delay = 450) {
  let timer;

  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}

async function searchPlaces(query) {
  const trimmed = query.trim();
  if (trimmed.length < 3) {
    return [];
  }

  const url = new URL(SEARCH_URL);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("addressdetails", "1");
  url.searchParams.set("limit", "5");
  url.searchParams.set("countrycodes", "in");
  url.searchParams.set("q", trimmed);

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("Location search failed.");
  }

  return response.json();
}

function renderSuggestions(list, places, onPick) {
  list.innerHTML = "";

  if (!places.length) {
    clearSuggestions(list);
    return;
  }

  places.forEach((place) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion-item";
    button.textContent = place.display_name;
    button.addEventListener("click", () => {
      clearSuggestions(list);
      onPick({
        label: place.display_name,
        lat: Number(place.lat),
        lon: Number(place.lon),
      });
    });
    list.appendChild(button);
  });

  list.hidden = false;
}

function setPickup(place) {
  selectedPickup = place;
  pickupInput.value = place.label;
  resultPickup.textContent = titleCase(place.label);
  setMapMessage("Pickup location selected.", "info");
}

function setDrop(place) {
  selectedDrop = place;
  dropInput.value = place.label;
  resultDrop.textContent = titleCase(place.label);
  setMapMessage("Drop location selected.", "info");
}

function updateSummary(distanceKm) {
  resultPickup.textContent = titleCase(selectedPickup.label);
  resultDrop.textContent = titleCase(selectedDrop.label);
  resultService.textContent = selectedService;
  resultDistance.textContent = formatKm(distanceKm);
  resultFare.textContent = formatMoney(estimateFare(distanceKm));
  resultEta.textContent = `${estimateEta(distanceKm)} min`;
  setNote(`Route traced successfully. Distance: ${formatKm(distanceKm)}.`, "success");
  setMapMessage(`Route ready. Distance ${formatKm(distanceKm)}.`, "success");
}

async function traceRoute() {
  const rate = SERVICE_RATES[selectedService] || SERVICE_RATES["Bike-Taxi"];
  if (!rate.bookable) {
    showEmptyState();
    setNote(`${selectedService} selected. Ride fare booking is available for Bike-Taxi, Auto, and Cab.`, "info");
    setMapMessage(`${selectedService} selected. Choose Bike-Taxi, Auto, or Cab for live route pricing.`, "info");
    return;
  }

  if (!selectedPickup || !selectedDrop) {
    showEmptyState();
    setNote("Please select pickup and drop from the location suggestions.", "error");
    return;
  }

  const coords = `${selectedPickup.lon},${selectedPickup.lat};${selectedDrop.lon},${selectedDrop.lat}`;
  const url = `${ROUTE_URL}/${coords}?overview=full&geometries=geojson`;

  try {
    setMapMessage("Tracing route and calculating price...", "info");
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("Route request failed.");
    }

    const data = await response.json();
    const route = data.routes?.[0];

    if (!route) {
      throw new Error("No route found.");
    }

    updateSummary(route.distance / 1000);
  } catch (error) {
    console.error(error);
    setMapMessage("Route service is busy. Try another nearby location.", "error");
    setNote("Could not trace this route right now. Please try again.", "error");
  }
}

const searchPickup = debounce(async () => {
  selectedPickup = null;
  resultPickup.textContent = pickupInput.value.trim() || "Enter a pickup location";

  try {
    const places = await searchPlaces(pickupInput.value);
    renderSuggestions(pickupSuggestions, places, setPickup);
  } catch (error) {
    console.error(error);
    clearSuggestions(pickupSuggestions);
    setMapMessage("Location search is unavailable right now.", "error");
  }
});

const searchDrop = debounce(async () => {
  selectedDrop = null;
  resultDrop.textContent = dropInput.value.trim() || "Enter a drop location";

  try {
    const places = await searchPlaces(dropInput.value);
    renderSuggestions(dropSuggestions, places, setDrop);
  } catch (error) {
    console.error(error);
    clearSuggestions(dropSuggestions);
    setMapMessage("Location search is unavailable right now.", "error");
  }
});

function initMap() {
  map = { center: DEFAULT_CENTER };
  setMapMessage("Location search ready. Map is hidden on the booking front-end.", "success");
  showEmptyState();
}

pickupInput.addEventListener("input", searchPickup);
dropInput.addEventListener("input", searchDrop);

serviceCards.forEach((card) => {
  card.addEventListener("click", () => {
    selectedService = card.dataset.service || "Bike-Taxi";
    resultService.textContent = selectedService;
    serviceCards.forEach((item) => item.classList.toggle("active", item === card));

    const rate = SERVICE_RATES[selectedService] || SERVICE_RATES["Bike-Taxi"];
    if (rate.bookable) {
      setNote(`${selectedService} selected. Select pickup and drop, then book ride.`, "info");
      setMapMessage(`${selectedService} selected from services.`, "info");

      if (selectedPickup && selectedDrop) {
        traceRoute();
      }

      return;
    }

    showEmptyState();
    setNote(`${selectedService} selected. This service is shown in the catalogue section.`, "info");
    setMapMessage(`${selectedService} selected from services.`, "info");
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await traceRoute();
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".field")) {
    clearSuggestions(pickupSuggestions);
    clearSuggestions(dropSuggestions);
  }
});

window.addEventListener("load", initMap);

contactForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const formData = new FormData(contactForm);
  const name = String(formData.get("name") || "").trim();
  const email = String(formData.get("email") || "").trim();
  const mobile = String(formData.get("mobile") || "").trim();
  const type = String(formData.get("type") || "").trim();
  const comment = String(formData.get("comment") || "").trim();
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const mobileOk = /^[6-9]\d{9}$/.test(mobile.replace(/\s+/g, ""));

  if (!name || !email || !mobile || !type || !comment) {
    contactStatus.textContent = "Please fill all required fields.";
    contactStatus.dataset.kind = "error";
    return;
  }

  if (!emailOk) {
    contactStatus.textContent = "Please enter a valid email address.";
    contactStatus.dataset.kind = "error";
    return;
  }

  if (!mobileOk) {
    contactStatus.textContent = "Please enter a valid 10 digit Indian mobile number.";
    contactStatus.dataset.kind = "error";
    return;
  }

  contactStatus.textContent = "Thanks! Your query has been submitted.";
  contactStatus.dataset.kind = "success";
  contactForm.reset();
});
