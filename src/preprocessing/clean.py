import logging
import numpy as np
import pandas as pd
from typing import List, Optional

logger = logging.getLogger("DataCleaner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class SpaceWeatherDataCleaner:
    """
    Robust preprocessing class for cleaning space weather observations.
    Handles extreme instrument spikes, physical boundary checks, and temporal missing values.
    """
    def __init__(self):
        # Dictionary of physical bounds for data validation (optional but professional)
        self.physical_bounds = {
            'electron_flux_800kev': (1e-2, 1e7),
            'electron_flux_2mev': (1e-2, 1e7),
            'dscovr_speed': (200.0, 1500.0),      # km/s
            'dscovr_density': (0.01, 150.0),       # cm^-3
            'dscovr_temperature': (1e3, 1e7),      # K
            'dscovr_bx': (-100.0, 100.0),         # nT
            'dscovr_by': (-100.0, 100.0),         # nT
            'dscovr_bz': (-100.0, 100.0)          # nT
        }

    def remove_outliers_rolling_zscore(self, df: pd.DataFrame, columns: List[str], 
                                      window: int = 12, threshold: float = 3.5) -> pd.DataFrame:
        """
        Removes sensor measurement spikes using a rolling Z-score method.
        Spikes are replaced with NaN to be imputed in the next stage.
        """
        df_cleaned = df.copy()
        for col in columns:
            if col in df_cleaned.columns:
                rolling_mean = df_cleaned[col].rolling(window=window, min_periods=1).mean()
                rolling_std = df_cleaned[col].rolling(window=window, min_periods=1).std()
                
                # Prevent division by zero
                rolling_std = rolling_std.replace(0, 1e-6)
                
                z_scores = (df_cleaned[col] - rolling_mean) / rolling_std
                outliers = z_scores.abs() > threshold
                
                num_outliers = outliers.sum()
                if num_outliers > 0:
                    logger.info(f"Flagged {num_outliers} spike outliers in column: {col}")
                    df_cleaned.loc[outliers, col] = np.nan
        return df_cleaned

    def enforce_physical_bounds(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clips or replaces values that exceed absolute physical limits for space environment metrics.
        """
        df_clipped = df.copy()
        for col, bounds in self.physical_bounds.items():
            if col in df_clipped.columns:
                min_val, max_val = bounds
                # Flag violations as NaN so they are properly imputed rather than hard clipped
                violations = (df_clipped[col] < min_val) | (df_clipped[col] > max_val)
                num_violations = violations.sum()
                if num_violations > 0:
                    logger.warning(f"Physical limit check failed for {num_violations} values in: {col}. Setting to NaN.")
                    df_clipped.loc[violations, col] = np.nan
        return df_clipped

    def impute_missing_values(self, df: pd.DataFrame, method: str = "time") -> pd.DataFrame:
        """
        Imputes missing values (NaNs) in the time series using robust interpolation.
        
        Args:
            df: Input pandas DataFrame with a DatetimeIndex.
            method: Interpolation method (e.g., 'time', 'linear', 'quadratic').
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be a DatetimeIndex for time-based interpolation.")
            
        df_imputed = df.copy()
        
        # Log missing statistics before cleaning
        null_counts = df_imputed.isnull().sum()
        for col, count in null_counts.items():
            if count > 0:
                pct = (count / len(df_imputed)) * 100
                logger.info(f"Column '{col}' has {count} missing values ({pct:.2f}%). Imputing...")

        # Perform time-aware interpolation
        df_imputed = df_imputed.interpolate(method=method, limit_direction="both")
        
        # Ensure any remaining NaNs at extremities are forward/backward filled
        df_imputed.ffill(inplace=True)
        df_imputed.bfill(inplace=True)
        
        return df_imputed
