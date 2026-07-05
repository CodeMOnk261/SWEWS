import os
import sys
import json
import numpy as np
import pandas as pd
import torch
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models.inference import SpaceWeatherPredictor
from src.models.tune_and_train import prepare_dataset, split_dataset, set_seed
from src.utils.config import load_config

def main():
    set_seed()
    config = load_config()
    
    print("Loading datasets and preparing features...")
    x_raw, y_class_seq, y_reg_seq, dataset_info = prepare_dataset(config)
    
    # Calculate splits
    num_samples = len(y_class_seq)
    train_ratio = config["data"]["train_split"]
    val_ratio = config["data"]["val_split"]
    train_end = int(num_samples * train_ratio)
    val_end = train_end + int(num_samples * val_ratio)
    
    # Normalize features using training statistics
    seq_len = dataset_info["seq_len"]
    train_feature_end = min(len(x_raw), train_end + seq_len - 1)
    train_slice = x_raw[:train_feature_end]
    mean = train_slice.mean(axis=0)
    std = train_slice.std(axis=0)
    std[std < 1e-6] = 1.0
    x_normalized = (x_raw - mean) / std

    # Timestamps index
    # Note: prepare_dataset filters to valid index
    # We load OMNI & GOES, merge them, select valid indexes.
    # The timestamps for y_class_seq are:
    goes_electrons, _ = prepare_dataset_for_timestamps(config)
    # Align to feature df indices
    goes_start = goes_electrons.index.min()
    goes_end = goes_electrons.index.max()
    
    # Recreate merged_df index to extract timestamps accurately
    from src.ingestion.goes_loader import GOESLoader
    from src.ingestion.omni_loader import OMNILoader
    from src.preprocessing.synchronize import SpaceWeatherDataSynchronizer
    
    goes_loader = GOESLoader(raw_data_dir=config["data"]["raw_dir"])
    goes_electrons_raw, _ = goes_loader.fetch_electron_flux(days=3, force_download=False), None
    if os.path.exists("datasets/historical/goes_electron_history.csv"):
        goes_electrons_raw = pd.read_csv("datasets/historical/goes_electron_history.csv", parse_dates=["timestamp"], index_col="timestamp")
    
    omni_loader = OMNILoader(raw_data_dir=config["data"]["raw_dir"])
    omni_df = pd.read_csv("datasets/historical/omni_2011-01-01_to_2020-03-31.csv", parse_dates=["timestamp"], index_col="timestamp")
    
    synchronizer = SpaceWeatherDataSynchronizer(target_frequency="5min")
    merged_df = synchronizer.resample_and_merge(
        goes_df=goes_electrons_raw[["electron_flux_2mev"]], 
        omni_df=omni_df[["BZ_GSE"]],
        dscovr_df=pd.DataFrame(),
        solar_df=pd.DataFrame()
    )
    merged_df = merged_df.loc[goes_electrons_raw.index.min() : goes_electrons_raw.index.max()].copy()
    
    # We must construct targets to align indices
    from src.preprocessing.feature_engineering import SpaceWeatherFeatureEngineer
    engineer = SpaceWeatherFeatureEngineer(target_flux_col=config["data"]["target_flux_col"])
    reg_targets = engineer.create_regression_targets(merged_df, horizons=config["model_2_tft_regressor"]["horizons"])
    valid_idx = reg_targets.dropna().index
    timestamps = valid_idx[seq_len - 1:]

    # Get holdout split datasets
    y_class_test = y_class_seq[val_end:]
    y_reg_test = y_reg_seq[val_end:]
    test_timestamps = timestamps[val_end:]
    
    print(f"Total test samples: {len(y_class_test)}")
    
    # Initialize Predictor
    print("Initializing inference engine...")
    predictor = SpaceWeatherPredictor(input_dim=x_raw.shape[-1])
    
    # Find some critical events (Severe = 2, Moderate = 1)
    severe_indices = np.where(y_class_test == 2)[0]
    moderate_indices = np.where(y_class_test == 1)[0]
    safe_indices = np.where(y_class_test == 0)[0]
    
    print(f"Found {len(severe_indices)} Severe samples, {len(moderate_indices)} Moderate samples, {len(safe_indices)} Safe samples in holdout set.")
    
    # Let's pick 3 Severe events, 3 Moderate events, and 2 Safe events
    # We want events that are spread out, not adjacent frames.
    def select_spread_indices(indices, count=3, min_gap=50):
        selected = []
        for idx in indices:
            if len(selected) >= count:
                break
            if not selected or all(abs(idx - s) > min_gap for s in selected):
                selected.append(int(idx))
        return selected

    selected_severe = select_spread_indices(severe_indices, 3)
    selected_moderate = select_spread_indices(moderate_indices, 3)
    selected_safe = select_spread_indices(safe_indices, 2)
    
    all_selected = [
        ("Severe", selected_severe),
        ("Moderate", selected_moderate),
        ("Safe", selected_safe)
    ]
    
    results = []
    
    for category, indices in all_selected:
        for idx in indices:
            # Reconstruct sequence index in the normalized features array
            seq_start_idx = val_end + idx
            feature_window = x_normalized[seq_start_idx : seq_start_idx + seq_len]
            
            # Predict
            pred = predictor.predict(feature_window)
            
            # Get actual values
            actual_class = int(y_class_test[idx])
            actual_reg = y_reg_test[idx].tolist() # 30m, 45m, 6h, 12h
            timestamp = test_timestamps[idx].isoformat()
            
            # Format comparison
            event_res = {
                "timestamp": timestamp,
                "category": category,
                "actual_class": predictor.class_labels[actual_class],
                "predicted_class": pred["storm_class"],
                "class_probabilities": pred["class_probabilities"],
                "actual_flux": {
                    "30_min": float(actual_reg[0]),
                    "45_min": float(actual_reg[1]),
                    "6_hours": float(actual_reg[2]),
                    "12_hours": float(actual_reg[3])
                },
                "predicted_flux": pred["forecasts"],
                "satellite_risk_level": pred["satellite_risk_level"]
            }
            results.append(event_res)
            
            print(f"Processed event at {timestamp} ({category}) -> Predicted {pred['storm_class']} (Risk: {pred['satellite_risk_level']})")

    # Output to file
    out_dir = os.path.join("outputs", "verification")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "critical_events_predictions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"Successfully generated critical events predictions and saved to {out_path}")
    
    # Let's generate a markdown report
    generate_markdown_report(results)

def prepare_dataset_for_timestamps(config):
    # Minimal target dataframe loading
    from src.models.tune_and_train import load_goes_target_dataframe
    goes_electrons, goes_target_source = load_goes_target_dataframe(config["data"]["raw_dir"])
    return goes_electrons, goes_target_source

def generate_markdown_report(results):
    report_content = """# Critical Events Prediction Report
Generated on: {now}

This report evaluates the Space Weather Early Warning System (SWEWS) prediction model on actual historical space weather events from the holdout validation/test set. We selected a set of historical events representing **Severe**, **Moderate**, and **Safe** geomagnetic storms to evaluate the performance of our prediction model.

## Model Summary
- **Classifier model**: Transformer Classifier (`clf_gpu_small_safe`)
- **Regressor model**: Custom Temporal Fusion Transformer (`reg_gpu_small_safe`)

---

## Prediction Performance Table

| Event Timestamp | Actual Category | Predicted Category | Risk Level | 30 Min Target / p50 | 45 Min Target / p50 | 6 Hr Target / p50 | 12 Hr Target / p50 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
""".format(now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    for r in results:
        t_30 = f"{r['actual_flux']['30_min']:.1f} / {r['predicted_flux']['30_min']['p50']:.1f}"
        t_45 = f"{r['actual_flux']['45_min']:.1f} / {r['predicted_flux']['45_min']['p50']:.1f}"
        t_6h = f"{r['actual_flux']['6_hours']:.1f} / {r['predicted_flux']['6_hours']['p50']:.1f}"
        t_12h = f"{r['actual_flux']['12_hours']:.1f} / {r['predicted_flux']['12_hours']['p50']:.1f}"
        
        report_content += "| {ts} | **{act}** | {pred} | `{risk}` | {t30} | {t45} | {t6h} | {t12h} |\n".format(
            ts=r["timestamp"], act=r["actual_class"], pred=r["predicted_class"],
            risk=r["satellite_risk_level"], t30=t_30, t45=t_45, t6h=t_6h, t12h=t_12h
        )
        
    report_content += "\n---\n\n## Detailed Event Analysis\n\n"
    
    for idx, r in enumerate(results):
        report_content += "### Event {num}: {ts} ({cat} Event)\n".format(num=idx+1, ts=r["timestamp"], cat=r["category"])
        report_content += "- **Actual Class**: `{act}`\n".format(act=r["actual_class"])
        report_content += "- **Predicted Class**: `{pred}`\n".format(pred=r["predicted_class"])
        report_content += "- **Satellite Risk Level**: `{risk}`\n".format(risk=r["satellite_risk_level"])
        report_content += "- **Class Probabilities**:\n"
        for label, prob in r["class_probabilities"].items():
            report_content += "  - **{label}**: {prob:.2%}\n".format(label=label, prob=prob)
            
        report_content += "- **Multi-Horizon Flux Forecasting (Quantiles vs Target)**:\n"
        report_content += "  | Horizon | Actual Target | Predicted p10 | Predicted p50 | Predicted p90 | Coverage Status |\n"
        report_content += "  | :--- | :---: | :---: | :---: | :---: | :---: |\n"
        
        for horizon in ["30_min", "45_min", "6_hours", "12_hours"]:
            act = r["actual_flux"][horizon]
            p10 = r["predicted_flux"][horizon]["p10"]
            p50 = r["predicted_flux"][horizon]["p50"]
            p90 = r["predicted_flux"][horizon]["p90"]
            
            covered = "✅ Within bounds" if p10 <= act <= p90 else "❌ Out of bounds"
            report_content += "  | {hor} | {act:.1f} | {p10:.1f} | **{p50:.1f}** | {p90:.1f} | {cov} |\n".format(
                hor=horizon, act=act, p10=p10, p50=p50, p90=p90, cov=covered
            )
        report_content += "\n"

    # Save to outputs
    md_out_path = os.path.join("outputs", "verification", "critical_events_analysis.md")
    with open(md_out_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    # Also save to conversation artifacts folder
    artifact_dir = "C:/Users/DELL 7520/.gemini/antigravity-cli/brain/ae75cc35-265e-4346-9a2c-fe5f94bbcc5f"
    os.makedirs(artifact_dir, exist_ok=True)
    artifact_path = os.path.join(artifact_dir, "critical_events_report.md")
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"Saved markdown report to {md_out_path} and artifact {artifact_path}")

if __name__ == "__main__":
    main()
