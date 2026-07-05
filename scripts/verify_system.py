import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import numpy as np
import torch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.evaluation.metrics import classification_metrics, regression_metrics
from src.models.inference import SpaceWeatherPredictor
from src.models.tune_and_train import (
    HORIZON_LABELS,
    build_loaders,
    prepare_dataset,
    set_seed,
    split_dataset,
)
from src.utils.config import load_config


def api_request(method: str, url: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def safe_api_request(method: str, url: str, payload: Dict[str, Any] | None = None) -> Tuple[bool, Dict[str, Any]]:
    try:
        return True, api_request(method, url, payload)
    except urllib.error.HTTPError as exc:
        return False, {"error": f"HTTP {exc.code}", "body": exc.read().decode('utf-8', errors='replace')}
    except Exception as exc:
        return False, {"error": str(exc)}


def iso_age_minutes(timestamp_str: str) -> float | None:
    if not timestamp_str:
        return None
    parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - parsed.astimezone(timezone.utc)).total_seconds() / 60.0


@torch.no_grad()
def run_holdout_verification() -> Dict[str, Any]:
    set_seed()
    config = load_config()
    x_raw, y_class_seq, y_reg_seq, dataset_info = prepare_dataset(config)
    data = split_dataset(
        x_raw,
        y_class_seq,
        y_reg_seq,
        dataset_info["seq_len"],
        config["data"]["train_split"],
        config["data"]["val_split"],
    )

    predictor = SpaceWeatherPredictor(input_dim=x_raw.shape[-1])
    test_dataset = data["test_dataset"]

    class_preds = []
    class_loader = build_loaders(test_dataset, batch_size=64, shuffle=False, target_type="classification")
    for inputs, _ in class_loader:
        logits = predictor.classifier(inputs.to(predictor.device))
        class_preds.append(torch.argmax(logits, dim=-1).cpu().numpy())
    class_preds_np = np.concatenate(class_preds)

    reg_preds = []
    reg_loader = build_loaders(test_dataset, batch_size=64, shuffle=False, target_type="regression")
    for inputs, _ in reg_loader:
        quantiles = predictor.regressor(inputs.to(predictor.device)).cpu().numpy()
        reg_preds.append(quantiles[:, :, 1])
    reg_preds_np = np.concatenate(reg_preds, axis=0)

    sample_window, sample_class_target, sample_reg_target = test_dataset[0]
    direct_prediction = predictor.predict(sample_window.numpy())

    return {
        "dataset": {
            "num_sequences": int(dataset_info["num_sequences"]),
            "seq_len": int(dataset_info["seq_len"]),
            "num_features": int(x_raw.shape[-1]),
            "test_sequences": int(len(test_dataset)),
            "goes_start": dataset_info["goes_start"],
            "goes_end": dataset_info["goes_end"],
            "target_source": dataset_info["source_path"],
            "omni_source": dataset_info["omni_source_path"],
        },
        "classifier_metrics": classification_metrics(data["y_class_test"], class_preds_np),
        "regressor_metrics": regression_metrics(data["y_reg_test"], reg_preds_np, HORIZON_LABELS),
        "sample_window": {
            "storm_target_class": int(sample_class_target.item()),
            "regression_target": sample_reg_target.numpy().tolist(),
            "direct_prediction": direct_prediction,
            "sequence": sample_window.numpy().tolist(),
        },
    }


def check_live_data(api_base: str) -> Dict[str, Any]:
    health_ok, health = safe_api_request("GET", f"{api_base}/health")
    goes_ok, goes = safe_api_request("GET", f"{api_base}/api/live/goes")
    dscovr_ok, dscovr = safe_api_request("GET", f"{api_base}/api/live/dscovr")
    intensity_ok, intensity = safe_api_request("GET", f"{api_base}/api/regression-intensity")

    live_report: Dict[str, Any] = {
        "health_ok": health_ok,
        "goes_ok": goes_ok,
        "dscovr_ok": dscovr_ok,
        "intensity_ok": intensity_ok,
        "health": health,
        "freshness": {},
        "physics_checks": {},
    }

    if goes_ok and goes.get("electrons"):
        latest_electron = goes["electrons"][-1]
        live_report["freshness"]["goes_electrons_minutes"] = iso_age_minutes(latest_electron.get("timestamp", ""))
        live_report["latest_goes_electron"] = latest_electron

    if dscovr_ok and dscovr.get("plasma"):
        latest_plasma = dscovr["plasma"][-1]
        live_report["freshness"]["dscovr_plasma_minutes"] = iso_age_minutes(latest_plasma.get("timestamp", ""))
        live_report["latest_dscovr_plasma"] = latest_plasma
    else:
        latest_plasma = {}

    if dscovr_ok and dscovr.get("mag"):
        latest_mag = dscovr["mag"][-1]
        live_report["freshness"]["dscovr_mag_minutes"] = iso_age_minutes(latest_mag.get("timestamp", ""))
        live_report["latest_dscovr_mag"] = latest_mag
    else:
        latest_mag = {}

    if intensity_ok:
        wind_speed = float(intensity.get("wind_speed", 0.0))
        density = float(intensity.get("density", 0.0))
        bz = float(intensity.get("bz", 0.0))
        dyn_pressure = float(intensity.get("dynamic_pressure", 0.0))
        scaling = float(intensity.get("scaling_factor", 0.0))
        reported_intensity = float(intensity.get("intensity", 0.0))

        recomputed_pressure = 1.67e-6 * density * (wind_speed ** 2)
        recomputed_scaling = max(0.38, min(1.25, (recomputed_pressure / 2.0) ** (-1.0 / 6.0)))
        bz_intensity = max(0.0, -bz / 18.0)
        speed_intensity = max(0.0, (wind_speed - 400.0) / 500.0)
        recomputed_intensity = max(0.05, min(0.98, 0.15 * speed_intensity + 0.85 * bz_intensity))

        live_report["physics_checks"] = {
            "dynamic_pressure_positive": dyn_pressure > 0.0,
            "wind_speed_positive": wind_speed > 0.0,
            "density_positive": density > 0.0,
            "scaling_factor_in_bounds": 0.38 <= scaling <= 1.25,
            "intensity_in_bounds": 0.05 <= reported_intensity <= 0.98,
            "dynamic_pressure_matches_formula": abs(dyn_pressure - recomputed_pressure) < 1e-6,
            "scaling_matches_formula": abs(scaling - recomputed_scaling) < 1e-6,
            "intensity_matches_formula": abs(reported_intensity - recomputed_intensity) < 1e-6,
            "live_flag": bool(intensity.get("live", False)),
        }

    return live_report


def check_predict_api(api_base: str, sample_window: list[list[float]], direct_prediction: Dict[str, Any]) -> Dict[str, Any]:
    ok, response = safe_api_request("POST", f"{api_base}/predict", {"sequence": sample_window})
    report: Dict[str, Any] = {"predict_ok": ok, "api_response": response}
    if not ok:
        return report

    api_probs = response.get("class_probabilities", {})
    direct_probs = direct_prediction.get("class_probabilities", {})
    probability_delta = {
        label: abs(float(api_probs.get(label, 0.0)) - float(direct_probs.get(label, 0.0)))
        for label in ["Safe", "Moderate", "Severe"]
    }

    report["consistency"] = {
        "storm_class_matches": response.get("storm_class") == direct_prediction.get("storm_class"),
        "risk_level_matches": response.get("satellite_risk_level") == direct_prediction.get("satellite_risk_level"),
        "probability_delta": probability_delta,
        "max_probability_delta": max(probability_delta.values()) if probability_delta else None,
    }
    return report


def run_quick_predict_check(api_base: str) -> Dict[str, Any]:
    predictor = SpaceWeatherPredictor()
    sample_window = np.zeros((12, predictor.input_dim), dtype=np.float32).tolist()
    direct_prediction = predictor.predict(np.array(sample_window, dtype=np.float32))
    return check_predict_api(api_base, sample_window, direct_prediction)


def summarize_status(report: Dict[str, Any]) -> Dict[str, Any]:
    holdout = report.get("holdout")
    classifier_accuracy = holdout["classifier_metrics"]["accuracy"] if holdout else None
    classifier_macro_f1 = holdout["classifier_metrics"]["macro_f1"] if holdout else None
    regressor_avg_mae = holdout["regressor_metrics"]["avg_mae"] if holdout else None
    regressor_avg_rmse = holdout["regressor_metrics"]["avg_rmse"] if holdout else None

    predict_report = report.get("api_predict", {})
    predict_consistency = predict_report.get("consistency", {})
    live_checks = report["live"].get("physics_checks", {})

    live_ok = (
        report["live"]["health_ok"]
        and report["live"]["goes_ok"]
        and report["live"]["dscovr_ok"]
        and report["live"]["intensity_ok"]
        and all(bool(v) for v in live_checks.values())
    )
    api_ok = predict_report.get("predict_ok", False) and bool(predict_consistency.get("storm_class_matches", False))

    return {
        "holdout_classifier_accuracy": classifier_accuracy,
        "holdout_classifier_macro_f1": classifier_macro_f1,
        "holdout_regressor_avg_mae": regressor_avg_mae,
        "holdout_regressor_avg_rmse": regressor_avg_rmse,
        "api_predict_consistent": api_ok,
        "live_data_consistent": live_ok,
        "overall_status": "pass" if api_ok and live_ok else "review",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify SWEWS model correctness and live data integrity.")
    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="full",
        help="Use 'quick' for API/live checks only, or 'full' for holdout metrics plus API/live checks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_base = os.environ.get("SWEWS_API_BASE", "http://127.0.0.1:8000")
    output_dir = os.path.join("outputs", "verification")
    os.makedirs(output_dir, exist_ok=True)

    holdout = None
    api_predict: Dict[str, Any]

    if args.mode == "full":
        holdout = run_holdout_verification()
        api_predict = check_predict_api(
            api_base,
            holdout["sample_window"]["sequence"],
            holdout["sample_window"]["direct_prediction"],
        )
    else:
        api_predict = run_quick_predict_check(api_base)

    live = check_live_data(api_base)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_base": api_base,
        "mode": args.mode,
        "holdout": holdout,
        "api_predict": api_predict,
        "live": live,
    }
    report["summary"] = summarize_status(report)

    report_path = os.path.join(output_dir, "verification_report.json")
    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(json.dumps(report["summary"], indent=2))
    print(f"Saved verification report to {report_path}")


if __name__ == "__main__":
    main()
