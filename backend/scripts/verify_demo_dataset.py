from __future__ import annotations

import argparse
import math
import sys
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
        analysis_response = client.post(
            "/api/analyze",
            files={"file": (sales_path.name, sales_file, "text/csv")},
            data={
                "date_column": "date",
                "sales_column": "total_value",
                "currency": "USD",
                "exclude_exact_duplicates": "true",
            },
        )
    analysis_response.raise_for_status()
    result = analysis_response.json()

    source = pd.read_csv(sales_path, low_memory=False).drop_duplicates()
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
    actual = float(result["report"]["sales_total"])

    assert profile["row_count"] == 641_843
    assert profile["exact_duplicate_candidates"] == 45
    assert result["receipt"]["excluded_duplicate_rows"] == 45
    assert result["report"]["week_start"] == week_start.date().isoformat()
    assert result["report"]["week_end"] == week_end.date().isoformat()
    assert math.isclose(actual, expected, abs_tol=0.01)

    print(f"rows={profile['row_count']}")
    print(f"duplicate_candidates={profile['exact_duplicate_candidates']}")
    print(f"week={week_start.date()}..{week_end.date()}")
    print(f"api_sales_total={actual:.2f}")
    print(f"independent_sales_total={expected:.2f}")
    print("verification=passed")


if __name__ == "__main__":
    main()
