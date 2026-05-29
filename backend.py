"""
Air Quality Monitoring Backend — FastAPI
CPCB Indian National AQI (NAQI) Standard
Accepts telemetry from ESP32 (MQ-7, MQ-135, DHT22, Sharp GP2Y10)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import sqlite3
import datetime
import math
import os
import logging

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "aqi_monitor.db")

# Indian NAQI PM2.5 breakpoints: (C_low, C_high, I_low, I_high)
PM25_BREAKPOINTS = [
    (0.0,   30.0,   0,   50),
    (31.0,  60.0,  51,  100),
    (61.0,  90.0, 101,  200),
    (91.0, 120.0, 201,  300),
    (121.0, 250.0, 301, 400),
    (251.0, 500.0, 401, 500),
]

# ─── Application ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="AQI Monitor Backend",
    description="Receives ESP32 sensor telemetry and stores CPCB-compliant Indian AQI data.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Model ──────────────────────────────────────────────────────────
class TelemetryPayload(BaseModel):
    co: float = Field(..., description="Carbon Monoxide concentration in ppm (MQ-7)")
    gas_raw: float = Field(..., description="Raw analog gas reading from MQ-135 (0–1023 or voltage)")
    temp: float = Field(..., description="Ambient temperature in °C from DHT22")
    humidity: float = Field(..., description="Relative humidity % from DHT22")
    pm25: float = Field(..., description="PM2.5 particulate concentration in µg/m³ from Sharp GP2Y10")

    @field_validator("pm25")
    @classmethod
    def pm25_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("pm25 must be ≥ 0 µg/m³")
        return v

    @field_validator("humidity")
    @classmethod
    def humidity_range(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError("humidity must be between 0 and 100 %")
        return v


# ─── Database Initializer ────────────────────────────────────────────────────
def init_db() -> None:
    """Create the telemetry table if it does not already exist."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    co          REAL    NOT NULL,
                    gas_raw     REAL    NOT NULL,
                    temp        REAL    NOT NULL,
                    humidity    REAL    NOT NULL,
                    pm25        REAL    NOT NULL,
                    indian_aqi  INTEGER NOT NULL
                )
            """)
            conn.commit()
            logger.info("Database initialised at: %s", DB_PATH)
    except sqlite3.Error as exc:
        logger.error("Failed to initialise database: %s", exc)
        raise RuntimeError(f"Database initialisation error: {exc}") from exc


# ─── AQI Calculation ─────────────────────────────────────────────────────────
def calculate_indian_aqi(pm25_concentration: float) -> int:
    """
    Compute Indian National AQI from PM2.5 concentration (µg/m³)
    using CPCB piecewise linear interpolation.

    Formula: AQI = ((I_high - I_low) / (C_high - C_low)) * (C_p - C_low) + I_low
    """
    # Round PM2.5 concentration to the nearest integer per CPCB guidelines
    c = round(pm25_concentration)

    # Cap at maximum breakpoint
    if c > 500:
        return 500

    for c_low, c_high, i_low, i_high in PM25_BREAKPOINTS:
        if c_low <= c <= c_high:
            aqi = ((i_high - i_low) / (c_high - c_low)) * (c - c_low) + i_low
            return math.floor(aqi)

    # Value exactly 0
    if c == 0:
        return 0

    # Fallback — should never reach here for valid input
    return 500


# ─── Startup Event ────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    init_db()
    logger.info("FastAPI AQI Monitor started.")


# ─── Telemetry Endpoint ───────────────────────────────────────────────────────
@app.post("/api/telemetry", status_code=201, summary="Ingest ESP32 sensor telemetry")
async def receive_telemetry(payload: TelemetryPayload):
    """
    Accept a JSON telemetry packet from the ESP32, compute Indian AQI,
    and persist all fields to SQLite.

    Returns:
        201 Created — record saved successfully with computed AQI.
        422 Unprocessable Entity — invalid field values.
        503 Service Unavailable — database write failure.
    """
    aqi_value = calculate_indian_aqi(payload.pm25)
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute(
                """
                INSERT INTO telemetry (timestamp, co, gas_raw, temp, humidity, pm25, indian_aqi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    payload.co,
                    payload.gas_raw,
                    payload.temp,
                    payload.humidity,
                    payload.pm25,
                    aqi_value,
                ),
            )
            conn.commit()
    except sqlite3.OperationalError as exc:
        logger.error("Database write failed (possible lock): %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable — {exc}. Retry in a moment.",
        )
    except sqlite3.Error as exc:
        logger.error("SQLite error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Unexpected database error: {exc}")

    logger.info(
        "Telemetry stored — PM2.5: %.2f µg/m³ | Indian AQI: %d | Temp: %.1f°C | "
        "Humidity: %.1f%% | CO: %.4f ppm",
        payload.pm25, aqi_value, payload.temp, payload.humidity, payload.co,
    )

    return {
        "status": "ok",
        "timestamp": timestamp,
        "indian_aqi": aqi_value,
        "message": f"Telemetry recorded. Computed Indian AQI (PM2.5): {aqi_value}",
    }


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", summary="Service health probe")
async def health_check():
    """Returns 200 OK if the service and database are reachable."""
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": DB_PATH}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}")


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
