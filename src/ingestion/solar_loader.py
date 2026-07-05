import os
import logging
import requests
import pandas as pd
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from typing import Optional

logger = logging.getLogger("SolarLoader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class SolarLoader:
    """
    Data ingestion loader for Solar Observatories and events data.
    Fetches solar flares, sunspot numbers, active region dynamics, and Coronal Mass Ejection (CME) alerts.
    """
    SWPC_BASE_URL = "https://services.swpc.noaa.gov/json"

    def __init__(self, raw_data_dir: str = "datasets/raw"):
        self.raw_data_dir = raw_data_dir
        os.makedirs(self.raw_data_dir, exist_ok=True)
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_sunspots_active_regions(self, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Ingests active region and sunspot details.
        """
        url = f"{self.SWPC_BASE_URL}/solar_regions.json"
        local_path = os.path.join(self.raw_data_dir, "solar_regions.json")
        
        if not force_download and os.path.exists(local_path):
            logger.info(f"Loading cached solar regions data from: {local_path}")
            try:
                df = pd.read_json(local_path)
                return self._process_regions(df)
            except Exception as e:
                logger.warning(f"Failed to read cached solar regions file ({e}). Re-downloading...")
                
        logger.info(f"Downloading solar regions from NOAA: {url}")
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            with open(local_path, "w") as f:
                f.write(response.text)
                
            df = pd.read_json(local_path)
            return self._process_regions(df)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to ingest active solar regions: {e}")
            if os.path.exists(local_path):
                return self._process_regions(pd.read_json(local_path))
            return None
 
    def fetch_solar_flares(self, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Ingests recent X-ray solar flare events.
        """
        # NOAA provides a list of flares over the last 7 days
        url = "https://services.swpc.noaa.gov/json/edited_events.json"
        local_path = os.path.join(self.raw_data_dir, "solar_events_list.json")
        
        if not force_download and os.path.exists(local_path):
            logger.info(f"Loading cached solar flare events list from: {local_path}")
            try:
                df = pd.read_json(local_path)
                return self._process_flares(df)
            except Exception as e:
                logger.warning(f"Failed to read cached solar events file ({e}). Re-downloading...")

        logger.info(f"Downloading solar events list from NOAA: {url}")
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            with open(local_path, "w") as f:
                f.write(response.text)
                
            df = pd.read_json(local_path)
            return self._process_flares(df)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to ingest solar flare events: {e}")
            if os.path.exists(local_path):
                return self._process_flares(pd.read_json(local_path))
            return None

    def fetch_cme_alerts(self, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Ingests NOAA SWPC alert feed and extracts CME-adjacent warning signals.
        """
        url = "https://services.swpc.noaa.gov/products/alerts.json"
        local_path = os.path.join(self.raw_data_dir, "cme_alerts.json")

        if not force_download and os.path.exists(local_path):
            logger.info(f"Loading cached CME alerts from: {local_path}")
            try:
                df = pd.read_json(local_path)
                return self._process_alerts(df)
            except Exception as e:
                logger.warning(f"Failed to read cached CME alerts file ({e}). Re-downloading...")

        logger.info(f"Downloading alert feed from NOAA: {url}")
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            with open(local_path, "w") as f:
                f.write(response.text)

            df = pd.read_json(local_path)
            return self._process_alerts(df)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to ingest alert feed: {e}")
            if os.path.exists(local_path):
                return self._process_alerts(pd.read_json(local_path))
            return None

    def _process_regions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Processes active solar region summaries into count and area metrics.
        """
        if df.empty:
            return df
            
        # Summarize sunspots area and count by observation time
        # Standard columns: ['observed_date', 'region', 'area', 'number_spots', ...]
        df['timestamp'] = pd.to_datetime(df['observed_date'])
        
        summary_df = df.groupby('timestamp').agg({
            'area': 'sum',
            'number_spots': 'sum',
            'region': 'count'
        }).rename(columns={
            'area': 'total_sunspot_area',
            'number_spots': 'total_sunspot_count',
            'region': 'active_regions_count'
        })
        
        summary_df.sort_index(inplace=True)
        return summary_df

    def _process_flares(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filters and groups recent raw solar events to count X-class, M-class flare occurrences.
        """
        if df.empty:
            return df
            
        # Standard edited event columns contain 'type' (e.g. 'XRA' for X-ray flare), 'begin_time', 'particulars' (class classification)
        df_flares = df[df['type'] == 'XRA'].copy()
        if df_flares.empty:
            return pd.DataFrame()
            
        df_flares['timestamp'] = pd.to_datetime(df_flares['begin_datetime'])
        
        # Categorize flare class (C, M, X class)
        def get_flare_class(particulars):
            particulars = str(particulars).upper()
            if particulars.startswith('X'):
                return 'flare_class_x'
            elif particulars.startswith('M'):
                return 'flare_class_m'
            elif particulars.startswith('C'):
                return 'flare_class_c'
            return 'flare_class_other'
            
        df_flares['flare_category'] = df_flares['particulars1'].apply(get_flare_class)
        
        # Resample flares count to hourly intervals
        df_flares.set_index('timestamp', inplace=True)
        pivot_df = pd.get_dummies(df_flares['flare_category']).resample('1h').sum()
        
        return pivot_df

    def _process_alerts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Converts NOAA alerts into hourly counts for CME-adjacent storm indicators.
        """
        if df.empty:
            return df

        alerts_df = df.copy()
        alerts_df["timestamp"] = pd.to_datetime(alerts_df["issue_datetime"])
        alerts_df["message"] = alerts_df["message"].astype(str).str.upper()
        alerts_df["product_id"] = alerts_df["product_id"].astype(str)

        alerts_df["cme_indicator"] = alerts_df["message"].str.contains("CME|SHOCK|SUDDEN IMPULSE|TYPE II|TYPE IV", regex=True)
        alerts_df["geomagnetic_alert"] = alerts_df["product_id"].str.startswith("K").astype(int)
        alerts_df["proton_alert"] = alerts_df["product_id"].str.startswith("P").astype(int)
        alerts_df["electron_alert"] = alerts_df["product_id"].str.startswith("EF").astype(int)
        alerts_df["xray_alert"] = alerts_df["product_id"].str.startswith("X").astype(int)

        alerts_df["cme_indicator"] = alerts_df["cme_indicator"].astype(int)
        alerts_df.set_index("timestamp", inplace=True)

        summary = alerts_df[
            ["cme_indicator", "geomagnetic_alert", "proton_alert", "electron_alert", "xray_alert"]
        ].resample("1h").sum()
        return summary
