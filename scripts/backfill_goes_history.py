import argparse
import os
import sys
from typing import List, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.goes_historical_loader import GOESHistoricalLoader


def build_year_month_pairs(start_year: int, start_month: int, end_year: int, end_month: int) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        pairs.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical GOES electron flux data from NOAA NCEI.")
    parser.add_argument("--start-year", type=int, required=True, help="Starting year, inclusive.")
    parser.add_argument("--start-month", type=int, default=1, help="Starting month, inclusive.")
    parser.add_argument("--end-year", type=int, required=True, help="Ending year, inclusive.")
    parser.add_argument("--end-month", type=int, default=12, help="Ending month, inclusive.")
    parser.add_argument(
        "--output",
        default=os.path.join("datasets", "historical", "goes_electron_history.csv"),
        help="Path to the combined output CSV."
    )
    parser.add_argument(
        "--raw-dir",
        default=os.path.join("datasets", "historical", "goes"),
        help="Directory for downloaded monthly source files."
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download monthly files even if they already exist locally."
    )
    args = parser.parse_args()

    if not 1 <= args.start_month <= 12 or not 1 <= args.end_month <= 12:
        raise ValueError("Months must be between 1 and 12.")
    if (args.start_year, args.start_month) > (args.end_year, args.end_month):
        raise ValueError("Start year/month must be earlier than or equal to end year/month.")

    loader = GOESHistoricalLoader(raw_data_dir=args.raw_dir)
    year_month_pairs = build_year_month_pairs(
        args.start_year,
        args.start_month,
        args.end_year,
        args.end_month
    )
    combined = loader.backfill_electron_history(
        year_month_pairs=year_month_pairs,
        output_path=args.output,
        force_download=args.force_download
    )

    print(
        f"Backfilled {len(combined)} rows across {len(year_month_pairs)} months "
        f"into {args.output}"
    )


if __name__ == "__main__":
    main()
