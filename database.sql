CREATE DATABASE IF NOT EXISTS electricity_db;
USE electricity_db;

CREATE TABLE IF NOT EXISTS consumers (
    consumer_id INT PRIMARY KEY AUTO_INCREMENT,
    consumer_type VARCHAR(50) NOT NULL, 
    region VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS meters (
    meter_id INT PRIMARY KEY AUTO_INCREMENT,
    consumer_id INT,
    meter_code VARCHAR(50) UNIQUE NOT NULL,
    FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meter_readings (
    reading_id INT PRIMARY KEY AUTO_INCREMENT,
    meter_id INT,
    reading_date DATE NOT NULL,
    cumulative_kwh FLOAT NOT NULL,
    FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE
);

-- Insert sample seed data for testing
INSERT INTO consumers (consumer_type, region) VALUES ('Residential', 'North Zone'), ('Commercial', 'Downtown');
INSERT INTO meters (consumer_id, meter_code) VALUES (1, 'MTR-1001'), (2, 'MTR-1002');
INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh) VALUES 
(1, '2026-01-01', 1200.0),
(1, '2026-02-01', 1650.0),
(1, '2026-03-01', 150.0); -- Simulates a meter rollover