"""
ESP32 Sensor Simulator
──────────────────────
Sends realistic synthetic telemetry to the FastAPI backend every 3 seconds.
Use this to populate the dashboard without physical hardware during development.

Run with:  python simulate_esp32.py
"""

import time
import math
import random
import requests
import sys

BACKEND_URL = "http://127.0.0.1:8000/api/telemetry"
INTERVAL_SECONDS = 3
TOTAL_PACKETS = 200          # Set to 0 for infinite loop


def generate_reading(tick: int) -> dict:
    """
    Generate a synthetic sensor reading with realistic slow-varying values.
    Uses sine waves to simulate natural diurnal patterns.
    """
    # Temperature: 22–36 °C with gentle oscillation + noise
    temp = 28.0 + 6.0 * math.sin(tick / 40.0) + random.gauss(0, 0.4)
    temp = round(max(15.0, min(45.0, temp)), 2)

    # Humidity: inversely correlated with temperature (65–85 %)
    humidity = 75.0 - 0.8 * (temp - 28.0) + random.gauss(0, 1.2)
    humidity = round(max(20.0, min(99.0, humidity)), 2)

    # CO: 0.002–0.08 ppm with occasional spikes
    co_base = 0.01 + 0.02 * abs(math.sin(tick / 25.0))
    co_spike = random.choices([0.0, random.uniform(0.05, 0.15)], weights=[0.92, 0.08])[0]
    co = round(co_base + co_spike + random.gauss(0, 0.002), 6)
    co = max(0.0, co)

    # MQ-135 raw analog (0–1023 ADC equivalent)
    gas_raw = round(300 + 120 * abs(math.sin(tick / 30.0)) + random.gauss(0, 15), 2)
    gas_raw = max(0.0, min(1023.0, gas_raw))

    # PM2.5: sweeps through AQI bands over time for demo richness
    # Cycles through 0 → 300 µg/m³ → back over ~600 ticks
    pm25_base = 150.0 * (1 - math.cos(tick / 95.0))
    pm25_noise = random.gauss(0, 4.0)
    pm25 = round(max(0.0, min(500.0, pm25_base + pm25_noise)), 2)

    return {
        "co": co,
        "gas_raw": gas_raw,
        "temp": temp,
        "humidity": humidity,
        "pm25": pm25,
    }


def main():
    print("=" * 58)
    print("  ESP32 Telemetry Simulator")
    print(f"  Target : {BACKEND_URL}")
    print(f"  Interval: {INTERVAL_SECONDS}s  |  Packets: "
          f"{'∞' if TOTAL_PACKETS == 0 else TOTAL_PACKETS}")
    print("=" * 58)
    print()

    sent = 0
    tick = 0

    try:
        while True:
            payload = generate_reading(tick)
            try:
                resp = requests.post(BACKEND_URL, json=payload, timeout=5)
                if resp.status_code == 201:
                    data = resp.json()
                    print(
                        f"[PKT {sent+1:>4}] ✅  AQI={data['indian_aqi']:>3}  "
                        f"PM2.5={payload['pm25']:>6.1f} µg/m³  "
                        f"Temp={payload['temp']:>5.1f}°C  "
                        f"Hum={payload['humidity']:>5.1f}%  "
                        f"CO={payload['co']:.5f} ppm"
                    )
                else:
                    print(
                        f"[PKT {sent+1:>4}] ⚠️  HTTP {resp.status_code}  "
                        f"Response: {resp.text[:120]}"
                    )
            except requests.exceptions.ConnectionError:
                print(
                    f"[PKT {sent+1:>4}] ❌  Connection refused — "
                    "Is the FastAPI backend running on port 8000?"
                )
            except requests.exceptions.Timeout:
                print(f"[PKT {sent+1:>4}] ❌  Request timed out.")

            sent += 1
            tick += 1

            if TOTAL_PACKETS > 0 and sent >= TOTAL_PACKETS:
                print(f"\n✅  Simulation complete — {sent} packets sent.")
                break

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print(f"\n\n⏹  Simulator stopped by user. {sent} packets sent.")
        sys.exit(0)


if __name__ == "__main__":
    main()
