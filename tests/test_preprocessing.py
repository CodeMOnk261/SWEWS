import os
import sys
import unittest
import numpy as np
import pandas as pd

# Append project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.preprocessing.clean import SpaceWeatherDataCleaner
from src.preprocessing.synchronize import SpaceWeatherDataSynchronizer
from src.preprocessing.feature_engineering import SpaceWeatherFeatureEngineer


class TestSpaceWeatherDataCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = SpaceWeatherDataCleaner()
        # Create a simple time-series dataframe
        self.dates = pd.date_range(start="2026-06-01 00:00:00", periods=20, freq="5min")
        self.df = pd.DataFrame({
            'electron_flux_2mev': [100.0] * 20,
            'dscovr_speed': [400.0] * 20,
            'dscovr_density': [5.0] * 20
        }, index=self.dates)

    def test_enforce_physical_bounds(self):
        # Inject boundary violations
        self.df.loc[self.dates[5], 'electron_flux_2mev'] = 1e8  # Max limit is 1e7
        self.df.loc[self.dates[10], 'dscovr_speed'] = 100.0     # Min limit is 200.0
        
        cleaned = self.cleaner.enforce_physical_bounds(self.df)
        
        # Violations should be converted to NaN
        self.assertTrue(pd.isna(cleaned.loc[self.dates[5], 'electron_flux_2mev']))
        self.assertTrue(pd.isna(cleaned.loc[self.dates[10], 'dscovr_speed']))
        # Valid values should remain unchanged
        self.assertEqual(cleaned.loc[self.dates[0], 'electron_flux_2mev'], 100.0)

    def test_remove_outliers_rolling_zscore(self):
        # Inject an extreme spike outlier (e.g. 50x mean)
        self.df.loc[self.dates[10], 'electron_flux_2mev'] = 5000.0
        
        cleaned = self.cleaner.remove_outliers_rolling_zscore(self.df, ['electron_flux_2mev'], window=20, threshold=3.0)
        
        # Outlier should be converted to NaN
        self.assertTrue(pd.isna(cleaned.loc[self.dates[10], 'electron_flux_2mev']))
        # Normal data point should not be affected
        self.assertEqual(cleaned.loc[self.dates[0], 'electron_flux_2mev'], 100.0)

    def test_impute_missing_values(self):
        # Inject NaNs
        self.df.loc[self.dates[5], 'electron_flux_2mev'] = np.nan
        self.df.loc[self.dates[0], 'dscovr_speed'] = np.nan # extremity boundary
        
        imputed = self.cleaner.impute_missing_values(self.df)
        
        # NaNs should be imputed
        self.assertFalse(imputed.isnull().values.any())
        self.assertAlmostEqual(imputed.loc[self.dates[5], 'electron_flux_2mev'], 100.0)
        self.assertAlmostEqual(imputed.loc[self.dates[0], 'dscovr_speed'], 400.0)


class TestSpaceWeatherDataSynchronizer(unittest.TestCase):
    def setUp(self):
        self.sync = SpaceWeatherDataSynchronizer(target_frequency="5min")
        self.dates_5m = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-01 02:00:00", freq="5min")
        self.dates_1h = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-01 02:00:00", freq="1h")

    def test_resample_and_merge(self):
        goes_df = pd.DataFrame({'electron_flux_2mev': np.random.rand(len(self.dates_5m))}, index=self.dates_5m)
        omni_df = pd.DataFrame({'DST': np.random.rand(len(self.dates_1h))}, index=self.dates_1h)
        
        merged = self.sync.resample_and_merge(goes_df=goes_df, omni_df=omni_df)
        
        # Output should be resampled to 5-min frequency
        self.assertEqual(len(merged), len(self.dates_5m))
        self.assertIn('electron_flux_2mev', merged.columns)
        self.assertIn('DST', merged.columns)
        # OMNI data should be interpolated/filled, so no NaNs in the middle
        self.assertFalse(merged['DST'].isnull().any())


class TestSpaceWeatherFeatureEngineer(unittest.TestCase):
    def setUp(self):
        self.engineer = SpaceWeatherFeatureEngineer(target_flux_col="electron_flux_2mev")
        self.dates = pd.date_range(start="2026-06-01 00:00:00", periods=50, freq="5min")
        self.df = pd.DataFrame({
            'electron_flux_2mev': np.random.uniform(10.0, 15000.0, len(self.dates)),
            'dscovr_speed': np.random.uniform(300.0, 600.0, len(self.dates)),
            'dscovr_density': np.random.uniform(1.0, 10.0, len(self.dates))
        }, index=self.dates)

    def test_generate_features(self):
        df_feats = self.engineer.generate_features(self.df, rolling_windows=[3], lag_steps=[1, 2])
        
        # Verify rolling columns created
        self.assertIn('dscovr_speed_roll_mean_3', df_feats.columns)
        self.assertIn('dscovr_speed_roll_std_3', df_feats.columns)
        self.assertIn('dscovr_speed_roll_max_3', df_feats.columns)
        self.assertIn('dscovr_speed_roll_min_3', df_feats.columns)
        
        # Verify diff/rate columns created
        self.assertIn('dscovr_speed_diff_1', df_feats.columns)
        
        # Verify EMA columns
        self.assertIn('dscovr_speed_ema_6', df_feats.columns)
        
        # Verify lag columns
        self.assertIn('electron_flux_2mev_lag_1', df_feats.columns)
        self.assertIn('electron_flux_2mev_lag_2', df_feats.columns)
        self.assertIn('dscovr_speed_lag_1', df_feats.columns)
        
        # Shifting/lags introduce NaNs which are dropped, so length will be reduced by max lag
        self.assertEqual(len(df_feats), len(self.df) - 2)

    def test_create_classification_targets(self):
        # Force specific values to check threshold classification
        self.df.loc[self.dates[0], 'electron_flux_2mev'] = 100.0
        self.df.loc[self.dates[1], 'electron_flux_2mev'] = 1500.0
        self.df.loc[self.dates[2], 'electron_flux_2mev'] = 15000.0
        
        labels = self.engineer.create_classification_targets(
            self.df, threshold_moderate=1000.0, threshold_severe=10000.0
        )
        
        self.assertEqual(labels.iloc[0], 0) # Safe
        self.assertEqual(labels.iloc[1], 1) # Moderate
        self.assertEqual(labels.iloc[2], 2) # Severe

    def test_create_regression_targets(self):
        horizons = [2, 5]
        reg_targets = self.engineer.create_regression_targets(self.df, horizons=horizons)
        
        self.assertIn('target_flux_plus_2steps', reg_targets.columns)
        self.assertIn('target_flux_plus_5steps', reg_targets.columns)
        
        # Test backward shift logic: current row target is equal to future row value
        # e.g., target_flux_plus_2steps at index 0 should equal electron_flux_2mev at index 2
        self.assertEqual(
            reg_targets.loc[self.dates[0], 'target_flux_plus_2steps'],
            self.df.loc[self.dates[2], 'electron_flux_2mev']
        )


if __name__ == "__main__":
    unittest.main()
