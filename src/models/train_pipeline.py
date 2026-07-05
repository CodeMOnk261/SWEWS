import os
import sys
import torch
import numpy as np
import pandas as pd
import requests
from torch.utils.data import TensorDataset, DataLoader

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.preprocessing.clean import SpaceWeatherDataCleaner
from src.preprocessing.synchronize import SpaceWeatherDataSynchronizer
from src.preprocessing.feature_engineering import SpaceWeatherFeatureEngineer
from src.models.classifier import SpaceWeatherTransformerClassifier
from src.models.transformer import CustomTemporalFusionTransformer
from src.models.trainer import SpaceWeatherTrainer
from src.ingestion.goes_loader import GOESLoader
from src.ingestion.omni_loader import OMNILoader
from src.ingestion.dscovr_loader import DSCOVRLoader
from src.ingestion.solar_loader import SolarLoader
from src.utils.logger import setup_logger

logger = setup_logger("TrainPipeline")

HISTORICAL_OMNI_CACHE = "omni_2024-01-01_to_2026-07-01.csv"

def download_file(url, local_path):
    logger.info(f"Downloading: {url} -> {local_path}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(local_path, "w") as f:
        f.write(response.text)


def load_json_dataframe(path: str) -> pd.DataFrame:
    return pd.read_json(path)


def load_cached_or_download(url: str, local_path: str, force_download: bool = False) -> pd.DataFrame:
    if force_download or not os.path.exists(local_path):
        download_file(url, local_path)
    return load_json_dataframe(local_path)

def main():
    logger.info("Initializing SWEWS Historical Data Fetching & Training Pipeline...")
    raw_dir = "datasets/raw"
    os.makedirs(raw_dir, exist_ok=True)
    
    # 1. Fetch 3 days of real-time GOES Data
    goes_loader = GOESLoader(raw_data_dir=raw_dir)
    logger.info("Fetching GOES 3-day electron, proton, x-ray, and magnetometer data...")
    goes_electrons = goes_loader.fetch_electron_flux(days=3, force_download=True)
    goes_protons = goes_loader.fetch_proton_flux(days=3, force_download=True)
    goes_xrays = goes_loader.fetch_xray_flux(days=3, force_download=False)
    goes_magnetometer = goes_loader.fetch_magnetometer(days=3, force_download=False)
    
    if goes_electrons is None or goes_electrons.empty:
        logger.error("Failed to fetch GOES electron flux.")
        return

    goes_frames = [goes_electrons]
    if goes_xrays is not None and not goes_xrays.empty:
        goes_frames.append(goes_xrays)
    if goes_magnetometer is not None and not goes_magnetometer.empty:
        goes_frames.append(goes_magnetometer)

    if goes_protons is not None and not goes_protons.empty:
        proton_features = goes_protons.copy()
        proton_features["timestamp"] = pd.to_datetime(proton_features["time_tag"])
        proton_features.set_index("timestamp", inplace=True)
        proton_columns = [
            col for col in ["flux", "energy", "satellite"] if col in proton_features.columns
        ]
        if proton_columns:
            proton_features = proton_features[proton_columns]
            if "flux" in proton_features.columns:
                proton_features["goes_proton_flux"] = pd.to_numeric(proton_features["flux"], errors="coerce")
            if "energy" in proton_features.columns:
                proton_features["energy"] = proton_features["energy"].astype(str)
                proton_features["goes_proton_energy_code"] = proton_features["energy"].factorize()[0]
            proton_features = proton_features.drop(columns=[col for col in ["flux", "energy", "satellite"] if col in proton_features.columns], errors="ignore")
            proton_features = proton_features.groupby(level=0).mean()
            goes_frames.append(proton_features)

    goes_df = pd.concat(goes_frames, axis=1).sort_index()

    # 2. Fetch 7 days of real-time DSCOVR Solar Wind data (to match the GOES range)
    dscovr_loader = DSCOVRLoader(raw_data_dir=raw_dir)
    logger.info("Fetching DSCOVR 7-day solar wind plasma and magnetic field data...")
    
    plasma_7d_path = os.path.join(raw_dir, "dscovr_plasma_7d.json")
    mag_7d_path = os.path.join(raw_dir, "dscovr_mag_7d.json")
    
    plasma_raw = load_cached_or_download(
        "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
        plasma_7d_path,
        force_download=True
    )
    mag_raw = load_cached_or_download(
        "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json",
        mag_7d_path,
        force_download=True
    )
    
    dscovr_plasma = dscovr_loader._parse_swpc_matrix(plasma_raw, "plasma")
    dscovr_mag = dscovr_loader._parse_swpc_matrix(mag_raw, "mag")
    
    if dscovr_plasma.empty or dscovr_mag.empty:
        logger.error("Failed to parse DSCOVR datasets.")
        return
        
    dscovr_df = dscovr_plasma.join(dscovr_mag, how="outer")

    # 3. Attempt to fetch OMNI hourly data for the corresponding 3 days
    omni_loader = OMNILoader(raw_data_dir=raw_dir)
    goes_times = goes_electrons.index
    start_str = goes_times.min().strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = goes_times.max().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    logger.info(f"Attempting to fetch OMNI dataset from NASA HAPI: {start_str} to {end_str}...")
    omni_df = None
    historical_omni_path = os.path.join(raw_dir, HISTORICAL_OMNI_CACHE)
    if os.path.exists(historical_omni_path):
        logger.info(f"Loading historical OMNI cache from {historical_omni_path} and slicing to GOES range...")
        historical_omni = omni_loader._read_cached_omni_csv(historical_omni_path)
        if historical_omni is not None and not historical_omni.empty:
            omni_df = historical_omni.loc[
                (historical_omni.index >= goes_times.min()) &
                (historical_omni.index <= goes_times.max())
            ].copy()

    try:
        if omni_df is None or omni_df.empty:
            omni_df = omni_loader.fetch_omni_data(
                start_time=start_str,
                end_time=end_str,
                dataset_id="OMNI2_H0_MRG1HR",
                force_download=False
            )
    except Exception as e:
        logger.warning(f"CDAWeb HAPI query failed: {e}")

    # Fallback to DSCOVR values if OMNI is lagging or unavailable
    if omni_df is None or omni_df.empty or "no data" in str(omni_df):
        logger.warning("NASA OMNI dataset is lagging or unavailable. Synthesizing OMNI metrics from DSCOVR L1 measurements...")
        
        omni_df = pd.DataFrame(index=goes_electrons.index)
        
        # Check DSCOVR columns dynamically (handle gsm or renamed headers)
        bx_col = 'dscovr_bx' if 'dscovr_bx' in dscovr_df.columns else 'bx_gsm'
        by_col = 'dscovr_by' if 'dscovr_by' in dscovr_df.columns else 'by_gsm'
        bz_col = 'dscovr_bz' if 'dscovr_bz' in dscovr_df.columns else 'bz_gsm'
        bt_col = 'dscovr_bt' if 'dscovr_bt' in dscovr_df.columns else 'bt'
        
        # Map values with backfill and forwardfill
        omni_df['IMF'] = dscovr_df[bt_col].reindex(goes_electrons.index).ffill().bfill().fillna(5.0)
        omni_df['BX_GSE'] = dscovr_df[bx_col].reindex(goes_electrons.index).ffill().bfill().fillna(0.0)
        omni_df['BY_GSE'] = dscovr_df[by_col].reindex(goes_electrons.index).ffill().bfill().fillna(0.0)
        omni_df['BZ_GSE'] = dscovr_df[bz_col].reindex(goes_electrons.index).ffill().bfill().fillna(0.0)
        omni_df['DENSITY'] = dscovr_df['dscovr_density'].reindex(goes_electrons.index).ffill().bfill().fillna(5.0)
        omni_df['TEMPERATURE'] = dscovr_df['dscovr_temperature'].reindex(goes_electrons.index).ffill().bfill().fillna(100000.0)
        omni_df['VELOCITY'] = dscovr_df['dscovr_speed'].reindex(goes_electrons.index).ffill().bfill().fillna(400.0)
        omni_df['KP'] = 2.0
        omni_df['DST'] = -15.0
        omni_df['AE'] = 120.0
    else:
        omni_df = omni_loader._normalize_omni_dataframe(omni_df)

    # 4. Fetch Solar Flare and regions lists
    solar_loader = SolarLoader(raw_data_dir=raw_dir)
    logger.info("Fetching NOAA solar flares, active regions, and alert-derived CME indicators...")
    regions_raw = solar_loader.fetch_sunspots_active_regions(force_download=True)
    flares_raw = solar_loader.fetch_solar_flares(force_download=True)
    cme_alerts = solar_loader.fetch_cme_alerts(force_download=False)

    solar_frames = [df for df in [regions_raw, flares_raw, cme_alerts] if df is not None and not df.empty]
    solar_df = pd.concat(solar_frames, axis=1).fillna(0) if solar_frames else pd.DataFrame()

    # 5. Synchronize and Merge at 5-minute sampling rate
    logger.info("Synchronizing and merging multiple sensor streams...")
    sync = SpaceWeatherDataSynchronizer(target_frequency="5min")
    merged_df = sync.resample_and_merge(
        goes_df=goes_df,
        omni_df=omni_df,
        dscovr_df=dscovr_df,
        solar_df=solar_df
    )
    
    # 6. Cleaning and Preprocessing
    logger.info("Cleaning dataset and imputing missing values...")
    cleaner = SpaceWeatherDataCleaner()
    cleaned_df = cleaner.enforce_physical_bounds(merged_df)
    cleaned_df = cleaner.remove_outliers_rolling_zscore(cleaned_df, ['electron_flux_2mev'])
    final_cleaned_df = cleaner.impute_missing_values(cleaned_df)
    
    # 7. Inject Solar Storm Spikes to teach models storm dynamics
    logger.info("Injecting solar storm signatures to balance classes...")
    np.random.seed(42)
    num_rows = len(final_cleaned_df)
    
    # Select 8% of points for Moderate storm signatures
    mod_idx = np.random.choice(num_rows, int(num_rows * 0.08), replace=False)
    # Select 4% of points for Severe storm signatures
    sev_idx = np.random.choice(list(set(range(num_rows)) - set(mod_idx)), int(num_rows * 0.04), replace=False)
    
    # Inject Moderate properties
    final_cleaned_df.iloc[mod_idx, final_cleaned_df.columns.get_loc('electron_flux_2mev')] = np.random.uniform(1500, 3000, len(mod_idx))
    final_cleaned_df.iloc[mod_idx, final_cleaned_df.columns.get_loc('VELOCITY')] = np.random.uniform(550, 680, len(mod_idx))
    final_cleaned_df.iloc[mod_idx, final_cleaned_df.columns.get_loc('BZ_GSE')] = np.random.uniform(-8, -4, len(mod_idx))
    final_cleaned_df.iloc[mod_idx, final_cleaned_df.columns.get_loc('KP')] = np.random.randint(4, 6, len(mod_idx))
    final_cleaned_df.iloc[mod_idx, final_cleaned_df.columns.get_loc('DST')] = np.random.uniform(-50, -30, len(mod_idx))
    
    # Inject Severe properties
    final_cleaned_df.iloc[sev_idx, final_cleaned_df.columns.get_loc('electron_flux_2mev')] = np.random.uniform(15000, 75000, len(sev_idx))
    final_cleaned_df.iloc[sev_idx, final_cleaned_df.columns.get_loc('VELOCITY')] = np.random.uniform(750, 950, len(sev_idx))
    final_cleaned_df.iloc[sev_idx, final_cleaned_df.columns.get_loc('BZ_GSE')] = np.random.uniform(-25, -12, len(sev_idx))
    final_cleaned_df.iloc[sev_idx, final_cleaned_df.columns.get_loc('KP')] = np.random.randint(7, 9, len(sev_idx))
    final_cleaned_df.iloc[sev_idx, final_cleaned_df.columns.get_loc('DST')] = np.random.uniform(-150, -80, len(sev_idx))
    engineer = SpaceWeatherFeatureEngineer(target_flux_col="electron_flux_2mev")
    df_features = engineer.generate_features(final_cleaned_df)
    
    # Create Targets
    class_targets = engineer.create_classification_targets(df_features)
    reg_targets = engineer.create_regression_targets(df_features, horizons=[6, 12]) # 30 min, 1 hr ahead
    
    # Align features and targets
    valid_idx = reg_targets.dropna().index
    features_final = df_features.loc[valid_idx]
    class_targets_final = class_targets.loc[valid_idx]
    reg_targets_final = reg_targets.loc[valid_idx]
    
    features_final = features_final.drop(columns=["electron_flux_2mev"])
    input_dim = features_final.shape[1]
    logger.info(f"Final training input dimensions: {features_final.shape}")
    
    # 9. Format Sequences
    X_tensor = torch.tensor(features_final.values, dtype=torch.float32)
    seq_len = 12
    num_samples = len(features_final) - seq_len + 1
    
    X_seq, y_class_seq, y_reg_seq = [], [], []
    for i in range(num_samples):
        X_seq.append(X_tensor[i : i + seq_len].unsqueeze(0))
        y_class_seq.append(class_targets_final.values[i + seq_len - 1])
        y_reg_seq.append(reg_targets_final.values[i + seq_len - 1])
        
    X_seq = torch.cat(X_seq, dim=0)
    y_class_seq = torch.tensor(y_class_seq, dtype=torch.long)
    y_reg_seq = torch.tensor(y_reg_seq, dtype=torch.float32)
    
    # Split into Train and Validation sets (80% / 20%)
    train_size = int(0.8 * num_samples)
    
    X_train, X_val = X_seq[:train_size], X_seq[train_size:]
    y_class_train, y_class_val = y_class_seq[:train_size], y_class_seq[train_size:]
    y_reg_train, y_reg_val = y_reg_seq[:train_size], y_reg_seq[train_size:]
    
    train_loader_class = DataLoader(TensorDataset(X_train, y_class_train), batch_size=256, shuffle=True)
    val_loader_class = DataLoader(TensorDataset(X_val, y_class_val), batch_size=256, shuffle=False)
    
    train_loader_reg = DataLoader(TensorDataset(X_train, y_reg_train), batch_size=256, shuffle=True)
    val_loader_reg = DataLoader(TensorDataset(X_val, y_reg_val), batch_size=256, shuffle=False)
    
    logger.info(f"Data partitioning complete: {train_size} training samples, {num_samples - train_size} validation samples.")
    
    # 10. Train Classifier
    classifier = SpaceWeatherTransformerClassifier(input_dim=input_dim, d_model=32, nhead=2, num_layers=2)
    trainer = SpaceWeatherTrainer(device="cpu")
    
    logger.info("Training Model 1 (Transformer Classifier) for 8 epochs...")
    class_counts = np.bincount(y_class_train.numpy(), minlength=3)
    total_samples = len(y_class_train)
    class_weights = torch.tensor([total_samples / (3 * max(1, count)) for count in class_counts], dtype=torch.float32)
    logger.info(f"Calculated class weights: {class_weights.tolist()}")
    
    trainer.train_classifier(
        model=classifier,
        train_loader=train_loader_class,
        val_loader=val_loader_class,
        epochs=8,
        lr=0.001,
        class_weights=class_weights,
        patience=5,
        checkpoint_dir="saved_models/test_run"
    )
    
    # 11. Train Regressor
    regressor = CustomTemporalFusionTransformer(num_features=input_dim, d_model=32, nhead=2, num_layers=1, horizons=[30, 60])
    logger.info("Training Model 2 (TFT Regressor) for 8 epochs...")
    trainer.train_regressor(
        model=regressor,
        train_loader=train_loader_reg,
        val_loader=val_loader_reg,
        epochs=8,
        lr=0.001,
        patience=5,
        checkpoint_dir="saved_models/test_run"
    )
    
    # 12. Evaluate Model Performance
    logger.info("Running evaluation on validation set...")
    classifier.eval()
    regressor.eval()
    
    with torch.no_grad():
        class_preds = []
        for inputs, _ in val_loader_class:
            logits = classifier(inputs)
            preds = torch.argmax(logits, dim=-1)
            class_preds.extend(preds.numpy())
        class_preds = np.array(class_preds)
        y_class_val_np = y_class_val.numpy()
        
        accuracy = np.mean(class_preds == y_class_val_np)
        logger.info(f"--- MODEL 1 (Classifier) VALIDATION METRICS ---")
        logger.info(f"Accuracy: {accuracy * 100:.2f}%")
        for c in range(3):
            c_mask = (y_class_val_np == c)
            c_acc = np.mean(class_preds[c_mask] == c) if np.sum(c_mask) > 0 else 0.0
            logger.info(f"Class {c} (Safe/Mod/Sev) Recall: {c_acc * 100:.2f}% (Support: {np.sum(c_mask)})")
            
        reg_preds = []
        for inputs, _ in val_loader_reg:
            preds = regressor(inputs)
            reg_preds.append(preds)
        reg_preds = torch.cat(reg_preds, dim=0).numpy()
        y_reg_val_np = y_reg_val.numpy()
        
        mae_30m = np.mean(np.abs(reg_preds[:, 0, 1] - y_reg_val_np[:, 0]))
        mae_1h = np.mean(np.abs(reg_preds[:, 1, 1] - y_reg_val_np[:, 1]))
        
        logger.info(f"--- MODEL 2 (TFT Regressor) VALIDATION METRICS (p50) ---")
        logger.info(f"30-min forecast MAE: {mae_30m:.4f} pfu")
        logger.info(f"1-hour forecast MAE: {mae_1h:.4f} pfu")
        
    logger.info("SWEWS model training pipeline executed successfully! Checkpoints exported to saved_models/test_run/.")

if __name__ == "__main__":
    main()
