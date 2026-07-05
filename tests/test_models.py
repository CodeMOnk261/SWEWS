import os
import sys
import unittest
import torch
import numpy as np
import shutil

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models.classifier import (
    PositionalEncoding,
    AttentionPooling,
    SpaceWeatherTransformerClassifier
)
from src.models.transformer import (
    GatedLinearUnit,
    GatedResidualNetwork,
    VariableSelectionNetwork,
    CustomTemporalFusionTransformer
)
from src.models.trainer import QuantileLoss, EarlyStopping
from src.models.inference import SpaceWeatherPredictor


class TestClassifierComponents(unittest.TestCase):
    def test_positional_encoding(self):
        pe = PositionalEncoding(d_model=32, max_len=100)
        x = torch.zeros(4, 10, 32)
        out = pe(x)
        self.assertEqual(out.shape, (4, 10, 32))
        # Ensure not all elements are zero (encodings added)
        self.assertFalse(torch.all(out == 0))

    def test_attention_pooling(self):
        pool = AttentionPooling(d_model=32)
        x = torch.randn(4, 10, 32)
        out = pool(x)
        self.assertEqual(out.shape, (4, 32))

    def test_transformer_classifier(self):
        model = SpaceWeatherTransformerClassifier(input_dim=15, d_model=32, nhead=2, num_layers=1, num_classes=3)
        x = torch.randn(4, 10, 15)
        out = model(x)
        self.assertEqual(out.shape, (4, 3))


class TestTransformerComponents(unittest.TestCase):
    def test_gated_linear_unit(self):
        glu = GatedLinearUnit(d_model=16)
        x = torch.randn(4, 10, 16)
        out = glu(x)
        self.assertEqual(out.shape, (4, 10, 16))

    def test_gated_residual_network(self):
        grn = GatedResidualNetwork(d_model=16)
        x = torch.randn(4, 10, 16)
        out = grn(x)
        self.assertEqual(out.shape, (4, 10, 16))

    def test_variable_selection_network(self):
        vsn = VariableSelectionNetwork(num_features=5, d_model=16)
        # Input shape: [batch, seq_len, num_features, d_model]
        x = torch.randn(4, 10, 5, 16)
        out = vsn(x)
        self.assertEqual(out.shape, (4, 10, 16))

    def test_custom_temporal_fusion_transformer(self):
        model = CustomTemporalFusionTransformer(
            num_features=10, d_model=16, nhead=2, num_layers=1, horizons=[30, 60]
        )
        x = torch.randn(4, 12, 10)
        out = model(x)
        # Should output shape [batch, len(horizons), num_quantiles]
        # Horizons length = 2, default num_quantiles = 3 (0.1, 0.5, 0.9)
        self.assertEqual(out.shape, (4, 2, 3))


class TestTrainerComponents(unittest.TestCase):
    def test_quantile_loss(self):
        loss_fn = QuantileLoss(quantiles=[0.1, 0.5, 0.9])
        
        # Preds shape: [batch_size, num_horizons, num_quantiles]
        preds = torch.tensor([[[1.0, 2.0, 3.0]]])  # shape [1, 1, 3]
        # Targets shape: [batch_size, num_horizons]
        targets = torch.tensor([[2.0]])  # shape [1, 1]
        
        # Error for q=0.1: 2.0 - 1.0 = 1.0. Loss = 0.1 * 1.0 = 0.1
        # Error for q=0.5: 2.0 - 2.0 = 0.0. Loss = 0.5 * 0.0 = 0.0
        # Error for q=0.9: 2.0 - 3.0 = -1.0. Loss = (0.9 - 1) * -1.0 = 0.1
        # Mean loss: (0.1 + 0.0 + 0.1) / 3 = 0.06666...
        loss = loss_fn(preds, targets)
        self.assertAlmostEqual(loss.item(), 0.06666667, places=5)

    def test_early_stopping(self):
        temp_dir = "saved_models/temp_test_stop"
        checkpoint_path = os.path.join(temp_dir, "best_model.pt")
        
        model = torch.nn.Linear(10, 2)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        
        early_stopping = EarlyStopping(patience=3, min_delta=0.0, checkpoint_path=checkpoint_path)
        
        # 1. Validation loss decreases (should save checkpoint)
        early_stopping(0.5, model, optimizer, epoch=1)
        self.assertTrue(os.path.exists(checkpoint_path))
        self.assertEqual(early_stopping.best_loss, 0.5)
        self.assertEqual(early_stopping.counter, 0)
        self.assertFalse(early_stopping.early_stop)
        
        # 2. Validation loss increases (counter should increment)
        early_stopping(0.6, model, optimizer, epoch=2)
        self.assertEqual(early_stopping.counter, 1)
        self.assertFalse(early_stopping.early_stop)
        
        # 3. Validation loss increases again
        early_stopping(0.7, model, optimizer, epoch=3)
        self.assertEqual(early_stopping.counter, 2)
        self.assertFalse(early_stopping.early_stop)
        
        # 4. Validation loss increases third time (should trigger early stop)
        early_stopping(0.8, model, optimizer, epoch=4)
        self.assertEqual(early_stopping.counter, 3)
        self.assertTrue(early_stopping.early_stop)
        
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


class TestInferencePredictor(unittest.TestCase):
    def test_predictor_mock_inference(self):
        # We can use the mock models trained during integration test
        # Let's instantiate predictor pointing to 'saved_models/test_run'
        # If checkpoints don't exist, it should fallback gracefully to random initialization.
        predictor = SpaceWeatherPredictor(
            classifier_checkpoint="saved_models/test_run/best_classifier.pt",
            regressor_checkpoint="saved_models/test_run/best_tft_regressor.pt",
            input_dim=707,
            classifier_d_model=32,
            classifier_nhead=2,
            classifier_num_layers=2,
            classifier_dim_feedforward=128,
            regressor_d_model=32,
            regressor_nhead=2,
            regressor_num_layers=1,
            horizons=[30, 60]
        )
        
        # Generate valid feature sequence of shape [seq_len=12, num_features=707]
        seq = np.random.randn(12, 707)
        res = predictor.predict(seq)
        
        self.assertEqual(res["status"], "success")
        self.assertIn(res["storm_class"], ["Safe", "Moderate", "Severe"])
        self.assertIn("class_probabilities", res)
        self.assertIn("forecasts", res)
        self.assertIn(res["satellite_risk_level"], ["Normal", "Elevated", "Critical"])
        
        # Check that forecast contains all target horizons
        self.assertIn("30_min", res["forecasts"])
        self.assertIn("45_min", res["forecasts"])


if __name__ == "__main__":
    unittest.main()
