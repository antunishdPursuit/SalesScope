from pathlib import Path

import nbformat as nbf


notebook = nbf.v4.new_notebook()
notebook["metadata"]["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}

notebook["cells"] = [
    nbf.v4.new_markdown_cell(
        """# Sales Coordinator Dataset Audit

## tl;dr

The downloaded package is usable for the Sales Coordinator MVP, but it does not match the Kaggle listing exactly. It contains 641,843 sales rows from January 1, 2021 through October 31, 2025, rather than 1.2 million rows from one year.

All required store, SKU, and populated customer joins succeed. Discounted prices and transaction totals reconcile for every sales row, so profit can be calculated reliably as `total_value - (cost_price × quantity)`.

Before ingestion, remove 45 exact duplicate sales rows. Treat the 24.9% missing customer IDs as anonymous transactions, and do not promise receipt-level or promotion-level analysis because `receipt_id` and `promo_id` are absent from the downloaded sales file."""
    ),
    nbf.v4.new_markdown_cell(
        """## Context & Methods

The intended product must support weekly sales, discount, and profit reporting without sampling the source data.

### Key Assumptions

- Each row in `bm_sales.csv` represents one store-SKU-customer transaction on one date.
- `sku_id`, `store_id`, and `customer_id` should join to their matching dimension tables.
- `total_value` should equal transaction unit price multiplied by quantity.
- Product cost comes from `bm_skus.csv`.
- Profit is calculated as `total_value - (cost_price × quantity)`.
- The Kaggle listing describes the package as 1.2 million transactions from 2025; the source files are checked independently."""
    ),
    nbf.v4.new_markdown_cell("## Data\n\n### 1. Load every source table"),
    nbf.v4.new_code_cell(
        """from pathlib import Path
import numpy as np
import pandas as pd

pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", lambda value: f"{value:,.4f}")

data_dir = Path("source")
files = {
    "sales": "bm_sales.csv",
    "skus": "bm_skus.csv",
    "stores": "bm_stores.csv",
    "customers": "bm_customers.csv",
    "promotions": "bm_promotions.csv",
    "inventory": "bm_inventory.csv",
}

tables = {name: pd.read_csv(data_dir / filename) for name, filename in files.items()}
sales = tables["sales"]
skus = tables["skus"]
stores = tables["stores"]
customers = tables["customers"]
promotions = tables["promotions"]
inventory = tables["inventory"]

inventory_summary = pd.DataFrame(
    [
        {
            "table": name,
            "file": files[name],
            "rows": len(table),
            "columns": len(table.columns),
            "size_mb": (data_dir / files[name]).stat().st_size / 1_000_000,
        }
        for name, table in tables.items()
    ]
)
inventory_summary"""
    ),
    nbf.v4.new_markdown_cell("### 2. Confirm schemas and date coverage"),
    nbf.v4.new_code_cell(
        """schema_summary = pd.DataFrame(
    [
        {
            "table": name,
            "columns": ", ".join(table.columns),
        }
        for name, table in tables.items()
    ]
)
schema_summary"""
    ),
    nbf.v4.new_code_cell(
        """date_columns = {
    "sales": ["date"],
    "stores": ["opening_date"],
    "customers": ["registration_date"],
    "promotions": ["start_date", "end_date"],
    "inventory": ["last_restock_date", "snapshot_date"],
}

date_ranges = []
for table_name, columns in date_columns.items():
    for column in columns:
        parsed = pd.to_datetime(tables[table_name][column], errors="coerce")
        date_ranges.append(
            {
                "table": table_name,
                "column": column,
                "min_date": parsed.min(),
                "max_date": parsed.max(),
                "invalid_dates": int(parsed.isna().sum()),
            }
        )

date_range_summary = pd.DataFrame(date_ranges)
date_range_summary"""
    ),
    nbf.v4.new_markdown_cell("## Results\n\n### 3. Profile sales volume by year"),
    nbf.v4.new_code_cell(
        """sales_dates = pd.to_datetime(sales["date"], errors="coerce")
sales_by_year = (
    sales.assign(year=sales_dates.dt.year)
    .groupby("year", dropna=False)
    .size()
    .rename("rows")
    .reset_index()
)
sales_by_year["share"] = sales_by_year["rows"] / len(sales)
sales_by_year"""
    ),
    nbf.v4.new_markdown_cell("### 4. Check completeness, uniqueness, and validity"),
    nbf.v4.new_code_cell(
        """null_summary = pd.DataFrame(
    [
        {
            "table": table_name,
            "column": column,
            "null_count": int(table[column].isna().sum()),
            "null_rate": float(table[column].isna().mean()),
        }
        for table_name, table in tables.items()
        for column in table.columns
        if table[column].isna().any()
    ]
).sort_values(["null_rate", "table", "column"], ascending=[False, True, True])
null_summary"""
    ),
    nbf.v4.new_code_cell(
        """duplicate_summary = pd.DataFrame(
    [
        {
            "table": name,
            "exact_duplicate_rows": int(table.duplicated().sum()),
            "duplicate_rate": float(table.duplicated().mean()),
        }
        for name, table in tables.items()
    ]
)

candidate_key_checks = pd.DataFrame(
    [
        {"table": "skus", "key": "sku_id", "duplicate_keys": int(skus["sku_id"].duplicated().sum())},
        {"table": "stores", "key": "store_id", "duplicate_keys": int(stores["store_id"].duplicated().sum())},
        {"table": "customers", "key": "cust_id", "duplicate_keys": int(customers["cust_id"].duplicated().sum())},
        {"table": "promotions", "key": "promo_id", "duplicate_keys": int(promotions["promo_id"].duplicated().sum())},
        {
            "table": "inventory",
            "key": "store_id + sku_id + snapshot_date",
            "duplicate_keys": int(inventory.duplicated(["store_id", "sku_id", "snapshot_date"]).sum()),
        },
    ]
)

display(duplicate_summary)
candidate_key_checks"""
    ),
    nbf.v4.new_code_cell(
        """validity_checks = pd.DataFrame(
    [
        {"check": "quantity <= 0", "failed_rows": int((sales["quantity"] <= 0).sum())},
        {"check": "unit_price < 0", "failed_rows": int((sales["unit_price"] < 0).sum())},
        {"check": "total_value < 0", "failed_rows": int((sales["total_value"] < 0).sum())},
        {
            "check": "discount_pct outside 0-100",
            "failed_rows": int(((sales["discount_pct"] < 0) | (sales["discount_pct"] > 100)).sum()),
        },
        {"check": "future sales dates after 2025-12-31", "failed_rows": int((sales_dates > "2025-12-31").sum())},
    ]
)
validity_checks["failed_rate"] = validity_checks["failed_rows"] / len(sales)
validity_checks"""
    ),
    nbf.v4.new_markdown_cell("### 5. Validate dimension joins"),
    nbf.v4.new_code_cell(
        """join_checks = pd.DataFrame(
    [
        {
            "relationship": "sales.sku_id -> skus.sku_id",
            "orphan_rows": int((~sales["sku_id"].isin(skus["sku_id"])).sum()),
        },
        {
            "relationship": "sales.store_id -> stores.store_id",
            "orphan_rows": int((~sales["store_id"].isin(stores["store_id"])).sum()),
        },
        {
            "relationship": "sales.customer_id -> customers.cust_id",
            "orphan_rows": int(
                (
                    sales["customer_id"].notna()
                    & ~sales["customer_id"].isin(customers["cust_id"])
                ).sum()
            ),
        },
        {
            "relationship": "inventory.sku_id -> skus.sku_id",
            "orphan_rows": int((~inventory["sku_id"].isin(skus["sku_id"])).sum()),
        },
        {
            "relationship": "inventory.store_id -> stores.store_id",
            "orphan_rows": int((~inventory["store_id"].isin(stores["store_id"])).sum()),
        },
    ]
)
join_checks["orphan_rate"] = join_checks["orphan_rows"] / [
    len(sales),
    len(sales),
    int(sales["customer_id"].notna().sum()),
    len(inventory),
    len(inventory),
]
join_checks"""
    ),
    nbf.v4.new_markdown_cell("### 6. Validate discount, total value, cost, and profit"),
    nbf.v4.new_code_cell(
        """sales_enriched = sales.merge(
    skus[["sku_id", "sku_name", "category", "subcategory", "unit_price", "cost_price"]],
    on="sku_id",
    how="left",
    validate="many_to_one",
    suffixes=("_sale", "_list"),
)

sales_enriched["expected_discounted_unit_price"] = (
    sales_enriched["unit_price_list"] * (1 - sales_enriched["discount_pct"] / 100)
).round(2)
sales_enriched["expected_total_value"] = (
    sales_enriched["unit_price_sale"] * sales_enriched["quantity"]
).round(2)
sales_enriched["profit"] = (
    sales_enriched["total_value"]
    - sales_enriched["cost_price"] * sales_enriched["quantity"]
)

calculation_checks = pd.DataFrame(
    [
        {
            "check": "sale unit price matches list price after discount",
            "matching_rows": int(
                np.isclose(
                    sales_enriched["unit_price_sale"],
                    sales_enriched["expected_discounted_unit_price"],
                    atol=0.011,
                ).sum()
            ),
        },
        {
            "check": "total_value matches sale unit price x quantity",
            "matching_rows": int(
                np.isclose(
                    sales_enriched["total_value"],
                    sales_enriched["expected_total_value"],
                    atol=0.011,
                ).sum()
            ),
        },
    ]
)
calculation_checks["match_rate"] = calculation_checks["matching_rows"] / len(sales_enriched)

profit_summary = pd.DataFrame(
    {
        "metric": [
            "total sales",
            "calculated profit",
            "profit margin",
            "negative-profit rows",
            "negative-profit rate",
        ],
        "value": [
            sales_enriched["total_value"].sum(),
            sales_enriched["profit"].sum(),
            sales_enriched["profit"].sum() / sales_enriched["total_value"].sum(),
            int((sales_enriched["profit"] < 0).sum()),
            float((sales_enriched["profit"] < 0).mean()),
        ],
    }
)

display(calculation_checks)
profit_summary"""
    ),
    nbf.v4.new_markdown_cell("### 7. Identify schema differences from the Kaggle listing"),
    nbf.v4.new_code_cell(
        """advertised_sales_columns = {
    "date",
    "receipt_id",
    "store_id",
    "sku_id",
    "customer_id",
    "quantity",
    "unit_price",
    "total_value",
    "channel",
    "discount_pct",
    "promo_id",
}
actual_sales_columns = set(sales.columns)

schema_differences = {
    "advertised_but_missing": sorted(advertised_sales_columns - actual_sales_columns),
    "present_but_not_advertised": sorted(actual_sales_columns - advertised_sales_columns),
}
schema_differences"""
    ),
    nbf.v4.new_markdown_cell(
        """## Takeaways

- **Keep the dataset with disclosure.** It is production-sized and supports weekly sales, discount, cost, profit, store, product, category, and channel analysis.
- **Correct the source description.** The actual package has 641,843 sales rows covering 2021–2025; this mismatch is high severity for documentation but does not block the MVP.
- **Use the complete history.** Retain 2021–2025 for comparisons and default the product to the latest complete reporting period.
- **Deduplicate during ingestion.** Remove the 45 exact duplicate sales rows before aggregation.
- **Allow anonymous transactions.** Missing customer IDs affect 159,821 rows (24.9%) but do not block sales or profit reporting.
- **Do not build unsupported features.** Promotion attribution and receipt-level order analysis are unavailable because the advertised `promo_id` and `receipt_id` columns are missing.
- **Automate stable checks.** Test dimension-key uniqueness, foreign-key coverage, valid ranges, duplicate rows, date bounds, discounted-price reconciliation, transaction-total reconciliation, and profit calculation on every ingestion."""
    ),
]

output_path = Path("sales-coordinator-data-audit.ipynb")
nbf.write(notebook, output_path)
print(output_path.resolve())
