from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.analysis import (
    AnalysisBundle,
    ColumnMap,
    build_report,
    build_verification,
    prepare_analysis,
    verification_export,
)
from app.session_cache import AnalysisSessionCache

DEFAULT_MAX_UPLOAD_MB = 100
SUPPORTED_SUFFIXES = {".csv", ".xlsx"}
LOCAL_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

COLUMN_ALIASES = {
    "date": (
        "date",
        "orderdate",
        "saledate",
        "transactiondate",
        "purchasedate",
    ),
    "sales": (
        "totalvalue",
        "revenue",
        "sales",
        "salesamount",
        "linetotal",
        "total",
    ),
    "quantity": ("quantity", "qty", "units", "unitssold"),
    "unit_price": ("unitprice", "price", "saleprice"),
    "product": (
        "productname",
        "skuname",
        "product",
        "sku",
        "productid",
        "skuid",
    ),
    "category": ("category", "productcategory"),
    "store": (
        "storename",
        "locationname",
        "store",
        "location",
        "storeid",
        "locationid",
    ),
    "channel": ("channel", "saleschannel", "orderchannel"),
    "region": ("region", "territory", "salesregion"),
    "discount": (
        "discountpct",
        "discountpercentage",
        "discountrate",
        "discount",
        "discountamount",
    ),
    "cost": ("costprice", "unitcost", "cost", "productcost"),
    "profit": ("profit", "grossprofit", "lineprofit"),
}


def normalize_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def configured_max_upload_mb() -> int:
    raw_value = os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_MB
    return value if value > 0 else DEFAULT_MAX_UPLOAD_MB


def configured_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def configured_cors_origins() -> list[str]:
    configured = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return [*LOCAL_ORIGINS, *configured]


def suggest_columns(columns: list[str]) -> dict[str, str | None]:
    normalized = {column: normalize_header(column) for column in columns}
    suggestions: dict[str, str | None] = {}
    for concept, aliases in COLUMN_ALIASES.items():
        suggestions[concept] = next(
            (
                column
                for alias in aliases
                for column, normalized_column in normalized.items()
                if normalized_column == alias
            ),
            None,
        )
    return suggestions


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
    max_upload_mb = configured_max_upload_mb()
    if len(data) > max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=(
                f"The uploaded file is larger than the {max_upload_mb} MB limit."
            ),
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


def require_column(frame: pd.DataFrame, column: str | None, label: str) -> None:
    if column and column not in frame.columns:
        raise HTTPException(
            status_code=400,
            detail=f"The selected {label} column was not found in the uploaded table.",
        )


def mappings_from_form(
    frame: pd.DataFrame,
    *,
    date_column: str,
    sales_column: str | None,
    quantity_column: str | None,
    unit_price_column: str | None,
    product_column: str | None,
    category_column: str | None,
    store_column: str | None,
    channel_column: str | None,
    region_column: str | None,
    discount_column: str | None,
    cost_column: str | None,
    profit_column: str | None,
) -> ColumnMap:
    selected = {
        "date": date_column,
        "sales": sales_column,
        "quantity": quantity_column,
        "unit price": unit_price_column,
        "product": product_column,
        "category": category_column,
        "store or location": store_column,
        "channel": channel_column,
        "region": region_column,
        "discount": discount_column,
        "cost": cost_column,
        "profit": profit_column,
    }
    for label, column in selected.items():
        require_column(frame, column, label)

    if not sales_column and not (quantity_column and unit_price_column):
        raise HTTPException(
            status_code=400,
            detail=(
                "Choose a sales amount column, or choose both quantity and unit price."
            ),
        )
    return ColumnMap(
        date=date_column,
        sales=sales_column,
        quantity=quantity_column,
        unit_price=unit_price_column,
        product=product_column,
        category=category_column,
        store=store_column,
        channel=channel_column,
        region=region_column,
        discount=discount_column,
        cost=cost_column,
        profit=profit_column,
    )


app = FastAPI(title="SalesScope API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
analysis_sessions = AnalysisSessionCache(
    ttl_seconds=configured_positive_int("ANALYSIS_SESSION_TTL_SECONDS", 1800),
    max_sessions=configured_positive_int("MAX_ANALYSIS_SESSIONS", 2),
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


def analyze_frame(
    frame: pd.DataFrame,
    *,
    filename: str | None,
    currency: str,
    exclude_exact_duplicates: bool,
    date_column: str,
    sales_column: str | None,
    quantity_column: str | None,
    unit_price_column: str | None,
    product_column: str | None,
    category_column: str | None,
    store_column: str | None,
    channel_column: str | None,
    region_column: str | None,
    discount_column: str | None,
    cost_column: str | None,
    profit_column: str | None,
) -> AnalysisBundle:
    mappings = mappings_from_form(
        frame,
        date_column=date_column,
        sales_column=sales_column,
        quantity_column=quantity_column,
        unit_price_column=unit_price_column,
        product_column=product_column,
        category_column=category_column,
        store_column=store_column,
        channel_column=channel_column,
        region_column=region_column,
        discount_column=discount_column,
        cost_column=cost_column,
        profit_column=profit_column,
    )
    try:
        bundle = prepare_analysis(
            frame,
            mappings,
            currency=currency,
            exclude_exact_duplicates=exclude_exact_duplicates,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    bundle.receipt["filename"] = filename
    return bundle


def analysis_payload(
    *,
    analysis_id: str,
    bundle: AnalysisBundle,
    currency: str,
    week_start: str | None = None,
) -> dict[str, object]:
    try:
        report = build_report(
            bundle,
            currency=currency,
            week_start=week_start,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    verification = build_verification(bundle, report, currency=currency)
    return {
        "analysis_id": analysis_id,
        "receipt": bundle.receipt,
        "report": report,
        "verification": verification,
    }


@app.post("/api/analyze")
async def analyze_upload(
    file: Annotated[UploadFile, File()],
    date_column: Annotated[str, Form()],
    sales_column: Annotated[str | None, Form()] = None,
    quantity_column: Annotated[str | None, Form()] = None,
    unit_price_column: Annotated[str | None, Form()] = None,
    product_column: Annotated[str | None, Form()] = None,
    category_column: Annotated[str | None, Form()] = None,
    store_column: Annotated[str | None, Form()] = None,
    channel_column: Annotated[str | None, Form()] = None,
    region_column: Annotated[str | None, Form()] = None,
    discount_column: Annotated[str | None, Form()] = None,
    cost_column: Annotated[str | None, Form()] = None,
    profit_column: Annotated[str | None, Form()] = None,
    sheet_name: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "USD",
    exclude_exact_duplicates: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    data, suffix = await read_upload(file)
    frame = load_frame(data, suffix, sheet_name)
    bundle = analyze_frame(
        frame,
        filename=file.filename,
        currency=currency,
        exclude_exact_duplicates=exclude_exact_duplicates,
        date_column=date_column,
        sales_column=sales_column,
        quantity_column=quantity_column,
        unit_price_column=unit_price_column,
        product_column=product_column,
        category_column=category_column,
        store_column=store_column,
        channel_column=channel_column,
        region_column=region_column,
        discount_column=discount_column,
        cost_column=cost_column,
        profit_column=profit_column,
    )
    analysis_id = analysis_sessions.create(bundle, currency)
    return analysis_payload(
        analysis_id=analysis_id,
        bundle=bundle,
        currency=currency,
    )


@app.get("/api/analyses/{analysis_id}/reports/{week_start}")
def selected_week_report(
    analysis_id: str,
    week_start: str,
) -> dict[str, object]:
    session = analysis_sessions.get(analysis_id)
    if session is None:
        raise HTTPException(
            status_code=410,
            detail=(
                "This analysis session expired. Upload the file again to "
                "continue reviewing its weekly reports."
            ),
        )
    return analysis_payload(
        analysis_id=analysis_id,
        bundle=session.bundle,
        currency=session.currency,
        week_start=week_start,
    )


@app.get(
    "/api/analyses/{analysis_id}/reports/{week_start}/verification.csv"
)
def selected_week_verification(
    analysis_id: str,
    week_start: str,
) -> Response:
    session = analysis_sessions.get(analysis_id)
    if session is None:
        raise HTTPException(
            status_code=410,
            detail=(
                "This analysis session expired. Upload the file again to "
                "download verification data."
            ),
        )
    payload = analysis_payload(
        analysis_id=analysis_id,
        bundle=session.bundle,
        currency=session.currency,
        week_start=week_start,
    )
    export = verification_export(session.bundle, payload["report"])
    return Response(
        content=export.to_csv(index=False),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="salescope-{week_start}-verification.csv"'
            )
        },
    )


@app.post("/api/verification.csv")
async def download_verification(
    file: Annotated[UploadFile, File()],
    date_column: Annotated[str, Form()],
    sales_column: Annotated[str | None, Form()] = None,
    quantity_column: Annotated[str | None, Form()] = None,
    unit_price_column: Annotated[str | None, Form()] = None,
    product_column: Annotated[str | None, Form()] = None,
    category_column: Annotated[str | None, Form()] = None,
    store_column: Annotated[str | None, Form()] = None,
    channel_column: Annotated[str | None, Form()] = None,
    region_column: Annotated[str | None, Form()] = None,
    discount_column: Annotated[str | None, Form()] = None,
    cost_column: Annotated[str | None, Form()] = None,
    profit_column: Annotated[str | None, Form()] = None,
    sheet_name: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "USD",
    exclude_exact_duplicates: Annotated[bool, Form()] = False,
) -> Response:
    data, suffix = await read_upload(file)
    frame = load_frame(data, suffix, sheet_name)
    bundle = analyze_frame(
        frame,
        filename=file.filename,
        currency=currency,
        exclude_exact_duplicates=exclude_exact_duplicates,
        date_column=date_column,
        sales_column=sales_column,
        quantity_column=quantity_column,
        unit_price_column=unit_price_column,
        product_column=product_column,
        category_column=category_column,
        store_column=store_column,
        channel_column=channel_column,
        region_column=region_column,
        discount_column=discount_column,
        cost_column=cost_column,
        profit_column=profit_column,
    )
    report = build_report(bundle, currency=currency)
    export = verification_export(bundle, report)
    return Response(
        content=export.to_csv(index=False),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="salescope-verification.csv"'
            )
        },
    )
