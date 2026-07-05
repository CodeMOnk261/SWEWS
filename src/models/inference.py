import os
import json
import torch
import numpy as np
from typing import Dict, Any, Optional
from src.models.classifier import SpaceWeatherTransformerClassifier
from src.models.transformer import CustomTemporalFusionTransformer
from src.utils.logger import setup_logger
from src.utils.config import load_config

logger = setup_logger("InferenceEngine")

DEFAULT_CLASSIFIER_CHECKPOINT = os.path.join(
    "outputs", "full_training", "classifier", "clf_gpu_small_safe", "best_classifier.pt"
)
DEFAULT_REGRESSOR_CHECKPOINT = os.path.join(
    "outputs", "full_training", "regressor", "reg_gpu_small_safe", "best_tft_regressor.pt"
)
DEFAULT_INPUT_DIM = 192
DEFAULT_HORIZONS = [6, 9, 72, 144]
DEFAULT_HORIZON_LABELS = ["30_min", "45_min", "6_hours", "12_hours"]
DEFAULT_QUANTILE_LABELS = ["p10", "p50", "p90"]
DEFAULT_CLASS_LABELS = ["Safe", "Moderate", "Severe"]

class SpaceWeatherPredictor:
    """
    Production-grade inference engine that loads trained models and runs sequential
    predictions for early warnings, flux forecasting, and satellite risk assessments.
    """
    def __init__(
        self,
        classifier_checkpoint: str = DEFAULT_CLASSIFIER_CHECKPOINT,
        regressor_checkpoint: str = DEFAULT_REGRESSOR_CHECKPOINT,
        input_dim: int = DEFAULT_INPUT_DIM,
        config_path: str = "config/config.yaml",
        classifier_d_model: Optional[int] = None,
        classifier_nhead: Optional[int] = None,
        classifier_num_layers: Optional[int] = None,
        classifier_dim_feedforward: Optional[int] = None,
        classifier_dropout: Optional[float] = None,
        regressor_d_model: Optional[int] = None,
        regressor_nhead: Optional[int] = None,
        regressor_num_layers: Optional[int] = None,
        regressor_dropout: Optional[float] = None,
        horizons: Optional[list[int]] = None,
        quantile_labels: list[str] = DEFAULT_QUANTILE_LABELS,
    ):
        # Load configuration file dynamically
        config = load_config(config_path)
        
        self.classifier_checkpoint = classifier_checkpoint
        self.regressor_checkpoint = regressor_checkpoint
        self.input_dim = input_dim
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # Prefer the new `forecast:` block; fall back to model_2_tft_regressor.horizons, then hard default.
        forecast_cfg = config.get("forecast", {})
        regressor_cfg = config.get("model_2_tft_regressor", {})
        self.horizons = horizons or forecast_cfg.get("horizons_steps") or regressor_cfg.get("horizons", DEFAULT_HORIZONS)
        self.horizon_labels = forecast_cfg.get("horizon_labels", DEFAULT_HORIZON_LABELS)
        self.quantile_labels = quantile_labels
        # Class label mapping (0 -> Safe, 1 -> Moderate, 2 -> Severe).
        index_to_label = config.get("classes", {}).get("index_to_label", {})
        self.class_labels = []
        for i in range(3):
            label = index_to_label.get(i) or index_to_label.get(str(i))
            self.class_labels.append(label if label is not None else DEFAULT_CLASS_LABELS[i])
        
        self.classifier_config = {
            "d_model": classifier_d_model or config.get("model_1_classifier", {}).get("d_model", 32),
            "nhead": classifier_nhead or config.get("model_1_classifier", {}).get("nhead", 2),
            "num_layers": classifier_num_layers or config.get("model_1_classifier", {}).get("num_layers", 2),
            "dim_feedforward": classifier_dim_feedforward or config.get("model_1_classifier", {}).get("dim_feedforward", 96),
            "dropout": classifier_dropout if classifier_dropout is not None else config.get("model_1_classifier", {}).get("dropout", 0.10),
        }
        self.regressor_config = {
            "d_model": regressor_d_model or config.get("model_2_tft_regressor", {}).get("d_model", 24),
            "nhead": regressor_nhead or config.get("model_2_tft_regressor", {}).get("nhead", 2),
            "num_layers": regressor_num_layers or config.get("model_2_tft_regressor", {}).get("num_layers", 1),
            "dropout": regressor_dropout if regressor_dropout is not None else config.get("model_2_tft_regressor", {}).get("dropout", 0.10),
        }

        # Auto-detect architecture parameters from checkpoints/report to override config mismatches
        self._detect_architecture_parameters()
        
        # Initialize model instances
        self._build_models()
        
        # Load weights
        self._load_checkpoints()
        
        self.classifier.to(self.device).eval()
        self.regressor.to(self.device).eval()

    def _detect_architecture_parameters(self):
        # Try to load metrics_report.json first
        metrics_report_path = os.path.join("outputs", "full_training", "metrics_report.json")
        metrics_data = None
        if os.path.exists(metrics_report_path):
            try:
                with open(metrics_report_path, "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load metrics_report.json: {e}")

        # 1. Classifier detection
        if os.path.exists(self.classifier_checkpoint):
            try:
                classifier_ckpt = torch.load(self.classifier_checkpoint, map_location="cpu")
                clf_sd = classifier_ckpt.get("model_state_dict", classifier_ckpt)
                
                clf_params = None
                if metrics_data:
                    norm_path = os.path.normpath(self.classifier_checkpoint)
                    candidates = metrics_data.get("classifier_candidates", [])
                    best_model = metrics_data.get("best_classifier", {})
                    if best_model:
                        candidates = candidates + [best_model]
                    for cand in candidates:
                        cand_dir = cand.get("checkpoint_dir", "")
                        if cand_dir and os.path.normpath(cand_dir) in norm_path:
                            clf_params = cand.get("params", {})
                            break
                
                if clf_params:
                    self.input_dim = metrics_data.get("dataset", {}).get("num_features", self.input_dim)
                    self.classifier_config["d_model"] = clf_params.get("d_model", self.classifier_config["d_model"])
                    self.classifier_config["nhead"] = clf_params.get("nhead", self.classifier_config["nhead"])
                    self.classifier_config["num_layers"] = clf_params.get("num_layers", self.classifier_config["num_layers"])
                    self.classifier_config["dim_feedforward"] = clf_params.get("dim_feedforward", self.classifier_config["dim_feedforward"])
                    logger.info("Classifier parameters loaded from metrics_report.json matching checkpoint.")
                else:
                    if "feature_projection.weight" in clf_sd:
                        self.input_dim = clf_sd["feature_projection.weight"].shape[1]
                        self.classifier_config["d_model"] = clf_sd["feature_projection.weight"].shape[0]
                    if "transformer_encoder.layers.0.linear1.weight" in clf_sd:
                        self.classifier_config["dim_feedforward"] = clf_sd["transformer_encoder.layers.0.linear1.weight"].shape[0]
                    layer_indices = set()
                    for key in clf_sd.keys():
                        if key.startswith("transformer_encoder.layers."):
                            parts = key.split(".")
                            if len(parts) > 2 and parts[2].isdigit():
                                layer_indices.add(int(parts[2]))
                    if layer_indices:
                        self.classifier_config["num_layers"] = len(layer_indices)
                    
                    # Deduce nhead
                    d_model = self.classifier_config["d_model"]
                    cfg_nhead = self.classifier_config["nhead"]
                    if d_model % cfg_nhead != 0:
                        for divisor in [4, 2, 8, 1]:
                            if d_model % divisor == 0:
                                self.classifier_config["nhead"] = divisor
                                break
                    logger.info("Classifier parameters deduced from state_dict: d_model=%d, nhead=%d, num_layers=%d, dim_feedforward=%d",
                                self.classifier_config["d_model"], self.classifier_config["nhead"],
                                self.classifier_config["num_layers"], self.classifier_config["dim_feedforward"])
            except Exception as e:
                logger.warning(f"Failed to auto-detect classifier architecture from checkpoint: {e}")

        # 2. Regressor detection
        if os.path.exists(self.regressor_checkpoint):
            try:
                regressor_ckpt = torch.load(self.regressor_checkpoint, map_location="cpu")
                reg_sd = regressor_ckpt.get("model_state_dict", regressor_ckpt)
                
                reg_params = None
                if metrics_data:
                    norm_path = os.path.normpath(self.regressor_checkpoint)
                    candidates = metrics_data.get("regressor_candidates", [])
                    best_model = metrics_data.get("best_regressor", {})
                    if best_model:
                        candidates = candidates + [best_model]
                    for cand in candidates:
                        cand_dir = cand.get("checkpoint_dir", "")
                        if cand_dir and os.path.normpath(cand_dir) in norm_path:
                            reg_params = cand.get("params", {})
                            break
                
                if reg_params:
                    self.regressor_config["d_model"] = reg_params.get("d_model", self.regressor_config["d_model"])
                    self.regressor_config["nhead"] = reg_params.get("nhead", self.regressor_config["nhead"])
                    self.regressor_config["num_layers"] = reg_params.get("num_layers", self.regressor_config["num_layers"])
                    logger.info("Regressor parameters loaded from metrics_report.json matching checkpoint.")
                else:
                    d_model = None
                    if "feature_weights" in reg_sd:
                        d_model = reg_sd["feature_weights"].shape[1]
                    elif "feature_projections.0.weight" in reg_sd:
                        d_model = reg_sd["feature_projections.0.weight"].shape[0]
                    
                    if d_model is not None:
                        self.regressor_config["d_model"] = d_model
                    
                    lstm_layers = set()
                    for key in reg_sd.keys():
                        if key.startswith("lstm.weight_ih_l"):
                            parts = key.split("_l")
                            if len(parts) > 1 and parts[-1].isdigit():
                                lstm_layers.add(int(parts[-1]))
                    if lstm_layers:
                        self.regressor_config["num_layers"] = len(lstm_layers)
                    
                    # Deduce nhead
                    d_model = self.regressor_config["d_model"]
                    cfg_nhead = self.regressor_config["nhead"]
                    if d_model % cfg_nhead != 0:
                        for divisor in [4, 2, 8, 1]:
                            if d_model % divisor == 0:
                                self.regressor_config["nhead"] = divisor
                                break
                    logger.info("Regressor parameters deduced from state_dict: d_model=%d, nhead=%d, num_layers=%d",
                                self.regressor_config["d_model"], self.regressor_config["nhead"],
                                self.regressor_config["num_layers"])
            except Exception as e:
                logger.warning(f"Failed to auto-detect regressor architecture from checkpoint: {e}")

    def _build_models(self) -> None:
        self.classifier = SpaceWeatherTransformerClassifier(
            input_dim=self.input_dim,
            d_model=self.classifier_config["d_model"],
            nhead=self.classifier_config["nhead"],
            num_layers=self.classifier_config["num_layers"],
            dim_feedforward=self.classifier_config["dim_feedforward"],
            dropout=self.classifier_config["dropout"]
        )
        self.regressor = CustomTemporalFusionTransformer(
            num_features=self.input_dim,
            d_model=self.regressor_config["d_model"],
            nhead=self.regressor_config["nhead"],
            num_layers=self.regressor_config["num_layers"],
            dropout=self.regressor_config["dropout"],
            horizons=self.horizons,
            num_quantiles=len(self.quantile_labels)
        )

    def _load_checkpoints(self):
        # Load Classifier
        if not os.path.exists(self.classifier_checkpoint):
            raise FileNotFoundError(f"Classifier checkpoint file not found at: {self.classifier_checkpoint}")
            
        try:
            checkpoint = torch.load(self.classifier_checkpoint, map_location=self.device)
            state_dict = checkpoint['model_state_dict']
            if 'feature_projection.weight' in state_dict:
                checkpoint_dim = state_dict['feature_projection.weight'].shape[1]
                if checkpoint_dim != self.input_dim:
                    logger.info(
                        "Classifier checkpoint dimension %s differs from expected %s. Rebuilding inference models.",
                        checkpoint_dim,
                        self.input_dim
                    )
                    self.input_dim = checkpoint_dim
                    self._build_models()
                    self.classifier.to(self.device)
                    self.regressor.to(self.device)
            
            self.classifier.load_state_dict(state_dict)
            logger.info("Successfully loaded classifier checkpoint from: %s", self.classifier_checkpoint)
        except Exception as e:
            logger.error(f"Critical failure loading classifier weights: {e}")
            raise RuntimeError(f"Critical failure loading classifier weights: {e}") from e
            
        # Load Regressor
        if not os.path.exists(self.regressor_checkpoint):
            raise FileNotFoundError(f"Regressor checkpoint file not found at: {self.regressor_checkpoint}")
            
        try:
            checkpoint = torch.load(self.regressor_checkpoint, map_location=self.device)
            self.regressor.load_state_dict(checkpoint['model_state_dict'])
            logger.info("Successfully loaded regressor checkpoint from: %s", self.regressor_checkpoint)
        except Exception as e:
            logger.error(f"Critical failure loading regressor weights: {e}")
            raise RuntimeError(f"Critical failure loading regressor weights: {e}") from e

    @torch.no_grad()
    def predict(self, feature_sequence: np.ndarray) -> Dict[str, Any]:
        """
        Runs sequential predictions.
        
        Args:
            feature_sequence: Sliding window features of shape [seq_len, num_features]
        Returns:
            Dict: Classification probabilities, multi-horizon flux quantiles, and satellite risk level.
        """
        # Ensure 3D shape: [batch_size=1, seq_len, num_features]
        if feature_sequence.ndim == 2:
            x = torch.tensor(feature_sequence, dtype=torch.float32).unsqueeze(0).to(self.device)
        elif feature_sequence.ndim == 3:
            x = torch.tensor(feature_sequence, dtype=torch.float32).to(self.device)
        else:
            raise ValueError("Input feature_sequence must be of shape [seq_len, num_features]")

        # 1. Model 1 (Classification)
        logits = self.classifier(x)
        probabilities = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
        
        class_idx = int(np.argmax(probabilities))
        storm_class = self.class_labels[class_idx] if class_idx < len(self.class_labels) else "Unknown"
        
        # 2. Model 2 (TFT Multi-Horizon Regressor)
        # Output shape: [batch_size=1, num_horizons, num_quantiles]
        quantile_preds = self.regressor(x).squeeze(0).cpu().numpy()
        
        # Define horizons and quantiles mappings
        forecast_output = {}
        for h_idx, h in enumerate(self.horizons):
            h_label = self.horizon_labels[h_idx] if h_idx < len(self.horizon_labels) else f"step_{h}"
            forecast_output[h_label] = {}
            for q_idx, q_label in enumerate(self.quantile_labels):
                val = float(quantile_preds[h_idx, q_idx])
                forecast_output[h_label][q_label] = max(0.0, val)

        # 3. Satellite Risk Level Assessment
        # Risk level is derived from class prediction and worst-case p90 flux projection
        p50_max_flux = max(forecast_output[h]["p50"] for h in forecast_output)
        p90_max_flux = max(forecast_output[h]["p90"] for h in forecast_output)
        
        if storm_class == "Severe" or p90_max_flux > 10000.0:
            risk_level = "Critical"
        elif storm_class == "Moderate" or p50_max_flux > 1000.0:
            risk_level = "Elevated"
        else:
            risk_level = "Normal"

        return {
            "status": "success",
            "storm_class": storm_class,
            "class_probabilities": {
                self.class_labels[0]: float(probabilities[0]),
                self.class_labels[1]: float(probabilities[1]),
                self.class_labels[2]: float(probabilities[2]),
            },
            "forecasts": forecast_output,
            "satellite_risk_level": risk_level
        }
