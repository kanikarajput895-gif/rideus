from __future__ import annotations

import os
import random
import secrets
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import mysql.connector
import numpy as np
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestRegressor


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = Path(tempfile.gettempdir()) / "RideUS" / "rideus_app.db"
SQLITE_PATH = Path(os.getenv("RIDEUS_SQLITE_PATH", DEFAULT_SQLITE_PATH))

SERVICES: dict[str, dict[str, Any]] = {
    "Bike": {"base": 25, "per_km": 9, "speed": 28, "bookable": True},
    "Auto": {"base": 35, "per_km": 14, "speed": 22, "bookable": True},
    "Cab": {"base": 55, "per_km": 20, "speed": 26, "bookable": True},
}

SERVICE_INDEX = {name: index for index, name in enumerate(SERVICES)}


class SignupRequest(BaseModel):
    name: str = Field(min_length=2)
    email: str = Field(min_length=5)
    mobile: str = Field(min_length=8)


class LoginRequest(BaseModel):
    mobile: str = Field(min_length=8)


class OtpRequest(BaseModel):
    mobile: str = Field(min_length=8)


class VerifyOtpRequest(BaseModel):
    mobile: str = Field(min_length=8)
    otp: str = Field(min_length=4, max_length=8)


class FareRequest(BaseModel):
    pickup: str = Field(min_length=2)
    drop_location: str = Field(min_length=2)
    ride_type: str = "Bike"


class BookingRequest(FareRequest):
    user_mobile: str | None = None
    coupon_code: str | None = None


class StatusUpdate(BaseModel):
    status: str


class CancelRequest(BaseModel):
    reason: str = "Cancelled by user"


class ContactRequest(BaseModel):
    name: str = Field(min_length=2)
    email: str = Field(min_length=5)
    mobile: str = Field(min_length=8)
    user_type: str = "Customer"
    comment: str = Field(min_length=2)


class AiRideRequest(BaseModel):
    pickup: str = Field(min_length=2)
    drop_location: str = Field(min_length=2)
    passengers: int = Field(default=1, ge=1, le=4)
    priority: str = "balanced"


class AiSupportRequest(BaseModel):
    message: str = Field(min_length=2)


class SavedAddressRequest(BaseModel):
    user_mobile: str = Field(min_length=8)
    label: str = Field(min_length=2)
    address: str = Field(min_length=2)
    lat: float | None = None
    lon: float | None = None


class RatingRequest(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class SosRequest(BaseModel):
    user_mobile: str = Field(min_length=8)
    booking_id: int | None = None
    message: str = "Emergency help requested"
    lat: float | None = None
    lon: float | None = None


class PaymentRequest(BaseModel):
    booking_id: int
    method: str = "cash"


class CouponApplyRequest(BaseModel):
    code: str
    fare: float = Field(gt=0)


def train_fare_model() -> RandomForestRegressor:
    rows: list[list[float]] = []
    targets: list[float] = []
    for service_name, rate in SERVICES.items():
        if not rate["bookable"]:
            continue
        for distance in np.linspace(1, 45, 80):
            service_index = SERVICE_INDEX[service_name]
            traffic_factor = 1 + (distance % 7) * 0.025
            base_fare = rate["base"] + max(distance * rate["per_km"], 18)
            targets.append(base_fare * traffic_factor)
            rows.append([distance, service_index, rate["base"], rate["per_km"]])
    model = RandomForestRegressor(n_estimators=120, random_state=42)
    model.fit(np.array(rows), np.array(targets))
    return model


fare_model = train_fare_model()

app = FastAPI(title="RideUS Real Working API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def mysql_config() -> dict[str, Any] | None:
    host = os.getenv("MYSQL_HOST")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE", "rideus_booking")
    if not host or not user:
        return None
    return {
        "host": host,
        "user": user,
        "password": password or "",
        "database": database,
    }


@contextmanager
def db_connection() -> Iterator[tuple[Any, str]]:
    config = mysql_config()
    if config:
        conn = mysql.connector.connect(**config)
        try:
            yield conn, "mysql"
            conn.commit()
        finally:
            conn.close()
        return

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH, timeout=20)
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn, "sqlite"
        conn.commit()
    finally:
        conn.close()


def execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor


def init_db() -> None:
    with db_connection() as (conn, driver):
        if driver == "mysql":
            execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  name VARCHAR(120) NOT NULL,
                  email VARCHAR(180) NOT NULL UNIQUE,
                  mobile VARCHAR(24) NOT NULL UNIQUE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS bookings (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  user_mobile VARCHAR(24),
                  pickup VARCHAR(255) NOT NULL,
                  drop_location VARCHAR(255) NOT NULL,
                  pickup_lat DECIMAL(10, 7),
                  pickup_lon DECIMAL(10, 7),
                  drop_lat DECIMAL(10, 7),
                  drop_lon DECIMAL(10, 7),
                  distance_source VARCHAR(32) DEFAULT 'offline-estimator',
                  ride_type VARCHAR(32) NOT NULL,
                  distance_km DECIMAL(8, 2) NOT NULL,
                  eta_min INT NOT NULL,
                  estimated_fare DECIMAL(10, 2) NOT NULL,
                  status VARCHAR(32) NOT NULL DEFAULT 'booked',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS contacts (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  name VARCHAR(120) NOT NULL,
                  email VARCHAR(180) NOT NULL,
                  mobile VARCHAR(24) NOT NULL,
                  user_type VARCHAR(64) NOT NULL,
                  comment TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            ensure_real_world_tables(conn, driver)
            ensure_booking_columns(conn, driver)
            seed_reference_data(conn, driver)
            return

        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              mobile TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_mobile TEXT,
              pickup TEXT NOT NULL,
              drop_location TEXT NOT NULL,
              pickup_lat REAL,
              pickup_lon REAL,
              drop_lat REAL,
              drop_lon REAL,
              distance_source TEXT DEFAULT 'offline-estimator',
              ride_type TEXT NOT NULL,
              distance_km REAL NOT NULL,
              eta_min INTEGER NOT NULL,
              estimated_fare REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'booked',
              created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS contacts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL,
              mobile TEXT NOT NULL,
              user_type TEXT NOT NULL,
              comment TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        ensure_real_world_tables(conn, driver)
        ensure_booking_columns(conn, driver)
        seed_reference_data(conn, driver)


def ensure_booking_columns(conn: Any, driver: str) -> None:
    columns = {
        "driver_id": "INTEGER",
        "pickup_lat": "REAL",
        "pickup_lon": "REAL",
        "drop_lat": "REAL",
        "drop_lon": "REAL",
        "distance_source": "TEXT DEFAULT 'offline-estimator'",
        "cancel_reason": "TEXT",
        "payment_status": "TEXT DEFAULT 'pending'",
        "coupon_code": "TEXT",
        "final_fare": "REAL",
    }
    if driver == "mysql":
        columns = {
            "driver_id": "INT NULL",
            "pickup_lat": "DECIMAL(10, 7)",
            "pickup_lon": "DECIMAL(10, 7)",
            "drop_lat": "DECIMAL(10, 7)",
            "drop_lon": "DECIMAL(10, 7)",
            "distance_source": "VARCHAR(32) DEFAULT 'offline-estimator'",
            "cancel_reason": "TEXT",
            "payment_status": "VARCHAR(32) DEFAULT 'pending'",
            "coupon_code": "VARCHAR(64)",
            "final_fare": "DECIMAL(10, 2)",
        }
        for name, sql_type in columns.items():
            try:
                execute(conn, f"ALTER TABLE bookings ADD COLUMN {name} {sql_type}")
            except Exception:
                pass
        return

    existing = {
        row["name"]
        for row in execute(conn, "PRAGMA table_info(bookings)").fetchall()
    }
    for name, sql_type in columns.items():
        if name not in existing:
            execute(conn, f"ALTER TABLE bookings ADD COLUMN {name} {sql_type}")


def ensure_real_world_tables(conn: Any, driver: str) -> None:
    if driver == "mysql":
        statements = [
            """
            CREATE TABLE IF NOT EXISTS drivers (
              id INT AUTO_INCREMENT PRIMARY KEY,
              name VARCHAR(120) NOT NULL,
              mobile VARCHAR(24) NOT NULL UNIQUE,
              vehicle_type VARCHAR(32) NOT NULL,
              vehicle_number VARCHAR(32) NOT NULL,
              rating DECIMAL(3, 2) DEFAULT 4.8,
              is_available BOOLEAN DEFAULT TRUE,
              current_lat DECIMAL(10, 7),
              current_lon DECIMAL(10, 7),
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payments (
              id INT AUTO_INCREMENT PRIMARY KEY,
              booking_id INT NOT NULL,
              amount DECIMAL(10, 2) NOT NULL,
              method VARCHAR(32) DEFAULT 'cash',
              status VARCHAR(32) DEFAULT 'pending',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ratings (
              id INT AUTO_INCREMENT PRIMARY KEY,
              booking_id INT NOT NULL,
              rating INT NOT NULL,
              comment TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS saved_addresses (
              id INT AUTO_INCREMENT PRIMARY KEY,
              user_mobile VARCHAR(24) NOT NULL,
              label VARCHAR(80) NOT NULL,
              address VARCHAR(255) NOT NULL,
              lat DECIMAL(10, 7),
              lon DECIMAL(10, 7),
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sos_alerts (
              id INT AUTO_INCREMENT PRIMARY KEY,
              user_mobile VARCHAR(24) NOT NULL,
              booking_id INT NULL,
              message TEXT,
              lat DECIMAL(10, 7),
              lon DECIMAL(10, 7),
              status VARCHAR(32) DEFAULT 'open',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS coupons (
              code VARCHAR(64) PRIMARY KEY,
              discount_percent INT NOT NULL,
              max_discount DECIMAL(10, 2) NOT NULL,
              is_active BOOLEAN DEFAULT TRUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_otps (
              mobile VARCHAR(24) PRIMARY KEY,
              otp VARCHAR(8) NOT NULL,
              token VARCHAR(128),
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS drivers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              mobile TEXT NOT NULL UNIQUE,
              vehicle_type TEXT NOT NULL,
              vehicle_number TEXT NOT NULL,
              rating REAL DEFAULT 4.8,
              is_available INTEGER DEFAULT 1,
              current_lat REAL,
              current_lon REAL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL,
              amount REAL NOT NULL,
              method TEXT DEFAULT 'cash',
              status TEXT DEFAULT 'pending',
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ratings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL,
              rating INTEGER NOT NULL,
              comment TEXT,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS saved_addresses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_mobile TEXT NOT NULL,
              label TEXT NOT NULL,
              address TEXT NOT NULL,
              lat REAL,
              lon REAL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sos_alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_mobile TEXT NOT NULL,
              booking_id INTEGER,
              message TEXT,
              lat REAL,
              lon REAL,
              status TEXT DEFAULT 'open',
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS coupons (
              code TEXT PRIMARY KEY,
              discount_percent INTEGER NOT NULL,
              max_discount REAL NOT NULL,
              is_active INTEGER DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_otps (
              mobile TEXT PRIMARY KEY,
              otp TEXT NOT NULL,
              token TEXT,
              created_at TEXT NOT NULL
            )
            """,
        ]
    for statement in statements:
        execute(conn, statement)


def seed_reference_data(conn: Any, driver: str) -> None:
    now = datetime.utcnow().isoformat()
    driver_rows = [
        ("Aarav Singh", "9000000001", "Bike", "RU-BIKE-101", 28.6139, 77.2090),
        ("Meera Khan", "9000000002", "Auto", "RU-AUTO-202", 28.6200, 77.2200),
        ("Kabir Rao", "9000000003", "Cab", "RU-CAB-303", 28.5900, 77.2300),
        ("Isha Verma", "9000000004", "Bike", "RU-BIKE-404", 28.5355, 77.3910),
        ("Dev Patel", "9000000005", "Cab", "RU-CAB-505", 28.7041, 77.1025),
    ]
    coupon_rows = [
        ("RIDEUS10", 10, 80),
        ("FIRST50", 20, 50),
        ("SAFE25", 15, 25),
    ]
    if driver == "mysql":
        for row in driver_rows:
            execute(
                conn,
                """
                INSERT IGNORE INTO drivers
                  (name, mobile, vehicle_type, vehicle_number, current_lat, current_lon)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                row,
            )
        for row in coupon_rows:
            execute(
                conn,
                "INSERT IGNORE INTO coupons (code, discount_percent, max_discount) VALUES (%s, %s, %s)",
                row,
            )
        return

    for row in driver_rows:
        execute(
            conn,
            """
            INSERT OR IGNORE INTO drivers
              (name, mobile, vehicle_type, vehicle_number, current_lat, current_lon, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (*row, now),
        )
    for row in coupon_rows:
        execute(
            conn,
            "INSERT OR IGNORE INTO coupons (code, discount_percent, max_discount) VALUES (?, ?, ?)",
            row,
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


def stable_distance(pickup: str, drop_location: str) -> float:
    seed = abs(hash(f"{pickup.lower()}|{drop_location.lower()}"))
    return round(2.4 + (seed % 260) / 10, 1)


def geocode(place: str) -> tuple[float, float] | None:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "jsonv2", "limit": 1, "countrycodes": "in"},
            headers={"User-Agent": "rideus-student-project/1.0"},
            timeout=7,
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def route_details(pickup: str, drop_location: str) -> dict[str, Any]:
    start = geocode(pickup)
    end = geocode(drop_location)
    if not start or not end:
        return {
            "distance_km": stable_distance(pickup, drop_location),
            "distance_source": "offline-estimator",
            "pickup_lat": None,
            "pickup_lon": None,
            "drop_lat": None,
            "drop_lon": None,
        }

    try:
        coords = f"{start[1]},{start[0]};{end[1]},{end[0]}"
        response = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/{coords}",
            params={"overview": "false"},
            timeout=8,
        )
        response.raise_for_status()
        route = response.json()["routes"][0]
        distance = round(route["distance"] / 1000, 1)
        source = "osrm"
    except Exception:
        distance = stable_distance(pickup, drop_location)
        source = "geocoded-estimator"

    return {
        "distance_km": distance,
        "distance_source": source,
        "pickup_lat": start[0],
        "pickup_lon": start[1],
        "drop_lat": end[0],
        "drop_lon": end[1],
    }


def predict_fare(distance_km: float, ride_type: str) -> int:
    service = SERVICES.get(ride_type, SERVICES["Bike"])
    features = np.array([[distance_km, SERVICE_INDEX.get(ride_type, 0), service["base"], service["per_km"]]])
    return int(max(service["base"], round(float(fare_model.predict(features)[0]))))


def support_ai(message: str) -> dict[str, str]:
    text = message.lower()
    if any(word in text for word in ["cancel", "refund", "money", "payment", "paid"]):
        category = "payment_or_cancellation"
        priority = "high"
        reply = "I found a payment/cancellation concern. Please share your booking ID; the RideUS team should verify payment status and update you."
    elif any(word in text for word in ["driver", "captain", "unsafe", "rude", "helmet", "safety"]):
        category = "safety"
        priority = "urgent"
        reply = "This looks safety-related. RideUS should review this with priority and contact the user before closing the request."
    elif any(word in text for word in ["fare", "price", "expensive", "charge", "distance"]):
        category = "fare_query"
        priority = "medium"
        reply = "This looks like a fare query. Fare depends on distance, service type, and live route estimate."
    elif any(word in text for word in ["location", "pickup", "drop", "map", "wrong"]):
        category = "location_issue"
        priority = "medium"
        reply = "This appears to be a location issue. Ask the user to confirm pickup/drop spelling and nearby landmark."
    else:
        category = "general_support"
        priority = "normal"
        reply = "Thanks for contacting RideUS support. We have recorded your request and the team will review it."
    return {"category": category, "priority": priority, "suggested_reply": reply}


def recommend_service(distance_km: float, passengers: int, priority: str) -> str:
    priority = priority.lower()
    if passengers >= 3:
        return "Cab"
    if priority in {"cheap", "budget", "low fare"}:
        return "Bike" if passengers == 1 else "Auto"
    if priority in {"comfort", "safe", "premium"}:
        return "Cab"
    if distance_km <= 7 and passengers == 1:
        return "Bike"
    if distance_km <= 15:
        return "Auto"
    return "Cab"


def estimate_ride(payload: FareRequest) -> dict[str, Any]:
    service = SERVICES.get(payload.ride_type)
    if not service:
        raise HTTPException(status_code=400, detail="Invalid ride_type")
    if not service["bookable"]:
        raise HTTPException(status_code=400, detail=f"{payload.ride_type} is catalogue-only in booking flow")

    route = route_details(payload.pickup, payload.drop_location)
    distance_km = route["distance_km"]
    eta_min = max(8, round((distance_km / service["speed"]) * 60) + 5)
    fare = predict_fare(distance_km, payload.ride_type)
    return {
        "pickup": payload.pickup,
        "drop_location": payload.drop_location,
        "ride_type": payload.ride_type,
        "distance_km": distance_km,
        "eta_min": eta_min,
        "estimated_fare": fare,
        **route,
    }


def get_placeholder(driver: str) -> str:
    return "%s" if driver == "mysql" else "?"


def assign_driver(conn: Any, driver: str, ride_type: str) -> dict[str, Any] | None:
    placeholder = get_placeholder(driver)
    availability_check = "is_available = TRUE" if driver == "mysql" else "is_available = 1"
    cursor = execute(
        conn,
        f"""
        SELECT id, name, mobile, vehicle_type, vehicle_number, rating, current_lat, current_lon
        FROM drivers
        WHERE vehicle_type = {placeholder} AND {availability_check}
        ORDER BY rating DESC, id ASC
        LIMIT 1
        """,
        (ride_type,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
    driver_row = row_to_dict(row, columns)
    execute(conn, f"UPDATE drivers SET is_available = 0 WHERE id = {placeholder}", (driver_row["id"],))
    return driver_row


def release_driver_for_booking(conn: Any, driver: str, booking_id: int) -> None:
    placeholder = get_placeholder(driver)
    cursor = execute(conn, f"SELECT driver_id FROM bookings WHERE id = {placeholder}", (booking_id,))
    row = cursor.fetchone()
    if not row:
        return
    driver_id = row["driver_id"] if isinstance(row, sqlite3.Row) else row[0]
    if driver_id:
        execute(conn, f"UPDATE drivers SET is_available = 1 WHERE id = {placeholder}", (driver_id,))


def apply_coupon_value(conn: Any, driver: str, code: str | None, fare: float) -> tuple[float, float, str | None]:
    if not code:
        return fare, 0.0, None
    placeholder = get_placeholder(driver)
    active_check = "is_active = TRUE" if driver == "mysql" else "is_active = 1"
    cursor = execute(
        conn,
        f"SELECT code, discount_percent, max_discount FROM coupons WHERE UPPER(code) = UPPER({placeholder}) AND {active_check}",
        (code,),
    )
    row = cursor.fetchone()
    if not row:
        return fare, 0.0, None
    data = row_to_dict(row, [desc[0] for desc in cursor.description])
    discount = min(fare * (float(data["discount_percent"]) / 100), float(data["max_discount"]))
    return round(max(0, fare - discount), 2), round(discount, 2), str(data["code"])


def row_to_dict(row: Any, columns: list[str] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if columns:
        return dict(zip(columns, row))
    return dict(row)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "database": "mysql" if mysql_config() else "sqlite", "time": datetime.utcnow().isoformat()}


@app.get("/services")
def get_services() -> list[dict[str, Any]]:
    return [{"name": name, **data} for name, data in SERVICES.items()]


@app.get("/users/{mobile}/rides")
def user_rides(mobile: str) -> list[dict[str, Any]]:
    with db_connection() as (conn, driver):
        placeholder = "%s" if driver == "mysql" else "?"
        cursor = execute(
            conn,
            f"SELECT * FROM bookings WHERE user_mobile = {placeholder} ORDER BY id DESC LIMIT 50",
            (mobile,),
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.post("/signup")
def signup(payload: SignupRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        placeholder = "%s" if driver == "mysql" else "?"
        cursor = execute(
            conn,
            f"SELECT id FROM users WHERE mobile = {placeholder} OR email = {placeholder} LIMIT 1",
            (payload.mobile, payload.email),
        )
        existing = cursor.fetchone()
        if existing:
            user_id = existing["id"] if isinstance(existing, sqlite3.Row) else existing[0]
            if driver == "mysql":
                execute(
                    conn,
                    "UPDATE users SET name = %s, email = %s, mobile = %s WHERE id = %s",
                    (payload.name, payload.email, payload.mobile, user_id),
                )
            else:
                execute(
                    conn,
                    "UPDATE users SET name = ?, email = ?, mobile = ? WHERE id = ?",
                    (payload.name, payload.email, payload.mobile, user_id),
                )
            return {"id": user_id, "name": payload.name, "mobile": payload.mobile, "status": "updated"}

        if driver == "mysql":
            cursor = execute(
                conn,
                "INSERT INTO users (name, email, mobile) VALUES (%s, %s, %s)",
                (payload.name, payload.email, payload.mobile),
            )
        else:
            cursor = execute(
                conn,
                "INSERT INTO users (name, email, mobile, created_at) VALUES (?, ?, ?, ?)",
                (payload.name, payload.email, payload.mobile, now),
            )
    return {"id": cursor.lastrowid, "name": payload.name, "mobile": payload.mobile, "status": "created"}


@app.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    with db_connection() as (conn, driver):
        placeholder = "%s" if driver == "mysql" else "?"
        cursor = execute(conn, f"SELECT id, name, email, mobile FROM users WHERE mobile = {placeholder}", (payload.mobile,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found. Please signup first.")
    columns = ["id", "name", "email", "mobile"]
    return row_to_dict(row, columns)


@app.post("/auth/request-otp")
def request_otp(payload: OtpRequest) -> dict[str, Any]:
    otp = f"{random.randint(100000, 999999)}"
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        if driver == "mysql":
            execute(
                conn,
                """
                INSERT INTO auth_otps (mobile, otp, token)
                VALUES (%s, %s, NULL)
                ON DUPLICATE KEY UPDATE otp = VALUES(otp), token = NULL
                """,
                (payload.mobile, otp),
            )
        else:
            execute(
                conn,
                "INSERT OR REPLACE INTO auth_otps (mobile, otp, token, created_at) VALUES (?, ?, NULL, ?)",
                (payload.mobile, otp, now),
            )
    return {
        "mobile": payload.mobile,
        "status": "otp_sent_mock",
        "dev_otp": otp,
        "message": "Attach SMS provider later. For demo, use dev_otp.",
    }


@app.post("/auth/verify-otp")
def verify_otp(payload: VerifyOtpRequest) -> dict[str, Any]:
    with db_connection() as (conn, driver):
        placeholder = get_placeholder(driver)
        cursor = execute(
            conn,
            f"SELECT otp FROM auth_otps WHERE mobile = {placeholder}",
            (payload.mobile,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OTP not requested")
        expected = row["otp"] if isinstance(row, sqlite3.Row) else row[0]
        if str(expected) != payload.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        token = secrets.token_urlsafe(32)
        execute(
            conn,
            f"UPDATE auth_otps SET token = {placeholder} WHERE mobile = {placeholder}",
            (token, payload.mobile),
        )
    return {"mobile": payload.mobile, "token": token, "status": "verified"}


@app.post("/estimate-fare")
def estimate_fare(payload: FareRequest) -> dict[str, Any]:
    return estimate_ride(payload)


@app.post("/ai/ride-advice")
def ai_ride_advice(payload: AiRideRequest) -> dict[str, Any]:
    route = route_details(payload.pickup, payload.drop_location)
    distance_km = route["distance_km"]
    recommended = recommend_service(distance_km, payload.passengers, payload.priority)
    estimates = []
    for service_name, service in SERVICES.items():
        fare = predict_fare(distance_km, service_name)
        eta_min = max(8, round((distance_km / service["speed"]) * 60) + 5)
        estimates.append(
            {
                "ride_type": service_name,
                "fare": fare,
                "eta_min": eta_min,
                "reason": "recommended" if service_name == recommended else "available",
            }
        )
    return {
        "pickup": payload.pickup,
        "drop_location": payload.drop_location,
        "distance_km": distance_km,
        **route,
        "recommended_ride": recommended,
        "ai_summary": f"RideUS AI recommends {recommended} for {distance_km:.1f} km with {payload.passengers} passenger(s), based on your '{payload.priority}' priority.",
        "estimates": estimates,
    }


@app.post("/ai/support")
def ai_support(payload: AiSupportRequest) -> dict[str, str]:
    return support_ai(payload.message)


@app.post("/book-ride")
def book_ride(payload: BookingRequest) -> dict[str, Any]:
    estimate = estimate_ride(payload)
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        assigned_driver = assign_driver(conn, driver, estimate["ride_type"])
        final_fare, discount, coupon_code = apply_coupon_value(
            conn,
            driver,
            payload.coupon_code,
            float(estimate["estimated_fare"]),
        )
        status = "accepted" if assigned_driver else "booked"
        if driver == "mysql":
            cursor = execute(
                conn,
                """
                INSERT INTO bookings
                  (user_mobile, driver_id, pickup, drop_location, pickup_lat, pickup_lon, drop_lat, drop_lon, distance_source, ride_type, distance_km, eta_min, estimated_fare, final_fare, coupon_code, payment_status, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                """,
                (
                    payload.user_mobile,
                    assigned_driver["id"] if assigned_driver else None,
                    estimate["pickup"],
                    estimate["drop_location"],
                    estimate["pickup_lat"],
                    estimate["pickup_lon"],
                    estimate["drop_lat"],
                    estimate["drop_lon"],
                    estimate["distance_source"],
                    estimate["ride_type"],
                    estimate["distance_km"],
                    estimate["eta_min"],
                    estimate["estimated_fare"],
                    final_fare,
                    coupon_code,
                    status,
                ),
            )
        else:
            cursor = execute(
                conn,
                """
                INSERT INTO bookings
                  (user_mobile, driver_id, pickup, drop_location, pickup_lat, pickup_lon, drop_lat, drop_lon, distance_source, ride_type, distance_km, eta_min, estimated_fare, final_fare, coupon_code, payment_status, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    payload.user_mobile,
                    assigned_driver["id"] if assigned_driver else None,
                    estimate["pickup"],
                    estimate["drop_location"],
                    estimate["pickup_lat"],
                    estimate["pickup_lon"],
                    estimate["drop_lat"],
                    estimate["drop_lon"],
                    estimate["distance_source"],
                    estimate["ride_type"],
                    estimate["distance_km"],
                    estimate["eta_min"],
                    estimate["estimated_fare"],
                    final_fare,
                    coupon_code,
                    status,
                    now,
                ),
            )
    return {
        "booking_id": cursor.lastrowid,
        "status": status,
        "driver": assigned_driver,
        "discount": discount,
        "final_fare": final_fare,
        "payment_status": "pending",
        "coupon_code": coupon_code,
        **estimate,
    }


@app.get("/ride-status/{booking_id}")
def ride_status(booking_id: int) -> dict[str, Any]:
    with db_connection() as (conn, driver):
        placeholder = "%s" if driver == "mysql" else "?"
        cursor = execute(conn, f"SELECT * FROM bookings WHERE id = {placeholder}", (booking_id,))
        row = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    return row_to_dict(row, columns)


@app.post("/ride-status/{booking_id}")
def update_status(booking_id: int, payload: StatusUpdate) -> dict[str, Any]:
    allowed = {"booked", "accepted", "ongoing", "completed", "cancelled"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(allowed)}")
    with db_connection() as (conn, driver):
        placeholder = get_placeholder(driver)
        execute(conn, f"UPDATE bookings SET status = {placeholder} WHERE id = {placeholder}", (payload.status, booking_id))
        if payload.status in {"completed", "cancelled"}:
            release_driver_for_booking(conn, driver, booking_id)
    return {"booking_id": booking_id, "status": payload.status}


@app.post("/cancel-ride/{booking_id}")
def cancel_ride(booking_id: int, payload: CancelRequest | None = None) -> dict[str, Any]:
    reason = payload.reason if payload else "Cancelled by user"
    with db_connection() as (conn, driver):
        placeholder = get_placeholder(driver)
        execute(
            conn,
            f"UPDATE bookings SET status = {placeholder}, cancel_reason = {placeholder} WHERE id = {placeholder}",
            ("cancelled", reason, booking_id),
        )
        release_driver_for_booking(conn, driver, booking_id)
    return {"booking_id": booking_id, "status": "cancelled", "reason": reason}


@app.post("/contact")
def contact(payload: ContactRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    ai = support_ai(payload.comment)
    with db_connection() as (conn, driver):
        if driver == "mysql":
            cursor = execute(
                conn,
                "INSERT INTO contacts (name, email, mobile, user_type, comment) VALUES (%s, %s, %s, %s, %s)",
                (payload.name, payload.email, payload.mobile, payload.user_type, payload.comment),
            )
        else:
            cursor = execute(
                conn,
                "INSERT INTO contacts (name, email, mobile, user_type, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (payload.name, payload.email, payload.mobile, payload.user_type, payload.comment, now),
            )
    return {"contact_id": cursor.lastrowid, "status": "saved", "ai": ai}


@app.get("/saved-addresses/{mobile}")
def saved_addresses(mobile: str) -> list[dict[str, Any]]:
    with db_connection() as (conn, driver):
        placeholder = get_placeholder(driver)
        cursor = execute(
            conn,
            f"SELECT * FROM saved_addresses WHERE user_mobile = {placeholder} ORDER BY id DESC",
            (mobile,),
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.post("/saved-addresses")
def save_address(payload: SavedAddressRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    lat = payload.lat
    lon = payload.lon
    if lat is None or lon is None:
        coords = geocode(payload.address)
        if coords:
            lat, lon = coords
    with db_connection() as (conn, driver):
        if driver == "mysql":
            cursor = execute(
                conn,
                """
                INSERT INTO saved_addresses (user_mobile, label, address, lat, lon)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (payload.user_mobile, payload.label, payload.address, lat, lon),
            )
        else:
            cursor = execute(
                conn,
                """
                INSERT INTO saved_addresses (user_mobile, label, address, lat, lon, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.user_mobile, payload.label, payload.address, lat, lon, now),
            )
    return {"address_id": cursor.lastrowid, "status": "saved", "lat": lat, "lon": lon}


@app.get("/coupons")
def coupons() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT * FROM coupons")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.post("/coupons/apply")
def apply_coupon(payload: CouponApplyRequest) -> dict[str, Any]:
    with db_connection() as (conn, driver):
        final_fare, discount, code = apply_coupon_value(conn, driver, payload.code, payload.fare)
    if not code:
        raise HTTPException(status_code=404, detail="Coupon not found or inactive")
    return {"code": code, "original_fare": payload.fare, "discount": discount, "final_fare": final_fare}


@app.post("/payments/mock")
def mock_payment(payload: PaymentRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        placeholder = get_placeholder(driver)
        cursor = execute(
            conn,
            f"SELECT final_fare, estimated_fare FROM bookings WHERE id = {placeholder}",
            (payload.booking_id,),
        )
        booking = cursor.fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        fare = booking["final_fare"] if isinstance(booking, sqlite3.Row) else booking[0]
        estimated = booking["estimated_fare"] if isinstance(booking, sqlite3.Row) else booking[1]
        amount = float(fare or estimated or 0)
        if driver == "mysql":
            cursor = execute(
                conn,
                "INSERT INTO payments (booking_id, amount, method, status) VALUES (%s, %s, %s, 'paid')",
                (payload.booking_id, amount, payload.method),
            )
        else:
            cursor = execute(
                conn,
                "INSERT INTO payments (booking_id, amount, method, status, created_at) VALUES (?, ?, ?, 'paid', ?)",
                (payload.booking_id, amount, payload.method, now),
            )
        execute(conn, f"UPDATE bookings SET payment_status = {placeholder} WHERE id = {placeholder}", ("paid", payload.booking_id))
    return {"payment_id": cursor.lastrowid, "booking_id": payload.booking_id, "amount": amount, "status": "paid"}


@app.post("/ratings")
def rate_ride(payload: RatingRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        if driver == "mysql":
            cursor = execute(
                conn,
                "INSERT INTO ratings (booking_id, rating, comment) VALUES (%s, %s, %s)",
                (payload.booking_id, payload.rating, payload.comment),
            )
        else:
            cursor = execute(
                conn,
                "INSERT INTO ratings (booking_id, rating, comment, created_at) VALUES (?, ?, ?, ?)",
                (payload.booking_id, payload.rating, payload.comment, now),
            )
    return {"rating_id": cursor.lastrowid, "status": "saved"}


@app.post("/sos")
def create_sos(payload: SosRequest) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with db_connection() as (conn, driver):
        if driver == "mysql":
            cursor = execute(
                conn,
                """
                INSERT INTO sos_alerts (user_mobile, booking_id, message, lat, lon)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (payload.user_mobile, payload.booking_id, payload.message, payload.lat, payload.lon),
            )
        else:
            cursor = execute(
                conn,
                """
                INSERT INTO sos_alerts (user_mobile, booking_id, message, lat, lon, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (payload.user_mobile, payload.booking_id, payload.message, payload.lat, payload.lon, now),
            )
    return {"sos_id": cursor.lastrowid, "status": "open", "message": "SOS alert sent to RideUS admin"}


@app.get("/admin/bookings")
def admin_bookings() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(
            conn,
            """
            SELECT b.*, d.name AS driver_name, d.mobile AS driver_mobile, d.vehicle_number
            FROM bookings b
            LEFT JOIN drivers d ON b.driver_id = d.id
            ORDER BY b.id DESC
            LIMIT 100
            """,
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.get("/admin/users")
def admin_users() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT id, name, email, mobile, created_at FROM users ORDER BY id DESC LIMIT 200")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.get("/admin/contacts")
def admin_contacts() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT * FROM contacts ORDER BY id DESC LIMIT 100")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.get("/admin/drivers")
def admin_drivers() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT * FROM drivers ORDER BY id DESC LIMIT 200")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.get("/admin/payments")
def admin_payments() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT * FROM payments ORDER BY id DESC LIMIT 100")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.get("/admin/sos")
def admin_sos() -> list[dict[str, Any]]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT * FROM sos_alerts ORDER BY id DESC LIMIT 100")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [row_to_dict(row, columns) for row in rows]


@app.post("/admin/bookings/{booking_id}/status")
def admin_update_booking_status(booking_id: int, payload: StatusUpdate) -> dict[str, Any]:
    return update_status(booking_id, payload)


@app.get("/admin/summary")
def admin_summary() -> dict[str, Any]:
    with db_connection() as (conn, _driver):
        cursor = execute(conn, "SELECT COUNT(*), COALESCE(SUM(estimated_fare), 0), COALESCE(AVG(distance_km), 0) FROM bookings")
        total_bookings, revenue, avg_distance = cursor.fetchone()
        total_users = execute(conn, "SELECT COUNT(*) FROM users").fetchone()[0]
        total_contacts = execute(conn, "SELECT COUNT(*) FROM contacts").fetchone()[0]
        active_rides = execute(conn, "SELECT COUNT(*) FROM bookings WHERE status IN ('booked', 'accepted', 'ongoing')").fetchone()[0]
        total_drivers = execute(conn, "SELECT COUNT(*) FROM drivers").fetchone()[0]
        available_drivers = execute(conn, "SELECT COUNT(*) FROM drivers WHERE is_available IN (1, TRUE)").fetchone()[0]
        open_sos = execute(conn, "SELECT COUNT(*) FROM sos_alerts WHERE status = 'open'").fetchone()[0]
    return {
        "total_users": int(total_users),
        "total_bookings": int(total_bookings),
        "active_rides": int(active_rides),
        "total_drivers": int(total_drivers),
        "available_drivers": int(available_drivers),
        "open_sos": int(open_sos),
        "support_requests": int(total_contacts),
        "estimated_revenue": float(revenue),
        "average_distance_km": round(float(avg_distance), 2),
    }


@app.get("/admin/ai-insights")
def admin_ai_insights() -> dict[str, Any]:
    with db_connection() as (conn, _driver):
        bookings_cursor = execute(conn, "SELECT ride_type, distance_km, estimated_fare, status FROM bookings ORDER BY id DESC LIMIT 200")
        bookings = [row_to_dict(row, [desc[0] for desc in bookings_cursor.description]) for row in bookings_cursor.fetchall()]

        contacts_cursor = execute(conn, "SELECT comment FROM contacts ORDER BY id DESC LIMIT 100")
        contacts = [row_to_dict(row, [desc[0] for desc in contacts_cursor.description]) for row in contacts_cursor.fetchall()]

    ride_counts: dict[str, int] = {}
    for booking in bookings:
        ride_type = str(booking.get("ride_type", "Unknown"))
        ride_counts[ride_type] = ride_counts.get(ride_type, 0) + 1

    support_categories: dict[str, int] = {}
    urgent_support = 0
    for contact_row in contacts:
        ai = support_ai(str(contact_row.get("comment", "")))
        support_categories[ai["category"]] = support_categories.get(ai["category"], 0) + 1
        if ai["priority"] in {"urgent", "high"}:
            urgent_support += 1

    top_ride = max(ride_counts, key=ride_counts.get) if ride_counts else "No rides yet"
    total_revenue = sum(float(item.get("estimated_fare") or 0) for item in bookings)
    avg_fare = round(total_revenue / len(bookings), 2) if bookings else 0

    recommendations = []
    if top_ride != "No rides yet":
        recommendations.append(f"{top_ride} is currently the most used RideUS service.")
    if urgent_support:
        recommendations.append(f"{urgent_support} urgent/high-priority support requests need author attention.")
    if avg_fare:
        recommendations.append(f"Average fare is Rs {avg_fare}; monitor long-distance cab rides for pricing quality.")
    if not recommendations:
        recommendations.append("No enough data yet. Book rides from the app to generate AI insights.")

    return {
        "top_ride_type": top_ride,
        "ride_counts": ride_counts,
        "support_categories": support_categories,
        "urgent_support_count": urgent_support,
        "average_fare": avg_fare,
        "recommendations": recommendations,
    }
