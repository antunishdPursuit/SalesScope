from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


DIMENSION_FIELDS = ("category", "store", "product", "channel", "region")

ANALYSIS_LABELS = {
    "weekly_sales": "Weekly sales",
    "units": "Units sold",
    "product": "Product performance",
    "category": "Category performance",
    "store": "Store or location performance",
    "channel": "Channel performance",
    "region": "Region performance",
    "discount": "Discount analysis",
    "profit": "Profit and margin",
    "trend": "Eight-week trend",
}


@dataclass(frozen=True)
class ColumnMap:
    date: str
    sales: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    product: str | None = None
    category: str | None = None
    store: str | None = None
    channel: str | None = None
    region: str | None = None
    discount: str | None = None
    cost: str | None = None
    profit: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            field: getattr(self, field)
            for field in (
                "date",
                "sales",
                "quantity",
                "unit_price",
                "product",
                "category",
                "store",
                "channel",
                "region",
                "discount",
                "cost",
                "profit",
            )
        }


@dataclass
class AnalysisBundle:
    analysis: pd.DataFrame
    audit: pd.DataFrame
    receipt: dict[str, Any]
    mappings: ColumnMap


def _numeric(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _dimension(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    values = frame[column].astype("string").str.strip()
    return values.mask(values.eq(""), pd.NA)


def _discount_percentage(
    frame: pd.DataFrame,
    column: str | None,
) -> tuple[pd.Series, str | None]:
    discount = _numeric(frame, column)
    if not column:
        return discount, None

    usable = discount.dropna()
    uses_fractional_scale = (
        not usable.empty
        and usable.between(0, 1).all()
        and usable.between(0, 1, inclusive="neither").any()
    )
    if uses_fractional_scale:
        return (
            discount * 100,
            (
                f"Discount values from {column} were interpreted as decimal "
                "fractions and converted to percentage points."
            ),
        )
    return (
        discount,
        f"Discount values from {column} were interpreted as percentage points.",
    )


def prepare_analysis(
    frame: pd.DataFrame,
    mappings: ColumnMap,
    *,
    currency: str,
    exclude_exact_duplicates: bool,
) -> AnalysisBundle:
    parsed_dates = pd.to_datetime(frame[mappings.date], errors="coerce")
    quantity = _numeric(frame, mappings.quantity)
    unit_price = _numeric(frame, mappings.unit_price)

    if mappings.sales:
        sales_amount = _numeric(frame, mappings.sales)
        sales_method = f"Sales amount comes from the {mappings.sales} column."
        sales_formula = mappings.sales
    else:
        sales_amount = quantity * unit_price
        sales_method = (
            f"Sales amount equals {mappings.quantity} multiplied by "
            f"{mappings.unit_price}."
        )
        sales_formula = f"{mappings.quantity} × {mappings.unit_price}"

    if mappings.profit:
        profit = _numeric(frame, mappings.profit)
        profit_method = f"Profit comes from the {mappings.profit} column."
        profit_formula = mappings.profit
    elif mappings.cost and mappings.quantity:
        cost = _numeric(frame, mappings.cost)
        profit = sales_amount - (cost * quantity)
        profit_method = (
            f"Profit equals sales minus {mappings.cost} multiplied by "
            f"{mappings.quantity}."
        )
        profit_formula = (
            f"{sales_formula} − ({mappings.cost} × {mappings.quantity})"
        )
    else:
        profit = pd.Series(np.nan, index=frame.index, dtype="float64")
        profit_method = None
        profit_formula = None

    discount, discount_assumption = _discount_percentage(
        frame,
        mappings.discount,
    )
    duplicate_mask = frame.duplicated(keep="first")
    excluded_duplicate_mask = (
        duplicate_mask
        if exclude_exact_duplicates
        else pd.Series(False, index=frame.index)
    )
    invalid_date_mask = parsed_dates.isna() & ~excluded_duplicate_mask
    invalid_sales_mask = sales_amount.isna() & ~excluded_duplicate_mask
    included_mask = ~(
        excluded_duplicate_mask | invalid_date_mask | invalid_sales_mask
    )

    audit = pd.DataFrame(
        {
            "source_row_number": frame.index.to_series().astype(int) + 2,
            "source_date_value": frame[mappings.date].astype("string"),
            "source_sales_value": (
                frame[mappings.sales].astype("string")
                if mappings.sales
                else sales_amount.astype("string")
            ),
            "transaction_date": parsed_dates,
            "sales_amount": sales_amount,
            "quantity": quantity,
            "unit_price": unit_price,
            "profit": profit,
            "discount_pct": discount,
            "duplicate_candidate": duplicate_mask,
            "included": included_mask,
        }
    )
    audit["exclusion_reason"] = ""
    audit.loc[excluded_duplicate_mask, "exclusion_reason"] = (
        "Possible duplicate excluded with user confirmation"
    )
    audit.loc[invalid_date_mask, "exclusion_reason"] = "Invalid transaction date"
    audit.loc[
        invalid_sales_mask & ~invalid_date_mask,
        "exclusion_reason",
    ] = "Invalid sales value"

    for dimension in DIMENSION_FIELDS:
        audit[dimension] = _dimension(frame, getattr(mappings, dimension))

    analysis = audit.loc[included_mask].copy()
    analysis["transaction_date"] = analysis["transaction_date"].dt.normalize()

    if analysis.empty:
        raise ValueError("No rows contain both a valid transaction date and sales amount.")

    profit_values = int(analysis["profit"].notna().sum())
    profit_coverage = profit_values / len(analysis)
    quantity_values = int(analysis["quantity"].notna().sum())
    quantity_coverage = quantity_values / len(analysis)

    assumptions = [
        "Reporting weeks run Monday through Sunday.",
        f"All mapped sales values are treated as {currency}.",
        (
            "Possible duplicate rows were excluded with your confirmation."
            if int(excluded_duplicate_mask.sum())
            else "Possible duplicate rows were kept in this analysis."
        ),
    ]
    if discount_assumption:
        assumptions.append(discount_assumption)

    receipt = {
        "original_rows": int(len(frame)),
        "analyzed_rows": int(len(analysis)),
        "duplicate_candidates": int(duplicate_mask.sum()),
        "excluded_duplicate_rows": int(excluded_duplicate_mask.sum()),
        "invalid_date_rows": int(invalid_date_mask.sum()),
        "invalid_sales_rows": int(invalid_sales_mask.sum()),
        "excluded_invalid_rows": int(
            (invalid_date_mask | invalid_sales_mask).sum()
        ),
        "sales_method": sales_method,
        "sales_formula": sales_formula,
        "profit_method": profit_method,
        "profit_formula": profit_formula,
        "profit_coverage_pct": profit_coverage * 100,
        "quantity_coverage_pct": quantity_coverage * 100,
        "assumptions": assumptions,
    }
    return AnalysisBundle(
        analysis=analysis,
        audit=audit,
        receipt=receipt,
        mappings=mappings,
    )


def complete_reporting_period(
    transaction_dates: pd.Series,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    latest_date = transaction_dates.max()
    latest_week_start = latest_date - pd.Timedelta(days=int(latest_date.weekday()))
    if int(latest_date.weekday()) < 6:
        latest_week_start -= pd.Timedelta(days=7)
    latest_week_end = latest_week_start + pd.Timedelta(days=6)
    prior_week_start = latest_week_start - pd.Timedelta(days=7)
    prior_week_end = latest_week_start - pd.Timedelta(days=1)
    return latest_week_start, latest_week_end, prior_week_start, prior_week_end


def _safe_sum(series: pd.Series) -> float | None:
    if series.notna().sum() == 0:
        return None
    return float(series.sum())


def _metric(
    current: float | None,
    prior: float | None,
) -> dict[str, float | None]:
    absolute_change = (
        current - prior if current is not None and prior is not None else None
    )
    percentage_change = (
        (absolute_change / prior) * 100
        if absolute_change is not None and prior not in (None, 0)
        else None
    )
    return {
        "current": current,
        "prior": prior,
        "absolute_change": absolute_change,
        "percentage_change": percentage_change,
    }


def _period_frames(
    analysis: pd.DataFrame,
    current_start: pd.Timestamp,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
]:
    current_start = current_start.normalize()
    current_end = current_start + pd.Timedelta(days=6)
    prior_start = current_start - pd.Timedelta(days=7)
    prior_end = current_start - pd.Timedelta(days=1)
    current = analysis[
        analysis["transaction_date"].between(current_start, current_end)
    ]
    prior = analysis[
        analysis["transaction_date"].between(prior_start, prior_end)
    ]
    return current, prior, current_start, current_end, prior_start, prior_end


def _coverage(
    bundle: AnalysisBundle,
    current: pd.DataFrame,
    prior: pd.DataFrame,
    complete_weeks: int,
) -> list[dict[str, str]]:
    mapped = bundle.mappings
    coverage: list[dict[str, str]] = [
        {
            "key": "weekly_sales",
            "label": ANALYSIS_LABELS["weekly_sales"],
            "status": "available",
            "reason": "A valid transaction date and sales amount are available.",
        }
    ]

    optional_requirements = {
        "units": mapped.quantity,
        "product": mapped.product,
        "category": mapped.category,
        "store": mapped.store,
        "channel": mapped.channel,
        "region": mapped.region,
        "discount": mapped.discount,
    }
    for key, column in optional_requirements.items():
        coverage.append(
            {
                "key": key,
                "label": ANALYSIS_LABELS[key],
                "status": "available" if column else "unavailable",
                "reason": (
                    f"Mapped from {column}."
                    if column
                    else f"No {ANALYSIS_LABELS[key].lower()} field was mapped."
                ),
            }
        )

    profit_rows = pd.concat([current["profit"], prior["profit"]]).notna()
    if not (mapped.profit or (mapped.cost and mapped.quantity)):
        profit_status = "unavailable"
        profit_reason = "Map profit, or map cost and quantity, to calculate margin."
    elif profit_rows.all():
        profit_status = "available"
        profit_reason = bundle.receipt["profit_method"]
    else:
        profit_status = "limited"
        profit_reason = "Some report-period rows do not contain usable profit inputs."
    coverage.append(
        {
            "key": "profit",
            "label": ANALYSIS_LABELS["profit"],
            "status": profit_status,
            "reason": profit_reason,
        }
    )

    coverage.append(
        {
            "key": "trend",
            "label": ANALYSIS_LABELS["trend"],
            "status": "available" if complete_weeks >= 2 else "unavailable",
            "reason": (
                f"{complete_weeks} reporting weeks are available."
                if complete_weeks >= 2
                else "At least two reporting weeks are required."
            ),
        }
    )
    return coverage


def _weekly_history(
    analysis: pd.DataFrame,
    current_start: pd.Timestamp,
) -> list[dict[str, Any]]:
    history = analysis.copy()
    history["week_start"] = history["transaction_date"] - pd.to_timedelta(
        history["transaction_date"].dt.weekday,
        unit="D",
    )
    earliest_date = history["transaction_date"].min().normalize()
    first_complete_start = earliest_date - pd.Timedelta(
        days=int(earliest_date.weekday())
    )
    if int(earliest_date.weekday()) > 0:
        first_complete_start += pd.Timedelta(days=7)

    history = history[
        history["week_start"].between(first_complete_start, current_start)
    ]
    rows: list[dict[str, Any]] = []
    prior_week_start: pd.Timestamp | None = None
    prior_sales: float | None = None
    for week_start, group in history.groupby("week_start", sort=True):
        sales = float(group["sales_amount"].sum())
        profit = _safe_sum(group["profit"])
        margin = profit / sales * 100 if profit is not None and sales else None
        has_prior_calendar_week = (
            prior_week_start is not None
            and week_start - prior_week_start == pd.Timedelta(days=7)
        )
        change = (
            _metric(sales, prior_sales)
            if has_prior_calendar_week
            else _metric(sales, None)
        )
        rows.append(
            {
                "week_start": week_start.date().isoformat(),
                "week_end": (week_start + pd.Timedelta(days=6)).date().isoformat(),
                "sales": sales,
                "profit": profit,
                "margin_pct": margin,
                "units": _safe_sum(group["quantity"]),
                "sales_change": change["absolute_change"],
                "sales_change_pct": change["percentage_change"],
            }
        )
        prior_week_start = week_start
        prior_sales = sales
    return rows


def _trend(
    weekly_history: list[dict[str, Any]],
    current_start: pd.Timestamp,
) -> list[dict[str, Any]]:
    current_key = current_start.date().isoformat()
    return [
        {
            "week_start": row["week_start"],
            "week_end": row["week_end"],
            "sales": row["sales"],
            "profit": row["profit"],
            "units": row["units"],
        }
        for row in [
            row for row in weekly_history if row["week_start"] <= current_key
        ][-8:]
    ]


def _breakdown(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    dimension: str,
) -> list[dict[str, Any]]:
    has_prior_period = not prior.empty
    current_grouped = (
        current.assign(label=current[dimension].fillna("Unspecified"))
        .groupby("label", dropna=False)
        .agg(
            current_sales=("sales_amount", "sum"),
            current_profit=("profit", lambda values: values.sum(min_count=1)),
            current_units=("quantity", lambda values: values.sum(min_count=1)),
        )
    )
    prior_grouped = (
        prior.assign(label=prior[dimension].fillna("Unspecified"))
        .groupby("label", dropna=False)
        .agg(
            prior_sales=("sales_amount", "sum"),
            prior_profit=("profit", lambda values: values.sum(min_count=1)),
            prior_units=("quantity", lambda values: values.sum(min_count=1)),
        )
    )
    combined = current_grouped.join(prior_grouped, how="outer")
    combined["current_sales"] = combined["current_sales"].fillna(0)
    if has_prior_period:
        combined["prior_sales"] = combined["prior_sales"].fillna(0)
        combined["sales_change"] = (
            combined["current_sales"] - combined["prior_sales"]
        )
    else:
        combined["prior_sales"] = np.nan
        combined["sales_change"] = np.nan
    combined["sales_change_pct"] = np.where(
        combined["prior_sales"] != 0,
        combined["sales_change"] / combined["prior_sales"] * 100,
        np.nan,
    )
    combined["margin_pct"] = np.where(
        combined["current_sales"] != 0,
        combined["current_profit"] / combined["current_sales"] * 100,
        np.nan,
    )
    combined = combined.sort_values("current_sales", ascending=False)

    rows: list[dict[str, Any]] = []
    for label, row in combined.iterrows():
        rows.append(
            {
                "label": str(label),
                "current_sales": float(row["current_sales"]),
                "prior_sales": (
                    None
                    if pd.isna(row["prior_sales"])
                    else float(row["prior_sales"])
                ),
                "sales_change": (
                    None
                    if pd.isna(row["sales_change"])
                    else float(row["sales_change"])
                ),
                "sales_change_pct": (
                    None
                    if pd.isna(row["sales_change_pct"])
                    else float(row["sales_change_pct"])
                ),
                "current_profit": (
                    None
                    if pd.isna(row["current_profit"])
                    else float(row["current_profit"])
                ),
                "margin_pct": (
                    None
                    if pd.isna(row["margin_pct"])
                    else float(row["margin_pct"])
                ),
                "current_units": (
                    None
                    if pd.isna(row["current_units"])
                    else float(row["current_units"])
                ),
            }
        )
    return rows


def _drivers(
    breakdowns: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    drivers: dict[str, list[dict[str, Any]]] = {}
    for dimension, rows in breakdowns.items():
        comparable = [
            row for row in rows if row["sales_change"] is not None
        ]
        ranked = sorted(
            comparable,
            key=lambda row: row["sales_change"],
            reverse=True,
        )
        drivers[dimension] = {
            "increases": [row for row in ranked if row["sales_change"] > 0][:5],
            "declines": [
                row
                for row in sorted(
                    comparable,
                    key=lambda row: row["sales_change"],
                )
                if row["sales_change"] < 0
            ][:5],
        }
    return drivers


def _currency(value: float, currency: str) -> str:
    return f"{currency} {abs(value):,.2f}"


def _manager_summary(
    metrics: dict[str, dict[str, float | None]],
    breakdowns: dict[str, list[dict[str, Any]]],
    current: pd.DataFrame,
    currency: str,
) -> list[str]:
    sales = metrics["sales"]
    sentences: list[str] = []
    if sales["percentage_change"] is None:
        sentences.append(
            f"Sales totaled {_currency(sales['current'] or 0, currency)}; "
            "a complete prior week was not available for comparison."
        )
    else:
        direction = "increased" if (sales["absolute_change"] or 0) >= 0 else "decreased"
        sentences.append(
            f"Sales {direction} {abs(sales['percentage_change']):.1f}% to "
            f"{_currency(sales['current'] or 0, currency)} compared with the prior week."
        )

    for dimension in ("category", "store", "channel", "product"):
        rows = [
            row
            for row in breakdowns.get(dimension, [])
            if row["sales_change"] is not None
        ]
        if rows:
            positive = max(rows, key=lambda row: row["sales_change"])
            if positive["sales_change"] > 0:
                sentences.append(
                    f"{positive['label']} produced the largest {dimension} increase, "
                    f"adding {_currency(positive['sales_change'], currency)} in sales."
                )
                break

    margin = metrics.get("margin")
    if margin and margin["current"] is not None:
        margin_sentence = f"Profit margin was {margin['current']:.1f}%"
        if margin["absolute_change"] is not None:
            direction = "up" if margin["absolute_change"] >= 0 else "down"
            margin_sentence += (
                f", {direction} {abs(margin['absolute_change']):.1f} percentage "
                "points from the prior week"
            )
        sentences.append(margin_sentence + ".")

    negative_profit_rows = int((current["profit"] < 0).sum())
    if negative_profit_rows:
        sentences.append(
            f"{negative_profit_rows:,} sales rows generated negative profit and "
            "should be reviewed."
        )
    return sentences


def build_report(
    bundle: AnalysisBundle,
    *,
    currency: str,
    week_start: str | None = None,
) -> dict[str, Any]:
    analysis = bundle.analysis
    latest_start, _, _, _ = complete_reporting_period(
        analysis["transaction_date"]
    )
    weekly_history = _weekly_history(analysis, latest_start)
    available_weeks = {
        row["week_start"]
        for row in weekly_history
    }
    if week_start is None:
        selected_start = latest_start
    else:
        try:
            selected_start = pd.Timestamp(week_start).normalize()
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Choose a complete reporting week available in this analysis."
            ) from error
        if selected_start.date().isoformat() not in available_weeks:
            raise ValueError(
                "Choose a complete reporting week available in this analysis."
            )

    (
        current,
        prior,
        current_start,
        current_end,
        prior_start,
        prior_end,
    ) = _period_frames(analysis, selected_start)

    current_sales = float(current["sales_amount"].sum())
    prior_sales = float(prior["sales_amount"].sum()) if len(prior) else None
    current_profit = _safe_sum(current["profit"])
    prior_profit = _safe_sum(prior["profit"]) if len(prior) else None
    current_units = _safe_sum(current["quantity"])
    prior_units = _safe_sum(prior["quantity"]) if len(prior) else None
    current_margin = (
        current_profit / current_sales * 100
        if current_profit is not None and current_sales
        else None
    )
    prior_margin = (
        prior_profit / prior_sales * 100
        if prior_profit is not None and prior_sales
        else None
    )

    metrics = {
        "sales": _metric(current_sales, prior_sales),
        "profit": _metric(current_profit, prior_profit),
        "margin": _metric(current_margin, prior_margin),
        "units": _metric(current_units, prior_units),
        "sales_rows": _metric(
            float(len(current)),
            float(len(prior)) if len(prior) else None,
        ),
    }

    breakdowns = {
        dimension: _breakdown(current, prior, dimension)
        for dimension in DIMENSION_FIELDS
        if getattr(bundle.mappings, dimension)
    }
    drivers = _drivers(breakdowns)

    discounted = current[current["discount_pct"].fillna(0) > 0]
    high_discount = current[current["discount_pct"].fillna(0) >= 20]
    risks: list[dict[str, Any]] = []
    negative_profit = current[current["profit"] < 0]
    if len(negative_profit):
        risks.append(
            {
                "key": "negative_profit",
                "severity": "warning",
                "title": "Negative-profit sales",
                "detail": (
                    f"{len(negative_profit):,} rows lost "
                    f"{_currency(abs(float(negative_profit['profit'].sum())), currency)}."
                ),
            }
        )
    if len(high_discount):
        high_discount_profit = _safe_sum(high_discount["profit"])
        detail = (
            f"{len(high_discount):,} rows used discounts of 20% or more, totaling "
            f"{_currency(float(high_discount['sales_amount'].sum()), currency)} in sales."
        )
        if high_discount_profit is not None:
            detail += f" Their profit was {_currency(high_discount_profit, currency)}."
        risks.append(
            {
                "key": "high_discount",
                "severity": "info",
                "title": "High-discount sales",
                "detail": detail,
            }
        )

    discount_summary = None
    if bundle.mappings.discount:
        discount_summary = {
            "discounted_sales": float(discounted["sales_amount"].sum()),
            "discounted_sales_share_pct": (
                float(discounted["sales_amount"].sum()) / current_sales * 100
                if current_sales
                else None
            ),
            "average_discount_pct": (
                float(current["discount_pct"].mean())
                if current["discount_pct"].notna().any()
                else None
            ),
            "high_discount_rows": int(len(high_discount)),
        }

    coverage = _coverage(bundle, current, prior, len(weekly_history))
    summary = _manager_summary(metrics, breakdowns, current, currency)

    return {
        "currency": currency,
        "week_start": current_start.date().isoformat(),
        "week_end": current_end.date().isoformat(),
        "is_latest_week": current_start == latest_start,
        "prior_week_start": prior_start.date().isoformat(),
        "prior_week_end": prior_end.date().isoformat(),
        "metrics": metrics,
        "trend": _trend(weekly_history, current_start),
        "weekly_history": weekly_history,
        "breakdowns": breakdowns,
        "drivers": drivers,
        "discount_summary": discount_summary,
        "risks": risks,
        "manager_summary": summary,
        "coverage": coverage,
    }


def build_verification(
    bundle: AnalysisBundle,
    report: dict[str, Any],
    *,
    currency: str,
) -> dict[str, Any]:
    mappings = bundle.mappings
    metrics = report["metrics"]
    formulas = [
        {
            "key": "sales",
            "label": "Total sales",
            "formula": f"SUM({bundle.receipt['sales_formula']})",
            "explanation": (
                f"Filter {mappings.date} to the report week, apply the same cleanup "
                f"choices, and add {bundle.receipt['sales_formula']}."
            ),
            "current_value": metrics["sales"]["current"],
            "prior_value": metrics["sales"]["prior"],
        },
        {
            "key": "sales_change",
            "label": "Sales change",
            "formula": "current week sales − prior week sales",
            "explanation": "Subtract the prior complete week's sales from the current week.",
            "current_value": metrics["sales"]["absolute_change"],
            "prior_value": None,
        },
        {
            "key": "sales_change_pct",
            "label": "Sales percentage change",
            "formula": "(current sales − prior sales) ÷ prior sales × 100",
            "explanation": "Divide the sales difference by prior-week sales.",
            "current_value": metrics["sales"]["percentage_change"],
            "prior_value": None,
        },
    ]
    if bundle.receipt["profit_formula"]:
        formulas.extend(
            [
                {
                    "key": "profit",
                    "label": "Profit",
                    "formula": f"SUM({bundle.receipt['profit_formula']})",
                    "explanation": bundle.receipt["profit_method"],
                    "current_value": metrics["profit"]["current"],
                    "prior_value": metrics["profit"]["prior"],
                },
                {
                    "key": "margin",
                    "label": "Profit margin",
                    "formula": "profit ÷ sales × 100",
                    "explanation": "Divide report-period profit by report-period sales.",
                    "current_value": metrics["margin"]["current"],
                    "prior_value": metrics["margin"]["prior"],
                },
            ]
        )

    steps = [
        "Open the original CSV or Excel sheet and turn on column filters.",
        (
            f"Filter {mappings.date} from {report['week_start']} through "
            f"{report['week_end']}."
        ),
        (
            "Exclude the possible duplicate rows."
            if bundle.receipt["excluded_duplicate_rows"]
            else "Keep the possible duplicate rows, matching your SalesScope choice."
        ),
        "Remove rows with invalid transaction dates or sales values.",
        f"Add the values using: {bundle.receipt['sales_formula']}.",
        (
            f"Repeat for {report['prior_week_start']} through "
            f"{report['prior_week_end']}."
        ),
        "Subtract the prior total from the current total and divide by the prior total.",
    ]

    return {
        "currency": currency,
        "filename": bundle.receipt.get("filename"),
        "mappings": mappings.as_dict(),
        "week_start": report["week_start"],
        "week_end": report["week_end"],
        "prior_week_start": report["prior_week_start"],
        "prior_week_end": report["prior_week_end"],
        "row_reconciliation": {
            "original_rows": bundle.receipt["original_rows"],
            "analyzed_rows": bundle.receipt["analyzed_rows"],
            "duplicate_candidates": bundle.receipt["duplicate_candidates"],
            "excluded_duplicate_rows": bundle.receipt["excluded_duplicate_rows"],
            "excluded_invalid_rows": bundle.receipt["excluded_invalid_rows"],
            "current_period_rows": int(metrics["sales_rows"]["current"] or 0),
            "prior_period_rows": int(metrics["sales_rows"]["prior"] or 0),
        },
        "assumptions": bundle.receipt["assumptions"],
        "formulas": formulas,
        "spreadsheet_steps": steps,
    }


def verification_export(
    bundle: AnalysisBundle,
    report: dict[str, Any],
) -> pd.DataFrame:
    audit = bundle.audit.copy()
    current_start = pd.Timestamp(report["week_start"])
    current_end = pd.Timestamp(report["week_end"])
    prior_start = pd.Timestamp(report["prior_week_start"])
    prior_end = pd.Timestamp(report["prior_week_end"])

    in_current = audit["transaction_date"].between(current_start, current_end)
    in_prior = audit["transaction_date"].between(prior_start, prior_end)
    relevant = in_current | in_prior
    export = audit.loc[relevant].copy()
    export["report_period"] = np.select(
        [
            export["transaction_date"].between(current_start, current_end),
            export["transaction_date"].between(prior_start, prior_end),
        ],
        ["current", "prior"],
        default="outside",
    )
    export["analysis_status"] = np.where(
        export["included"],
        "included",
        "excluded",
    )
    export["transaction_date"] = export["transaction_date"].dt.date.astype("string")
    columns = [
        "source_row_number",
        "report_period",
        "analysis_status",
        "exclusion_reason",
        "source_date_value",
        "source_sales_value",
        "transaction_date",
        "sales_amount",
        "quantity",
        "unit_price",
        "profit",
        "discount_pct",
        "product",
        "category",
        "store",
        "channel",
        "region",
        "duplicate_candidate",
    ]
    return export[columns]
