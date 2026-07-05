import os
import logging
import requests
import pandas as pd
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from typing import Optional

logger = logging.getLogger("DSCOVRLoader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class DSCOVRLoader:
    """
    Data ingestion loader for NOAA DSCOVR Solar Wind observations.
    DSCOVR is positioned at L1 and measures real-time solar wind plasma (speed, density, temperature)
    and interplanetary magnetic field (IMF) Bx, By, Bz about 30-60 minutes before striking Earth.
    """
    PRODUCTS_BASE_URL = "https://services.swpc.noaa.gov/json/rtsw"

    def __init__(self, raw_data_dir: str = "datasets/raw"):
        self.raw_data_dir = raw_data_dir
        os.makedirs(self.raw_data_dir, exist_ok=True)
        self._cache = {}
        
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_realtime_plasma(self, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches the 1-day real-time solar wind plasma measurements from NOAA.
        Includes wind speed, proton density, and temperature.
        """
        url = f"{self.PRODUCTS_BASE_URL}/rtsw_wind_1m.json"
        local_path = os.path.join(self.raw_data_dir, "dscovr_plasma_1d.json")
        return self._fetch_and_parse_noaa_json(url, local_path, "plasma", force_download)

    def fetch_realtime_mag(self, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches the 1-day real-time IMF magnetic field measurements (Bx, By, Bz) from NOAA.
        """
        url = f"{self.PRODUCTS_BASE_URL}/rtsw_mag_1m.json"
        local_path = os.path.join(self.raw_data_dir, "dscovr_mag_1d.json")
        return self._fetch_and_parse_noaa_json(url, local_path, "mag", force_download)

    def _fetch_and_parse_noaa_json(self, url: str, local_path: str, data_type: str, 
                                   force_download: bool) -> Optional[pd.DataFrame]:
        """
        Helper method to fetch SWPC JSON lists, parse the embedded headers, and convert to DataFrame.
        """
        import time
        need_download = force_download or not os.path.exists(local_path)
        
        # If file exists, check if it's older than 5 minutes (300 seconds)
        if not need_download:
            file_age = time.time() - os.path.getmtime(local_path)
            if file_age >= 300:
                need_download = True
                
        if not need_download:
            # File is fresh. Check in-memory cache first
            try:
                mtime = os.path.getmtime(local_path)
                if local_path in self._cache and self._cache[local_path][0] == mtime:
                    return self._cache[local_path][1]
                
                logger.info(f"Loading cached DSCOVR {data_type} data from: {local_path}")
                df = pd.read_json(local_path)
                parsed_df = self._parse_swpc_matrix(df, data_type)
                self._cache[local_path] = (mtime, parsed_df)
                return parsed_df
            except Exception as e:
                logger.warning(f"Failed to read cached DSCOVR {data_type} file ({e}). Re-downloading...")
                need_download = True

        if need_download:
            logger.info(f"Downloading DSCOVR {data_type} from NOAA SWPC: {url}")
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                with open(local_path, "w") as f:
                    f.write(response.text)
                    
                df = pd.read_json(local_path)
                parsed_df = self._parse_swpc_matrix(df, data_type)
                mtime = os.path.getmtime(local_path)
                self._cache[local_path] = (mtime, parsed_df)
                return parsed_df
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download DSCOVR {data_type} data: {e}")
                if os.path.exists(local_path):
                    logger.warning(f"Returning cached DSCOVR {data_type} fallback.")
                    try:
                        df = pd.read_json(local_path)
                        parsed_df = self._parse_swpc_matrix(df, data_type)
                        mtime = os.path.getmtime(local_path)
                        self._cache[local_path] = (mtime, parsed_df)
                        return parsed_df
                    except Exception:
                        return None
                return None

    def _parse_swpc_matrix(self, raw_df: pd.DataFrame, data_type: str) -> pd.DataFrame:
        """
        NOAA SWPC json format is either a list of dicts (new format) or a matrix where row 0 is header columns (legacy format).
        This helper parses it into a clean pandas DataFrame.
        """
        if raw_df.empty:
            return pd.DataFrame()
            
        if 'time_tag' in raw_df.columns:
            # New format (list of objects)
            df = raw_df.copy()
        else:
            # Legacy matrix format
            if len(raw_df) < 2:
                return pd.DataFrame()
            headers = raw_df.iloc[0].tolist()
            data_rows = raw_df.iloc[1:]
            df = pd.DataFrame(data_rows.values, columns=headers)
            
        # Standardize timestamp
        df['timestamp'] = pd.to_datetime(df['time_tag'])
        df.set_index('timestamp', inplace=True)
        df.drop(columns=['time_tag'], inplace=True, errors='ignore')
        
        # Cast numerical columns
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # Rename columns to prevent conflicts and ensure clarity
        if data_type == "plasma":
            if 'proton_density' in df.columns:
                df = df.rename(columns={
                    'proton_density': 'dscovr_density',
                    'proton_speed': 'dscovr_speed',
                    'proton_temperature': 'dscovr_temperature'
                })
            else:
                df = df.rename(columns={
                    'density': 'dscovr_density',
                    'speed': 'dscovr_speed',
                    'temperature': 'dscovr_temperature'
                })
        elif data_type == "mag":
            if 'bz_gsm' in df.columns:
                df = df.rename(columns={
                    'bx_gsm': 'dscovr_bx',
                    'by_gsm': 'dscovr_by',
                    'bz_gsm': 'dscovr_bz',
                    'bt': 'dscovr_bt'
                })
            elif 'bz_gse' in df.columns:
                df = df.rename(columns={
                    'bx_gse': 'dscovr_bx',
                    'by_gse': 'dscovr_by',
                    'bz_gse': 'dscovr_bz',
                    'bt': 'dscovr_bt'
                })
            else:
                df = df.rename(columns={
                    'bx': 'dscovr_bx',
                    'by': 'dscovr_by',
                    'bz': 'dscovr_bz',
                    'bt': 'dscovr_bt'
                })
                
        # Clean missing values via forward interpolation
        df.ffill(inplace=True)
        df.bfill(inplace=True)
        
        df.sort_index(inplace=True)
        return df
