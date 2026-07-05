import argparse
import os
import sys
from typing import List

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.omni_loader import OMNILoader


def build_year_ranges(start_year: int, end_year: int) -> List[tuple[str, str]]:
    ranges: List[tuple[str, str]] = []
    for year in range(start_year, end_year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z"
        ranges.append((start, end))
    return ranges


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical OMNI hourly data from NASA CDAWeb.")
    parser.add_argument("--start-year", type=int, required=True, help="Starting year, inclusive.")
    parser.add_argument("--end-year", type=int, required=True, help="Ending year, inclusive.")
    parser.add_argument(
        "--output",
        default=os.path.join("datasets", "historical", "omni_2011-01-01_to_2020-03-31.csv"),
        help="Path to the combined output CSV."
    )
    parser.add_argument(
        "--raw-dir",
        default=os.path.join("datasets", "historical", "omni"),
        help="Directory for yearly OMNI cache files."
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download yearly cache files even if they already exist locally."
    )
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise ValueError("Start year must be earlier than or equal to end year.")

    loader = OMNILoader(raw_data_dir=args.raw_dir)
    frames: List[pd.DataFrame] = []

    for start, end in build_year_ranges(args.start_year, args.end_year):
        yearly_df = loader.fetch_omni_data(
            start_time=start,
            end_time=end,
            dataset_id="OMNI2_H0_MRG1HR",
            force_download=args.force_download
        )
        if yearly_df is None or yearly_df.empty:
            continue
        frames.append(yearly_df)

    if not frames:
        raise RuntimeError("No OMNI data was downloaded for the requested range.")

    combined = pd.concat(frames, axis=0).sort_index()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    combined.to_csv(args.output)
    print(f"Backfilled {len(combined)} OMNI rows into {args.output}")


if __name__ == "__main__":
    main()
