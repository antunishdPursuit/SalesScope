# SalesScope

SalesScope helps transaction-based Sales Coordinators turn CSV or Excel exports into a clear, trustworthy weekly sales report.

## Try the live demo

Open the [SalesScope live demo](https://salesscope-bs61.onrender.com) and use one of the fictional datasets included in this repository:

- [Download the small sample dataset](https://raw.githubusercontent.com/antunishdPursuit/SalesScope/main/examples/sample-sales.csv) for a quick test.
- [Download the representative dataset](https://raw.githubusercontent.com/antunishdPursuit/SalesScope/main/examples/representative-sales.csv) for a more realistic report with 53,479 transaction rows.

To try the complete workflow:

1. Download one of the datasets above.
2. Open the live demo and select the downloaded CSV file.
3. Review the suggested column mappings and cleanup choices.
4. Create the report to see weekly sales, comparisons, performance breakdowns, risks, and a manager summary.
5. Open **Verify calculations** to review the formulas, row counts, and spreadsheet verification steps.

The free demo can take up to a minute to wake up after a period of inactivity. Use only fictional or non-sensitive data.

## The problem

Marcus is a Sales Coordinator at a retail company. Every Monday, he exports raw order data, pastes it into a spreadsheet, sorts and compares the rows, writes a summary, and sends it to regional managers. The same process takes more than three hours each week. When a manager asks why performance changed, Marcus must search through rows instead of getting a direct answer.

Our problem statement is:

> Marcus, a Sales Coordinator, struggles to create timely weekly sales reports and explain performance changes because his company’s order system records transactions but does not support its recurring reporting needs. As a result, he spends more than three hours every Monday preparing the report, and managers may receive late or incomplete answers.

SalesScope does not try to replace a full business-intelligence platform. It focuses on Marcus’s repeated Monday workflow:

1. prepare the report on one page by uploading a sales export, confirming column meanings, and choosing cleanup rules;
2. receive the analysis the file can support; and
3. optionally verify the report with formulas, row counts, spreadsheet steps, and a downloadable evidence file.

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

The minimum fields support weekly sales totals and prior-week comparisons. Product, category, store, region, channel, discount, cost, and profit fields are optional. If they are missing, the upload can still be analyzed, but SalesScope labels the related analysis as limited or unavailable and identifies the fields needed to unlock it.

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

## Current MVP

The working MVP supports:

- CSV and Excel uploads up to 100 MB;
- Excel sheet selection;
- one preparation page for upload, column mapping, cleanup choices, and report readiness;
- automatic matching for common required and optional sales fields;
- manual correction of those mappings;
- user-controlled exclusion of possible duplicate rows;
- invalid-date and invalid-sales reporting;
- the latest complete Monday-through-Sunday period and prior-week comparison;
- sales, profit, profit margin, and units-sold headline metrics when supported;
- an eight-week sales trend;
- category, store, product, channel, and region breakdowns when supported;
- performance drivers, discount findings, and risk flags;
- a rule-based manager summary;
- clear available, limited, and unavailable analysis coverage; and
- an optional verification page with formulas, row reconciliation, independent spreadsheet steps, and a downloadable verification CSV.

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

Create the enriched local upload used for the full report:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\prepare_demo_upload.py "..\Sales Coordinator Dataset\source"
```

The script joins the sales, product, and store tables without changing the number of sales rows. It writes `Sales Coordinator Dataset/demo_sales_enriched.csv`, which remains excluded from Git because it is about 95 MB.

The verified latest complete week is October 20–26, 2025. With the 45 possible duplicate rows kept, the API and an independent calculation both return **$176,838.39** in sales and **$59,671.67** in profit.

For a quick public demo, upload [`examples/sample-sales.csv`](examples/sample-sales.csv). It contains fictional transaction rows and all optional fields needed to exercise the main report sections.

For a more realistic hosted test, upload
[`examples/representative-sales.csv`](examples/representative-sales.csv). It is
a deterministic, date-stratified 7.55 MiB sample of the enriched synthetic
dataset with 53,479 rows. It preserves the full date range and all category,
store, channel, product, profit, and discount fields needed by the detailed
report. Regenerate it with:

```powershell
cd backend
python scripts\prepare_public_demo.py `
  "..\Sales Coordinator Dataset\demo_sales_enriched.csv" `
  "..\examples\representative-sales.csv"
```

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

- The React interface manages report preparation, reporting, and optional verification.
- FastAPI validates requests and returns the data-quality receipt and report.
- DuckDB performs the weekly aggregation.
- Pandas reads CSV and Excel inputs before they are registered with DuckDB.

## Repository structure

```text
backend/
  app/analysis.py
  app/main.py
  scripts/prepare_demo_upload.py
  scripts/verify_demo_dataset.py
  tests/test_api.py
examples/
  sample-sales.csv
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

## Deployment settings

SalesScope can deploy as two native Render services without Docker:

- a Python web service rooted at `backend`; and
- a static site rooted at `frontend`.

The backend accepts these environment variables:

- `MAX_UPLOAD_MB` controls the server-side upload limit and defaults to `100`;
- `CORS_ORIGINS` is a comma-separated list of deployed frontend addresses.

The frontend accepts these build-time environment variables:

- `VITE_API_URL` points to the deployed backend;
- `VITE_MAX_UPLOAD_MB` displays and enforces the matching browser-side limit.

For the free public demo, set both upload-limit variables to `10`. Use the
7.55 MiB representative file for realistic hosted testing. The 31.22 MiB raw
sales file caused the free service to restart during processing, and the
90.7 MiB enriched file requires even more memory. Keep both larger files for
local testing. The local upload defaults remain `100`. Public-demo users should
upload only fictional or non-sensitive data.

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

Verify the full enriched local demo dataset:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\verify_demo_dataset.py "..\Sales Coordinator Dataset\demo_sales_enriched.csv"
```

The script compares sales and profit totals with separate Pandas calculations, confirms each available breakdown reconciles to the headline result, downloads the verification CSV, and checks its included rows.

## Commit workflow

This repository uses small, coherent commits. A significant working behavior, test boundary, documentation change, or infrastructure change should receive its own commit after the relevant checks pass.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit scale and branch workflow.

## Next steps

1. Run usability tests with Sales Coordinators and revise labels or report order based on observed confusion.
2. Add saved report history only after defining authentication, access control, retention, and privacy requirements.
3. Add configurable reporting periods after validating that Monday-through-Sunday is too restrictive for target users.
4. Add export of the manager summary and report visuals.
5. Prepare a production deployment and repeat the full upload, calculation, verification, accessibility, and responsive test suite.
