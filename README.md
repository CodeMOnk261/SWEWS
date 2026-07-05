# Space Weather Early Warning System (SWEWS)

The Space Weather Early Warning System (SWEWS) is an operational and research-grade forecasting platform designed to predict high-energy electron fluxes at Geostationary Earth Orbit (GEO) and assess radiation storm risks for satellite systems. The system integrates real-time physics-based satellite observations with modern deep learning and a hybrid prediction strategy.

---

## 1. System Architecture

SWEWS separates prediction into two sequential stages to ensure high-fidelity warnings:
1. **Model 1 (Storm Classifier)**: A Transformer Encoder model classifying the radiation environment into Safe, Moderate, or Severe classes.
2. **Model 2 (Flux Regressor)**: A parameter-optimized Temporal Fusion Transformer (TFT) predicting exact electron flux values (at 30-minute, 45-minute, 6-hour, and 12-hour horizons) with 10%, 50%, and 90% quantile confidence intervals.

---

## 2. Project Structure

```text
.
├── LICENSE                          # MIT License file
├── README.md                         # Project documentation
├── Dockerfile                        # Docker configuration
├── package.json                      # Workspace root package definition
├── pnpm-workspace.yaml               # pnpm monorepo configuration
├── requirements.txt                  # Python dependencies
├── tsconfig.json                     # TypeScript configuration
│
├── config/
│   └── config.yaml                   # Model hyperparameters & environment settings
│
├── datasets/                         # Local cached datasets (git-ignored)
│   ├── raw/                          # Raw telemetries (GOES, OMNI, DSCOVR)
│   └── processed/                    # Normalized and time-aligned features
│
├── src/                              # Python backend source code
│   ├── api/
│   │   └── app.py                    # FastAPI prediction & diagnostic server
│   ├── dashboard/
│   │   └── streamlit_app.py          # Backup Streamlit control panel
│   ├── ingestion/
│   │   ├── dscovr_loader.py          # L1 solar wind plasma observations
│   │   ├── goes_historical_loader.py # NOAA NCEI historical archive access
│   │   ├── goes_loader.py            # GOES integral electron & proton flux
│   │   ├── omni_loader.py            # NASA OMNI database HAPI integration
│   │   └── solar_loader.py           # Solar flare & sunspot event loaders
│   ├── preprocessing/
│   │   ├── clean.py                  # Outlier rejection and imputation
│   │   ├── feature_engineering.py    # Temporal features, lags, and rolling EMAs
│   │   └── synchronize.py            # Time-alignment of multi-rate sensor matrices
│   └── models/
│       ├── classifier.py             # Transformer Encoder classifier network
│       ├── transformer.py            # Temporal Fusion Transformer regressor
│       ├── trainer.py                # PyTorch model training loop
│       └── inference.py              # Unified prediction pipeline handler
│
├── artifacts/
│   └── swews/                        # React/Vite operations control dashboard
│       ├── package.json              # Frontend package configuration
│       ├── vite.config.ts            # Vite build configuration
│       ├── public/                   # Static dashboard assets
│       └── src/
│           ├── main.tsx              # React entry point
│           ├── components/           # Reusable UI widgets and diagrams
│           ├── pages/
│           │   ├── Landing.tsx       # Landing page with 2D model preview
│           │   ├── Dashboard.tsx     # Mission Control operations panel
│           │   ├── LiveWeather.tsx   # Live space weather graphs
│           │   └── Observation.tsx   # Advanced observation portal
│           └── hooks/                # React custom hooks
│
└── tests/
    └── test_pipeline.py              # End-to-end integration verification tests
```

---

## 3. Installation & Local Setup

### Prerequisites
Make sure the following dependencies are installed on your system:
*   Python 3.10 or higher
*   Node.js v18 or higher
*   pnpm (Preferred package manager for the frontend monorepo)

### Step 1: Clone the Repository
Clone the repository to your local machine:
```bash
git clone https://github.com/CodeMOnk261/SWEWS.git
cd SWEWS
```

### Step 2: Set Up Python Backend
Create a virtual environment, activate it, and install the required dependencies:

On Windows:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Set Up Frontend Dashboard
Install frontend dependencies at the workspace root using pnpm:
```bash
pnpm install
```

---

## 4. Usage Instructions

### Running Ingestion & Pipeline Verification
To verify the data processing pipeline, model architectures, and ingestion scripts:
```bash
python tests/test_pipeline.py
```
This script downloads a slice of telemetry, cleans the data, runs feature engineering, and performs a single epoch of training to confirm system integrity.

### Launching the Backend FastAPI Server
To start the FastAPI backend serving predictions and real-time telemetry:
```bash
python -m src.api.app
```
*   **Health Check**: `GET http://localhost:8000/health`
*   **Prediction Endpoint**: `POST http://localhost:8000/predict` (Expects history matrix)

### Launching the Operations Control Dashboard
To run the React/Vite frontend locally:
```bash
pnpm --filter @workspace/swews run dev
```
Open `http://localhost:5173` in your browser.

---

## 5. Data Sources & Licensing

### Data Attribution
All space weather telemetry utilized by this system are sourced from public-access scientific databases provided by agencies of the United States Government:
*   **NOAA GOES Satellite Telemetry**: Sourced from the [NOAA Space Weather Prediction Center (SWPC)](https://services.swpc.noaa.gov) and [National Centers for Environmental Information (NCEI)](https://www.ncei.noaa.gov).
*   **NASA OMNI & DSCOVR Data**: Sourced from the [NASA Goddard Space Flight Center (GSFC) CDAWeb HAPI Service](https://cdaweb.gsfc.nasa.gov).

### Legal Status
Under **17 U.S.C. § 105**, works created by officers or employees of the United States Government as part of their official duties are not subject to copyright protection and reside in the **public domain** within the United States. 

The APIs and endpoints used by the ingestion scripts are designated for open public access. The code incorporates local file caching (with a minimum 5-minute threshold) to ensure compliance with server usage guidelines and avoid overloading public endpoints.

### Disclaimer
This project is an independent open-source tool and is not officially affiliated with, endorsed by, or representative of NOAA, NASA, or any other government agency. Predictions, storm classifications, and warnings generated by this system are for research and educational purposes and should not be used as a substitute for official space weather alerts.
