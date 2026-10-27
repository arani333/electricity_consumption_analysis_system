from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Prevents GUI thread crash
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sqlite3
import os

app = Flask(__name__)
DB_NAME = "electricity.db"

def init_db():
    """Initializes SQLite database and sample tables automatically."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS consumers (
            consumer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            consumer_type TEXT NOT NULL,
            region TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meters (
            meter_id INTEGER PRIMARY KEY AUTOINCREMENT,
            consumer_id INTEGER,
            meter_code TEXT UNIQUE NOT NULL,
            FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meter_readings (
            reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meter_id INTEGER,
            reading_date TEXT NOT NULL,
            cumulative_kwh REAL NOT NULL,
            FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE
        )
    """)
    
    # Insert sample seed data if tables are empty
    cursor.execute("SELECT COUNT(*) FROM consumers")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO consumers (consumer_type, region) VALUES ('Residential', 'North Zone'), ('Commercial', 'Downtown')")
        cursor.execute("INSERT INTO meters (consumer_id, meter_code) VALUES (1, 'MTR-1001'), (2, 'MTR-1002')")
        cursor.execute("INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh) VALUES (1, '2026-01-01', 1200.0), (1, '2026-02-01', 1650.0), (1, '2026-03-01', 150.0)")
        conn.commit()
        
    conn.close()

# ---> CRITICAL FIX: Run database initialization on startup for Gunicorn <---
init_db()

def analyze_readings(high_threshold=350):
    conn = sqlite3.connect(DB_NAME)
    query = """
        SELECT r.reading_id, m.meter_id, m.meter_code, c.consumer_type, r.reading_date, r.cumulative_kwh 
        FROM meter_readings r
        LEFT JOIN meters m ON r.meter_id = m.meter_id
        LEFT JOIN consumers c ON m.consumer_id = c.consumer_id
    """
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        return df

    df['reading_date'] = pd.to_datetime(df['reading_date'])
    df = df.sort_values(by=['meter_id', 'reading_date']).copy()

    df['prev_reading'] = df.groupby('meter_id')['cumulative_kwh'].shift(1)
    df['prev_date'] = df.groupby('meter_id')['reading_date'].shift(1)

    df['is_rollover'] = np.where(df['cumulative_kwh'] < df['prev_reading'], True, False)

    def compute_kwh(row):
        if pd.isna(row['prev_reading']):
            return 0.0
        if row['is_rollover']:
            return (100000 - row['prev_reading']) + row['cumulative_kwh']
        return row['cumulative_kwh'] - row['prev_reading']

    df['consumption_kwh'] = df.apply(compute_kwh, axis=1)
    df['is_chronology_valid'] = df.groupby('meter_id')['reading_date'].diff().dt.days >= 0
    df['is_chronology_valid'] = df['is_chronology_valid'].fillna(True)
    df['high_usage_flag'] = np.where(df['consumption_kwh'] > high_threshold, 'FLAGGED: High Usage', 'Normal')

    return df

@app.route("/")
def index():
    df = analyze_readings(high_threshold=350)
    
    os.makedirs('static/charts', exist_ok=True)
    plt.figure(figsize=(7, 4))
    
    if not df.empty:
        for meter_code, group in df.groupby('meter_code'):
            plt.plot(group['reading_date'], group['consumption_kwh'], marker='o', label=meter_code)
            
        # --- DYNAMIC X-AXIS FORMATTING ---
        ax = plt.gca()
        date_range = df['reading_date'].max() - df['reading_date'].min()
        
        if date_range.days <= 31:
            # Show daily ticks if range is within a month
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        elif date_range.days <= 365:
            # Show monthly ticks if range is within a year
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        else:
            # Show yearly ticks for long-term data
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))

    plt.title('Consumption Trends by Meter')
    plt.xlabel('Date')
    plt.ylabel('kWh')
    plt.xticks(rotation=30, ha='right')
    plt.gcf().autofmt_xdate()
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('static/charts/trend.png')
    plt.close()

    records = df.to_dict(orient='records') if not df.empty else []
    return render_template("index.html", records=records)

@app.route("/add_reading", methods=["POST"])
def add_reading():
    meter_id = request.form.get("meter_id")
    consumer_type = request.form.get("consumer_type")
    reading_date = request.form.get("reading_date")
    cumulative_kwh = request.form.get("cumulative_kwh")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check if this meter_id already exists in the meters table
    cursor.execute("SELECT consumer_id FROM meters WHERE meter_id = ?", (meter_id,))
    meter_row = cursor.fetchone()
    
    if not meter_row:
        # If the meter doesn't exist, create a new consumer and a new meter automatically
        cursor.execute("INSERT INTO consumers (consumer_type, region) VALUES (?, ?)", (consumer_type, "Default Region"))
        consumer_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO meters (meter_id, consumer_id, meter_code) VALUES (?, ?, ?)", 
                       (meter_id, consumer_id, f"MTR-100{meter_id}"))
    else:
        # If meter exists, update its consumer type
        consumer_id = meter_row[0]
        cursor.execute("UPDATE consumers SET consumer_type = ? WHERE consumer_id = ?", (consumer_type, consumer_id))

    # Insert the new meter reading
    cursor.execute(
        "INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh) VALUES (?, ?, ?)",
        (meter_id, reading_date, cumulative_kwh)
    )
    
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route("/delete_reading/<int:reading_id>", methods=["POST", "GET"])
def delete_reading(reading_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM meter_readings WHERE reading_id = ?", (reading_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)