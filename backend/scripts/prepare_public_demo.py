from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "total_value",
    "quantity",
    "sku_name",
    "category",
    "store_name",
    "channel",
    "profit",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a deterministic, date-stratified public demo sample from "
            "the enriched SalesScope dataset."
        )
    )
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument(
        "--fraction",
        type=float,
        default=1 / 12,
        help="Fraction sampled within each transaction date. Defaults to 1/12.",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=9,
        help="Fail validation when the generated file exceeds this size.",
    )
    return parser.parse_args()


def maximum_share_drift(
    source: pd.DataFrame,
    sample: pd.DataFrame,
    column: str,
) -> float:
    source_share = source[column].value_counts(normalize=True, dropna=False)
    sample_share = sample[column].value_counts(normalize=True, dropna=False)
    aligned = source_share.align(sample_share, fill_value=0)
    return float((aligned[0] - aligned[1]).abs().max() * 100)


def prepare_public_demo(
    source_path: Path,
    output_path: Path,
    fraction: float,
    max_size_mb: float,
) -> None:
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be greater than 0 and no more than 1.")

    source = pd.read_csv(source_path, low_memory=False)
    missing = sorted(REQUIRED_COLUMNS - set(source.columns))
    if missing:
        raise ValueError(f"Source file is missing required columns: {missing}")

    source = source.copy()
    source["_source_order"] = range(len(source))
    source_dates = pd.to_datetime(source["date"], errors="coerce")
    if source_dates.isna().any():
        raise ValueError("Source file contains invalid transaction dates.")
    source["_sample_date"] = source_dates.dt.strftime("%Y-%m-%d")

    sample = (
        source.groupby("_sample_date", group_keys=False, sort=False)
        .sample(frac=fraction, random_state=20260727)
        .sort_values("_source_order")
        .drop(columns=["_source_order", "_sample_date"])
    )

    if sample.empty:
        raise ValueError("Sampling produced an empty dataset.")
    if sample[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("Sample contains nulls in required analysis columns.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output_path, index=False)

    size_bytes = output_path.stat().st_size
    size_mib = size_bytes / (1024 * 1024)
    if size_mib > max_size_mb:
        raise ValueError(
            f"Generated sample is {size_mib:.2f} MiB, above the "
            f"{max_size_mb:.2f} MiB limit."
        )

    sample_dates = pd.to_datetime(sample["date"], errors="raise")
    category_drift = maximum_share_drift(source, sample, "category")
    channel_drift = maximum_share_drift(source, sample, "channel")

    print(f"source_rows={len(source)}")
    print(f"sample_rows={len(sample)}")
    print(f"sample_size_bytes={size_bytes}")
    print(f"sample_size_mib={size_mib:.2f}")
    print(f"date_min={sample_dates.min().date()}")
    print(f"date_max={sample_dates.max().date()}")
    print(f"categories={sample['category'].nunique()}")
    print(f"stores={sample['store_name'].nunique()}")
    print(f"channels={sample['channel'].nunique()}")
    print(f"max_category_share_drift_pp={category_drift:.2f}")
    print(f"max_channel_share_drift_pp={channel_drift:.2f}")
    print(f"output={output_path.resolve()}")


def main() -> None:
    args = parse_args()
    prepare_public_demo(
        args.source_csv.resolve(),
        args.output_csv.resolve(),
        args.fraction,
        args.max_size_mb,
    )


if __name__ == "__main__":
    main()
