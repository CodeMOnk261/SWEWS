import json
import os
import random
import sys
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.evaluation.metrics import classification_metrics, regression_metrics
from src.ingestion.dscovr_loader import DSCOVRLoader
from src.ingestion.goes_loader import GOESLoader
from src.ingestion.omni_loader import OMNILoader
from src.ingestion.solar_loader import SolarLoader
from src.models.classifier import SpaceWeatherTransformerClassifier
from src.models.trainer import SpaceWeatherTrainer
from src.models.transformer import CustomTemporalFusionTransformer
from src.preprocessing.clean import SpaceWeatherDataCleaner
from src.preprocessing.feature_engineering import SpaceWeatherFeatureEngineer
from src.preprocessing.synchronize import SpaceWeatherDataSynchronizer
from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger("TuneAndTrain")

SEED = 42
HORIZON_LABELS = ["30_min", "45_min", "6_hours", "12_hours"]
TOP_FEATURE_COUNT = 192
HISTORICAL_GOES_PATH = os.path.join("datasets", "historical", "goes_electron_history.csv")
HISTORICAL_OMNI_PATH = os.path.join("datasets", "historical", "omni_2011-01-01_to_2020-03-31.csv")
RUN_MODE = os.environ.get("SWEWS_RUN_MODE", "all").strip().lower()


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_available_vram_gb(device: str) -> float:
    if device != "cuda" or not torch.cuda.is_available():
        return 0.0
    return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)


def process_proton_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    proton_df = df.copy()
    proton_df["timestamp"] = pd.to_datetime(proton_df["time_tag"])
    proton_df["flux"] = pd.to_numeric(proton_df["flux"], errors="coerce")

    pivot_df = proton_df.pivot_table(
        index="timestamp",
        columns="energy",
        values="flux",
        aggfunc="mean"
    )

    rename_map = {}
    for col in pivot_df.columns:
        safe_label = (
            str(col)
            .replace(">", "gt_")
            .replace(">=", "gte_")
            .replace(" ", "")
            .replace(".", "p")
            .replace("/", "_")
            .replace("-", "_")
            .replace("(", "")
            .replace(")", "")
        )
        rename_map[col] = f"goes_proton_{safe_label.lower()}"

    pivot_df.rename(columns=rename_map, inplace=True)
    pivot_df.columns.name = None
    pivot_df.sort_index(inplace=True)
    return pivot_df


class SequenceWindowDataset(Dataset):
    def __init__(
        self,
        features: np.ndarray,
        class_targets: np.ndarray,
        reg_targets: np.ndarray,
        seq_len: int,
        start_idx: int,
        end_idx: int
    ) -> None:
        self.features = features
        self.class_targets = class_targets
        self.reg_targets = reg_targets
        self.seq_len = seq_len
        self.start_idx = start_idx
        self.end_idx = end_idx

    def __len__(self) -> int:
        return max(0, self.end_idx - self.start_idx)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        seq_idx = self.start_idx + idx
        window = self.features[seq_idx : seq_idx + self.seq_len]
        class_target = self.class_targets[seq_idx]
        reg_target = self.reg_targets[seq_idx]
        return (
            torch.from_numpy(window),
            torch.tensor(class_target, dtype=torch.long),
            torch.from_numpy(reg_target)
        )


def restrict_to_timerange(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    clipped = df.copy()
    if clipped.index.tz is not None:
        clipped.index = clipped.index.tz_localize(None)
    clipped = clipped.sort_index().loc[(clipped.index >= start) & (clipped.index <= end)]
    return clipped


def load_goes_target_dataframe(raw_dir: str) -> Tuple[pd.DataFrame, str]:
    if os.path.exists(HISTORICAL_GOES_PATH):
        historical_df = pd.read_csv(
            HISTORICAL_GOES_PATH,
            parse_dates=["timestamp"],
            index_col="timestamp"
        ).sort_index()
        required_columns = ["electron_flux_800kev", "electron_flux_2mev"]
        available_columns = [col for col in required_columns if col in historical_df.columns]
        historical_df = historical_df[available_columns]
        if historical_df.index.tz is not None:
            historical_df.index = historical_df.index.tz_localize(None)
        logger.info("Using historical GOES target dataset from %s", HISTORICAL_GOES_PATH)
        return historical_df, HISTORICAL_GOES_PATH

    goes_loader = GOESLoader(raw_data_dir=raw_dir)
    recent_df = goes_loader.fetch_electron_flux(days=3, force_download=False)
    if recent_df is None or recent_df.empty:
        raise RuntimeError("GOES electron flux cache is missing or empty.")
    if recent_df.index.tz is not None:
        recent_df.index = recent_df.index.tz_localize(None)
    logger.info("Historical GOES target dataset not found. Falling back to recent GOES cache.")
    return recent_df.sort_index(), "recent_goes_cache"


def load_omni_dataframe(raw_dir: str, goes_start: pd.Timestamp, goes_end: pd.Timestamp) -> Tuple[pd.DataFrame, str]:
    omni_loader = OMNILoader(raw_data_dir=raw_dir)
    candidate_paths = [
        HISTORICAL_OMNI_PATH,
        os.path.join(raw_dir, "omni_2024-01-01_to_2026-07-01.csv")
    ]

    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        omni_df = omni_loader._read_cached_omni_csv(path)
        omni_df = restrict_to_timerange(omni_df, goes_start, goes_end)
        if not omni_df.empty:
            logger.info("Using OMNI dataset from %s", path)
            return omni_df, path

    raise RuntimeError(
        "No OMNI dataset overlaps the GOES target range. "
        "Backfill a historical OMNI cache before long-span training."
    )


def prepare_dataset(config: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    raw_dir = config["data"]["raw_dir"]

    goes_loader = GOESLoader(raw_data_dir=raw_dir)
    dscovr_loader = DSCOVRLoader(raw_data_dir=raw_dir)
    solar_loader = SolarLoader(raw_data_dir=raw_dir)

    goes_electrons, goes_target_source = load_goes_target_dataframe(raw_dir)
    goes_start = goes_electrons.index.min()
    goes_end = goes_electrons.index.max()
    goes_protons = process_proton_dataframe(goes_loader.fetch_proton_flux(days=3, force_download=False))
    goes_xrays = goes_loader.fetch_xray_flux(days=3, force_download=False)
    goes_magnetometer = goes_loader.fetch_magnetometer(days=3, force_download=False)

    goes_frames = [goes_electrons]
    for frame in [goes_protons, goes_xrays, goes_magnetometer]:
        clipped_frame = restrict_to_timerange(frame, goes_start, goes_end)
        if not clipped_frame.empty:
            goes_frames.append(clipped_frame)
    goes_df = pd.concat(goes_frames, axis=1, sort=False).sort_index()
    if goes_df.index.tz is not None:
        goes_df.index = goes_df.index.tz_localize(None)

    plasma_7d_path = os.path.join(raw_dir, "dscovr_plasma_7d.json")
    mag_7d_path = os.path.join(raw_dir, "dscovr_mag_7d.json")
    dscovr_plasma = dscovr_loader._parse_swpc_matrix(pd.read_json(plasma_7d_path), "plasma")
    dscovr_mag = dscovr_loader._parse_swpc_matrix(pd.read_json(mag_7d_path), "mag")
    dscovr_df = restrict_to_timerange(dscovr_plasma.join(dscovr_mag, how="outer"), goes_start, goes_end)

    omni_df, omni_source = load_omni_dataframe(raw_dir, goes_start, goes_end)

    regions_df = solar_loader.fetch_sunspots_active_regions(force_download=False)
    flares_df = solar_loader.fetch_solar_flares(force_download=False)
    alerts_df = solar_loader.fetch_cme_alerts(force_download=False)
    solar_frames = []
    for frame in [regions_df, flares_df, alerts_df]:
        clipped_frame = restrict_to_timerange(frame, goes_start, goes_end)
        if not clipped_frame.empty:
            solar_frames.append(clipped_frame)
    solar_df = pd.concat(solar_frames, axis=1, sort=False).fillna(0) if solar_frames else pd.DataFrame()

    synchronizer = SpaceWeatherDataSynchronizer(target_frequency="5min")
    merged_df = synchronizer.resample_and_merge(
        goes_df=goes_df,
        omni_df=omni_df,
        dscovr_df=dscovr_df,
        solar_df=solar_df
    )
    merged_df = merged_df.loc[goes_df.index.min() : goes_df.index.max()].copy()

    cleaner = SpaceWeatherDataCleaner()
    cleaned_df = cleaner.enforce_physical_bounds(merged_df)
    cleaned_df = cleaner.remove_outliers_rolling_zscore(cleaned_df, ["electron_flux_2mev"])
    cleaned_df = cleaner.impute_missing_values(cleaned_df)

    engineer = SpaceWeatherFeatureEngineer(target_flux_col=config["data"]["target_flux_col"])
    feature_df = engineer.generate_features(cleaned_df)
    class_targets = engineer.create_classification_targets(
        feature_df,
        threshold_moderate=config["data"]["classification_thresholds"]["moderate"],
        threshold_severe=config["data"]["classification_thresholds"]["severe"]
    )
    reg_targets = engineer.create_regression_targets(
        feature_df,
        horizons=config["model_2_tft_regressor"]["horizons"]
    )

    valid_idx = reg_targets.dropna().index
    target_series = feature_df.loc[valid_idx, config["data"]["target_flux_col"]]
    feature_df = feature_df.loc[valid_idx].drop(columns=[config["data"]["target_flux_col"]])
    feature_scores = feature_df.corrwith(target_series).abs().fillna(0.0)
    selected_columns = feature_scores.sort_values(ascending=False).head(
        min(TOP_FEATURE_COUNT, len(feature_scores))
    ).index.tolist()
    feature_df = feature_df[selected_columns]
    class_targets = class_targets.loc[valid_idx]
    reg_targets = reg_targets.loc[valid_idx]

    seq_len = 12
    num_samples = len(feature_df) - seq_len + 1
    if num_samples <= 0:
        raise RuntimeError("Not enough rows to create sequence windows.")

    X_raw = feature_df.values.astype(np.float32)
    y_class_seq = class_targets.values.astype(np.int64)[seq_len - 1 :]
    y_reg_seq = reg_targets.values.astype(np.float32)[seq_len - 1 :]

    train_split = config["data"]["train_split"]
    val_split = config["data"]["val_split"]

    train_end = int(num_samples * train_split)
    train_feature_end = min(len(X_raw), train_end + seq_len - 1)
    train_slice = X_raw[:train_feature_end]
    mean = train_slice.mean(axis=0)
    std = train_slice.std(axis=0)
    std[std < 1e-6] = 1.0
    X_raw = (X_raw - mean) / std

    logger.info(
        "Prepared dataset with %s samples, sequence length %s, and %s selected features.",
        num_samples,
        seq_len,
        X_raw.shape[-1]
    )

    dataset_info = {
        "source_path": goes_target_source,
        "omni_source_path": omni_source,
        "goes_start": goes_df.index.min().isoformat(),
        "goes_end": goes_df.index.max().isoformat(),
        "selected_feature_count": int(X_raw.shape[-1]),
        "num_sequences": int(num_samples),
        "seq_len": int(seq_len)
    }

    return X_raw, y_class_seq, y_reg_seq, dataset_info


def split_dataset(
    X_raw: np.ndarray,
    y_class_seq: np.ndarray,
    y_reg_seq: np.ndarray,
    seq_len: int,
    train_ratio: float,
    val_ratio: float
) -> Dict[str, Any]:
    num_samples = len(y_class_seq)
    train_end = int(num_samples * train_ratio)
    val_end = train_end + int(num_samples * val_ratio)
    return {
        "train_dataset": SequenceWindowDataset(X_raw, y_class_seq, y_reg_seq, seq_len, 0, train_end),
        "val_dataset": SequenceWindowDataset(X_raw, y_class_seq, y_reg_seq, seq_len, train_end, val_end),
        "test_dataset": SequenceWindowDataset(X_raw, y_class_seq, y_reg_seq, seq_len, val_end, num_samples),
        "y_class_train": y_class_seq[:train_end],
        "y_class_val": y_class_seq[train_end:val_end],
        "y_class_test": y_class_seq[val_end:],
        "y_reg_val": y_reg_seq[train_end:val_end],
        "y_reg_test": y_reg_seq[val_end:]
    }


def build_loaders(
    dataset: Dataset,
    batch_size: int,
    shuffle: bool,
    target_type: str
) -> DataLoader:
    loader_kwargs = {
        "batch_size": batch_size,
        "shuffle": shuffle
    }
    if torch.cuda.is_available():
        loader_kwargs["pin_memory"] = True

    if target_type == "classification":
        return DataLoader(
            dataset,
            **loader_kwargs,
            collate_fn=lambda batch: (
                torch.stack([item[0] for item in batch]),
                torch.stack([item[1] for item in batch])
            )
        )
    return DataLoader(
        dataset,
        **loader_kwargs,
        collate_fn=lambda batch: (
            torch.stack([item[0] for item in batch]),
            torch.stack([item[2] for item in batch])
        )
    )


def get_classifier_candidates(device: str, vram_gb: float) -> List[Dict[str, Any]]:
    if device == "cuda" and vram_gb <= 4.5:
        return [
            {
                "name": "clf_gpu_small_safe",
                "d_model": 32,
                "nhead": 2,
                "num_layers": 2,
                "dim_feedforward": 96,
                "dropout": 0.10,
                "lr": 1e-3,
                "weight_decay": 1e-4,
                "batch_size": 16,
                "epochs": 12,
                "patience": 3
            },
            {
                "name": "clf_gpu_balanced_safe",
                "d_model": 48,
                "nhead": 4,
                "num_layers": 2,
                "dim_feedforward": 128,
                "dropout": 0.12,
                "lr": 8e-4,
                "weight_decay": 1e-4,
                "batch_size": 12,
                "epochs": 16,
                "patience": 4
            }
        ]

    return [
        {
            "name": "clf_small_fast",
            "d_model": 32,
            "nhead": 2,
            "num_layers": 2,
            "dim_feedforward": 128,
            "dropout": 0.10,
            "lr": 1e-3,
            "weight_decay": 1e-4,
            "batch_size": 128,
            "epochs": 16,
            "patience": 4
        },
        {
            "name": "clf_balanced",
            "d_model": 64,
            "nhead": 4,
            "num_layers": 2,
            "dim_feedforward": 128,
            "dropout": 0.10,
            "lr": 1e-3,
            "weight_decay": 1e-4,
            "batch_size": 64,
            "epochs": 20,
            "patience": 5
        },
        {
            "name": "clf_deeper",
            "d_model": 64,
            "nhead": 4,
            "num_layers": 3,
            "dim_feedforward": 256,
            "dropout": 0.15,
            "lr": 5e-4,
            "weight_decay": 1e-4,
            "batch_size": 64,
            "epochs": 24,
            "patience": 6
        }
    ]


def get_regressor_candidates(device: str, vram_gb: float) -> List[Dict[str, Any]]:
    if device == "cuda" and vram_gb <= 4.5:
        return [
            {
                "name": "reg_gpu_small_safe",
                "d_model": 24,
                "nhead": 2,
                "num_layers": 1,
                "dropout": 0.10,
                "lr": 1e-3,
                "weight_decay": 1e-4,
                "batch_size": 32,
                "epochs": 4,
                "patience": 2
            },
            {
                "name": "reg_gpu_balanced_safe",
                "d_model": 32,
                "nhead": 2,
                "num_layers": 1,
                "dropout": 0.12,
                "lr": 8e-4,
                "weight_decay": 1e-4,
                "batch_size": 24,
                "epochs": 5,
                "patience": 3
            }
        ]

    return [
        {
            "name": "reg_small_fast",
            "d_model": 32,
            "nhead": 2,
            "num_layers": 1,
            "dropout": 0.10,
            "lr": 1e-3,
            "weight_decay": 1e-4,
            "batch_size": 128,
            "epochs": 8,
            "patience": 3
        },
        {
            "name": "reg_balanced",
            "d_model": 64,
            "nhead": 4,
            "num_layers": 1,
            "dropout": 0.15,
            "lr": 1e-3,
            "weight_decay": 1e-4,
            "batch_size": 64,
            "epochs": 10,
            "patience": 4
        }
    ]


@torch.no_grad()
def predict_classifier(model: torch.nn.Module, dataset: Dataset, batch_size: int, device: str) -> np.ndarray:
    model.eval()
    preds = []
    loader = build_loaders(dataset, batch_size, False, "classification")
    for inputs, _ in loader:
        logits = model(inputs.to(device))
        preds.append(torch.argmax(logits, dim=-1).cpu().numpy())
    return np.concatenate(preds)


@torch.no_grad()
def predict_regressor(model: torch.nn.Module, dataset: Dataset, batch_size: int, device: str) -> np.ndarray:
    model.eval()
    preds = []
    loader = build_loaders(dataset, batch_size, False, "regression")
    for inputs, _ in loader:
        quantiles = model(inputs.to(device)).cpu().numpy()
        preds.append(quantiles[:, :, 1])
    return np.concatenate(preds, axis=0)


def train_classifier_candidate(
    params: Dict[str, Any],
    data: Dict[str, torch.Tensor],
    input_dim: int,
    device: str,
    output_dir: str
) -> Dict[str, Any]:
    run_dir = os.path.join(output_dir, "classifier", params["name"])
    checkpoint_path = os.path.join(run_dir, "best_classifier.pt")
    trainer = SpaceWeatherTrainer(device=device)
    model = SpaceWeatherTransformerClassifier(
        input_dim=input_dim,
        d_model=params["d_model"],
        nhead=params["nhead"],
        num_layers=params["num_layers"],
        dim_feedforward=params["dim_feedforward"],
        dropout=params["dropout"]
    )

    if os.path.exists(checkpoint_path):
        logger.info("Reusing existing classifier checkpoint for candidate %s", params["name"])
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        val_pred = predict_classifier(model, data["val_dataset"], params["batch_size"], device)
        val_metrics = classification_metrics(data["y_class_val"], val_pred)
        score = 0.7 * val_metrics["macro_f1"] + 0.3 * val_metrics["balanced_accuracy"]
        return {
            "params": params,
            "checkpoint_dir": run_dir,
            "val_metrics": val_metrics,
            "selection_score": score
        }

    class_counts = np.bincount(data["y_class_train"], minlength=3)
    total_samples = len(data["y_class_train"])
    class_weights = torch.tensor(
        [total_samples / (3 * max(1, count)) for count in class_counts],
        dtype=torch.float32
    )

    train_loader = build_loaders(data["train_dataset"], params["batch_size"], True, "classification")
    val_loader = build_loaders(data["val_dataset"], params["batch_size"], False, "classification")

    trainer.train_classifier(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=params["epochs"],
        lr=params["lr"],
        weight_decay=params["weight_decay"],
        class_weights=class_weights,
        patience=params["patience"],
        checkpoint_dir=run_dir
    )

    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)

    val_pred = predict_classifier(model, data["val_dataset"], params["batch_size"], device)
    val_metrics = classification_metrics(data["y_class_val"], val_pred)
    score = 0.7 * val_metrics["macro_f1"] + 0.3 * val_metrics["balanced_accuracy"]

    return {
        "params": params,
        "checkpoint_dir": run_dir,
        "val_metrics": val_metrics,
        "selection_score": score
    }


def train_regressor_candidate(
    params: Dict[str, Any],
    data: Dict[str, torch.Tensor],
    input_dim: int,
    horizons: List[int],
    quantiles: List[float],
    device: str,
    output_dir: str
) -> Dict[str, Any]:
    run_dir = os.path.join(output_dir, "regressor", params["name"])
    checkpoint_path = os.path.join(run_dir, "best_tft_regressor.pt")
    trainer = SpaceWeatherTrainer(device=device)
    model = CustomTemporalFusionTransformer(
        num_features=input_dim,
        d_model=params["d_model"],
        nhead=params["nhead"],
        num_layers=params["num_layers"],
        dropout=params["dropout"],
        horizons=horizons,
        num_quantiles=len(quantiles)
    )

    if os.path.exists(checkpoint_path):
        logger.info("Reusing existing regressor checkpoint for candidate %s", params["name"])
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        val_pred = predict_regressor(model, data["val_dataset"], params["batch_size"], device)
        val_metrics = regression_metrics(data["y_reg_val"], val_pred, HORIZON_LABELS)
        score = -val_metrics["avg_mae"]
        return {
            "params": params,
            "checkpoint_dir": run_dir,
            "val_metrics": val_metrics,
            "selection_score": score
        }

    train_loader = build_loaders(data["train_dataset"], params["batch_size"], True, "regression")
    val_loader = build_loaders(data["val_dataset"], params["batch_size"], False, "regression")

    trainer.train_regressor(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=params["epochs"],
        lr=params["lr"],
        weight_decay=params["weight_decay"],
        quantiles=quantiles,
        patience=params["patience"],
        checkpoint_dir=run_dir
    )

    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)

    val_pred = predict_regressor(model, data["val_dataset"], params["batch_size"], device)
    val_metrics = regression_metrics(data["y_reg_val"], val_pred, HORIZON_LABELS)
    score = -val_metrics["avg_mae"]

    return {
        "params": params,
        "checkpoint_dir": run_dir,
        "val_metrics": val_metrics,
        "selection_score": score
    }


def evaluate_best_models(
    classifier_result: Dict[str, Any],
    regressor_result: Dict[str, Any],
    data: Dict[str, torch.Tensor],
    input_dim: int,
    horizons: List[int],
    quantiles: List[float],
    device: str
) -> Dict[str, Any]:
    classifier_params = classifier_result["params"]
    classifier = SpaceWeatherTransformerClassifier(
        input_dim=input_dim,
        d_model=classifier_params["d_model"],
        nhead=classifier_params["nhead"],
        num_layers=classifier_params["num_layers"],
        dim_feedforward=classifier_params["dim_feedforward"],
        dropout=classifier_params["dropout"]
    )
    classifier_ckpt = torch.load(
        os.path.join(classifier_result["checkpoint_dir"], "best_classifier.pt"),
        map_location=device
    )
    classifier.load_state_dict(classifier_ckpt["model_state_dict"])
    classifier.to(device)

    regressor_params = regressor_result["params"]
    regressor = CustomTemporalFusionTransformer(
        num_features=input_dim,
        d_model=regressor_params["d_model"],
        nhead=regressor_params["nhead"],
        num_layers=regressor_params["num_layers"],
        dropout=regressor_params["dropout"],
        horizons=horizons,
        num_quantiles=len(quantiles)
    )
    regressor_ckpt = torch.load(
        os.path.join(regressor_result["checkpoint_dir"], "best_tft_regressor.pt"),
        map_location=device
    )
    regressor.load_state_dict(regressor_ckpt["model_state_dict"])
    regressor.to(device)

    test_class_pred = predict_classifier(
        classifier,
        data["test_dataset"],
        classifier_params["batch_size"],
        device
    )
    test_reg_pred = predict_regressor(
        regressor,
        data["test_dataset"],
        regressor_params["batch_size"],
        device
    )

    return {
        "classifier_test_metrics": classification_metrics(data["y_class_test"], test_class_pred),
        "regressor_test_metrics": regression_metrics(data["y_reg_test"], test_reg_pred, HORIZON_LABELS)
    }


def main() -> None:
    set_seed()
    config = load_config()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    vram_gb = get_available_vram_gb(device)
    output_dir = os.path.join("outputs", "full_training")
    os.makedirs(output_dir, exist_ok=True)

    X_raw, y_class_seq, y_reg_seq, dataset_info = prepare_dataset(config)
    data = split_dataset(
        X_raw,
        y_class_seq,
        y_reg_seq,
        dataset_info["seq_len"],
        config["data"]["train_split"],
        config["data"]["val_split"]
    )
    input_dim = X_raw.shape[-1]
    horizons = config["model_2_tft_regressor"]["horizons"]
    quantiles = config["model_2_tft_regressor"]["quantiles"]

    classifier_candidates = get_classifier_candidates(device, vram_gb)
    regressor_candidates = get_regressor_candidates(device, vram_gb)

    logger.info("Training device: %s | Approx VRAM: %.2f GB", device, vram_gb)
    logger.info("Run mode: %s", RUN_MODE)

    classifier_results: List[Dict[str, Any]] = []
    regressor_results: List[Dict[str, Any]] = []

    if RUN_MODE in {"all", "classifier"}:
        logger.info("Starting classifier tuning across %s candidates...", len(classifier_candidates))
        classifier_results = [
            train_classifier_candidate(candidate, data, input_dim, device, output_dir)
            for candidate in classifier_candidates
        ]
    else:
        logger.info("Skipping classifier training due to run mode: %s", RUN_MODE)
        classifier_results = [
            train_classifier_candidate(candidate, data, input_dim, device, output_dir)
            for candidate in classifier_candidates
            if os.path.exists(os.path.join(output_dir, "classifier", candidate["name"], "best_classifier.pt"))
        ]

    if RUN_MODE in {"all", "regressor"}:
        logger.info("Starting regressor tuning across %s candidates...", len(regressor_candidates))
        regressor_results = [
            train_regressor_candidate(candidate, data, input_dim, horizons, quantiles, device, output_dir)
            for candidate in regressor_candidates
        ]
    else:
        logger.info("Skipping regressor training due to run mode: %s", RUN_MODE)
        regressor_results = [
            train_regressor_candidate(candidate, data, input_dim, horizons, quantiles, device, output_dir)
            for candidate in regressor_candidates
            if os.path.exists(os.path.join(output_dir, "regressor", candidate["name"], "best_tft_regressor.pt"))
        ]

    if not classifier_results:
        raise RuntimeError("No classifier results are available for evaluation.")
    if not regressor_results:
        raise RuntimeError("No regressor results are available for evaluation.")

    best_classifier = max(classifier_results, key=lambda item: item["selection_score"])
    best_regressor = max(regressor_results, key=lambda item: item["selection_score"])

    final_metrics = evaluate_best_models(
        best_classifier,
        best_regressor,
        data,
        input_dim,
        horizons,
        quantiles,
        device
    )

    report = {
        "device": device,
        "dataset": {
            "num_sequences": int(dataset_info["num_sequences"]),
            "seq_len": int(dataset_info["seq_len"]),
            "num_features": int(input_dim),
            "top_feature_count": int(input_dim),
            "train_sequences": int(len(data["train_dataset"])),
            "val_sequences": int(len(data["val_dataset"])),
            "test_sequences": int(len(data["test_dataset"])),
            "target_source": dataset_info["source_path"],
            "omni_source": dataset_info["omni_source_path"],
            "goes_start": dataset_info["goes_start"],
            "goes_end": dataset_info["goes_end"]
        },
        "best_classifier": best_classifier,
        "best_regressor": best_regressor,
        "classifier_candidates": classifier_results,
        "regressor_candidates": regressor_results,
        "final_test_metrics": final_metrics
    }

    report_path = os.path.join(output_dir, "metrics_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Training and tuning complete. Metrics report saved to %s", report_path)
    print(json.dumps(report["final_test_metrics"], indent=2))


if __name__ == "__main__":
    main()
