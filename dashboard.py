"""
Air Quality Monitoring Dashboard — Streamlit Frontend
Indian National AQI (NAQI) Standard — CPCB Color Banding
Reads from local SQLite database populated by the FastAPI backend.
"""

import sqlite3
import os
import datetime
import math

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

# ─── Page Configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="AQI Monitor | CPCB India",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Constants ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "aqi_monitor.db")

REFRESH_INTERVAL_MS = 5_000  # 5-second auto-refresh

# CPCB India AQI Color Bands
AQI_BANDS = [
    (0,   50,  "#00B050", "#FFFFFF", "Good"),
    (51,  100, "#92D050", "#1A1A1A", "Satisfactory"),
    (101, 200, "#FFFF00", "#1A1A1A", "Moderate"),
    (201, 300, "#FFC000", "#FFFFFF", "Poor"),
    (301, 400, "#FF0000", "#FFFFFF", "Very Poor"),
    (401, 500, "#C00000", "#FFFFFF", "Severe"),
]

TIME_FILTER_OPTIONS = {
    "Last 1 Hour": 60,
    "Last 12 Hours": 720,
    "All Records": None,
}

# Indian NAQI PM2.5 breakpoints for AQI calculation: (C_low, C_high, I_low, I_high)
PM25_BREAKPOINTS = [
    (0.0,   30.0,   0,   50),
    (31.0,  60.0,  51,  100),
    (61.0,  90.0, 101,  200),
    (91.0, 120.0, 201,  300),
    (121.0, 250.0, 301, 400),
    (251.0, 500.0, 401, 500),
]


def _calculate_indian_aqi(pm25_concentration: float) -> int:
    """Compute Indian National AQI from PM2.5 using CPCB piecewise linear interpolation."""
    c = round(pm25_concentration)
    if c > 500:
        return 500
    for c_low, c_high, i_low, i_high in PM25_BREAKPOINTS:
        if c_low <= c <= c_high:
            aqi = ((i_high - i_low) / (c_high - c_low)) * (c - c_low) + i_low
            return math.floor(aqi)
    if c == 0:
        return 0
    return 500


# ─── Demo Data (Fake Sensor Readings) ─────────────────────────────────────────
# Raw table from hardware testing session — used for demonstration without
# a live ESP32 or database.
_DEMO_RAW = [
    # (time_str, temp, humidity, mq135_raw, mq7_co_raw, sharp_pm25)
    ("9:00 AM",  28.4, 55, 1120, 850,  45),
    ("9:10 AM",  28.5, 55, 1125, 845,  60),
    ("9:20 AM",  28.6, 54, 1118, 860,  35),
    ("9:30 AM",  28.5, 54, 1130, 855,  50),
    ("9:40 AM",  29.1, 58, 1850, 920, 450),
    ("9:50 AM",  29.4, 62, 2100, 980, 1250),
    ("10:00 AM", 29.2, 60, 1540, 890, 320),
    ("10:10 AM", 28.9, 57, 1210, 865, 140),
    ("10:20 AM", 28.7, 56, 1140, 850,  85),
    ("10:30 AM", 28.6, 55, 1135, 840,  55),
    ("10:40 AM", 28.5, 55, 1128, 842,  40),
    ("10:50 AM", 28.8, 54, 2400, 1950, 110),
    ("11:00 AM", 29.1, 56, 3150, 2840, 240),
    ("11:10 AM", 29.5, 58, 3400, 3210, 410),
    ("11:20 AM", 29.2, 55, 2200, 1850, 180),
    ("11:30 AM", 28.8, 52, 1450, 1100,  95),
    ("11:40 AM", 28.6, 51, 1180, 890,  65),
    ("11:50 AM", 28.5, 52, 1130, 855,  50),
    ("12:00 PM", 28.4, 52, 1122, 848,  35),
]


def get_demo_dataframe() -> pd.DataFrame:
    """
    Build a demo DataFrame from the hardcoded sensor table.
    Uses today's date combined with the sample time values.
    Maps raw sensor columns to the dashboard's expected schema.
    """
    today = datetime.date.today()
    rows = []
    for time_str, temp, humidity, gas_raw, co_raw, pm25 in _DEMO_RAW:
        ts = datetime.datetime.combine(
            today,
            datetime.datetime.strptime(time_str, "%I:%M %p").time(),
        )
        # Convert MQ-7 raw analog to approximate ppm (simple model)
        co_ppm = round(co_raw / 1000.0, 4)
        aqi = _calculate_indian_aqi(pm25)
        rows.append({
            "timestamp": ts,
            "co": co_ppm,
            "gas_raw": float(gas_raw),
            "temp": temp,
            "humidity": humidity,
            "pm25": float(pm25),
            "indian_aqi": aqi,
        })
    return pd.DataFrame(rows)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  html, body, [class*="css"] {
      font-family: 'Inter', sans-serif;
  }

  /* Dark background */
  .stApp {
      background: linear-gradient(135deg, #0d0f14 0%, #111520 50%, #0a0d12 100%);
  }

  /* Sidebar */
  section[data-testid="stSidebar"] {
      background: rgba(255,255,255,0.03);
      border-right: 1px solid rgba(255,255,255,0.07);
  }

  /* Metric card style */
  .metric-card {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.09);
      border-radius: 16px;
      padding: 20px 24px;
      text-align: center;
      backdrop-filter: blur(12px);
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      position: relative;
      overflow: hidden;
  }
  .metric-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  .metric-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: linear-gradient(90deg, #00B050, #92D050, #FFFF00, #FFC000, #FF0000, #C00000);
  }

  .metric-label {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: rgba(255,255,255,0.45);
      margin-bottom: 8px;
  }

  .metric-value {
      font-size: 2.1rem;
      font-weight: 800;
      color: #FFFFFF;
      line-height: 1;
      margin-bottom: 4px;
  }

  .metric-unit {
      font-size: 0.75rem;
      font-weight: 400;
      color: rgba(255,255,255,0.38);
  }

  /* AQI card has dynamic background set inline */
  .aqi-badge {
      display: inline-block;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      margin-top: 8px;
  }

  /* Header */
  .dashboard-header {
      text-align: center;
      padding: 12px 0 28px 0;
  }
  .dashboard-header h1 {
      font-size: 2rem;
      font-weight: 800;
      color: #FFFFFF;
      margin: 0;
      letter-spacing: -0.02em;
  }
  .dashboard-header p {
      font-size: 0.85rem;
      color: rgba(255,255,255,0.4);
      margin: 6px 0 0 0;
  }

  /* Section titles */
  .section-title {
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: rgba(255,255,255,0.35);
      padding: 16px 0 10px 0;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      margin-bottom: 16px;
  }

  /* Divider */
  hr {
      border: none;
      border-top: 1px solid rgba(255,255,255,0.06);
      margin: 24px 0;
  }

  /* Timestamp */
  .timestamp-text {
      font-size: 0.72rem;
      color: rgba(255,255,255,0.3);
      text-align: right;
      font-style: italic;
  }

  /* Status dot */
  .status-dot {
      display: inline-block;
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #00B050;
      box-shadow: 0 0 8px #00B050;
      animation: pulse 2s infinite;
      margin-right: 6px;
  }
  @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.35; }
  }

  /* Empty state */
  .empty-state {
      background: rgba(255,255,255,0.03);
      border: 1px dashed rgba(255,255,255,0.12);
      border-radius: 12px;
      padding: 40px;
      text-align: center;
      color: rgba(255,255,255,0.4);
      font-size: 0.9rem;
  }
</style>
""", unsafe_allow_html=True)


# ─── Auto Refresh ─────────────────────────────────────────────────────────────
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="aqi_autorefresh")


# ─── Helper: AQI Band Lookup ──────────────────────────────────────────────────
def get_aqi_band(aqi: int) -> tuple:
    """Return (bg_color, text_color, label) for a given AQI integer."""
    for lo, hi, bg, fg, label in AQI_BANDS:
        if lo <= aqi <= hi:
            return bg, fg, label
    # Beyond 500 — treat as Severe
    return "#C00000", "#FFFFFF", "Severe"


# ─── Helper: Database Query ───────────────────────────────────────────────────
def fetch_data(minutes: int | None) -> pd.DataFrame:
    """
    Query the SQLite telemetry table.

    Args:
        minutes: If None, returns all records. Otherwise, filters to the
                 most recent `minutes` window using UTC timestamps.

    Returns:
        A pandas DataFrame with columns:
        [timestamp, co, gas_raw, temp, humidity, pm25, indian_aqi]
        Returns an empty DataFrame on any error.
    """
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()

    try:
        with sqlite3.connect(DB_PATH, timeout=8) as conn:
            if minutes is None:
                query = "SELECT * FROM telemetry ORDER BY timestamp ASC"
                df = pd.read_sql_query(query, conn)
            else:
                cutoff = (
                    datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)
                ).strftime("%Y-%m-%d %H:%M:%S")
                query = """
                    SELECT * FROM telemetry
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """
                df = pd.read_sql_query(query, conn, params=(cutoff,))

        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    except sqlite3.OperationalError as exc:
        st.error(
            f"⚠️ **Database Locked or Table Missing** — `{exc}`\n\n"
            "The database may still be initialising or is currently being written to. "
            "This page will auto-refresh in 5 seconds."
        )
        return pd.DataFrame()
    except Exception as exc:
        st.error(f"⚠️ **Unexpected error reading database** — `{exc}`")
        return pd.DataFrame()


# ─── Helper: Render Metric Card ───────────────────────────────────────────────
def render_metric_card(label: str, value: str, unit: str, icon: str = "") -> None:
    """Render a standard (non-AQI) dark-glass metric card."""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{icon} {label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-unit">{unit}</div>
    </div>
    """, unsafe_allow_html=True)


def render_aqi_card(aqi: int) -> None:
    """Render the AQI metric card with CPCB dynamic color banding."""
    bg, fg, label = get_aqi_band(aqi)
    st.markdown(f"""
    <div class="metric-card" style="background: {bg}22; border-color: {bg}55;">
        <div class="metric-label" style="color: {bg}cc;">🏭 Dust AQI (India)</div>
        <div class="metric-value" style="color: {bg};">{aqi}</div>
        <div class="aqi-badge" style="background: {bg}; color: {fg};">{label}</div>
    </div>
    """, unsafe_allow_html=True)


# ─── Plotly Chart: PM2.5 & AQI ────────────────────────────────────────────────
def render_pm25_aqi_chart(df: pd.DataFrame) -> None:
    """
    Render a dual-trace Plotly line chart:
      - Trace 1 (left Y-axis):  PM2.5 concentration in µg/m³
      - Trace 2 (right Y-axis): Calculated Indian AQI

    Includes CPCB AQI band shading in the background.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # PM2.5 trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["pm25"],
            name="PM2.5 (µg/m³)",
            mode="lines+markers",
            line=dict(color="#00C9FF", width=2.5, shape="spline"),
            marker=dict(size=4, color="#00C9FF"),
            fill="tozeroy",
            fillcolor="rgba(0,201,255,0.06)",
            hovertemplate="<b>PM2.5</b>: %{y:.1f} µg/m³<br>%{x}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Indian AQI trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["indian_aqi"],
            name="Indian AQI",
            mode="lines+markers",
            line=dict(color="#FF6B6B", width=2.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#FF6B6B"),
            hovertemplate="<b>AQI</b>: %{y}<br>%{x}<extra></extra>",
        ),
        secondary_y=True,
    )

    # CPCB AQI band shading (on secondary axis)
    band_ranges = [
        (0,   50,  "rgba(0,176,80,0.07)",   "Good"),
        (51,  100, "rgba(146,208,80,0.07)",  "Satisfactory"),
        (101, 200, "rgba(255,255,0,0.06)",   "Moderate"),
        (201, 300, "rgba(255,192,0,0.07)",   "Poor"),
        (301, 400, "rgba(255,0,0,0.07)",     "Very Poor"),
        (401, 500, "rgba(192,0,0,0.09)",     "Severe"),
    ]
    for lo, hi, color, band_label in band_ranges:
        fig.add_hrect(
            y0=lo, y1=hi,
            fillcolor=color,
            line_width=0,
            secondary_y=True,
            annotation_text=band_label,
            annotation_position="right",
            annotation=dict(
                font_size=9,
                font_color="rgba(255,255,255,0.25)",
            ),
        )

    fig.update_layout(
        title=dict(
            text="PM2.5 Concentration & Indian AQI Trend",
            font=dict(color="#FFFFFF", size=14, family="Inter"),
            x=0.02,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        legend=dict(
            orientation="h",
            y=1.12, x=0,
            font=dict(color="rgba(255,255,255,0.6)", size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        margin=dict(l=0, r=60, t=56, b=0),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            linecolor="rgba(255,255,255,0.08)",
        ),
        yaxis=dict(
            title="PM2.5 (µg/m³)",
            title_font=dict(color="#00C9FF", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            gridcolor="rgba(255,255,255,0.05)",
            rangemode="tozero",
        ),
        yaxis2=dict(
            title="Indian AQI",
            title_font=dict(color="#FF6B6B", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            range=[0, 520],
            showgrid=False,
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─── Plotly Chart: Temperature & Humidity ─────────────────────────────────────
def render_temp_humidity_chart(df: pd.DataFrame) -> None:
    """
    Render a dual-axis Plotly line chart:
      - Trace 1 (left Y-axis):  Temperature in °C (DHT22)
      - Trace 2 (right Y-axis): Relative Humidity % (DHT22)
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Temperature trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["temp"],
            name="Temperature (°C)",
            mode="lines+markers",
            line=dict(color="#FFA500", width=2.5, shape="spline"),
            marker=dict(size=4, color="#FFA500"),
            fill="tozeroy",
            fillcolor="rgba(255,165,0,0.05)",
            hovertemplate="<b>Temp</b>: %{y:.1f}°C<br>%{x}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Humidity trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["humidity"],
            name="Humidity (%)",
            mode="lines+markers",
            line=dict(color="#7EC8E3", width=2.5, shape="spline"),
            marker=dict(size=4, color="#7EC8E3"),
            hovertemplate="<b>Humidity</b>: %{y:.1f}%<br>%{x}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(
            text="Temperature & Humidity Trend (DHT22)",
            font=dict(color="#FFFFFF", size=14, family="Inter"),
            x=0.02,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        legend=dict(
            orientation="h",
            y=1.12, x=0,
            font=dict(color="rgba(255,255,255,0.6)", size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        margin=dict(l=0, r=60, t=56, b=0),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            linecolor="rgba(255,255,255,0.08)",
        ),
        yaxis=dict(
            title="Temperature (°C)",
            title_font=dict(color="#FFA500", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            gridcolor="rgba(255,255,255,0.05)",
        ),
        yaxis2=dict(
            title="Humidity (%)",
            title_font=dict(color="#7EC8E3", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            range=[0, 105],
            showgrid=False,
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─── Plotly Chart: Gas Sensors (MQ-135 & MQ-7) ────────────────────────────────
def render_gas_chart(df: pd.DataFrame) -> None:
    """
    Render a dual-axis Plotly line chart:
      - Trace 1 (left Y-axis):  MQ-135 Raw Gas Analog reading
      - Trace 2 (right Y-axis): MQ-7 CO concentration in ppm
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # MQ-135 Gas Raw trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["gas_raw"],
            name="MQ-135 (Gas Raw)",
            mode="lines+markers",
            line=dict(color="#B388FF", width=2.5, shape="spline"),
            marker=dict(size=4, color="#B388FF"),
            fill="tozeroy",
            fillcolor="rgba(179,136,255,0.06)",
            hovertemplate="<b>MQ-135</b>: %{y:.0f}<br>%{x}<extra></extra>",
        ),
        secondary_y=False,
    )

    # MQ-7 CO ppm trace
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["co"],
            name="MQ-7 CO (ppm)",
            mode="lines+markers",
            line=dict(color="#FF8A65", width=2.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#FF8A65"),
            hovertemplate="<b>CO</b>: %{y:.4f} ppm<br>%{x}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(
            text="Gas Sensor Trends (MQ-135 & MQ-7)",
            font=dict(color="#FFFFFF", size=14, family="Inter"),
            x=0.02,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        legend=dict(
            orientation="h",
            y=1.12, x=0,
            font=dict(color="rgba(255,255,255,0.6)", size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        margin=dict(l=0, r=60, t=56, b=0),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            linecolor="rgba(255,255,255,0.08)",
        ),
        yaxis=dict(
            title="MQ-135 Raw",
            title_font=dict(color="#B388FF", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            gridcolor="rgba(255,255,255,0.05)",
            rangemode="tozero",
        ),
        yaxis2=dict(
            title="CO (ppm)",
            title_font=dict(color="#FF8A65", size=11),
            tickfont=dict(color="rgba(255,255,255,0.4)", size=10),
            showgrid=False,
            rangemode="tozero",
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("---")

    # ── Demo Mode Toggle ──────────────────────────────────────────────────
    demo_mode = st.toggle(
        "🎭 Demo Mode",
        value=False,
        help="Enable to load sample sensor data without a live ESP32 or database.",
    )
    if demo_mode:
        st.markdown(
            '<div style="background:rgba(255,165,0,0.12);border:1px solid rgba(255,165,0,0.3);'
            'border-radius:8px;padding:8px 12px;margin:4px 0 8px 0;">'
            '<span style="font-size:0.72rem;color:#FFA500;">'
            '⚡ Showing <b>demo data</b> — 19 sample readings from a hardware test session.'
            '</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    time_filter_label = st.selectbox(
        "📅 Time Window",
        options=list(TIME_FILTER_OPTIONS.keys()),
        index=0,
        help="Choose the historical range to display in the charts.",
        disabled=demo_mode,
    )
    selected_minutes = TIME_FILTER_OPTIONS[time_filter_label]

    st.markdown("---")
    st.markdown("### 🌈 CPCB AQI Scale")
    for lo, hi, bg, fg, label in AQI_BANDS:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
            f'<div style="width:14px;height:14px;border-radius:3px;background:{bg};flex-shrink:0;"></div>'
            f'<span style="font-size:0.78rem;color:rgba(255,255,255,0.65);">'
            f'{lo}–{hi} &nbsp;·&nbsp; <b>{label}</b></span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### 📡 Hardware")
    st.markdown(
        """
        <div style="font-size:0.75rem;color:rgba(255,255,255,0.4);line-height:1.7;">
        • <b>MCU:</b> ESP32<br>
        • <b>CO:</b> MQ-7<br>
        • <b>Gas:</b> MQ-135<br>
        • <b>Climate:</b> DHT22<br>
        • <b>Dust:</b> Sharp GP2Y10<br>
        • <b>AQI Standard:</b> CPCB India
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.68rem;color:rgba(255,255,255,0.2);text-align:center;">'
        '🔄 Auto-refresh every 5 s</div>',
        unsafe_allow_html=True,
    )


# ─── Main Dashboard ────────────────────────────────────────────────────────────
# Header
st.markdown("""
<div class="dashboard-header">
    <h1>🌿 Real-Time Air Quality Monitor</h1>
    <p>Indian National AQI (NAQI) &nbsp;·&nbsp; Central Pollution Control Board (CPCB) Standard</p>
</div>
""", unsafe_allow_html=True)

# Fetch data — use demo DataFrame when Demo Mode is active
if demo_mode:
    df = get_demo_dataframe()
else:
    df = fetch_data(selected_minutes)

# Demo mode banner
if demo_mode:
    st.markdown(
        '<div style="background:linear-gradient(90deg,rgba(255,165,0,0.15),rgba(255,100,0,0.08));'
        'border:1px solid rgba(255,165,0,0.25);border-radius:10px;padding:10px 18px;margin-bottom:12px;'
        'display:flex;align-items:center;gap:10px;">'
        '<span style="font-size:1.4rem;">🎭</span>'
        '<span style="font-size:0.82rem;color:#FFA500;">'
        '<b>Demo Mode Active</b> — Displaying 19 sample sensor readings from a hardware test session. '
        'Toggle off in the sidebar to switch to live data.</span></div>',
        unsafe_allow_html=True,
    )

# Live timestamp & record count
now_str = datetime.datetime.now().strftime("%d %b %Y, %H:%M:%S IST")
record_count = len(df) if not df.empty else 0

col_ts, col_rc = st.columns([3, 1])
with col_ts:
    if demo_mode:
        st.markdown(
            '<div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            'background:#FFA500;box-shadow:0 0 8px #FFA500;margin-right:6px;"></span>'
            f'<span style="font-size:0.72rem;color:rgba(255,255,255,0.3);">Demo &nbsp;·&nbsp; {now_str}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div><span class="status-dot"></span>'
            f'<span style="font-size:0.72rem;color:rgba(255,255,255,0.3);">Live &nbsp;·&nbsp; {now_str}</span></div>',
            unsafe_allow_html=True,
        )
with col_rc:
    st.markdown(
        f'<div class="timestamp-text">{record_count} records in view</div>',
        unsafe_allow_html=True,
    )

st.markdown("<hr>", unsafe_allow_html=True)

# ─── Metric Cards ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Current Readings</div>', unsafe_allow_html=True)

if df.empty:
    st.markdown("""
    <div class="empty-state">
        <div style="font-size:2rem;margin-bottom:12px;">📭</div>
        <b>No data available yet</b><br>
        Waiting for the first telemetry packet from the ESP32.<br>
        POST a reading to <code>/api/telemetry</code> to begin.
    </div>
    """, unsafe_allow_html=True)
else:
    latest = df.iloc[-1]

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_metric_card(
            label="Temperature / Humidity",
            value=f"{latest['temp']:.1f}° / {latest['humidity']:.0f}%",
            unit="°C  ·  % RH",
            icon="🌡️",
        )
    with c2:
        render_metric_card(
            label="Air Quality (MQ-135)",
            value=f"{latest['gas_raw']:.0f}",
            unit="Raw Analog  ·  MQ-135",
            icon="🏭",
        )
    with c3:
        render_metric_card(
            label="Carbon Monoxide",
            value=f"{latest['co']:.4f}",
            unit="ppm  ·  MQ-7",
            icon="💨",
        )
    with c4:
        render_metric_card(
            label="Dust / PM2.5",
            value=f"{latest['pm25']:.1f}",
            unit="µg/m³  ·  Sharp GP2Y10",
            icon="🌫️",
        )
    with c5:
        render_aqi_card(int(latest["indian_aqi"]))

    # ─── Charts ───────────────────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)

    if len(df) < 2:
        st.info(
            "📊 Charts will render once **2 or more** data points have been recorded. "
            "Keep the ESP32 sending telemetry — the dashboard will update automatically."
        )
    else:
        trend_label = "Demo Data" if demo_mode else time_filter_label
        st.markdown(
            '<div class="section-title">Historical Trends · ' + trend_label + '</div>',
            unsafe_allow_html=True,
        )

        render_pm25_aqi_chart(df)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        render_temp_humidity_chart(df)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ─── Gas Sensors Chart (MQ-135 & MQ-7) ─────────────────────────────
        render_gas_chart(df)

    # ─── Raw Data Table (collapsed) ───────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.expander("🗃️ Raw Telemetry Table", expanded=False):
        display_df = df.copy()
        display_df["timestamp"] = display_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        display_df = display_df.rename(columns={
            "timestamp":  "Timestamp (UTC)",
            "co":         "CO (ppm)",
            "gas_raw":    "Gas Raw",
            "temp":       "Temp (°C)",
            "humidity":   "Humidity (%)",
            "pm25":       "PM2.5 (µg/m³)",
            "indian_aqi": "Indian AQI",
        })
        display_df = display_df.drop(columns=["id"], errors="ignore")
        st.dataframe(
            display_df.sort_values("Timestamp (UTC)", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
