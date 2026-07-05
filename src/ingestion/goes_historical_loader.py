import calendar
import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException
from urllib3.util import Retry

logger = logging.getLogger("GOESHistoricalLoader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@dataclass
class GOESHistoricalProduct:
    year: int
    month: int
    satellite: str
    product: str
    cadence: str
    local_path: str


class GOESHistoricalLoader:
    """
    Downloader and parser for NOAA NCEI GOES historical archive files.
    Focuses on the averaged monthly archive, which exposes long-span particle,
    X-ray, and magnetometer products in a consistent directory structure.
    """

    BASE_URL = "https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/avg"

    def __init__(self, raw_data_dir: str = "datasets/historical/goes") -> None:
        self.raw_data_dir = raw_data_dir
        os.makedirs(self.raw_data_dir, exist_ok=True)

        self.session = requests.Session()
        self.session.trust_env = False
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def build_month_url(self, year: int, month: int) -> str:
        return f"{self.BASE_URL}/{year:04d}/{month:02d}/"

    def list_satellites(self, year: int, month: int) -> List[str]:
        url = self.build_month_url(year, month)
        logger.info("Discovering historical GOES satellites for %04d-%02d...", year, month)
        response = self.session.get(url, timeout=120, headers={"User-Agent": "SWEWS historical backfill/1.0"})
        try:
            response.raise_for_status()
        except HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("No historical GOES directory found for %04d-%02d", year, month)
                return []
            raise
        satellites = re.findall(r'href=["\'](goes\d+/)["\']', response.text, flags=re.IGNORECASE)
        normalized = sorted({sat.rstrip("/") for sat in satellites})
        return normalized

    def choose_satellite(self, year: int, month: int) -> Optional[str]:
        satellites = self.list_satellites(year, month)
        if not satellites:
            return None
        return max(satellites, key=lambda sat: int(re.search(r"(\d+)$", sat).group(1)))

    def build_product_filename(
        self,
        satellite: str,
        product: str,
        cadence: str,
        year: int,
        month: int
    ) -> str:
        sat_num = re.search(r"(\d+)$", satellite).group(1)
        last_day = calendar.monthrange(year, month)[1]
        start = f"{year:04d}{month:02d}01"
        end = f"{year:04d}{month:02d}{last_day:02d}"
        return f"g{sat_num}_{product}_{cadence}_{start}_{end}.csv"

    def build_product_url(
        self,
        satellite: str,
        product: str,
        cadence: str,
        year: int,
        month: int
    ) -> str:
        filename = self.build_product_filename(satellite, product, cadence, year, month)
        return f"{self.build_month_url(year, month)}{satellite}/csv/{filename}"

    def download_product(
        self,
        year: int,
        month: int,
        product: str,
        cadence: str,
        satellite: Optional[str] = None,
        force_download: bool = False
    ) -> Optional[GOESHistoricalProduct]:
        satellite = satellite or self.choose_satellite(year, month)
        if satellite is None:
            logger.warning("No historical GOES satellite archive found for %04d-%02d", year, month)
            return None

        filename = self.build_product_filename(satellite, product, cadence, year, month)
        local_dir = os.path.join(self.raw_data_dir, f"{year:04d}", f"{month:02d}", satellite)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)

        if os.path.exists(local_path) and not force_download:
            logger.info("Using cached historical file: %s", local_path)
            return GOESHistoricalProduct(year, month, satellite, product, cadence, local_path)

        url = self.build_product_url(satellite, product, cadence, year, month)
        logger.info("Downloading historical GOES product: %s", url)
        response = self.session.get(url, timeout=300, headers={"User-Agent": "SWEWS historical backfill/1.0"})
        try:
            response.raise_for_status()
        except HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("Historical GOES product not found for %04d-%02d: %s", year, month, url)
                return None
            raise

        with open(local_path, "wb") as f:
            f.write(response.content)

        return GOESHistoricalProduct(year, month, satellite, product, cadence, local_path)

    def parse_metadata_csv(self, file_path: str) -> pd.DataFrame:
        """
        NOAA historical CSVs embed metadata before a `data:` marker and a normal CSV section.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        data_idx = None
        for idx, line in enumerate(lines):
            if line.strip().lower() == "data:":
                data_idx = idx
                break

        if data_idx is None or data_idx + 1 >= len(lines):
            raise ValueError(f"Could not locate data section in historical file: {file_path}")

        csv_blob = "".join(lines[data_idx + 1 :])
        df = pd.read_csv(io.StringIO(csv_blob), skipinitialspace=True)
        if "time_tag" in df.columns:
            df["timestamp"] = pd.to_datetime(df["time_tag"])
            df.set_index("timestamp", inplace=True)
            df.drop(columns=["time_tag"], inplace=True, errors="ignore")
        return df

    def build_electron_flux_dataframe(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        df = raw_df.copy()
        numeric_cols = [col for col in df.columns if col != "timestamp"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["electron_flux_800kev"] = df[["E1E_COR_FLUX", "E1W_COR_FLUX"]].mean(axis=1, skipna=True)
        df["electron_flux_2mev"] = df[["E2E_COR_FLUX", "E2W_COR_FLUX"]].mean(axis=1, skipna=True)
        df = df[["electron_flux_800kev", "electron_flux_2mev"]]
        df.replace(-99999, pd.NA, inplace=True)
        df.sort_index(inplace=True)
        return df

    def backfill_electron_history(
        self,
        year_month_pairs: List[tuple[int, int]],
        output_path: str = "datasets/historical/goes_electron_history.csv",
        force_download: bool = False
    ) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []

        for year, month in year_month_pairs:
            try:
                product = self.download_product(
                    year=year,
                    month=month,
                    product="epead_e13ew",
                    cadence="5m",
                    force_download=force_download
                )
            except RequestException as exc:
                logger.warning("Failed to download %04d-%02d historical GOES data: %s", year, month, exc)
                continue

            if product is None:
                continue

            try:
                monthly_df = self.parse_metadata_csv(product.local_path)
                monthly_electrons = self.build_electron_flux_dataframe(monthly_df)
                monthly_electrons["source_satellite"] = product.satellite
                frames.append(monthly_electrons)
                logger.info(
                    "Parsed %s rows for %04d-%02d from %s",
                    len(monthly_electrons),
                    year,
                    month,
                    product.satellite
                )
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", product.local_path, exc)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, axis=0).sort_index()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        combined.to_csv(output_path)
        logger.info("Historical GOES electron backfill saved to %s", output_path)
        return combined
