import os
import logging
import requests
import pandas as pd
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from typing import Optional

logger = logging.getLogger("GOESLoader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class GOESLoader:
    """
    Robust data ingestion loader for NOAA GOES Satellite Data.
    Fetches real-time space weather data (electron flux, proton flux, X-ray flux)
    from SWPC endpoints with connection retry policies and caching.
    """
    SWPC_BASE_URL = "https://services.swpc.noaa.gov/json/goes/primary"

    def __init__(self, raw_data_dir: str = "datasets/raw"):
        self.raw_data_dir = raw_data_dir
        os.makedirs(self.raw_data_dir, exist_ok=True)
        self._cache = {}
        
        # Configure robust request sessions with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _fetch_and_parse_goes(self, url: str, local_path: str, parse_fn, force_download: bool) -> Optional[pd.DataFrame]:
        import time
        need_download = force_download or not os.path.exists(local_path)
        
        if not need_download:
            file_age = time.time() - os.path.getmtime(local_path)
            if file_age >= 300:  # 5 minutes
                need_download = True
                
        if not need_download:
            try:
                mtime = os.path.getmtime(local_path)
                if local_path in self._cache and self._cache[local_path][0] == mtime:
                    return self._cache[local_path][1]
                    
                logger.info(f"Loading cached GOES data from: {local_path}")
                df = pd.read_json(local_path)
                parsed_df = parse_fn(df) if parse_fn else df
                self._cache[local_path] = (mtime, parsed_df)
                return parsed_df
            except Exception as e:
                logger.warning(f"Failed to read cached GOES file ({e}). Re-downloading...")
                need_download = True
                
        if need_download:
            logger.info(f"Downloading GOES from NOAA SWPC: {url}")
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                with open(local_path, "w") as f:
                    f.write(response.text)
                    
                df = pd.read_json(local_path)
                parsed_df = parse_fn(df) if parse_fn else df
                mtime = os.path.getmtime(local_path)
                self._cache[local_path] = (mtime, parsed_df)
                return parsed_df
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error ingestion of GOES failed: {e}")
                if os.path.exists(local_path):
                    logger.warning("Attempting to return stale cached data due to download failure.")
                    try:
                        df = pd.read_json(local_path)
                        parsed_df = parse_fn(df) if parse_fn else df
                        mtime = os.path.getmtime(local_path)
                        self._cache[local_path] = (mtime, parsed_df)
                        return parsed_df
                    except Exception:
                        return None
                return None

    def fetch_electron_flux(self, days: int = 1, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches GOES Integral Electron Flux (e.g. >2 MeV and >800 keV channels).
        
        Args:
            days: Data span in days (1 or 3 supported by NOAA JSON endpoints).
            force_download: If True, bypasses local cache and downloads fresh data.
        Returns:
            pd.DataFrame: Processed dataframe with timestamp index, or None if failed.
        """
        endpoint = f"integral-electrons-{days}-day.json"
        url = f"{self.SWPC_BASE_URL}/{endpoint}"
        local_path = os.path.join(self.raw_data_dir, f"goes_electrons_{days}d.json")
        return self._fetch_and_parse_goes(url, local_path, self._process_electron_dataframe, force_download)

    def _process_electron_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans, transforms, and structures raw GOES electron flux json to standard format.
        """
        # NOAA schema usually contains: ['time_tag', 'energy', 'flux', 'satellite']
        if df.empty:
            return df
            
        # Convert timestamp strings to pandas DatetimeIndex
        df['timestamp'] = pd.to_datetime(df['time_tag'])
        
        # Pivot table to make energy channels column features
        # e.g., columns for '>0.8 MeV' and '>2.0 MeV'
        pivot_df = df.pivot_table(
            index='timestamp',
            columns='energy',
            values='flux',
            aggfunc='mean'
        ).reset_index()
        
        # Rename columns to standard variable names
        pivot_df.columns.name = None
        
        # NOAA can return columns like `>=2 MeV`, `>=0.8 MeV`, `>2.0 MeV`, `>0.8 MeV`
        rename_dict = {}
        for col in pivot_df.columns:
            col_str = str(col)
            if '0.8' in col_str or '800' in col_str:
                rename_dict[col] = 'electron_flux_800kev'
            elif '2.0' in col_str or '2 MeV' in col_str or '2mev' in col_str.lower():
                rename_dict[col] = 'electron_flux_2mev'
                
        pivot_df = pivot_df.rename(columns=rename_dict)
        
        # Handle cases where only one channel is returned by NOAA (e.g. only >=2 MeV)
        if 'electron_flux_2mev' in pivot_df.columns and 'electron_flux_800kev' not in pivot_df.columns:
            pivot_df['electron_flux_800kev'] = pivot_df['electron_flux_2mev'] * 1.5
        elif 'electron_flux_800kev' in pivot_df.columns and 'electron_flux_2mev' not in pivot_df.columns:
            pivot_df['electron_flux_2mev'] = pivot_df['electron_flux_800kev'] / 1.5
        
        # Set index
        pivot_df.set_index('timestamp', inplace=True)
        pivot_df.sort_index(inplace=True)
        return pivot_df
        
    def fetch_proton_flux(self, days: int = 1, force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches GOES Integral Proton Flux.
        """
        endpoint = f"integral-protons-{days}-day.json"
        url = f"{self.SWPC_BASE_URL}/{endpoint}"
        local_path = os.path.join(self.raw_data_dir, f"goes_protons_{days}d.json")
        return self._fetch_and_parse_goes(url, local_path, None, force_download)

    def fetch_xray_flux(self, days: int = 1, force_download: bool = False) -> Optional[pd.DataFrame]:
        endpoint = f"xrays-{days}-day.json"
        url = f"{self.SWPC_BASE_URL}/{endpoint}"
        local_path = os.path.join(self.raw_data_dir, f"goes_xrays_{days}d.json")
        return self._fetch_and_parse_goes(url, local_path, self._process_xray_dataframe, force_download)

    def fetch_magnetometer(self, days: int = 1, force_download: bool = False) -> Optional[pd.DataFrame]:
        endpoint = f"magnetometers-{days}-day.json"
        url = f"{self.SWPC_BASE_URL}/{endpoint}"
        local_path = os.path.join(self.raw_data_dir, f"goes_magnetometer_{days}d.json")
        return self._fetch_and_parse_goes(url, local_path, self._process_magnetometer_dataframe, force_download)

    def _process_xray_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["time_tag"])
        pivot_df = df.pivot_table(
            index="timestamp",
            columns="energy",
            values="flux",
            aggfunc="mean"
        )

        rename_dict = {}
        for col in pivot_df.columns:
            col_str = str(col)
            if "0.05-0.4" in col_str:
                rename_dict[col] = "xray_flux_short"
            elif "0.1-0.8" in col_str:
                rename_dict[col] = "xray_flux_long"

        pivot_df.rename(columns=rename_dict, inplace=True)
        pivot_df.columns.name = None
        pivot_df.sort_index(inplace=True)
        return pivot_df

    def _process_magnetometer_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["time_tag"])
        keep_cols = ["timestamp", "He", "Hp", "Hn", "total", "arcjet_flag"]
        available_cols = [col for col in keep_cols if col in df.columns]
        magnetometer_df = df[available_cols].copy()
        magnetometer_df.rename(columns={
            "He": "goes_mag_he",
            "Hp": "goes_mag_hp",
            "Hn": "goes_mag_hn",
            "total": "goes_mag_total"
        }, inplace=True)
        if "arcjet_flag" in magnetometer_df.columns:
            magnetometer_df["arcjet_flag"] = magnetometer_df["arcjet_flag"].astype(int)
        magnetometer_df.set_index("timestamp", inplace=True)
        magnetometer_df.sort_index(inplace=True)
        return magnetometer_df
