from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Join the local synthetic sales, product, and store tables into one "
            "flat SalesScope demo upload."
        )
    )
    parser.add_argument(
        "source_directory",
        type=Path,
        help="Directory containing bm_sales.csv, bm_skus.csv, and bm_stores.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to demo_sales_enriched.csv beside the source folder.",
    )
    return parser.parse_args()


def prepare_demo_upload(source_directory: Path, output_path: Path) -> None:
    source_directory = source_directory.resolve()
    sales = pd.read_csv(source_directory / "bm_sales.csv", low_memory=False)
    products = pd.read_csv(source_directory / "bm_skus.csv")
    stores = pd.read_csv(source_directory / "bm_stores.csv")

    if products["sku_id"].duplicated().any():
        raise ValueError("bm_skus.csv contains duplicate sku_id values.")
    if stores["store_id"].duplicated().any():
        raise ValueError("bm_stores.csv contains duplicate store_id values.")

    enriched = sales.merge(
        products[
            [
                "sku_id",
                "sku_name",
                "category",
                "subcategory",
                "cost_price",
                "brand",
            ]
        ],
        on="sku_id",
        how="left",
        validate="many_to_one",
    ).merge(
        stores[["store_id", "store_name", "city", "store_type"]],
        on="store_id",
        how="left",
        validate="many_to_one",
    )

    if enriched["sku_name"].isna().any():
        raise ValueError("One or more sales rows did not match a product.")
    if enriched["store_name"].isna().any():
        raise ValueError("One or more sales rows did not match a store.")
    if len(enriched) != len(sales):
        raise ValueError("The joins changed the number of sales rows.")

    calculated_profit = (
        enriched["total_value"] - enriched["cost_price"] * enriched["quantity"]
    )
    enriched["profit"] = calculated_profit.round(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(output_path, index=False)

    print(f"rows={len(enriched)}")
    print(f"columns={len(enriched.columns)}")
    print(f"possible_duplicate_sales_rows={int(sales.duplicated().sum())}")
    print(f"output={output_path}")


def main() -> None:
    args = parse_args()
    source_directory = args.source_directory.resolve()
    output_path = (
        args.output.resolve()
        if args.output
        else source_directory.parent / "demo_sales_enriched.csv"
    )
    prepare_demo_upload(source_directory, output_path)


if __name__ == "__main__":
    main()
