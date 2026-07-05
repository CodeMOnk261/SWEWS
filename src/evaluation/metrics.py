import math
from typing import Dict, List

import numpy as np


def _safe_divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int = 3) -> Dict[str, object]:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    confusion = np.zeros((num_classes, num_classes), dtype=int)
    for truth, pred in zip(y_true, y_pred):
        confusion[truth, pred] += 1

    per_class = {}
    precisions: List[float] = []
    recalls: List[float] = []
    f1_scores: List[float] = []
    supports: List[int] = []

    for class_idx in range(num_classes):
        tp = confusion[class_idx, class_idx]
        fp = confusion[:, class_idx].sum() - tp
        fn = confusion[class_idx, :].sum() - tp
        support = confusion[class_idx, :].sum()

        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        f1 = _safe_divide(2 * precision * recall, precision + recall)

        per_class[str(class_idx)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": int(support)
        }
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
        supports.append(int(support))

    total = max(1, int(np.sum(supports)))
    weighted_precision = float(np.sum(np.array(precisions) * np.array(supports)) / total)
    weighted_recall = float(np.sum(np.array(recalls) * np.array(supports)) / total)
    weighted_f1 = float(np.sum(np.array(f1_scores) * np.array(supports)) / total)

    accuracy = float(np.mean(y_true == y_pred)) if len(y_true) else 0.0
    balanced_accuracy = float(np.mean(recalls)) if recalls else 0.0

    return {
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "macro_precision": float(np.mean(precisions)) if precisions else 0.0,
        "macro_recall": float(np.mean(recalls)) if recalls else 0.0,
        "macro_f1": float(np.mean(f1_scores)) if f1_scores else 0.0,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": confusion.tolist()
    }


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray, horizon_labels: List[str]) -> Dict[str, object]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    metrics_by_horizon: Dict[str, Dict[str, float]] = {}
    maes, rmses, mapes, pears = [], [], [], []

    for idx, label in enumerate(horizon_labels):
        true_vals = y_true[:, idx]
        pred_vals = y_pred[:, idx]
        errors = pred_vals - true_vals

        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(np.square(errors))))

        nonzero_mask = np.abs(true_vals) > 1e-8
        mape = float(np.mean(np.abs(errors[nonzero_mask] / true_vals[nonzero_mask])) * 100) if np.any(nonzero_mask) else 0.0

        if len(true_vals) > 1 and np.std(true_vals) > 0 and np.std(pred_vals) > 0:
            pearson = float(np.corrcoef(true_vals, pred_vals)[0, 1])
        else:
            pearson = 0.0

        ss_res = float(np.sum(np.square(errors)))
        ss_tot = float(np.sum(np.square(true_vals - np.mean(true_vals))))
        r2 = 1.0 - _safe_divide(ss_res, ss_tot) if ss_tot else 0.0

        metrics_by_horizon[label] = {
            "mae": mae,
            "rmse": rmse,
            "mape": mape,
            "pearson": pearson,
            "r2": r2
        }
        maes.append(mae)
        rmses.append(rmse)
        mapes.append(mape)
        pears.append(pearson)

    return {
        "by_horizon": metrics_by_horizon,
        "avg_mae": float(np.mean(maes)) if maes else 0.0,
        "avg_rmse": float(np.mean(rmses)) if rmses else 0.0,
        "avg_mape": float(np.mean(mapes)) if mapes else 0.0,
        "avg_pearson": float(np.mean(pears)) if pears else 0.0
    }
