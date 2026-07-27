from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

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
    assert body["report"]["sales_total"] == 400
    assert body["report"]["prior_sales_total"] == 300
    assert body["report"]["absolute_change"] == 100


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
    assert body["report"]["sales_total"] == 90
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
    assert body["report"]["sales_total"] == 400
