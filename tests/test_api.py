import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# We import the FastAPI app instance from src.api.app
from src.api.app import app, PredictionRequest


class TestAPI(unittest.TestCase):
    def setUp(self):
        # Create a TestClient instance for testing the FastAPI application
        self.client = TestClient(app)

    @patch("src.api.app.predictor")
    def test_health_check(self, mock_predictor):
        # Configure mock predictor
        mock_predictor.device = "cpu"
        
        # Test GET /health
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["device"], "cpu")
        self.assertTrue(data["models_loaded"])

    @patch("src.api.app.predictor")
    def test_predict_endpoint_success(self, mock_predictor):
        # Configure mock predictor.predict output
        mock_predictor.input_dim = 5
        mock_predictor.predict.return_value = {
            "status": "success",
            "storm_class": "Safe",
            "class_probabilities": {"Safe": 0.95, "Moderate": 0.04, "Severe": 0.01},
            "forecasts": {
                "30_min": {"p10": 100.0, "p50": 120.0, "p90": 150.0},
                "45_min": {"p10": 110.0, "p50": 130.0, "p90": 160.0},
                "6_hours": {"p10": 150.0, "p50": 180.0, "p90": 220.0},
                "12_hours": {"p10": 200.0, "p50": 250.0, "p90": 300.0}
            },
            "satellite_risk_level": "Normal"
        }

        # Send valid 2D array of shape [seq_len=2, num_features=5]
        payload = {
            "sequence": [
                [1.0, 2.0, 3.0, 4.0, 5.0],
                [1.1, 2.1, 3.1, 4.1, 5.1]
            ]
        }
        
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["storm_class"], "Safe")
        self.assertEqual(data["satellite_risk_level"], "Normal")
        
        # Verify the predictor was called with the converted numpy array
        mock_predictor.predict.assert_called_once()

    @patch("src.api.app.predictor")
    def test_predict_endpoint_dimension_mismatch(self, mock_predictor):
        mock_predictor.input_dim = 5
        
        # Send array with wrong number of features (4 columns instead of 5)
        payload = {
            "sequence": [
                [1.0, 2.0, 3.0, 4.0]
            ]
        }
        
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Features dimension mismatch", response.json()["detail"])

    @patch("src.api.app.predictor")
    def test_predict_endpoint_invalid_dimensions(self, mock_predictor):
        mock_predictor.input_dim = 5
        
        # Send 1D array instead of 2D
        payload = {
            "sequence": [1.0, 2.0, 3.0, 4.0, 5.0]
        }
        
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
