CREATE DATABASE IF NOT EXISTS rideus_booking;
USE rideus_booking;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(180) NOT NULL UNIQUE,
  mobile VARCHAR(24) NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drivers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  mobile VARCHAR(24) NOT NULL UNIQUE,
  vehicle_type VARCHAR(32) NOT NULL,
  vehicle_number VARCHAR(32) NOT NULL,
  is_available BOOLEAN DEFAULT TRUE,
  current_lat DECIMAL(10, 7),
  current_lon DECIMAL(10, 7),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(64) NOT NULL UNIQUE,
  base_fare DECIMAL(10, 2) NOT NULL,
  per_km DECIMAL(10, 2) NOT NULL,
  avg_speed_kmph INT NOT NULL,
  is_bookable BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS bookings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_mobile VARCHAR(24),
  driver_id INT NULL,
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
  final_fare DECIMAL(10, 2),
  coupon_code VARCHAR(64),
  payment_status VARCHAR(32) DEFAULT 'pending',
  cancel_reason TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'booked',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (driver_id) REFERENCES drivers(id)
);

CREATE TABLE IF NOT EXISTS payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  amount DECIMAL(10, 2) NOT NULL,
  method VARCHAR(32) DEFAULT 'cash',
  status VARCHAR(32) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS contacts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(180) NOT NULL,
  mobile VARCHAR(24) NOT NULL,
  user_type VARCHAR(64) NOT NULL,
  comment TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ratings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  rating INT NOT NULL,
  comment TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS saved_addresses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_mobile VARCHAR(24) NOT NULL,
  label VARCHAR(80) NOT NULL,
  address VARCHAR(255) NOT NULL,
  lat DECIMAL(10, 7),
  lon DECIMAL(10, 7),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sos_alerts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_mobile VARCHAR(24) NOT NULL,
  booking_id INT NULL,
  message TEXT,
  lat DECIMAL(10, 7),
  lon DECIMAL(10, 7),
  status VARCHAR(32) DEFAULT 'open',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coupons (
  code VARCHAR(64) PRIMARY KEY,
  discount_percent INT NOT NULL,
  max_discount DECIMAL(10, 2) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS auth_otps (
  mobile VARCHAR(24) PRIMARY KEY,
  otp VARCHAR(8) NOT NULL,
  token VARCHAR(128),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT IGNORE INTO services (name, base_fare, per_km, avg_speed_kmph, is_bookable) VALUES
('Bike', 25, 9, 28, TRUE),
('Auto', 35, 14, 22, TRUE),
('Cab', 55, 20, 26, TRUE);

INSERT IGNORE INTO drivers (name, mobile, vehicle_type, vehicle_number, current_lat, current_lon) VALUES
('Aarav Singh', '9000000001', 'Bike', 'RU-BIKE-101', 28.6139, 77.2090),
('Meera Khan', '9000000002', 'Auto', 'RU-AUTO-202', 28.6200, 77.2200),
('Kabir Rao', '9000000003', 'Cab', 'RU-CAB-303', 28.5900, 77.2300);

INSERT IGNORE INTO coupons (code, discount_percent, max_discount) VALUES
('RIDEUS10', 10, 80),
('FIRST50', 20, 50),
('SAFE25', 15, 25);
