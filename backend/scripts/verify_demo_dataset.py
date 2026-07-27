from __future__ import annotations

import argparse
import math
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify SalesScope against the full demo sales file."
    )
    parser.add_argument("sales_csv", type=Path)
    args = parser.parse_args()

    sales_path = args.sales_csv.resolve()
    client = TestClient(app)

    with sales_path.open("rb") as sales_file:
        profile_response = client.post(
            "/api/profile",
            files={"file": (sales_path.name, sales_file, "text/csv")},
        )
    profile_response.raise_for_status()
    profile = profile_response.json()

    with sales_path.open("rb") as sales_file:
        suggestions = profile["suggestions"]
        analysis_form = {
            "date_column": suggestions["date"],
            "sales_column": suggestions["sales"],
            "quantity_column": suggestions["quantity"] or "",
            "unit_price_column": suggestions["unit_price"] or "",
            "product_column": suggestions["product"] or "",
            "category_column": suggestions["category"] or "",
            "store_column": suggestions["store"] or "",
            "channel_column": suggestions["channel"] or "",
            "region_column": suggestions["region"] or "",
            "discount_column": suggestions["discount"] or "",
            "cost_column": suggestions["cost"] or "",
            "profit_column": suggestions["profit"] or "",
            "currency": "USD",
            "exclude_exact_duplicates": "true",
        }
        analysis_response = client.post(
            "/api/analyze",
            files={"file": (sales_path.name, sales_file, "text/csv")},
            data=analysis_form,
        )
    analysis_response.raise_for_status()
    result = analysis_response.json()

    with sales_path.open("rb") as sales_file:
        verification_response = client.post(
            "/api/verification.csv",
            files={"file": (sales_path.name, sales_file, "text/csv")},
            data=analysis_form,
        )
    verification_response.raise_for_status()
    verification_rows = pd.read_csv(BytesIO(verification_response.content))

    raw_source = pd.read_csv(sales_path, low_memory=False)
    expected_rows = len(raw_source)
    expected_duplicate_candidates = int(raw_source.duplicated().sum())
    source = raw_source.drop_duplicates()
    source["date"] = pd.to_datetime(source["date"], errors="coerce")
    source["total_value"] = pd.to_numeric(source["total_value"], errors="coerce")
    source = source.dropna(subset=["date", "total_value"])

    latest_date = source["date"].max().normalize()
    week_start = latest_date - pd.Timedelta(days=int(latest_date.weekday()))
    if int(latest_date.weekday()) < 6:
        week_start -= pd.Timedelta(days=7)
    week_end = week_start + pd.Timedelta(days=6)

    expected = float(
        source.loc[
            source["date"].between(week_start, week_end),
            "total_value",
        ].sum()
    )
    actual = float(result["report"]["metrics"]["sales"]["current"])

    assert profile["row_count"] == expected_rows
    assert profile["exact_duplicate_candidates"] == expected_duplicate_candidates
    assert (
        result["receipt"]["excluded_duplicate_rows"]
        == expected_duplicate_candidates
    )
    assert result["report"]["week_start"] == week_start.date().isoformat()
    assert result["report"]["week_end"] == week_end.date().isoformat()
    assert math.isclose(actual, expected, abs_tol=0.01)
    exported_current = verification_rows[
        (verification_rows["report_period"] == "current")
        & (verification_rows["analysis_status"] == "included")
    ]
    assert math.isclose(
        float(exported_current["sales_amount"].sum()),
        expected,
        abs_tol=0.01,
    )

    expected_profit = None
    actual_profit = result["report"]["metrics"]["profit"]["current"]
    if "profit" in source.columns:
        source["profit"] = pd.to_numeric(source["profit"], errors="coerce")
        expected_profit = float(
            source.loc[
                source["date"].between(week_start, week_end),
                "profit",
            ].sum()
        )
        assert actual_profit is not None
        assert math.isclose(float(actual_profit), expected_profit, abs_tol=0.01)
        assert math.isclose(
            float(exported_current["profit"].sum()),
            expected_profit,
            abs_tol=0.01,
        )

    for dimension, rows in result["report"]["breakdowns"].items():
        assert math.isclose(
            sum(float(row["current_sales"]) for row in rows),
            expected,
            abs_tol=0.01,
        ), f"{dimension} breakdown does not reconcile"

    print(f"rows={profile['row_count']}")
    print(f"duplicate_candidates={profile['exact_duplicate_candidates']}")
    print(f"week={week_start.date()}..{week_end.date()}")
    print(f"api_sales_total={actual:.2f}")
    print(f"independent_sales_total={expected:.2f}")
    if expected_profit is not None:
        print(f"api_profit_total={float(actual_profit):.2f}")
        print(f"independent_profit_total={expected_profit:.2f}")
    print(
        "available_breakdowns="
        + ",".join(result["report"]["breakdowns"].keys())
    )
    print(f"verification_export_rows={len(verification_rows)}")
    print("verification=passed")


if __name__ == "__main__":
    main()
