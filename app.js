const form = document.querySelector(".ride-form");
const pickupInput = document.getElementById("pickupInput");
const dropInput = document.getElementById("dropInput");
const resultPickup = document.getElementById("resultPickup");
const resultDrop = document.getElementById("resultDrop");
const resultFare = document.getElementById("resultFare");
const resultDistance = document.getElementById("resultDistance");
const resultEta = document.getElementById("resultEta");
const resultNote = document.getElementById("resultNote");
const mapStatus = document.getElementById("mapStatus");

const GOOGLE_MAPS_API_KEY = window.GOOGLE_MAPS_API_KEY || "";

let directionsService;
let directionsRenderer;
let pickupAutocomplete;
let dropAutocomplete;
let selectedPickup = null;
let selectedDrop = null;
let mapsReady = false;

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
  return `₹${Math.round(amount)}`;
}

function estimateFare(distanceKm) {
  const baseFare = 35;
  const perKm = 14;
  return baseFare + Math.max(distanceKm * perKm, 18);
}

function estimateEta(distanceKm) {
  return Math.max(8, Math.round(distanceKm * 3.5) + 4);
}

function manualDistanceEstimate() {
  const pickup = pickupInput.value.trim();
  const drop = dropInput.value.trim();
  const score = pickup.length + drop.length;
  return Math.max(1.5, Math.min(24, score / 8));
}

function manualResult() {
  const pickup = titleCase(pickupInput.value);
  const drop = titleCase(dropInput.value);

  if (!pickup || !drop) {
    resultPickup.textContent = pickup || "Enter a pickup location";
    resultDrop.textContent = drop || "Enter a drop location";
    resultDistance.textContent = "-- km";
    resultFare.textContent = "₹0";
    resultEta.textContent = "-- min";
    setNote("Please fill in both pickup and drop locations to continue.", "error");
    return;
  }

  const distanceKm = manualDistanceEstimate();
  resultPickup.textContent = pickup;
  resultDrop.textContent = drop;
  resultDistance.textContent = formatKm(distanceKm);
  resultFare.textContent = formatMoney(estimateFare(distanceKm));
  resultEta.textContent = `${estimateEta(distanceKm)} min`;
  setNote("Approximate pricing is showing until Google Maps is connected.", "info");
}

function makeLatLng(place) {
  if (!place?.geometry?.location) {
    return null;
  }

  return {
    lat: place.geometry.location.lat(),
    lng: place.geometry.location.lng(),
  };
}

function placeSummary(place, fallbackInput) {
  return titleCase(place?.formatted_address || place?.name || fallbackInput.value);
}

function loadGoogleMapsApi() {
  return new Promise((resolve, reject) => {
    if (window.google?.maps) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.async = true;
    script.defer = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&libraries=places`;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Google Maps API failed to load."));
    document.head.appendChild(script);
  });
}

function updateSummaryFromResult(routeResult) {
  const leg = routeResult.routes?.[0]?.legs?.[0];
  if (!leg) {
    throw new Error("Route data missing.");
  }

  const distanceKm = leg.distance.value / 1000;
  const fare = estimateFare(distanceKm);
  const etaSeconds = leg.duration_in_traffic?.value || leg.duration.value;

  resultPickup.textContent = titleCase(leg.start_address);
  resultDrop.textContent = titleCase(leg.end_address);
  resultDistance.textContent = formatKm(distanceKm);
  resultFare.textContent = formatMoney(fare);
  resultEta.textContent = `${Math.max(8, Math.round(etaSeconds / 60))} min`;
  setNote(`Route traced successfully. Distance: ${formatKm(distanceKm)}.`, "success");
  setMapMessage(`Live route ready. Distance ${formatKm(distanceKm)}.`, "success");
}

async function traceRoute() {
  if (!mapsReady || !directionsService || !directionsRenderer) {
    manualResult();
    return;
  }

  if (!selectedPickup || !selectedDrop || !selectedPickup.location || !selectedDrop.location) {
    manualResult();
    return;
  }

  try {
    const routeResult = await new Promise((resolve, reject) => {
      directionsService.route(
        {
          origin: selectedPickup.location,
          destination: selectedDrop.location,
          travelMode: google.maps.TravelMode.DRIVING,
          provideRouteAlternatives: false,
        },
        (response, status) => {
          if (status === "OK") {
            resolve(response);
            return;
          }

          reject(new Error(status));
        }
      );
    });

    directionsRenderer.setDirections(routeResult);
    updateSummaryFromResult(routeResult);
  } catch (error) {
    console.error(error);
    setMapMessage("Route lookup failed. Using a local estimate for now.", "error");
    manualResult();
  }
}

function attachAutocomplete() {
  pickupAutocomplete = new google.maps.places.Autocomplete(pickupInput, {
    fields: ["geometry", "formatted_address", "name"],
  });
  dropAutocomplete = new google.maps.places.Autocomplete(dropInput, {
    fields: ["geometry", "formatted_address", "name"],
  });

  pickupAutocomplete.addListener("place_changed", () => {
    const place = pickupAutocomplete.getPlace();
    selectedPickup = {
      location: makeLatLng(place),
      label: placeSummary(place, pickupInput),
    };
    pickupInput.value = selectedPickup.label;
    resultPickup.textContent = selectedPickup.label;
    setMapMessage("Pickup location captured.", "info");
  });

  dropAutocomplete.addListener("place_changed", () => {
    const place = dropAutocomplete.getPlace();
    selectedDrop = {
      location: makeLatLng(place),
      label: placeSummary(place, dropInput),
    };
    dropInput.value = selectedDrop.label;
    resultDrop.textContent = selectedDrop.label;
    setMapMessage("Drop location captured.", "info");
  });

  pickupInput.addEventListener("input", () => {
    selectedPickup = null;
  });

  dropInput.addEventListener("input", () => {
    selectedDrop = null;
  });
}

async function initMaps() {
  if (!GOOGLE_MAPS_API_KEY) {
    setMapMessage("Add your Google Maps API key in index.html to enable live route tracing.", "error");
    manualResult();
    return;
  }

  try {
    await loadGoogleMapsApi();

    const map = new google.maps.Map(document.getElementById("map"), {
      center: { lat: 28.6139, lng: 77.209 },
      zoom: 11,
      disableDefaultUI: true,
      gestureHandling: "greedy",
      styles: [
        { featureType: "poi", stylers: [{ visibility: "off" }] },
        { featureType: "transit", stylers: [{ visibility: "off" }] },
      ],
    });

    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({
      map,
      preserveViewport: false,
      suppressMarkers: false,
      polylineOptions: {
        strokeColor: "#f7c51d",
        strokeOpacity: 0.95,
        strokeWeight: 6,
      },
    });

    attachAutocomplete();
    mapsReady = true;
    setMapMessage("Map ready. Choose pickup and drop to trace the route.", "success");
    manualResult();
  } catch (error) {
    console.error(error);
    setMapMessage("Google Maps could not load. Using approximate pricing instead.", "error");
    manualResult();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await traceRoute();
});

pickupInput.addEventListener("blur", () => {
  if (!pickupInput.value.trim()) {
    resultPickup.textContent = "Enter a pickup location";
  }
});

dropInput.addEventListener("blur", () => {
  if (!dropInput.value.trim()) {
    resultDrop.textContent = "Enter a drop location";
  }
});

initMaps();
