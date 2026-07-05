import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import time

# Set up page configurations for a premium dark mode dashboard
st.set_page_config(
    page_title="SWEWS Dashboard",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS styling (glassmorphism details, colors, fonts)
st.markdown("""
<style>
    .reportview-container {
        background: #0f111a;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        backdrop-filter: blur(10px);
        margin-bottom: 10px;
    }
    .risk-normal {
        color: #00e676;
        font-weight: bold;
        font-size: 24px;
    }
    .risk-elevated {
        color: #ff9100;
        font-weight: bold;
        font-size: 24px;
    }
    .risk-critical {
        color: #ff1744;
        font-weight: bold;
        font-size: 24px;
    }
</style>
""", unsafe_allow_html=True)

API_URL = "http://localhost:8000"

st.sidebar.image("https://img.icons8.com/nolan/128/satellite.png", width=70)
st.sidebar.title("SWEWS Controller")
page = st.sidebar.radio("SWEWS Navigation", ["Forecast Dashboard", "Live Data Streaming"])
st.sidebar.markdown("---")

# 1. Connection Health Check
connection_placeholder = st.sidebar.empty()
num_features = 192  # Default fallback matching the production-trained model features
try:
    health_response = requests.get(f"{API_URL}/health", timeout=2)
    if health_response.status_code == 200:
        health_data = health_response.json()
        device = health_data.get("device", "CPU")
        num_features = health_data.get("input_dim", 192)
        connection_placeholder.success(f"API Server: Online ({device}) | Features: {num_features}")
    else:
        connection_placeholder.warning("API Server: Unreachable, running offline simulation.")
except Exception:
    connection_placeholder.error("API Server: Offline (Simulating metrics)")

# 2. Select Space Weather Scenarios
st.sidebar.subheader("Select Simulation Scenario")
scenario = st.sidebar.selectbox(
    "Choose a preset Sun condition:",
    ["Quiet Sun (Safe)", "Solar Flare Activity (Elevated)", "CME Radiation Storm (Critical)"]
)

# Generate mock data for the features
seq_len = 12

def get_scenario_data(scenario_name: str) -> np.ndarray:
    np.random.seed(42)
    # Base feature array
    base = np.random.normal(0, 0.5, (seq_len, num_features))
    if scenario_name == "Quiet Sun (Safe)":
        # low solar wind speeds, low electron fluxes
        base[:, 0] = 350.0 + np.random.uniform(-10, 10, seq_len) # speed
        base[:, 1] = 5.0 + np.random.uniform(-1, 1, seq_len)   # density
        base[:, 2] = 200.0 + np.random.uniform(-20, 20, seq_len) # flux
    elif scenario_name == "Solar Flare Activity (Elevated)":
        # elevated solar wind speeds, moderate electron fluxes
        base[:, 0] = 580.0 + np.random.uniform(-20, 20, seq_len) # speed
        base[:, 1] = 12.0 + np.random.uniform(-2, 2, seq_len)   # density
        base[:, 2] = 2500.0 + np.random.uniform(-200, 200, seq_len) # flux
    else:
        # high solar wind speed (CME storm), extreme fluxes
        base[:, 0] = 850.0 + np.random.uniform(-50, 50, seq_len) # speed
        base[:, 1] = 25.0 + np.random.uniform(-5, 5, seq_len)   # density
        base[:, 2] = 45000.0 + np.random.uniform(-3000, 3000, seq_len) # flux
    return base

input_sequence = get_scenario_data(scenario)

# Fetch predictions
prediction = None
try:
    payload = {"sequence": input_sequence.tolist()}
    res = requests.post(f"{API_URL}/predict", json=payload, timeout=5)
    if res.status_code == 200:
        prediction = res.json()
except Exception:
    pass

# If API failed, simulate predictions locally for high-fidelity interactive user demo
if prediction is None:
    if scenario == "Quiet Sun (Safe)":
        prediction = {
            "storm_class": "Safe",
            "class_probabilities": {"Safe": 0.95, "Moderate": 0.04, "Severe": 0.01},
            "forecasts": {
                "30_min": {"p10": 150, "p50": 210, "p90": 290},
                "45_min": {"p10": 160, "p50": 225, "p90": 310},
                "6_hours": {"p10": 180, "p50": 240, "p90": 340},
                "12_hours": {"p10": 170, "p50": 235, "p90": 330}
            },
            "satellite_risk_level": "Normal"
        }
    elif scenario == "Solar Flare Activity (Elevated)":
        prediction = {
            "storm_class": "Moderate",
            "class_probabilities": {"Safe": 0.12, "Moderate": 0.82, "Severe": 0.06},
            "forecasts": {
                "30_min": {"p10": 1800, "p50": 2400, "p90": 3100},
                "45_min": {"p10": 2100, "p50": 2750, "p90": 3500},
                "6_hours": {"p10": 2800, "p50": 3600, "p90": 4600},
                "12_hours": {"p10": 2400, "p50": 3200, "p90": 4100}
            },
            "satellite_risk_level": "Elevated"
        }
    else:
        prediction = {
            "storm_class": "Severe",
            "class_probabilities": {"Safe": 0.00, "Moderate": 0.08, "Severe": 0.92},
            "forecasts": {
                "30_min": {"p10": 32000, "p50": 41000, "p90": 53000},
                "45_min": {"p10": 38000, "p50": 49000, "p90": 62000},
                "6_hours": {"p10": 45000, "p50": 58000, "p90": 74000},
                "12_hours": {"p10": 41000, "p50": 54000, "p90": 69000}
            },
            "satellite_risk_level": "Critical"
        }


if page == "Live Data Streaming":
    st.title("🛰️ Real-Time Space Weather Data Streams")
    st.subheader("Direct Monitoring of Satellite Telemetry & Provider Endpoints")
    st.markdown("Verify the authenticity of live space weather data fetched from NOAA Space Weather Prediction Center (NOAA SWPC) and NASA CDAWeb.")
    
    stream_source = st.selectbox(
        "Select Live Stream Source:",
        ["NOAA GOES Satellite (Fluxes)", "NOAA DSCOVR Satellite (Solar Wind)"]
    )
    
    st.markdown("---")
    
    if stream_source == "NOAA GOES Satellite (Fluxes)":
        st.markdown("### 🛰️ GOES Primary Satellite Stream")
        st.info("GOES satellites in geostationary orbit monitor the Earth's radiation environment, providing integral electron and proton fluxes.")
        
        # Show provider URLs
        st.markdown("**Data Provider Source URLs (NOAA SWPC):**")
        st.code("https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-1-day.json\nhttps://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json", language="text")
        
        # Fetch from API
        goes_data = None
        try:
            res = requests.get(f"{API_URL}/api/live/goes", timeout=5)
            if res.status_code == 200:
                goes_data = res.json()
        except Exception:
            pass
            
        if goes_data is None:
            st.warning("API Server offline or unreachable. Displaying simulated live telemetry.")
            # Generate mock live goes data
            dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='15min')
            electrons_df = pd.DataFrame({
                'timestamp': dates.strftime('%Y-%m-%d %H:%M:%S'),
                'electron_flux_2mev': np.random.uniform(500, 3000, 100),
                'electron_flux_800kev': np.random.uniform(2000, 15000, 100)
            })
            protons_df = pd.DataFrame({
                'timestamp': dates.strftime('%Y-%m-%d %H:%M:%S'),
                'proton_flux_10mev': np.random.uniform(0.1, 0.5, 100)
            })
        else:
            electrons_df = pd.DataFrame(goes_data["electrons"])
            protons_df = pd.DataFrame(goes_data["protons"])
            
        # Display live electron flux chart
        st.markdown("#### Live Geostationary Electron Flux (>800 keV & >2 MeV)")
        fig_goes = go.Figure()
        fig_goes.add_trace(go.Scatter(x=electrons_df['timestamp'], y=electrons_df['electron_flux_800kev'], mode='lines', name='>800 keV Flux', line=dict(color='#ff9100')))
        fig_goes.add_trace(go.Scatter(x=electrons_df['timestamp'], y=electrons_df['electron_flux_2mev'], mode='lines', name='>2 MeV Flux', line=dict(color='#29b6f6')))
        fig_goes.update_layout(template="plotly_dark", yaxis_title="Flux [pfu]", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_goes, width="stretch")
        
        # Display data table
        st.markdown("#### Raw GOES Stream Table")
        st.dataframe(electrons_df.tail(20), use_container_width=True)
        
    else:
        st.markdown("### 📡 DSCOVR Satellite Solar Wind Stream")
        st.info("DSCOVR positioned at the Sun-Earth L1 Lagrangian point acts as an early warning sensor, measuring raw interplanetary magnetic field and plasma speed.")
        
        # Show provider URLs
        st.markdown("**Data Provider Source URLs (NOAA SWPC):**")
        st.code("https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json\nhttps://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json", language="text")
        
        # Fetch from API
        dscovr_data = None
        try:
            res = requests.get(f"{API_URL}/api/live/dscovr", timeout=5)
            if res.status_code == 200:
                dscovr_data = res.json()
        except Exception:
            pass
            
        if dscovr_data is None:
            st.warning("API Server offline or unreachable. Displaying simulated live telemetry.")
            dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='15min')
            plasma_df = pd.DataFrame({
                'timestamp': dates.strftime('%Y-%m-%d %H:%M:%S'),
                'speed': np.random.uniform(350, 650, 100),
                'density': np.random.uniform(2, 10, 100)
            })
            mag_df = pd.DataFrame({
                'timestamp': dates.strftime('%Y-%m-%d %H:%M:%S'),
                'bt': np.random.uniform(3, 12, 100)
            })
        else:
            plasma_df = pd.DataFrame(dscovr_data["plasma"])
            mag_df = pd.DataFrame(dscovr_data["mag"])
            
        # Display live solar wind speed chart
        st.markdown("#### Live Solar Wind Velocity (L1)")
        fig_dscovr = go.Figure()
        fig_dscovr.add_trace(go.Scatter(x=plasma_df['timestamp'], y=plasma_df['speed'], mode='lines', name='Wind Speed (km/s)', line=dict(color='#00e676')))
        fig_dscovr.update_layout(template="plotly_dark", yaxis_title="Velocity [km/s]", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_dscovr, width="stretch")
        
        # Display data table
        st.markdown("#### Raw DSCOVR Stream Table")
        st.dataframe(plasma_df.tail(20), use_container_width=True)
        
    st.stop()

# --- HEADER SECTION ---
st.title("🛰️ Space Weather Early Warning System (SWEWS)")
st.subheader("Geostationary Electron Flux Forecasting & Radiation Alerts")
st.markdown("Designed for space operations, communications protection, and orbital risk monitoring.")

# --- TOP METRIC CARDS ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    risk = prediction["satellite_risk_level"]
    risk_class = "risk-normal" if risk == "Normal" else ("risk-elevated" if risk == "Elevated" else "risk-critical")
    st.markdown(f"""
    <div class="metric-card">
        <h3>Satellite Risk Level</h3>
        <p class="{risk_class}">{risk}</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    storm_c = prediction["storm_class"]
    st.markdown(f"""
    <div class="metric-card">
        <h3>Storm Environment</h3>
        <p style="font-size: 24px; font-weight: bold; color: #e0e0e0;">{storm_c}</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    p50_30m = prediction["forecasts"]["30_min"]["p50"]
    st.markdown(f"""
    <div class="metric-card">
        <h3>30-Min Forecast (p50)</h3>
        <p style="font-size: 24px; font-weight: bold; color: #29b6f6;">{p50_30m:,.1f} <span style="font-size: 14px; color: #888;">pfu</span></p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    p50_12h = prediction["forecasts"]["12_hours"]["p50"]
    st.markdown(f"""
    <div class="metric-card">
        <h3>12-Hour Forecast (p50)</h3>
        <p style="font-size: 24px; font-weight: bold; color: #ab47bc;">{p50_12h:,.1f} <span style="font-size: 14px; color: #888;">pfu</span></p>
    </div>
    """, unsafe_allow_html=True)

# --- GRAPH SECTIONS ---
st.markdown("### Forecast Analysis")
g1, g2 = st.columns([2, 1])

with g1:
    # 1. Multi-Horizon Quantile Prediction Curve
    horizons = ["30 Min", "45 Min", "6 Hours", "12 Hours"]
    keys = ["30_min", "45_min", "6_hours", "12_hours"]
    
    p10 = [prediction["forecasts"][k]["p10"] for k in keys]
    p50 = [prediction["forecasts"][k]["p50"] for k in keys]
    p90 = [prediction["forecasts"][k]["p90"] for k in keys]
    
    fig = go.Figure()
    
    # Add bounds shading (p10 to p90 confidence interval)
    fig.add_trace(go.Scatter(
        x=horizons + horizons[::-1],
        y=p90 + p10[::-1],
        fill='toself',
        fillcolor='rgba(41, 182, 246, 0.12)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=True,
        name="10% - 90% Confidence Band"
    ))
    
    # Add median line (p50)
    fig.add_trace(go.Scatter(
        x=horizons,
        y=p50,
        mode='lines+markers',
        line=dict(color='#29b6f6', width=3),
        name="Median Forecast (p50)",
        marker=dict(size=8)
    ))
    
    # Add p90 line
    fig.add_trace(go.Scatter(
        x=horizons,
        y=p90,
        mode='lines',
        line=dict(color='#ef5350', width=1.5, dash='dash'),
        name="Worst Case Bound (p90)"
    ))

    fig.update_layout(
        title="Electron Flux Multi-Horizon Prediction & Uncertainty Bounds",
        xaxis_title="Forecast Horizon",
        yaxis_title="Electron Flux (>2 MeV) [pfu]",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, width="stretch")

with g2:
    # 2. Classifier Probabilities Chart
    probs = prediction["class_probabilities"]
    categories = list(probs.keys())
    values = list(probs.values())
    
    colors = ['#00e676', '#ff9100', '#ff1744'] # Green, Orange, Red
    
    fig_bar = go.Figure(data=[go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[f"{v*100:.1f}%" for v in values],
        textposition='auto'
    )])
    
    fig_bar.update_layout(
        title="Storm Likelihood Probabilities",
        xaxis_title="Classification Class",
        yaxis_title="Probability",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis_range=[0, 1.1]
    )
    st.plotly_chart(fig_bar, width="stretch")

# --- DETAILED INFORMATION ---
st.markdown("### Model Properties & Space Variables")
d1, d2 = st.columns(2)

with d1:
    st.subheader("Feature Importance & Contribution")
    # Show dummy feature importance for the 466 engineered variables
    feat_names = [
        "dscovr_speed_ema_24", 
        "electron_flux_2mev_lag_1", 
        "BZ_GSE_roll_mean_12", 
        "total_sunspot_area", 
        "DST_diff_3"
    ]
    importances = [0.35, 0.28, 0.18, 0.11, 0.08]
    
    fi_df = pd.DataFrame({"Feature": feat_names, "Importance": importances})
    fig_fi = px.bar(
        fi_df, x="Importance", y="Feature", orientation="h",
        title="Top 5 Space Weather Feature Importances",
        color="Importance",
        color_continuous_scale=px.colors.sequential.Tealgrn,
        template="plotly_dark"
    )
    fig_fi.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        coloraxis_showscale=False
    )
    st.plotly_chart(fig_fi, width="stretch")

with d2:
    st.subheader("Operational Guidance")
    if risk == "Normal":
        st.success("🛰️ **Systems Safe**: Geostationary electron environment is quiet. Regular communications and satellite telemetry operating under normal conditions.")
    elif risk == "Elevated":
        st.warning("⚠️ **Warning**: Elevated energetic electron fluxes detected. Increase electrostatic monitoring. Recommend pausing non-critical satellite maneuvers and deep orbital operations.")
    else:
        st.error("🚨 **Alert**: Critical radiation enhancement in progress. Severe satellite surface charging and Deep Dielectric Charging risks are active. Recommend activating spacecraft safe-mode procedures.")
        
    # Quick metadata
    st.info("💡 **Model Info**: Model 1 is powered by a multi-head Self-Attention Transformer. Model 2 utilizes a lightweight Temporal Fusion Transformer (TFT) optimizing Pinball Quantile Loss.")
