import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import shutil

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.goes_loader import GOESLoader
from src.ingestion.omni_loader import OMNILoader
from src.ingestion.dscovr_loader import DSCOVRLoader
from src.ingestion.solar_loader import SolarLoader


class TestIngestionLoaders(unittest.TestCase):
    def setUp(self):
        self.temp_dir = "datasets/temp_test_ingestion"
        os.makedirs(self.temp_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("requests.Session.get")
    def test_goes_loader_fetch_electron_flux(self, mock_get):
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """[
            {"time_tag": "2026-06-30 12:00:00", "energy": ">2.0 MeV", "flux": 1500.0, "satellite": 16},
            {"time_tag": "2026-06-30 12:00:00", "energy": ">0.8 MeV", "flux": 5000.0, "satellite": 16},
            {"time_tag": "2026-06-30 12:05:00", "energy": ">2.0 MeV", "flux": 1600.0, "satellite": 16},
            {"time_tag": "2026-06-30 12:05:00", "energy": ">0.8 MeV", "flux": 5200.0, "satellite": 16}
        ]"""
        mock_get.return_value = mock_response

        loader = GOESLoader(raw_data_dir=self.temp_dir)
        df = loader.fetch_electron_flux(days=1, force_download=True)

        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        # Expected pivoted shape: 2 timestamps as index, 2 columns (electron_flux_800kev, electron_flux_2mev)
        self.assertEqual(df.shape, (2, 2))
        self.assertIn("electron_flux_800kev", df.columns)
        self.assertIn("electron_flux_2mev", df.columns)
        self.assertEqual(df.loc[pd.to_datetime("2026-06-30 12:00:00"), "electron_flux_2mev"], 1500.0)

    @patch("requests.Session.get")
    def test_omni_loader_fetch_omni_data(self, mock_get):
        # Mock OMNI HAPI CSV output
        # Columns are requested in OMNI2 native order.
        # We inject a fill value (999.9 for DENSITY) to verify clean mapping to NaN
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            "2026-06-30T12:00:00Z,5.5,1.2,-2.3,4.0,100000.0,3.5,450.0,1.2,3,-15,120\n"
            "2026-06-30T13:00:00Z,5.6,1.3,-2.4,4.1,105000.0,999.9,460.0,1.3,3,-16,125\n"
        )
        mock_get.return_value = mock_response

        loader = OMNILoader(raw_data_dir=self.temp_dir)
        df = loader.fetch_omni_data(
            start_time="2026-06-30T12:00:00Z",
            end_time="2026-06-30T14:00:00Z",
            dataset_id="OMNI2_H0_MRG1HR",
            force_download=True
        )

        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertIn("DENSITY", df.columns)
        self.assertIn("VELOCITY", df.columns)
        self.assertIn("DYNAMIC_PRESSURE", df.columns)
        
        # Row 0: density is 3.5
        self.assertEqual(df.iloc[0]["DENSITY"], 3.5)
        # Row 1: density had 999.9, which should be cleaned to NaN then filled via ffill/bfill
        # Since it forward fills from row 0, it should be 3.5
        self.assertEqual(df.iloc[1]["DENSITY"], 3.5)

    @patch("requests.Session.get")
    def test_dscovr_loader_fetch_realtime_plasma(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        # NOAA SWPC JSON matrices
        mock_response.text = """[
            ["time_tag", "density", "speed", "temperature"],
            ["2026-06-30 12:00:00.000", "5.1", "400.2", "80000.0"],
            ["2026-06-30 12:01:00.000", "5.2", "401.5", "81000.0"]
        ]"""
        mock_get.return_value = mock_response

        loader = DSCOVRLoader(raw_data_dir=self.temp_dir)
        df = loader.fetch_realtime_plasma(force_download=True)

        self.assertIsNotNone(df)
        self.assertEqual(df.shape, (2, 3))
        self.assertIn("dscovr_density", df.columns)
        self.assertIn("dscovr_speed", df.columns)
        self.assertIn("dscovr_temperature", df.columns)
        self.assertEqual(df.iloc[0]["dscovr_speed"], 400.2)

    @patch("requests.Session.get")
    def test_solar_loader_fetch_regions_and_flares(self, mock_get):
        # 1. Test fetch active regions
        mock_response_regions = MagicMock()
        mock_response_regions.status_code = 200
        mock_response_regions.text = """[
            {"observed_date": "2026-06-30", "region": 13000, "area": 150, "number_spots": 5},
            {"observed_date": "2026-06-30", "region": 13001, "area": 200, "number_spots": 8},
            {"observed_date": "2026-07-01", "region": 13000, "area": 160, "number_spots": 6}
        ]"""
        mock_get.return_value = mock_response_regions

        loader = SolarLoader(raw_data_dir=self.temp_dir)
        regions_df = loader.fetch_sunspots_active_regions(force_download=True)

        self.assertIsNotNone(regions_df)
        # Groups by date: 2026-06-30 should sum to area=350, count=13, active_regions=2
        idx_date = pd.to_datetime("2026-06-30")
        self.assertEqual(regions_df.loc[idx_date, "total_sunspot_area"], 350)
        self.assertEqual(regions_df.loc[idx_date, "total_sunspot_count"], 13)
        self.assertEqual(regions_df.loc[idx_date, "active_regions_count"], 2)

        # 2. Test fetch solar flares
        mock_response_flares = MagicMock()
        mock_response_flares.status_code = 200
        mock_response_flares.text = """[
            {"type": "XRA", "begin_datetime": "2026-06-30 12:00:00", "particulars1": "M1.2"},
            {"type": "XRA", "begin_datetime": "2026-06-30 12:30:00", "particulars1": "X2.5"},
            {"type": "XRA", "begin_datetime": "2026-06-30 13:00:00", "particulars1": "C5.4"},
            {"type": "OTH", "begin_datetime": "2026-06-30 13:10:00", "particulars1": "TypeII"}
        ]"""
        mock_get.return_value = mock_response_flares

        flares_df = loader.fetch_solar_flares(force_download=True)
        self.assertIsNotNone(flares_df)
        # Should pivot flare categories (flare_class_m, flare_class_x, flare_class_c) and aggregate hourly
        self.assertIn("flare_class_m", flares_df.columns)
        self.assertIn("flare_class_x", flares_df.columns)
        self.assertIn("flare_class_c", flares_df.columns)
        # Hour 12 flare counts
        idx_hour_12 = pd.to_datetime("2026-06-30 12:00:00")
        self.assertEqual(flares_df.loc[idx_hour_12, "flare_class_m"], 1)
        self.assertEqual(flares_df.loc[idx_hour_12, "flare_class_x"], 1)

    def test_solar_loader_process_alerts(self):
        alerts_df = pd.DataFrame([
            {
                "product_id": "TIIA",
                "issue_datetime": "2026-06-30 21:07:33.340",
                "message": "ALERT: Type II Radio Emission"
            },
            {
                "product_id": "P11W",
                "issue_datetime": "2026-06-30 16:00:16.053",
                "message": "WARNING: Proton 10MeV Integral Flux above 10pfu expected"
            }
        ])

        loader = SolarLoader(raw_data_dir=self.temp_dir)
        processed = loader._process_alerts(alerts_df)

        self.assertIn("cme_indicator", processed.columns)
        self.assertIn("proton_alert", processed.columns)
        self.assertEqual(processed["cme_indicator"].sum(), 1)
        self.assertEqual(processed["proton_alert"].sum(), 1)


if __name__ == "__main__":
    unittest.main()
