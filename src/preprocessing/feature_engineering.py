import logging
import numpy as np
import pandas as pd
from typing import List, Tuple

logger = logging.getLogger("FeatureEngineer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class SpaceWeatherFeatureEngineer:
    """
    Generates engineered temporal features (rolling statistics, lag elements,
    rates of change) and constructs prediction targets for the modeling suite.
    """
    def __init__(self, target_flux_col: str = "electron_flux_2mev"):
        self.target_flux_col = target_flux_col

    def generate_features(self, df: pd.DataFrame, 
                          rolling_windows: List[int] = [3, 6, 12, 24], 
                          lag_steps: List[int] = [1, 2, 6, 12, 24]) -> pd.DataFrame:
        """
        Calculates time-series features based on physical features (solar wind, IMF, index).
        
        Args:
            df: Synchronized input DataFrame.
            rolling_windows: List of window lengths (in terms of index steps) for calculating rolling stats.
            lag_steps: List of step shifts to create lag features.
        """
        df_feats = df.copy()
        
        # Base physical features to engineer from
        base_cols = [col for col in df.columns if col != self.target_flux_col]
        
        new_features = {}
        
        # 1. Generate Rolling Statistics (Mean, Std Dev, Min, Max)
        logger.info("Computing rolling average, deviation, and extremity features...")
        for col in base_cols:
            if col in df.columns:
                for w in rolling_windows:
                    new_features[f"{col}_roll_mean_{w}"] = df[col].rolling(window=w, min_periods=1).mean()
                    new_features[f"{col}_roll_std_{w}"] = df[col].rolling(window=w, min_periods=1).std().fillna(0)
                    new_features[f"{col}_roll_max_{w}"] = df[col].rolling(window=w, min_periods=1).max()
                    new_features[f"{col}_roll_min_{w}"] = df[col].rolling(window=w, min_periods=1).min()

        # 2. Rate of Change (First-order differences)
        logger.info("Computing rates of change (derivatives)...")
        for col in base_cols:
            if col in df.columns:
                new_features[f"{col}_diff_1"] = df[col].diff(periods=1).fillna(0)
                new_features[f"{col}_diff_3"] = df[col].diff(periods=3).fillna(0)

        # 3. Exponential Moving Averages (EMA)
        logger.info("Computing Exponential Moving Averages...")
        for col in base_cols:
            if col in df.columns:
                new_features[f"{col}_ema_6"] = df[col].ewm(span=6, adjust=False).mean()
                new_features[f"{col}_ema_24"] = df[col].ewm(span=24, adjust=False).mean()

        # 4. Lag Features
        logger.info("Generating historical lag representations...")
        for col in [self.target_flux_col] + base_cols:
            if col in df.columns:
                for lag in lag_steps:
                    new_features[f"{col}_lag_{lag}"] = df[col].shift(periods=lag)

        # Combine original dataframe with the new features dataframe in a single step to avoid fragmentation
        new_features_df = pd.DataFrame(new_features, index=df.index)
        df_feats = pd.concat([df, new_features_df], axis=1)

        # Drop rows containing NaNs introduced by shift/lag operations to keep models clean
        df_feats.dropna(inplace=True)
        return df_feats

    def create_classification_targets(self, df: pd.DataFrame, 
                                       threshold_moderate: float = 1000.0, 
                                       threshold_severe: float = 10000.0) -> pd.Series:
        """
        Creates categorical labels for Model 1 (Storm Classifier).
        
        Args:
            df: Feature engineered DataFrame.
            threshold_moderate: Threshold (pfu) above which environment is 'Moderate'.
            threshold_severe: Threshold (pfu) above which environment is 'Severe'.
        Returns:
            pd.Series: Integer series containing 0 (Safe), 1 (Moderate), or 2 (Severe).
        """
        flux = df[self.target_flux_col]
        
        # Categorize: 0 = Safe, 1 = Moderate, 2 = Severe
        labels = pd.Series(0, index=df.index)
        labels[flux > threshold_moderate] = 1
        labels[flux > threshold_severe] = 2
        
        logger.info(f"Classification targets created. Class counts:\n{labels.value_counts()}")
        return labels

    def create_regression_targets(self, df: pd.DataFrame, 
                                     horizons: List[int] = [6, 9, 72, 144]) -> pd.DataFrame:
        """
        Creates shifted multi-horizon regression targets for Model 2 (TFT Regressor).
        
        Args:
            df: Feature engineered DataFrame.
            horizons: Target indexes to shift (e.g. [6, 9, 72, 144] steps ahead.
                     If indices are 5-min frequency:
                     - 6 steps = 30 minutes
                     - 9 steps = 45 minutes
                     - 72 steps = 6 hours
                     - 144 steps = 12 hours
        Returns:
            pd.DataFrame: DataFrame containing future shifted values.
        """
        targets = {}
        for h in horizons:
            # We shift the target columns backward (shift negative) to represent the future values
            # at the current row's timestamp.
            label = f"target_flux_plus_{h}steps"
            targets[label] = df[self.target_flux_col].shift(-h)
            
        targets_df = pd.DataFrame(targets, index=df.index)
        return targets_df
