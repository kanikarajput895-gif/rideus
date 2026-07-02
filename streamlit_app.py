import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
import streamlit as st
from mysql.connector import Error, connect
from sklearn.ensemble import RandomForestRegressor


st.set_page_config(page_title="Rapido Ride Booking", page_icon="R", layout="wide")


@dataclass
class Location:
    label: str
    lat: float
    lon: float


RIDE_RATES = {
    "Bike": {"base": 25, "per_km": 9, "speed": 28},
    "Auto": {"base": 35, "per_km": 14, "speed": 22},
    "Cab": {"base": 55, "per_km": 20, "speed": 26},
}


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.strip().split())


@st.cache_data(show_spinner=False)
def geocode(query: str) -> list[Location]:
    if len(query.strip()) < 3:
        return []

    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "in",
            "addressdetails": 1,
        },
        headers={"User-Agent": "rapido-streamlit-learning-app/1.0"},
        timeout=10,
    )
    response.raise_for_status()

    return [
        Location(item["display_name"], float(item["lat"]), float(item["lon"]))
        for item in response.json()
    ]


def haversine_km(a: Location, b: Location) -> float:
    radius = 6371
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


@st.cache_resource(show_spinner=False)
def fare_model() -> RandomForestRegressor:
    rng = np.random.default_rng(42)
    distances = rng.uniform(1, 45, 420)
    ride_codes = rng.integers(0, 3, 420)
    hour = rng.integers(0, 24, 420)
    surge = np.where((hour >= 8) & (hour <= 11) | (hour >= 17) & (hour <= 21), 1.18, 1.0)
    base = np.choose(ride_codes, [25, 35, 55])
    per_km = np.choose(ride_codes, [9, 14, 20])
    fares = (base + distances * per_km) * surge + rng.normal(0, 5, 420)

    model = RandomForestRegressor(n_estimators=80, random_state=7)
    model.fit(pd.DataFrame({"distance_km": distances, "ride_code": ride_codes, "hour": hour}), fares)
    return model


def predict_fare(distance_km: float, ride_type: str) -> int:
    ride_code = list(RIDE_RATES).index(ride_type)
    hour = pd.Timestamp.now().hour
    prediction = fare_model().predict(
        pd.DataFrame([{"distance_km": distance_km, "ride_code": ride_code, "hour": hour}])
    )[0]
    return max(20, round(prediction))


def eta_minutes(distance_km: float, ride_type: str) -> int:
    speed = RIDE_RATES[ride_type]["speed"]
    return max(5, round((distance_km / speed) * 60 + 5))


def mysql_connection():
    required = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
    if not all(os.getenv(key) for key in required):
        return None

    return connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )


def save_booking(pickup: str, drop: str, distance: float, eta: int, fare: int, ride_type: str) -> bool:
    try:
        connection = mysql_connection()
        if connection is None:
            return False

        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO bookings
              (pickup, drop_location, distance_km, eta_min, estimated_fare, ride_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (pickup, drop, distance, eta, fare, ride_type),
        )
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error:
        return False


st.markdown(
    """
    <style>
      .stApp { background: linear-gradient(180deg, #fbfcff 0%, #eff5ff 100%); }
      h1 { font-family: Georgia, serif; letter-spacing: 0; }
      div[data-testid="stMetric"] {
        background: white;
        border: 1px solid rgba(25,31,44,.09);
        border-radius: 8px;
        padding: 14px 16px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([0.92, 1.08], gap="large")

with left:
    st.markdown("### rapido")
    st.title("India's #1 Ride-hailing App")
    st.caption("Quick, affordable rides at your doorstep")

    pickup_query = st.text_input("Pickup location", placeholder="Enter Pickup Location")
    drop_query = st.text_input("Drop location", placeholder="Enter Drop Location")
    ride_type = st.radio("Ride type", list(RIDE_RATES), horizontal=True)

    pickup_options = geocode(pickup_query) if pickup_query else []
    drop_options = geocode(drop_query) if drop_query else []

    pickup = st.selectbox(
        "Select pickup",
        pickup_options,
        format_func=lambda item: item.label,
        placeholder="Choose from search results",
        disabled=not pickup_options,
    )
    drop = st.selectbox(
        "Select drop",
        drop_options,
        format_func=lambda item: item.label,
        placeholder="Choose from search results",
        disabled=not drop_options,
    )

    booked = st.button("Book Ride", type="primary", use_container_width=True)

with right:
    st.subheader("Map and fare estimate")

    if pickup and drop:
        distance = haversine_km(pickup, drop) * 1.25
        fare = predict_fare(distance, ride_type)
        eta = eta_minutes(distance, ride_type)

        st.map(
            pd.DataFrame(
                [
                    {"lat": pickup.lat, "lon": pickup.lon},
                    {"lat": drop.lat, "lon": drop.lon},
                ]
            ),
            latitude="lat",
            longitude="lon",
            zoom=11,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Distance", f"{distance:.1f} km")
        c2.metric("ETA", f"{eta} min")
        c3.metric("Fare", f"Rs {fare}")

        if booked:
            saved = save_booking(pickup.label, drop.label, distance, eta, fare, ride_type)
            if saved:
                st.success("Ride booked and saved to MySQL.")
            else:
                st.info("Ride calculated. Add MySQL env vars to save bookings.")
    else:
        st.map(pd.DataFrame([{"lat": 28.6139, "lon": 77.209}]), latitude="lat", longitude="lon", zoom=10)
        st.info("Search and select both locations to calculate distance, ETA, and ML fare.")
