import os
import logging
import requests
import numpy as np
import pandas as pd
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from typing import Optional, List

logger = logging.getLogger("OMNILoader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class OMNILoader:
    """
    Data ingestion loader for NASA OMNI database.
    OMNI provides solar wind, interplanetary magnetic field (IMF), and geomagnetic
    indices (Kp, Dst, AE) from OMNIWeb or CDAWeb HAPI endpoints.
    
    Includes automatic handling of OMNI-specific missing value codes (e.g., 999.9, 99.9).
    """
    HAPI_BASE_URL = "https://cdaweb.gsfc.nasa.gov/hapi"
    DEFAULT_PARAMETERS = [
        "F1800",
        "BX_GSE1800",
        "BY_GSE1800",
        "BZ_GSE1800",
        "T1800",
        "N1800",
        "V1800",
        "Pressure1800",
        "KP1800",
        "DST1800",
        "AE1800"
    ]
    RENAME_MAP = {
        "F1800": "IMF",
        "BX_GSE1800": "BX_GSE",
        "BY_GSE1800": "BY_GSE",
        "BZ_GSE1800": "BZ_GSE",
        "N1800": "DENSITY",
        "T1800": "TEMPERATURE",
        "V1800": "VELOCITY",
        "Pressure1800": "DYNAMIC_PRESSURE",
        "KP1800": "KP",
        "DST1800": "DST",
        "AE1800": "AE"
    }

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

    def fetch_omni_data(self, start_time: str, end_time: str, 
                        dataset_id: str = "OMNI_HAPI_hourly", 
                        force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches solar wind and IMF parameters from NASA OMNI HAPI endpoint.
        
        Args:
            start_time: ISO-8601 start time (e.g., '2023-01-01T00:00:00Z').
            end_time: ISO-8601 end time (e.g., '2023-01-03T00:00:00Z').
            dataset_id: The specific dataset ID on NASA's HAPI server.
            force_download: Bypass local cache.
        Returns:
            pd.DataFrame: Cleaned OMNI dataset with timestamp index.
        """
        local_filename = f"omni_{start_time.split('T')[0]}_to_{end_time.split('T')[0]}.csv"
        local_path = os.path.join(self.raw_data_dir, local_filename)

        if not force_download and os.path.exists(local_path):
            logger.info(f"Loading cached OMNI data from: {local_path}")
            try:
                return self._read_cached_omni_csv(local_path)
            except Exception as e:
                logger.warning(f"Failed to read cached OMNI file ({e}). Re-downloading...")

        # Construct HAPI Query url
        parameters = self._resolve_parameters(dataset_id)
        parameters_str = ",".join(parameters)
        url = f"{self.HAPI_BASE_URL}/data?id={dataset_id}&time.min={start_time}&time.max={end_time}&parameters={parameters}&format=csv"
        url = f"{self.HAPI_BASE_URL}/data?id={dataset_id}&time.min={start_time}&time.max={end_time}&parameters={parameters_str}&format=csv"
        
        logger.info(f"Downloading OMNI data from NASA CDAWeb HAPI: {url}")
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            if "Parameter out of order" in response.text or "no data for time range" in response.text:
                logger.warning(f"OMNI HAPI request returned an informational response: {response.text.strip()}")
                return None
            
            # Save raw csv text
            with open(local_path, "w") as f:
                f.write(response.text)
                
            return self._process_omni_csv(local_path, parameters)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch OMNI data from NASA: {e}")
            if os.path.exists(local_path):
                logger.warning("Falling back to cached OMNI dataset.")
                return self._read_cached_omni_csv(local_path)
            return None

    def _resolve_parameters(self, dataset_id: str) -> List[str]:
        if dataset_id == "OMNI2_H0_MRG1HR":
            return self.DEFAULT_PARAMETERS
        return ["IMF", "BX_GSE", "BY_GSE", "BZ_GSE", "DENSITY", "TEMPERATURE", "VELOCITY", "KP", "DST", "AE"]

    def _read_cached_omni_csv(self, file_path: str) -> pd.DataFrame:
        try:
            df = pd.read_csv(file_path, parse_dates=["timestamp"], index_col="timestamp")
            return self._normalize_omni_dataframe(df)
        except Exception:
            if os.path.getsize(file_path) == 0:
                return pd.DataFrame()
            df = pd.read_csv(file_path, header=None)
            if df.empty:
                return df
            columns = self.DEFAULT_PARAMETERS if df.shape[1] == len(self.DEFAULT_PARAMETERS) + 1 else self._resolve_parameters("OMNI_HAPI_hourly")
            return self._process_omni_csv(file_path, columns)

    def _process_omni_csv(self, file_path: str, columns: list) -> pd.DataFrame:
        """
        Parses OMNI HAPI CSV output, flags missing values properly, and assigns column names.
        """
        # HAPI CSV typically returns: [Time_Tag, Col1, Col2, ...]
        df = pd.read_csv(file_path, header=None)
        if df.empty:
            return df
            
        headers = ["timestamp"] + columns
        df.columns = headers
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        return self._normalize_omni_dataframe(df, save_path=file_path)

    def _normalize_omni_dataframe(self, df: pd.DataFrame, save_path: Optional[str] = None) -> pd.DataFrame:
        df = df.copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)

        rename_candidates = {
            "IMF1800": "IMF",
            "F1800": "IMF",
            "BX_GSE1800": "BX_GSE",
            "BY_GSE1800": "BY_GSE",
            "BZ_GSE1800": "BZ_GSE",
            "N1800": "DENSITY",
            "T1800": "TEMPERATURE",
            "V1800": "VELOCITY",
            "Pressure1800": "DYNAMIC_PRESSURE",
            "KP1800": "KP",
            "DST1800": "DST",
            "AE1800": "AE"
        }
        df.rename(columns=rename_candidates, inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        fill_mappings = {
            'BX_GSE': 999.9,
            'BY_GSE': 999.9,
            'BZ_GSE': 999.9,
            'IMF': 999.9,
            'DENSITY': 999.9,
            'TEMPERATURE': 9999999.0,
            'VELOCITY': 9999.0,
            'DYNAMIC_PRESSURE': 99.99,
            'KP': 99.0,
            'DST': 99999,
            'AE': 9999
        }
        
        for col, fill_val in fill_mappings.items():
            if col in df.columns:
                # Replace values close to fill value with NaN
                df[col] = df[col].apply(lambda x: np.nan if pd.notnull(x) and abs(x - fill_val) < 0.1 else x)
                
        # Forward fill and backward fill remaining missing values for robustness
        df.ffill(inplace=True)
        df.bfill(inplace=True)
        df.sort_index(inplace=True)
        
        if save_path is not None:
            df.to_csv(save_path)
        return df
