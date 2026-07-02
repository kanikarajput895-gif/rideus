const form = document.querySelector(".ride-form");
const pickupInput = document.querySelector('input[aria-label="Pickup location"]');
const dropInput = document.querySelector('input[aria-label="Drop location"]');

const resultPickup = document.getElementById("resultPickup");
const resultDrop = document.getElementById("resultDrop");
const resultFare = document.getElementById("resultFare");
const resultEta = document.getElementById("resultEta");
const resultNote = document.getElementById("resultNote");

function titleCase(value) {
  return value
    .trim()
    .replace(/\s+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function calcFare(pickup, drop) {
  const routeSize = pickup.length + drop.length;
  const base = 45;
  const variable = Math.max(15, Math.round(routeSize * 2.4));
  return base + variable;
}

function calcEta(pickup, drop) {
  const score = pickup.length + drop.length;
  return Math.max(8, Math.min(32, Math.round(score / 4) + 8));
}

function updateResult(message, kind = "info") {
  resultNote.textContent = message;
  resultNote.dataset.kind = kind;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const pickup = titleCase(pickupInput.value);
  const drop = titleCase(dropInput.value);

  if (!pickup || !drop) {
    updateResult("Please fill in both pickup and drop locations to continue.", "error");
    resultFare.textContent = "₹0";
    resultEta.textContent = "-- min";
    resultPickup.textContent = pickup || "Enter a pickup location";
    resultDrop.textContent = drop || "Enter a drop location";
    return;
  }

  const fare = calcFare(pickup, drop);
  const eta = calcEta(pickup, drop);

  resultPickup.textContent = pickup;
  resultDrop.textContent = drop;
  resultFare.textContent = `₹${fare}`;
  resultEta.textContent = `${eta} min`;
  updateResult(`Ride found successfully for ${pickup} to ${drop}.`, "success");
});

pickupInput.addEventListener("input", () => {
  if (pickupInput.value.trim()) {
    resultPickup.textContent = titleCase(pickupInput.value);
  }
});

dropInput.addEventListener("input", () => {
  if (dropInput.value.trim()) {
    resultDrop.textContent = titleCase(dropInput.value);
  }
});
