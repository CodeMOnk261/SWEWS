import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import numpy as np
import pandas as pd
import math
from typing import List, Dict, Any
from src.models.inference import SpaceWeatherPredictor
from src.ingestion.goes_loader import GOESLoader
from src.ingestion.dscovr_loader import DSCOVRLoader
from src.utils.logger import setup_logger

logger = setup_logger("API_Server")

import time

# In-memory TTL Cache for performance optimization
_CACHE = {
    "goes": {"data": None, "expiry": 0},
    "dscovr": {"data": None, "expiry": 0},
    "intensity": {"data": None, "expiry": 0}
}
CACHE_TTL = 3.0  # Cache duration in seconds


# Initialize global loaders
goes_loader = GOESLoader(raw_data_dir="datasets/raw")
dscovr_loader = DSCOVRLoader(raw_data_dir="datasets/raw")

def clean_json_content(val):
    if isinstance(val, dict):
        return {k: clean_json_content(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_json_content(v) for v in val]
    elif isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    return val

class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        clean_content = clean_json_content(content)
        return super().render(clean_content)

app = FastAPI(
    title="Space Weather Early Warning System (SWEWS) API",
    description="Operational API for geostationary electron flux forecasting and satellite risk assessment.",
    version="1.0.0",
    default_response_class=SafeJSONResponse
)

# Enable CORS for Streamlit dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Predictor Instance
predictor = None

class PredictionRequest(BaseModel):
    # Expects [sequence_length, num_features] feature matrix
    # e.g., 12 steps history (1 hour) of 466 features
    sequence: List[List[float]] = Field(
        ..., 
        description="A 2D array of shape [seq_len, num_features] representing the historical context."
    )

class HealthResponse(BaseModel):
    status: str
    device: str
    models_loaded: bool
    input_dim: int

async def background_monitoring_loop():
    logger.info("Starting background space weather alert monitoring loop...")
    while True:
        try:
            from src.api.swews_bot import check_and_send_alert
            
            # Fetch latest data (safe due to 5-min caching loader optimization)
            intensity_data = get_regression_intensity()
            goes_data = get_live_goes()
            
            # Calculate metrics
            electrons = goes_data.get("electrons", [])
            latest_electron = 0.0
            if electrons:
                last_el = electrons[-1].get("electron_flux_2mev", 0.0)
                if last_el is not None:
                    latest_electron = float(last_el)
            
            wind_speed = float(intensity_data.get("wind_speed", 450.0))
            bz = float(intensity_data.get("bz", -1.5))
            dyn_pressure = float(intensity_data.get("dynamic_pressure", 2.0))
            intensity = float(intensity_data.get("intensity", 0.15))
            
            # Compute physical parameters & storm probability matching frontend metrics
            kp = max(0.0, min(9.0, 1.4 + intensity * 7.2))
            
            electron_score = min(20.0, (latest_electron / 10000.0) * 20.0)
            bz_score = min(30.0, max(0.0, -bz) * 2.3)
            speed_score = min(25.0, max(0.0, wind_speed - 400.0) / 14.0)
            pressure_score = min(15.0, dyn_pressure * 1.15)
            
            probability = round(
                min(99.0, max(5.0, intensity * 18.0 + electron_score + bz_score + speed_score + pressure_score))
            )
            
            telemetry_data = {
                "speed": wind_speed,
                "bz": bz,
                "kp": round(kp, 1)
            }
            
            logger.info(f"Background monitoring check: Probability = {probability}%, Telemetry = {telemetry_data}")
            check_and_send_alert(probability, telemetry_data)
        except Exception as e:
            logger.error(f"Error in background monitoring loop: {e}")
            
        await asyncio.sleep(60)

@app.on_event("startup")
def startup_event():
    global predictor
    logger.info("Starting up FastAPI Server and initializing Predictor models...")
    try:
        predictor = SpaceWeatherPredictor()
        asyncio.create_task(background_monitoring_loop())
    except Exception as e:
        logger.critical(f"Failed to initialize SpaceWeatherPredictor: {e}")
        raise e

@app.get("/health", response_model=HealthResponse)
def health_check():
    """
    Service health probe and hardware diagnostics.
    """
    global predictor
    models_loaded = predictor is not None
    device = str(predictor.device) if predictor else "unknown"
    input_dim = predictor.input_dim if predictor else 192
    return {
        "status": "healthy",
        "device": device,
        "models_loaded": models_loaded,
        "input_dim": input_dim
    }

@app.post("/predict")
def predict(request: PredictionRequest):
    """
    Accepts space weather sliding window sequence and outputs real-time hazard classifications
    along with multi-horizon quantile regression curves.
    """
    global predictor
    if predictor is None:
        raise HTTPException(
            status_code=503, 
            detail="Inference Engine is not initialized or failed to load. Check server logs."
        )
    
    sequence_np = np.array(request.sequence)
    
    # Expected shape verification: [seq_len, num_features]
    if sequence_np.ndim != 2:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid array dimensions. Expected 2D list of shape [seq_len, num_features], got {sequence_np.ndim}D."
        )
        
    if sequence_np.shape[1] != predictor.input_dim:
        raise HTTPException(
            status_code=400,
            detail=f"Features dimension mismatch. Expected {predictor.input_dim} columns, got {sequence_np.shape[1]}."
        )
        
    try:
        prediction_results = predictor.predict(sequence_np)
        return prediction_results
    except Exception as e:
        logger.error(f"Inference prediction loop encountered an error: {e}")
        raise HTTPException(status_code=500, detail=f"Inference failure: {e}")

@app.get("/api/live/goes")
def get_live_goes(force: bool = False):
    """
    Fetches real-time GOES integral electron and proton flux data directly from NOAA SWPC.
    """
    global _CACHE
    now_time = time.time()
    if not force and _CACHE["goes"]["data"] is not None and now_time < _CACHE["goes"]["expiry"]:
        return _CACHE["goes"]["data"]

    try:
        electron_df = goes_loader.fetch_electron_flux(days=1, force_download=force)
        proton_df = goes_loader.fetch_proton_flux(days=1, force_download=force)
        
        electrons_data = []
        if electron_df is not None and not electron_df.empty:
            electron_df_slice = electron_df.tail(100)
            electron_df_slice = electron_df_slice.astype(object).where(pd.notnull(electron_df_slice), None)
            df_reset = electron_df_slice.reset_index()
            df_reset['timestamp'] = df_reset['timestamp'].astype(str)
            electrons_data = df_reset.to_dict(orient='records')
            
        protons_data = []
        if proton_df is not None and not proton_df.empty:
            proton_df_slice = proton_df.tail(100).copy()
            proton_df_slice = proton_df_slice.astype(object).where(pd.notnull(proton_df_slice), None)
            proton_df_slice['timestamp'] = pd.to_datetime(proton_df_slice['time_tag'])
            proton_df_slice['timestamp'] = proton_df_slice['timestamp'].astype(str)
            # Remove objects that can't be JSON serialized easily
            if 'time_tag' in proton_df_slice.columns:
                proton_df_slice.drop(columns=['time_tag'], inplace=True)
            protons_data = proton_df_slice.to_dict(orient='records')
            
        res = {
            "source": "NOAA Space Weather Prediction Center (GOES Primary Satellite)",
            "url_electrons": "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-1-day.json",
            "url_protons": "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json",
            "electrons": electrons_data,  # already sliced to last 100
            "protons": protons_data
        }
        _CACHE["goes"] = {"data": res, "expiry": now_time + CACHE_TTL}
        return res
    except Exception as e:
        logger.error(f"Error fetching live GOES data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/live/dscovr")
def get_live_dscovr(force: bool = False):
    """
    Fetches real-time solar wind plasma and magnetic field data from the NOAA DSCOVR satellite at L1.
    """
    global _CACHE
    now_time = time.time()
    if not force and _CACHE["dscovr"]["data"] is not None and now_time < _CACHE["dscovr"]["expiry"]:
        return _CACHE["dscovr"]["data"]

    try:
        plasma_df = dscovr_loader.fetch_realtime_plasma(force_download=force)
        mag_df = dscovr_loader.fetch_realtime_mag(force_download=force)
        
        plasma_data = []
        if plasma_df is not None and not plasma_df.empty:
            plasma_df_slice = plasma_df.tail(100)
            plasma_df_slice = plasma_df_slice.astype(object).where(pd.notnull(plasma_df_slice), None)
            df_reset = plasma_df_slice.reset_index()
            df_reset['timestamp'] = df_reset['timestamp'].astype(str)
            plasma_data = df_reset.to_dict(orient='records')
            
        mag_data = []
        if mag_df is not None and not mag_df.empty:
            mag_df_slice = mag_df.tail(100)
            mag_df_slice = mag_df_slice.astype(object).where(pd.notnull(mag_df_slice), None)
            df_reset = mag_df_slice.reset_index()
            df_reset['timestamp'] = df_reset['timestamp'].astype(str)
            mag_data = df_reset.to_dict(orient='records')
            
        res = {
            "source": "NOAA Space Weather Prediction Center (DSCOVR Satellite at L1)",
            "url_plasma": "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
            "url_mag": "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json",
            "plasma": plasma_data,  # already sliced to last 100
            "mag": mag_data
        }
        _CACHE["dscovr"] = {"data": res, "expiry": now_time + CACHE_TTL}
        return res
    except Exception as e:
        logger.error(f"Error fetching live DSCOVR data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import time
import math
import asyncio
from fastapi import WebSocket, WebSocketDisconnect

@app.get("/api/regression-intensity")
def get_regression_intensity():
    """
    Extracts live NOAA DSCOVR solar wind telemetry and translates them into physical
    dynamic pressure, IMF Bz reconnection states, and magnetopause compression scaling factors.
    """
    global _CACHE
    now_time = time.time()
    if _CACHE["intensity"]["data"] is not None and now_time < _CACHE["intensity"]["expiry"]:
        return _CACHE["intensity"]["data"]

    try:
        # Query the latest live DSCOVR telemetry
        dscovr_data = get_live_dscovr()
        plasma = dscovr_data.get("plasma", [])
        mag = dscovr_data.get("mag", [])
        
        latest_p = plasma[-1] if plasma else {}
        latest_m = mag[-1] if mag else {}
        
        # Physical parameters (with safe default baselines)
        v = latest_p.get("dscovr_speed", 450.0) or 450.0
        n = latest_p.get("dscovr_density", 5.0) or 5.0
        bz = latest_m.get("dscovr_bz", -1.5) or latest_m.get("bz_gsm", -1.5) or -1.5
        
        # 1. Calculate Solar Wind Dynamic Pressure (P_dyn = m * n * v^2)
        # m_proton = 1.67e-27 kg. P_dyn = 1.67e-6 * n * v^2 (in nPa, with n in N/cm3 and v in km/s)
        p_dyn = 1.67e-6 * n * (v ** 2)
        
        # 2. Shue et al. (1998) Magnetopause Standoff Distance scaling
        # R_mp = R_0 * (P_dyn / P_baseline)^(-1/6.0)
        p_baseline = 2.0  # Baseline pressure (nPa)
        scaling_factor = (p_dyn / p_baseline) ** (-1.0 / 6.0)
        
        # Clamp scaling factor to avoid extreme clipping
        scaling_factor = max(0.38, min(1.25, scaling_factor))
        
        # 3. Calculate Storm Intensity based on southward IMF Bz & Wind Speed
        # Southward Bz (< 0) drives geomagnetic storms. Carrington level at Bz ~ -20 nT
        bz_intensity = max(0.0, -bz / 18.0)
        speed_intensity = max(0.0, (v - 400.0) / 500.0)
        intensity = 0.15 * speed_intensity + 0.85 * bz_intensity
        intensity = max(0.05, min(0.98, intensity))
        
        # Classify storm state based on physical thresholds
        if bz < -12.0 or v > 720.0:
            state = "Carrington Event"
        elif bz < -4.0 or v > 540.0:
            state = "X3 Solar Flare"
        else:
            state = "Calm Conditions"
            
        res = {
            "intensity": intensity,
            "state": state,
            "scaling_factor": scaling_factor,
            "wind_speed": v,
            "density": n,
            "bz": bz,
            "dynamic_pressure": p_dyn,
            "timestamp": now_time,
            "live": True
        }
        _CACHE["intensity"] = {"data": res, "expiry": now_time + CACHE_TTL}
        return res
    except Exception as e:
        logger.error(f"Error calculating live regression intensity: {e}")
        # Dynamic fallback loop if NOAA connection fails
        cycle_period = 60.0
        t = now_time % cycle_period
        if t < 20.0:
            intensity = 0.15 + 0.05 * math.sin(t * math.pi / 10.0)
            state = "Calm Conditions"
        elif t < 40.0:
            intensity = 0.45 + 0.12 * math.sin((t - 20.0) * math.pi / 10.0)
            state = "X3 Solar Flare"
        else:
            intensity = 0.85 + 0.12 * math.sin((t - 40.0) * math.pi / 10.0)
            state = "Carrington Event"
            
        scaling_factor = 1.0 - 0.6 * intensity
        
        res = {
            "intensity": intensity,
            "state": state,
            "scaling_factor": scaling_factor,
            "wind_speed": 450.0 + 250.0 * intensity,
            "density": 5.0 + 15.0 * intensity,
            "bz": 1.0 - 15.0 * intensity,
            "dynamic_pressure": 2.0 + 10.0 * intensity,
            "timestamp": now_time,
            "live": False
        }
        _CACHE["intensity"] = {"data": res, "expiry": now_time + CACHE_TTL}
        return res

@app.websocket("/ws/intensity")
async def websocket_intensity(websocket: WebSocket):
    """
    Pushes real-time physical space weather updates to connected WebGL clients.
    """
    await websocket.accept()
    try:
        while True:
            data = get_regression_intensity()
            clean_data = clean_json_content(data)
            await websocket.send_json(clean_data)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket connection encountered an error: {e}")

if __name__ == "__main__":
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
