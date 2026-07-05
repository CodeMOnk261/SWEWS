import os
import sys
import torch
import numpy as np
import pandas as pd
from torch.utils.data import TensorDataset, DataLoader

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.preprocessing.clean import SpaceWeatherDataCleaner
from src.preprocessing.synchronize import SpaceWeatherDataSynchronizer
from src.preprocessing.feature_engineering import SpaceWeatherFeatureEngineer
from src.models.classifier import SpaceWeatherTransformerClassifier
from src.models.transformer import CustomTemporalFusionTransformer
from src.models.trainer import SpaceWeatherTrainer
from src.utils.logger import setup_logger

logger = setup_logger("PipelineIntegrationTest")

def generate_mock_goes(dates) -> pd.DataFrame:
    # 5-min intervals
    np.random.seed(42)
    flux = 100 + np.exp(np.random.normal(5, 1.5, len(dates))) # simulated exponential electron flux
    # Add occasional severe spikes
    flux[np.random.choice(len(dates), 5, replace=False)] = 50000.0
    
    df = pd.DataFrame({
        'time_tag': dates,
        'energy': ['>2.0 MeV'] * len(dates),
        'flux': flux
    })
    # Add a second channel
    df2 = pd.DataFrame({
        'time_tag': dates,
        'energy': ['>0.8 MeV'] * len(dates),
        'flux': flux * 1.5
    })
    return pd.concat([df, df2]).reset_index(drop=True)

def generate_mock_omni(dates) -> pd.DataFrame:
    # hourly intervals
    hourly_dates = dates[::12]
    np.random.seed(42)
    df = pd.DataFrame({
        'timestamp': hourly_dates,
        'BX_GSE': np.random.normal(0, 5, len(hourly_dates)),
        'BY_GSE': np.random.normal(0, 5, len(hourly_dates)),
        'BZ_GSE': np.random.normal(-2, 6, len(hourly_dates)),
        'DENSITY': np.random.uniform(1.0, 30.0, len(hourly_dates)),
        'TEMPERATURE': np.random.uniform(50000, 200000, len(hourly_dates)),
        'VELOCITY': np.random.uniform(300, 700, len(hourly_dates)),
        'KP': np.random.randint(0, 9, len(hourly_dates)),
        'DST': np.random.normal(-10, 40, len(hourly_dates)),
        'AE': np.random.uniform(10, 800, len(hourly_dates)),
        'IMF': np.random.normal(5, 2, len(hourly_dates))
    })
    # Inject OMNI missing value markers (e.g. 999.9) to test clean script
    df.iloc[5, df.columns.get_loc('DENSITY')] = 999.9
    df.iloc[10, df.columns.get_loc('VELOCITY')] = 9999.0
    return df

def generate_mock_dscovr(dates) -> pd.DataFrame:
    # 1-min intervals, we'll simulate 5-min averages directly
    np.random.seed(42)
    return pd.DataFrame({
        'time_tag': dates,
        'bx': np.random.normal(0, 4, len(dates)),
        'by': np.random.normal(0, 4, len(dates)),
        'bz': np.random.normal(-1, 5, len(dates)),
        'bt': np.random.normal(4, 2, len(dates)),
        'density': np.random.uniform(1.0, 25.0, len(dates)),
        'speed': np.random.uniform(310, 680, len(dates)),
        'temperature': np.random.uniform(40000, 180000, len(dates))
    })

def generate_mock_solar(dates) -> pd.DataFrame:
    # daily active regions, sparse flare events
    np.random.seed(42)
    daily_dates = dates[::288] # 1 day is 288 steps of 5-min
    regions_df = pd.DataFrame({
        'observed_date': daily_dates,
        'region': np.random.randint(1000, 1005, len(daily_dates)),
        'area': np.random.randint(10, 500, len(daily_dates)),
        'number_spots': np.random.randint(1, 20, len(daily_dates))
    })
    
    # sparse flare event dataframe
    flare_times = np.random.choice(dates, 10, replace=False)
    events_df = pd.DataFrame({
        'type': ['XRA'] * len(flare_times),
        'begin_datetime': flare_times,
        'particulars1': np.random.choice(['M1.2', 'C4.5', 'X2.3', 'M5.6'], len(flare_times))
    })
    return regions_df, events_df

def run_integration_test():
    logger.info("Initializing Space Weather Pipeline Integration Test...")
    
    # 1. Generate Timestamps (e.g. 5 days of data at 5-minute sampling)
    dates = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-06 00:00:00", freq="5min")
    
    # Generate mock databases
    goes_raw = generate_mock_goes(dates)
    omni_raw = generate_mock_omni(dates)
    dscovr_raw = generate_mock_dscovr(dates)
    solar_regions, solar_events = generate_mock_solar(dates)
    
    logger.info("Simulated raw databases successfully generated.")
    
    # 2. Resample & Synchronize
    sync = SpaceWeatherDataSynchronizer(target_frequency="5min")
    
    # Process loaders internally (mimic output processing of goes, omni, etc.)
    from src.ingestion.goes_loader import GOESLoader
    from src.ingestion.omni_loader import OMNILoader
    from src.ingestion.dscovr_loader import DSCOVRLoader
    from src.ingestion.solar_loader import SolarLoader
    
    goes_loader = GOESLoader()
    goes_processed = goes_loader._process_electron_dataframe(goes_raw)
    
    omni_loader = OMNILoader()
    # Save temporary file to mock process
    temp_omni_csv = "datasets/raw/temp_omni_test.csv"
    omni_raw.to_csv(temp_omni_csv, index=False, header=False)
    omni_processed = omni_loader._process_omni_csv(temp_omni_csv, 
                     ["IMF","BX_GSE","BY_GSE","BZ_GSE","DENSITY","TEMPERATURE","VELOCITY","KP","DST","AE"])
    os.remove(temp_omni_csv)
    
    dscovr_loader = DSCOVRLoader()
    # Mock structure matrix
    dscovr_matrix = pd.DataFrame(
        [['time_tag', 'bx', 'by', 'bz', 'bt', 'density', 'speed', 'temperature']] + 
        dscovr_raw.values.tolist()
    )
    dscovr_processed_mag = dscovr_loader._parse_swpc_matrix(dscovr_matrix, "mag")
    dscovr_processed_plasma = dscovr_loader._parse_swpc_matrix(dscovr_matrix, "plasma")
    dscovr_processed = dscovr_processed_mag.join(dscovr_processed_plasma)
    
    solar_loader = SolarLoader()
    solar_processed_regions = solar_loader._process_regions(solar_regions)
    solar_processed_flares = solar_loader._process_flares(solar_events)
    solar_processed = solar_processed_regions.join(solar_processed_flares, how="outer").fillna(0)
    
    # Perform synchronization merge
    merged_df = sync.resample_and_merge(
        goes_df=goes_processed,
        omni_df=omni_processed,
        dscovr_df=dscovr_processed,
        solar_df=solar_processed
    )
    
    # 3. Clean
    cleaner = SpaceWeatherDataCleaner()
    cleaned_df = cleaner.enforce_physical_bounds(merged_df)
    cleaned_df = cleaner.remove_outliers_rolling_zscore(cleaned_df, ['electron_flux_2mev'])
    final_cleaned_df = cleaner.impute_missing_values(cleaned_df)
    
    # 4. Feature Engineering
    engineer = SpaceWeatherFeatureEngineer(target_flux_col="electron_flux_2mev")
    df_features = engineer.generate_features(final_cleaned_df, rolling_windows=[3, 6], lag_steps=[1, 2])
    
    # Create Targets
    class_targets = engineer.create_classification_targets(df_features)
    reg_targets = engineer.create_regression_targets(df_features, horizons=[6, 12]) # 30 min, 1 hr ahead
    
    # Align features and targets by dropping NaNs in targets due to future shifting
    valid_idx = reg_targets.dropna().index
    features_final = df_features.loc[valid_idx]
    class_targets_final = class_targets.loc[valid_idx]
    reg_targets_final = reg_targets.loc[valid_idx]
    
    # Remove target column from input feature list
    features_final = features_final.drop(columns=["electron_flux_2mev"])
    
    logger.info(f"Feature matrix complete. Features count: {features_final.shape[1]}")
    
    # Convert to PyTorch Dataloaders
    X_tensor = torch.tensor(features_final.values, dtype=torch.float32)
    # Reshape features to simulate sequence length window for Transformer: [Batch, Seq_Len, Features]
    # For test, let's treat seq_len = 12 steps (1 hour of 5-min data)
    seq_len = 12
    num_samples = len(features_final) - seq_len + 1
    
    X_seq = []
    y_class_seq = []
    y_reg_seq = []
    
    for i in range(num_samples):
        X_seq.append(X_tensor[i : i + seq_len].unsqueeze(0))
        y_class_seq.append(class_targets_final.values[i + seq_len - 1])
        y_reg_seq.append(reg_targets_final.values[i + seq_len - 1])
        
    X_seq = torch.cat(X_seq, dim=0) # [Num_Samples, Seq_Len, Features]
    y_class_seq = torch.tensor(y_class_seq, dtype=torch.long)
    y_reg_seq = torch.tensor(y_reg_seq, dtype=torch.float32)
    
    dataset_class = TensorDataset(X_seq, y_class_seq)
    loader_class = DataLoader(dataset_class, batch_size=8, shuffle=True)
    
    dataset_reg = TensorDataset(X_seq, y_reg_seq)
    loader_reg = DataLoader(dataset_reg, batch_size=8, shuffle=True)
    
    logger.info(f"PyTorch sequences prepared. Samples: {num_samples} | Sequence window: {seq_len}")
    
    # 5. Initialize Models
    input_dim = features_final.shape[1]
    
    classifier = SpaceWeatherTransformerClassifier(input_dim=input_dim, d_model=32, nhead=2, num_layers=2)
    regressor = CustomTemporalFusionTransformer(num_features=input_dim, d_model=32, nhead=2, num_layers=1, horizons=[30, 60])
    
    # 6. Train Mock Single Epoch
    trainer = SpaceWeatherTrainer(device="cpu")
    
    logger.info("Testing Model 1 (Transformer Classifier) training step...")
    class_history = trainer.train_classifier(
        model=classifier,
        train_loader=loader_class,
        val_loader=loader_class,
        epochs=1,
        lr=0.01,
        patience=1,
        checkpoint_dir="saved_models/test_run"
    )
    logger.info("Classifier training step successful.")
    
    logger.info("Testing Model 2 (TFT Regressor) training step...")
    reg_history = trainer.train_regressor(
        model=regressor,
        train_loader=loader_reg,
        val_loader=loader_reg,
        epochs=1,
        lr=0.01,
        patience=1,
        checkpoint_dir="saved_models/test_run"
    )
    logger.info("Regressor training step successful.")
    logger.info("Space Weather Pipeline Integration Test completed successfully!")

if __name__ == "__main__":
    run_integration_test()
