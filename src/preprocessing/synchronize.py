import logging
import pandas as pd
from typing import Dict, List, Optional

logger = logging.getLogger("DataSynchronizer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class SpaceWeatherDataSynchronizer:
    """
    Combines heterogeneous space weather datasets (GOES, OMNI, DSCOVR, Solar events)
    sampled at different rates (1-min, 5-min, hourly, and event-based) into a unified,
    uniformly sampled time series.
    """
    def __init__(self, target_frequency: str = "5T"):
        """
        Args:
            target_frequency: Target pandas offset alias (e.g., '5T' for 5 minutes, '1H' for hourly).
        """
        self.target_frequency = target_frequency

    def resample_and_merge(self, goes_df: Optional[pd.DataFrame] = None,
                           omni_df: Optional[pd.DataFrame] = None,
                           dscovr_df: Optional[pd.DataFrame] = None,
                           solar_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Resamples and aligns all available datasets onto a single, synchronized datetime index.
        
        Args:
            goes_df: GOES electron/proton flux DataFrame.
            omni_df: NASA OMNI solar wind/index DataFrame.
            dscovr_df: DSCOVR solar wind plasma/mag DataFrame.
            solar_df: Solar events and flare classification DataFrame.
        Returns:
            pd.DataFrame: Merged, synchronized DataFrame.
        """
        dataframes_to_merge = []
        
        # 1. Resample GOES Data (Typically 5-minute sampling)
        if goes_df is not None and not goes_df.empty:
            logger.info("Resampling GOES satellite measurements...")
            goes_resampled = goes_df.resample(self.target_frequency).mean()
            dataframes_to_merge.append(goes_resampled)
            
        # 2. Resample OMNI Data (Typically hourly sampling)
        if omni_df is not None and not omni_df.empty:
            logger.info("Resampling NASA OMNI planetary indices...")
            # We use forward-fill or linear interpolation to upsample hourly data to e.g. 5-min frequency
            omni_resampled = omni_df.resample(self.target_frequency).interpolate(method="time")
            dataframes_to_merge.append(omni_resampled)
            
        # 3. Resample DSCOVR Data (Typically 1-minute sampling)
        if dscovr_df is not None and not dscovr_df.empty:
            logger.info("Resampling DSCOVR real-time L1 measurements...")
            dscovr_resampled = dscovr_df.resample(self.target_frequency).mean()
            dataframes_to_merge.append(dscovr_resampled)
            
        # 4. Resample Solar Events (Event-based sparse series)
        if solar_df is not None and not solar_df.empty:
            logger.info("Resampling active regions and solar flare events...")
            # Event counts should be aggregated using sum() rather than mean()
            solar_resampled = solar_df.resample(self.target_frequency).sum()
            # If active regions counts are daily, we forward fill them rather than summing
            for col in solar_resampled.columns:
                if 'total_sunspot' in col or 'active_regions' in col:
                    solar_resampled[col] = solar_df[col].resample(self.target_frequency).ffill()
            
            # Fill missing event counts with 0 (no flares observed in interval)
            solar_resampled.fillna(0, inplace=True)
            dataframes_to_merge.append(solar_resampled)
            
        if not dataframes_to_merge:
            logger.warning("No dataframes provided for synchronization!")
            return pd.DataFrame()

        # Merge all dataframes on their DatetimeIndex
        logger.info("Aligning and merging datasets...")
        
        # Localize all datetime indexes to tz-naive to prevent merge failures
        sanitized_dfs = []
        for df in dataframes_to_merge:
            df_copy = df.copy()
            if df_copy.index.tz is not None:
                df_copy.index = df_copy.index.tz_localize(None)
            sanitized_dfs.append(df_copy)
            
        merged_df = sanitized_dfs[0]
        for df in sanitized_dfs[1:]:
            merged_df = merged_df.join(df, how="outer")
            
        # Sort index chronologically
        merged_df.sort_index(inplace=True)
        
        # Log final matrix properties
        logger.info(f"Synchronization complete. Shape: {merged_df.shape} | Columns: {list(merged_df.columns)}")
        return merged_df
