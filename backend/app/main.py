from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Annotated

import duckdb
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SUPPORTED_SUFFIXES = {".csv", ".xlsx"}

COLUMN_ALIASES = {
    "date": {
        "date",
        "orderdate",
        "saledate",
        "transactiondate",
        "purchasedate",
    },
    "sales": {
        "totalvalue",
        "revenue",
        "sales",
        "salesamount",
        "linetotal",
        "total",
    },
    "quantity": {"quantity", "qty", "units", "unitssold"},
    "unit_price": {"unitprice", "price", "saleprice"},
}


def normalize_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def suggest_columns(columns: list[str]) -> dict[str, str | None]:
    normalized = {column: normalize_header(column) for column in columns}
    return {
        concept: next(
            (
                column
                for column, normalized_column in normalized.items()
                if normalized_column in aliases
            ),
            None,
        )
        for concept, aliases in COLUMN_ALIASES.items()
    }


async def read_upload(upload: UploadFile) -> tuple[bytes, str]:
    filename = upload.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Upload a CSV or Excel (.xlsx) file.",
        )

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The uploaded file is larger than the 100 MB MVP limit.",
        )
    return data, suffix


def workbook_sheets(data: bytes, suffix: str) -> list[str]:
    if suffix != ".xlsx":
        return []
    with pd.ExcelFile(BytesIO(data), engine="openpyxl") as workbook:
        return list(workbook.sheet_names)


def load_frame(data: bytes, suffix: str, sheet_name: str | None) -> pd.DataFrame:
    try:
        if suffix == ".csv":
            try:
                frame = pd.read_csv(BytesIO(data), low_memory=False)
            except UnicodeDecodeError:
                frame = pd.read_csv(
                    BytesIO(data),
                    encoding="cp1252",
                    low_memory=False,
                )
        else:
            frame = pd.read_excel(
                BytesIO(data),
                sheet_name=sheet_name or 0,
                engine="openpyxl",
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="SalesScope could not read this file. Check the file format and try again.",
        ) from error

    if frame.empty:
        raise HTTPException(
            status_code=400,
            detail="The selected table has column headers but no sales rows.",
        )

    frame.columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in frame.columns):
        raise HTTPException(
            status_code=400,
            detail="Every uploaded column must have a header.",
        )
    if len(set(frame.columns)) != len(frame.columns):
        raise HTTPException(
            status_code=400,
            detail="The uploaded table contains duplicate column headers.",
        )
    return frame


def require_column(frame: pd.DataFrame, column: str, label: str) -> None:
    if column not in frame.columns:
        raise HTTPException(
            status_code=400,
            detail=f"The selected {label} column was not found in the uploaded table.",
        )


app = FastAPI(title="SalesScope API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/profile")
async def profile_upload(
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    data, suffix = await read_upload(file)
    sheets = workbook_sheets(data, suffix)
    selected_sheet = sheet_name or (sheets[0] if sheets else None)
    frame = load_frame(data, suffix, selected_sheet)

    return {
        "filename": file.filename,
        "file_size_bytes": len(data),
        "sheet_names": sheets,
        "selected_sheet": selected_sheet,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": list(frame.columns),
        "suggestions": suggest_columns(list(frame.columns)),
        "exact_duplicate_candidates": int(frame.duplicated().sum()),
    }


@app.post("/api/analyze")
async def analyze_upload(
    file: Annotated[UploadFile, File()],
    date_column: Annotated[str, Form()],
    sales_column: Annotated[str | None, Form()] = None,
    quantity_column: Annotated[str | None, Form()] = None,
    unit_price_column: Annotated[str | None, Form()] = None,
    sheet_name: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "USD",
    exclude_exact_duplicates: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    data, suffix = await read_upload(file)
    frame = load_frame(data, suffix, sheet_name)
    require_column(frame, date_column, "transaction date")

    if sales_column:
        require_column(frame, sales_column, "sales amount")
    elif quantity_column and unit_price_column:
        require_column(frame, quantity_column, "quantity")
        require_column(frame, unit_price_column, "unit price")
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "Choose a sales amount column, or choose both quantity and unit price."
            ),
        )

    original_rows = int(len(frame))
    duplicate_candidates = int(frame.duplicated().sum())
    working = frame.drop_duplicates().copy() if exclude_exact_duplicates else frame.copy()
    excluded_duplicates = original_rows - int(len(working))

    parsed_dates = pd.to_datetime(working[date_column], errors="coerce")
    if sales_column:
        sales_amount = pd.to_numeric(working[sales_column], errors="coerce")
        sales_method = f"Used values from {sales_column}."
    else:
        quantity = pd.to_numeric(working[quantity_column], errors="coerce")
        unit_price = pd.to_numeric(working[unit_price_column], errors="coerce")
        sales_amount = quantity * unit_price
        sales_method = (
            f"Calculated sales as {quantity_column} multiplied by "
            f"{unit_price_column}."
        )

    invalid_dates = int(parsed_dates.isna().sum())
    invalid_sales = int(sales_amount.isna().sum())
    valid = parsed_dates.notna() & sales_amount.notna()
    excluded_invalid = int((~valid).sum())

    analysis = pd.DataFrame(
        {
            "transaction_date": parsed_dates[valid].dt.normalize(),
            "sales_amount": sales_amount[valid].astype(float),
        }
    )
    if analysis.empty:
        raise HTTPException(
            status_code=400,
            detail="No rows contain both a valid transaction date and sales amount.",
        )

    latest_date = analysis["transaction_date"].max()
    latest_week_start = latest_date - pd.Timedelta(days=int(latest_date.weekday()))
    if int(latest_date.weekday()) < 6:
        latest_week_start -= pd.Timedelta(days=7)
    latest_week_end = latest_week_start + pd.Timedelta(days=6)
    prior_week_start = latest_week_start - pd.Timedelta(days=7)
    prior_week_end = latest_week_start - pd.Timedelta(days=1)

    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("analysis_frame", analysis)
        connection.execute(
            """
            CREATE TABLE sales_analysis AS
            SELECT
                CAST(transaction_date AS DATE) AS transaction_date,
                CAST(sales_amount AS DOUBLE) AS sales_amount
            FROM analysis_frame
            """
        )
        weekly = connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(sales_amount) FILTER (
                        WHERE transaction_date BETWEEN ? AND ?
                    ),
                    0
                ) AS current_sales,
                COUNT(*) FILTER (
                    WHERE transaction_date BETWEEN ? AND ?
                ) AS current_rows,
                COALESCE(
                    SUM(sales_amount) FILTER (
                        WHERE transaction_date BETWEEN ? AND ?
                    ),
                    0
                ) AS prior_sales,
                COUNT(*) FILTER (
                    WHERE transaction_date BETWEEN ? AND ?
                ) AS prior_rows
            FROM sales_analysis
            """,
            [
                latest_week_start.date(),
                latest_week_end.date(),
                latest_week_start.date(),
                latest_week_end.date(),
                prior_week_start.date(),
                prior_week_end.date(),
                prior_week_start.date(),
                prior_week_end.date(),
            ],
        ).fetchone()
    finally:
        connection.close()

    current_sales = float(weekly[0])
    current_rows = int(weekly[1])
    prior_sales = float(weekly[2])
    prior_rows = int(weekly[3])
    absolute_change = current_sales - prior_sales if prior_rows else None
    percentage_change = (
        (absolute_change / prior_sales) * 100
        if absolute_change is not None and prior_sales != 0
        else None
    )

    return {
        "receipt": {
            "filename": file.filename,
            "original_rows": original_rows,
            "analyzed_rows": int(len(analysis)),
            "duplicate_candidates": duplicate_candidates,
            "excluded_duplicate_rows": excluded_duplicates,
            "invalid_date_rows": invalid_dates,
            "invalid_sales_rows": invalid_sales,
            "excluded_invalid_rows": excluded_invalid,
            "sales_method": sales_method,
            "assumptions": [
                "Reporting weeks run Monday through Sunday.",
                f"All sales values are treated as {currency}.",
                (
                    "Possible duplicate rows were excluded with your confirmation."
                    if excluded_duplicates
                    else "Possible duplicate rows were kept in this analysis."
                ),
            ],
        },
        "report": {
            "currency": currency,
            "week_start": latest_week_start.date().isoformat(),
            "week_end": latest_week_end.date().isoformat(),
            "sales_total": current_sales,
            "sales_rows": current_rows,
            "prior_week_start": prior_week_start.date().isoformat(),
            "prior_week_end": prior_week_end.date().isoformat(),
            "prior_sales_total": prior_sales if prior_rows else None,
            "prior_sales_rows": prior_rows,
            "absolute_change": absolute_change,
            "percentage_change": percentage_change,
        },
    }
