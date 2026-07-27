# SalesScope

SalesScope helps transaction-based Sales Coordinators turn CSV or Excel exports into a clear, trustworthy weekly sales report.

## The problem

Marcus is a Sales Coordinator at a retail company. Every Monday, he exports raw order data, pastes it into a spreadsheet, sorts and compares the rows, writes a summary, and sends it to regional managers. The same process takes more than three hours each week. When a manager asks why performance changed, Marcus must search through rows instead of getting a direct answer.

Our problem statement is:

> Marcus, a Sales Coordinator, struggles to create timely weekly sales reports and explain performance changes because his company’s order system records transactions but does not support its recurring reporting needs. As a result, he spends more than three hours every Monday preparing the report, and managers may receive late or incomplete answers.

SalesScope does not try to replace a full business-intelligence platform. It focuses on Marcus’s repeated Monday workflow:

1. upload a sales export;
2. confirm what the columns mean;
3. review data-quality findings and cleanup choices;
4. receive the analysis the file can support;
5. prepare a manager-ready summary.

## Who it is for

The MVP is for Sales Coordinators in transaction-based businesses such as retail, wholesale, and distribution.

The title “Sales Coordinator” is not identical across industries. Software companies may focus on opportunities, stages, contracts, and recurring revenue. Service businesses may use bookings or projects. SalesScope currently supports transaction-line data, not every possible sales workflow.

## Data expectations

SalesScope accepts one `.csv` file or one sheet from an `.xlsx` workbook. Each row should represent one transaction line.

### Minimum analysis

The file must include:

- a transaction date; and
- a sales amount, or both quantity and unit price.

### Fields that unlock more analysis

- quantity for units sold;
- product and category for product performance;
- store, location, territory, or region for geographic performance;
- channel for channel performance;
- discount percentage or amount for discount analysis;
- cost or profit for profit and margin analysis.

Missing optional fields do not cause the entire upload to fail. SalesScope should complete the supported analysis and clearly list what it could not calculate and which fields would unlock those results.

## Assumptions and limitations

SalesScope currently makes these assumptions:

- the user is a Sales Coordinator, or someone doing similar transaction-based sales reporting;
- the upload is a `.csv` file or one sheet from an `.xlsx` workbook, not a PDF;
- each row represents one sales transaction line;
- every column has a unique header;
- the file contains a transaction date and either a sales amount or both quantity and unit price;
- reporting weeks run from Monday through Sunday; and
- all mapped sales values use the currency selected by the user.

The minimum fields support weekly sales totals and prior-week comparisons. Product, category, store, region, channel, discount, cost, and profit fields are optional. If they are missing, the upload can still be analyzed, but SalesScope cannot provide the related breakdowns or explain every performance change. Future versions will show each available, limited, and unavailable analysis with the fields needed to unlock it.

This MVP does not support PDFs, images, `.xls` workbooks, multiple files at once, opportunity-pipeline data, forecasting, or automatic decisions. It also cannot determine whether two identical rows are true duplicates without a reliable transaction-line identifier, so it asks the user before excluding them.

The current backend reads each upload into process memory and creates a temporary in-memory DuckDB table; it does not intentionally save the uploaded file. A production deployment still needs an approved security, retention, access-control, and privacy policy. Until then, users should not upload confidential customer information or other sensitive business data.

## Trust and cleanup rules

SalesScope keeps the raw upload unchanged and creates a temporary DuckDB analysis table.

The product must report:

- original rows;
- analyzed rows;
- invalid rows;
- possible duplicate rows;
- excluded rows and the reason;
- assumptions and calculations;
- available, limited, and unavailable analyses.

SalesScope does not silently remove repeated rows. If the file has no reliable transaction-line identifier, identical rows are only possible duplicates. The user chooses whether to include or exclude them.

## Current working slice

The first vertical slice supports:

- CSV and Excel uploads up to 100 MB;
- Excel sheet selection;
- automatic matching for common date, sales, quantity, and unit-price headers;
- manual correction of those mappings;
- user-controlled exclusion of possible duplicate rows;
- invalid-date and invalid-sales reporting;
- a transparent data-quality receipt;
- the latest complete Monday-through-Sunday sales total;
- a prior-week comparison.

Product, store, category, channel, discount, cost, profit, margin, risk findings, and manager-summary features are planned next.

## Demo dataset

Development uses the Kaggle [Synthetic Retail Dataset — 1.2M Transactions](https://www.kaggle.com/datasets/amirkhanh/synthetic-retail-dataset-1-2m-transactions).

The downloaded package differs from its listing:

- 641,843 sales rows, not 1.2 million;
- January 1, 2021 through October 31, 2025, not 2025 only;
- 45 exact duplicate candidates;
- no `receipt_id` or sales-level `promo_id`;
- no store-region field.

The full ZIP and raw CSV files remain local and are excluded from Git. The repository keeps the audit code and notebook. Download the dataset from Kaggle and place the files under:

```text
Sales Coordinator Dataset/
  source/
    bm_sales.csv
    bm_skus.csv
    bm_stores.csv
    bm_customers.csv
    bm_inventory.csv
    bm_promotions.csv
```

The verified latest complete week in `bm_sales.csv` is October 20–26, 2025. After excluding the 45 possible duplicate rows with confirmation, both the API and an independent calculation return **$176,838.39** in sales.

## Architecture

```text
React + TypeScript + Vite
        |
        | CSV/XLSX upload and mappings
        v
FastAPI
        |
        | temporary raw table and analysis table
        v
DuckDB
```

- The React interface manages upload, mapping, review, and report steps.
- FastAPI validates requests and returns the data-quality receipt and report.
- DuckDB performs the weekly aggregation.
- Pandas reads CSV and Excel inputs before they are registered with DuckDB.

## Repository structure

```text
backend/
  app/main.py
  scripts/verify_demo_dataset.py
  tests/test_api.py
frontend/
  src/App.tsx
  src/index.css
Sales Coordinator Dataset/
  create_data_audit_notebook.py
  sales-coordinator-data-audit.ipynb
CONTRIBUTING.md
README.md
```

## Run locally

### 1. Start the backend

Prerequisite: Python 3.11.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Expected result: the API runs at `http://localhost:8000`.

### 2. Start the frontend

Prerequisite: Node.js and npm.

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Expected result: open `http://localhost:5173`.

## Verify

Run backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend checks:

```powershell
cd frontend
npm.cmd run build
npm.cmd run lint
```

Verify the full local demo dataset:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\verify_demo_dataset.py "<path-to-bm_sales.csv>"
```

Replace `<path-to-bm_sales.csv>` with the full path to the downloaded sales CSV. The script compares the API result with a separate Pandas calculation.

## Commit workflow

This repository uses small, coherent commits. A significant working behavior, test boundary, documentation change, or infrastructure change should receive its own commit after the relevant checks pass.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit scale and branch workflow.

## Next steps

1. Create a flat demo upload by joining sales, product, and store data.
2. Add mapping and coverage rules for the optional analysis fields.
3. Add weekly product, category, store, and channel breakdowns.
4. Add discount, profit, margin, and risk findings.
5. Generate a transparent rule-based manager summary.
6. Test the complete flow with partial and complete datasets.
