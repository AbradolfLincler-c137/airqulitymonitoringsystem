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


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("---")

    time_filter_label = st.selectbox(
        "📅 Time Window",
        options=list(TIME_FILTER_OPTIONS.keys()),
        index=0,
        help="Choose the historical range to display in the charts.",
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

# Fetch data
df = fetch_data(selected_minutes)

# Live timestamp & record count
now_str = datetime.datetime.now().strftime("%d %b %Y, %H:%M:%S IST")
record_count = len(df) if not df.empty else 0

col_ts, col_rc = st.columns([3, 1])
with col_ts:
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

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        render_metric_card(
            label="Temperature / Humidity",
            value=f"{latest['temp']:.1f}° / {latest['humidity']:.0f}%",
            unit="°C  ·  % RH",
            icon="🌡️",
        )
    with c2:
        render_metric_card(
            label="Carbon Monoxide",
            value=f"{latest['co']:.4f}",
            unit="ppm  ·  MQ-7",
            icon="💨",
        )
    with c3:
        render_metric_card(
            label="Raw Particulates",
            value=f"{latest['pm25']:.1f}",
            unit="µg/m³  ·  PM2.5",
            icon="🌫️",
        )
    with c4:
        render_aqi_card(int(latest["indian_aqi"]))

    # ─── Charts ───────────────────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)

    if len(df) < 2:
        st.info(
            "📊 Charts will render once **2 or more** data points have been recorded. "
            "Keep the ESP32 sending telemetry — the dashboard will update automatically."
        )
    else:
        st.markdown(
            '<div class="section-title">Historical Trends · ' + time_filter_label + '</div>',
            unsafe_allow_html=True,
        )

        render_pm25_aqi_chart(df)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        render_temp_humidity_chart(df)

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
