from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app, configured_cors_origins

client = TestClient(app)


def sample_csv() -> bytes:
    return b"""order_date,revenue,product
2026-07-06,100,Desk
2026-07-12,200,Chair
2026-07-13,150,Desk
2026-07-19,250,Chair
2026-07-20,300,Desk
2026-07-20,300,Desk
2026-07-24,invalid,Chair
bad-date,50,Lamp
"""


def upload(data: bytes | None = None) -> dict[str, tuple[str, BytesIO, str]]:
    return {
        "file": (
            "weekly-sales.csv",
            BytesIO(data or sample_csv()),
            "text/csv",
        )
    }


def test_profile_suggests_minimum_columns_and_counts_duplicates() -> None:
    response = client.post("/api/profile", files=upload())

    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 8
    assert body["suggestions"]["date"] == "order_date"
    assert body["suggestions"]["sales"] == "revenue"
    assert body["exact_duplicate_candidates"] == 1


def test_analyze_uses_latest_complete_week_and_reports_cleanup() -> None:
    response = client.post(
        "/api/analyze",
        files=upload(),
        data={
            "date_column": "order_date",
            "sales_column": "revenue",
            "currency": "USD",
            "exclude_exact_duplicates": "true",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["original_rows"] == 8
    assert body["receipt"]["excluded_duplicate_rows"] == 1
    assert body["receipt"]["invalid_date_rows"] == 1
    assert body["receipt"]["invalid_sales_rows"] == 1
    assert body["receipt"]["analyzed_rows"] == 5
    assert body["report"]["week_start"] == "2026-07-13"
    assert body["report"]["week_end"] == "2026-07-19"
    assert body["report"]["metrics"]["sales"]["current"] == 400
    assert body["report"]["metrics"]["sales"]["prior"] == 300
    assert body["report"]["metrics"]["sales"]["absolute_change"] == 100


def test_analyze_can_calculate_sales_from_quantity_and_price() -> None:
    data = b"""sale_date,qty,price
2026-07-06,2,10
2026-07-12,3,10
2026-07-13,4,10
2026-07-19,5,10
"""
    response = client.post(
        "/api/analyze",
        files=upload(data),
        data={
            "date_column": "sale_date",
            "quantity_column": "qty",
            "unit_price_column": "price",
            "currency": "USD",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["metrics"]["sales"]["current"] == 90
    assert "multiplied" in body["receipt"]["sales_method"]


def test_profile_reads_the_selected_excel_sheet() -> None:
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"notes": ["Use the Sales sheet"]}).to_excel(
            writer,
            sheet_name="Instructions",
            index=False,
        )
        pd.DataFrame(
            {
                "transaction_date": ["2026-07-13", "2026-07-19"],
                "sales_amount": [125, 225],
            }
        ).to_excel(writer, sheet_name="Sales", index=False)
    workbook.seek(0)

    response = client.post(
        "/api/profile",
        files={
            "file": (
                "weekly-sales.xlsx",
                workbook,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"sheet_name": "Sales"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sheet_names"] == ["Instructions", "Sales"]
    assert body["selected_sheet"] == "Sales"
    assert body["row_count"] == 2
    assert body["suggestions"]["date"] == "transaction_date"
    assert body["suggestions"]["sales"] == "sales_amount"


def test_profile_rejects_pdf_uploads() -> None:
    response = client.post(
        "/api/profile",
        files={
            "file": (
                "weekly-sales.pdf",
                BytesIO(b"%PDF-1.7"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload a CSV or Excel (.xlsx) file."


def test_profile_uses_the_configured_upload_limit(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    response = client.post(
        "/api/profile",
        files={
            "file": (
                "oversized.csv",
                BytesIO(b"x" * (1024 * 1024 + 1)),
                "text/csv",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "The uploaded file is larger than the 1 MB limit."
    )


def test_cors_origins_include_the_deployed_frontend(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://salescope.onrender.com, https://preview.example.com",
    )

    origins = configured_cors_origins()

    assert "http://localhost:5173" in origins
    assert "https://salescope.onrender.com" in origins
    assert "https://preview.example.com" in origins


def test_analyze_succeeds_without_optional_breakdown_columns() -> None:
    data = b"""date,sales
2026-07-06,100
2026-07-12,200
2026-07-13,150
2026-07-19,250
"""
    response = client.post(
        "/api/analyze",
        files=upload(data),
        data={
            "date_column": "date",
            "sales_column": "sales",
            "currency": "USD",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["analyzed_rows"] == 4
    assert body["report"]["metrics"]["sales"]["current"] == 400
    unavailable = {
        item["key"]
        for item in body["report"]["coverage"]
        if item["status"] == "unavailable"
    }
    assert {"product", "category", "store", "channel", "profit"} <= unavailable


def rich_sample_csv() -> bytes:
    return b"""date,sales,quantity,sku_name,category,store_name,channel,discount_pct,cost_price
2026-07-06,100,2,Desk,Furniture,East,Store,0,30
2026-07-12,200,2,Chair,Furniture,West,Online,10,60
2026-07-13,150,3,Desk,Furniture,East,Store,0,30
2026-07-15,300,3,Laptop,Technology,West,Online,20,80
2026-07-19,50,1,Chair,Furniture,West,Store,30,60
"""


def rich_form() -> dict[str, str]:
    return {
        "date_column": "date",
        "sales_column": "sales",
        "quantity_column": "quantity",
        "product_column": "sku_name",
        "category_column": "category",
        "store_column": "store_name",
        "channel_column": "channel",
        "discount_column": "discount_pct",
        "cost_column": "cost_price",
        "currency": "USD",
    }


def test_profile_prefers_names_over_identifier_columns() -> None:
    data = b"""date,sales,sku_id,sku_name,store_id,store_name
2026-07-13,100,1001,Desk,10,East
"""
    response = client.post("/api/profile", files=upload(data))

    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert suggestions["product"] == "sku_name"
    assert suggestions["store"] == "store_name"


def test_detailed_report_reconciles_metrics_drivers_and_risks() -> None:
    response = client.post(
        "/api/analyze",
        files=upload(rich_sample_csv()),
        data=rich_form(),
    )

    assert response.status_code == 200
    body = response.json()
    report = body["report"]
    metrics = report["metrics"]

    assert metrics["sales"]["current"] == 500
    assert metrics["sales"]["prior"] == 300
    assert metrics["sales"]["absolute_change"] == 200
    assert round(metrics["sales"]["percentage_change"], 2) == 66.67
    assert metrics["profit"]["current"] == 110
    assert metrics["profit"]["prior"] == 120
    assert metrics["margin"]["current"] == 22
    assert metrics["margin"]["prior"] == 40
    assert metrics["margin"]["absolute_change"] == -18
    assert metrics["units"]["current"] == 7

    categories = report["breakdowns"]["category"]
    assert sum(row["current_sales"] for row in categories) == 500
    assert sum(row["prior_sales"] for row in categories) == 300
    assert report["drivers"]["category"]["increases"][0]["label"] == "Technology"
    assert report["drivers"]["category"]["declines"][0]["label"] == "Furniture"

    assert report["discount_summary"]["discounted_sales"] == 350
    assert report["discount_summary"]["discounted_sales_share_pct"] == 70
    assert round(report["discount_summary"]["average_discount_pct"], 2) == 16.67
    risk_keys = {risk["key"] for risk in report["risks"]}
    assert {"negative_profit", "high_discount"} <= risk_keys
    assert len(report["manager_summary"]) >= 3

    coverage = {item["key"]: item["status"] for item in report["coverage"]}
    assert coverage["profit"] == "available"
    assert coverage["category"] == "available"
    assert coverage["region"] == "unavailable"


def test_weekly_history_keeps_complete_represented_weeks_and_calendar_changes() -> None:
    data = b"""date,sales,quantity,profit
2026-01-03,50,1,5
2026-01-05,100,2,10
2026-01-11,200,3,40
2026-01-12,150,2,20
2026-01-18,50,1,10
2026-01-26,400,4,60
2026-02-01,100,2,15
"""
    response = client.post(
        "/api/analyze",
        files=upload(data),
        data={
            "date_column": "date",
            "sales_column": "sales",
            "quantity_column": "quantity",
            "profit_column": "profit",
            "currency": "USD",
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    history = report["weekly_history"]

    assert [row["week_start"] for row in history] == [
        "2026-01-05",
        "2026-01-12",
        "2026-01-26",
    ]
    assert history[0]["sales"] == 300
    assert history[0]["profit"] == 50
    assert history[0]["units"] == 5
    assert round(history[0]["margin_pct"], 2) == 16.67
    assert history[0]["sales_change"] is None
    assert history[1]["sales_change"] == -100
    assert round(history[1]["sales_change_pct"], 2) == -33.33
    assert history[2]["sales"] == 500
    assert history[2]["sales_change"] is None
    assert report["trend"] == [
        {
            key: row[key]
            for key in ("week_start", "week_end", "sales", "profit", "units")
        }
        for row in history
    ]
    trend_coverage = next(
        item for item in report["coverage"] if item["key"] == "trend"
    )
    assert trend_coverage["reason"] == "3 reporting weeks are available."


def test_analyze_normalizes_fractional_discount_values() -> None:
    data = b"""date,sales,discount,profit
2026-07-06,100,0.1,10
2026-07-12,200,0.2,20
2026-07-13,150,0.2,15
2026-07-15,300,0.5,-30
2026-07-19,50,0,5
"""
    response = client.post(
        "/api/analyze",
        files=upload(data),
        data={
            "date_column": "date",
            "sales_column": "sales",
            "discount_column": "discount",
            "profit_column": "profit",
            "currency": "USD",
        },
    )

    assert response.status_code == 200
    body = response.json()
    summary = body["report"]["discount_summary"]
    assert round(summary["average_discount_pct"], 2) == 23.33
    assert summary["high_discount_rows"] == 2
    assert "high_discount" in {
        risk["key"] for risk in body["report"]["risks"]
    }
    assert any(
        "decimal fractions" in assumption
        for assumption in body["receipt"]["assumptions"]
    )


def test_verification_page_data_matches_report_math() -> None:
    response = client.post(
        "/api/analyze",
        files=upload(rich_sample_csv()),
        data=rich_form(),
    )

    assert response.status_code == 200
    body = response.json()
    verification = body["verification"]
    formulas = {item["key"]: item for item in verification["formulas"]}

    assert verification["mappings"]["sales"] == "sales"
    assert verification["mappings"]["cost"] == "cost_price"
    assert verification["row_reconciliation"]["current_period_rows"] == 3
    assert verification["row_reconciliation"]["prior_period_rows"] == 2
    assert formulas["sales"]["current_value"] == 500
    assert formulas["sales"]["prior_value"] == 300
    assert formulas["profit"]["current_value"] == 110
    assert formulas["margin"]["current_value"] == 22


def test_verification_csv_contains_source_rows_and_derived_values() -> None:
    response = client.post(
        "/api/verification.csv",
        files=upload(rich_sample_csv()),
        data=rich_form(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "salescope-verification.csv" in response.headers["content-disposition"]

    exported = pd.read_csv(BytesIO(response.content))
    assert len(exported) == 5
    assert exported["source_row_number"].tolist() == [2, 3, 4, 5, 6]
    assert set(exported["report_period"]) == {"current", "prior"}
    assert exported.loc[
        exported["report_period"] == "current",
        "sales_amount",
    ].sum() == 500
    assert exported.loc[
        exported["report_period"] == "current",
        "profit",
    ].sum() == 110
