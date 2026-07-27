import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import './index.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Suggestions = {
  date: string | null
  sales: string | null
  quantity: string | null
  unit_price: string | null
}

type Profile = {
  filename: string
  file_size_bytes: number
  sheet_names: string[]
  selected_sheet: string | null
  row_count: number
  column_count: number
  columns: string[]
  suggestions: Suggestions
  exact_duplicate_candidates: number
}

type Receipt = {
  filename: string
  original_rows: number
  analyzed_rows: number
  duplicate_candidates: number
  excluded_duplicate_rows: number
  invalid_date_rows: number
  invalid_sales_rows: number
  excluded_invalid_rows: number
  sales_method: string
  assumptions: string[]
}

type Report = {
  currency: string
  week_start: string
  week_end: string
  sales_total: number
  sales_rows: number
  prior_week_start: string
  prior_week_end: string
  prior_sales_total: number | null
  prior_sales_rows: number
  absolute_change: number | null
  percentage_change: number | null
}

type Analysis = {
  receipt: Receipt
  report: Report
}

type Step = 1 | 2 | 3 | 4

const steps = ['Upload', 'Map columns', 'Review data', 'Weekly report']

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDateRange(start: string, end: string) {
  const dateFormatter = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
  return `${dateFormatter.format(new Date(`${start}T00:00:00Z`))}–${dateFormatter.format(
    new Date(`${end}T00:00:00Z`),
  )}`
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

function App() {
  const [step, setStep] = useState<Step>(1)
  const [file, setFile] = useState<File | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [sheetName, setSheetName] = useState('')
  const [dateColumn, setDateColumn] = useState('')
  const [salesColumn, setSalesColumn] = useState('')
  const [quantityColumn, setQuantityColumn] = useState('')
  const [unitPriceColumn, setUnitPriceColumn] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [excludeDuplicates, setExcludeDuplicates] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const canAnalyze = Boolean(
    dateColumn && (salesColumn || (quantityColumn && unitPriceColumn)),
  )

  const progressLabel = useMemo(
    () => `Step ${step} of 4: ${steps[step - 1]}`,
    [step],
  )

  async function readError(response: Response) {
    const body = await response.json().catch(() => null)
    return body?.detail ?? 'SalesScope could not process this file.'
  }

  async function profileFile(selectedFile: File, selectedSheet = '') {
    setIsLoading(true)
    setError('')
    setAnalysis(null)

    try {
      const form = new FormData()
      form.append('file', selectedFile)
      if (selectedSheet) form.append('sheet_name', selectedSheet)

      const response = await fetch(`${API_URL}/api/profile`, {
        method: 'POST',
        body: form,
      })
      if (!response.ok) throw new Error(await readError(response))

      const nextProfile = (await response.json()) as Profile
      setProfile(nextProfile)
      setSheetName(nextProfile.selected_sheet ?? '')
      setDateColumn(nextProfile.suggestions.date ?? '')
      setSalesColumn(nextProfile.suggestions.sales ?? '')
      setQuantityColumn(nextProfile.suggestions.quantity ?? '')
      setUnitPriceColumn(nextProfile.suggestions.unit_price ?? '')
      setExcludeDuplicates(false)
      setStep(2)
    } catch (caughtError) {
      setProfile(null)
      setError(getErrorMessage(caughtError))
      setStep(1)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return
    setFile(selectedFile)
    await profileFile(selectedFile)
  }

  async function handleSheetChange(event: ChangeEvent<HTMLSelectElement>) {
    const selectedSheet = event.target.value
    setSheetName(selectedSheet)
    if (file) await profileFile(file, selectedSheet)
  }

  async function analyzeFile(event: FormEvent) {
    event.preventDefault()
    if (!file || !canAnalyze) return

    setIsLoading(true)
    setError('')

    try {
      const form = new FormData()
      form.append('file', file)
      form.append('date_column', dateColumn)
      if (salesColumn) form.append('sales_column', salesColumn)
      if (!salesColumn && quantityColumn) {
        form.append('quantity_column', quantityColumn)
      }
      if (!salesColumn && unitPriceColumn) {
        form.append('unit_price_column', unitPriceColumn)
      }
      if (sheetName) form.append('sheet_name', sheetName)
      form.append('currency', currency)
      form.append('exclude_exact_duplicates', String(excludeDuplicates))

      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        body: form,
      })
      if (!response.ok) throw new Error(await readError(response))

      setAnalysis((await response.json()) as Analysis)
      setStep(3)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
    } finally {
      setIsLoading(false)
    }
  }

  function reset() {
    setStep(1)
    setFile(null)
    setProfile(null)
    setAnalysis(null)
    setError('')
    if (fileInput.current) fileInput.current.value = ''
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" onClick={reset}>
          SalesScope
        </a>
        <span className="header-note">Transparent weekly sales reporting</span>
      </header>

      <main id="top" className="main-content">
        <nav aria-label="Analysis progress" className="stepper">
          <p className="sr-only" aria-live="polite">
            {progressLabel}
          </p>
          <ol>
            {steps.map((label, index) => {
              const number = index + 1
              const state =
                number === step ? 'current' : number < step ? 'complete' : 'upcoming'
              return (
                <li
                  key={label}
                  className={`step step--${state}`}
                  aria-current={state === 'current' ? 'step' : undefined}
                >
                  <span className="step__number">{number}</span>
                  <span>{label}</span>
                </li>
              )
            })}
          </ol>
        </nav>

        {error && (
          <div className="notice notice--error" role="alert">
            <strong>We could not continue.</strong>
            <span>{error}</span>
          </div>
        )}

        {step === 1 && (
          <section className="narrow-panel" aria-labelledby="upload-title">
            <div className="eyebrow">Weekly reporting, without spreadsheet cleanup</div>
            <h1 id="upload-title">Turn a sales spreadsheet into a clear weekly report.</h1>
            <p className="intro">
              SalesScope checks your file, explains what can be analyzed, and shows
              every cleanup decision before calculating results.
            </p>

            <div className="requirements">
              <h2>What your file needs</h2>
              <p>
                At minimum, include a <strong>transaction date</strong> and a{' '}
                <strong>sales amount</strong>. You can also provide quantity and unit
                price so SalesScope can calculate the sales amount.
              </p>
              <details>
                <summary>Fields that unlock a fuller analysis</summary>
                <ul>
                  <li>Quantity for units sold</li>
                  <li>Product and category for performance breakdowns</li>
                  <li>Store, location, territory, or region</li>
                  <li>Sales channel</li>
                  <li>Discount percentage or amount</li>
                  <li>Cost or profit for margin analysis</li>
                </ul>
              </details>
            </div>

            <div className="upload-zone">
              <label htmlFor="sales-file">Upload sales file</label>
              <p>Choose one CSV or Excel file, up to 100 MB.</p>
              <input
                ref={fileInput}
                id="sales-file"
                type="file"
                accept=".csv,.xlsx"
                onChange={handleFile}
                disabled={isLoading}
              />
              <button
                className="button button--primary"
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={isLoading}
              >
                {isLoading ? 'Reading file…' : 'Choose file'}
              </button>
            </div>

            <p className="privacy-note">
              Your original file stays unchanged. During this MVP, uploads are
              processed temporarily and are not saved as report history.
            </p>
          </section>
        )}

        {step === 2 && profile && (
          <section aria-labelledby="mapping-title">
            <div className="page-heading">
              <div>
                <div className="eyebrow">File recognized</div>
                <h1 id="mapping-title">Confirm what each column means.</h1>
                <p>
                  {profile.filename} · {formatNumber(profile.row_count)} rows ·{' '}
                  {profile.column_count} columns
                </p>
              </div>
              <button className="button button--quiet" type="button" onClick={reset}>
                Replace file
              </button>
            </div>

            <form onSubmit={analyzeFile}>
              {profile.sheet_names.length > 1 && (
                <div className="form-field sheet-field">
                  <label htmlFor="sheet-name">
                    Select the sheet with your sales rows
                  </label>
                  <select
                    id="sheet-name"
                    value={sheetName}
                    onChange={handleSheetChange}
                    disabled={isLoading}
                  >
                    {profile.sheet_names.map((sheet) => (
                      <option key={sheet} value={sheet}>
                        {sheet}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="mapping-card">
                <div className="mapping-header" aria-hidden="true">
                  <span>Sales concept</span>
                  <span>Uploaded column</span>
                  <span>Status</span>
                </div>
                <MappingRow
                  id="date-column"
                  label="Transaction date"
                  required
                  value={dateColumn}
                  columns={profile.columns}
                  onChange={setDateColumn}
                />
                <MappingRow
                  id="sales-column"
                  label="Sales amount"
                  value={salesColumn}
                  columns={profile.columns}
                  onChange={setSalesColumn}
                  hint="Optional when quantity and unit price are both mapped."
                />
                <MappingRow
                  id="quantity-column"
                  label="Quantity"
                  value={quantityColumn}
                  columns={profile.columns}
                  onChange={setQuantityColumn}
                />
                <MappingRow
                  id="unit-price-column"
                  label="Unit price"
                  value={unitPriceColumn}
                  columns={profile.columns}
                  onChange={setUnitPriceColumn}
                />
              </div>

              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="currency">Currency for this analysis</label>
                  <select
                    id="currency"
                    value={currency}
                    onChange={(event) => setCurrency(event.target.value)}
                  >
                    <option value="USD">USD — US dollar</option>
                    <option value="CAD">CAD — Canadian dollar</option>
                    <option value="EUR">EUR — Euro</option>
                    <option value="GBP">GBP — British pound</option>
                  </select>
                </div>

                <fieldset className="duplicate-choice">
                  <legend>Possible duplicate rows</legend>
                  <p>
                    We found {formatNumber(profile.exact_duplicate_candidates)} exact
                    row {profile.exact_duplicate_candidates === 1 ? 'match' : 'matches'}.
                    Without a reliable transaction-line ID, these may be real sales.
                  </p>
                  <label>
                    <input
                      type="checkbox"
                      checked={excludeDuplicates}
                      onChange={(event) => setExcludeDuplicates(event.target.checked)}
                      disabled={profile.exact_duplicate_candidates === 0}
                    />
                    Exclude these rows from this analysis
                  </label>
                </fieldset>
              </div>

              {!canAnalyze && (
                <p className="field-guidance" role="status">
                  Map a transaction date and either a sales amount or both quantity
                  and unit price.
                </p>
              )}

              <div className="actions">
                <button className="button button--secondary" type="button" onClick={reset}>
                  Back
                </button>
                <button
                  className="button button--primary"
                  type="submit"
                  disabled={!canAnalyze || isLoading}
                >
                  {isLoading ? 'Checking data…' : 'Review data'}
                </button>
              </div>
            </form>
          </section>
        )}

        {step === 3 && analysis && (
          <section aria-labelledby="review-title">
            <div className="page-heading">
              <div>
                <div className="eyebrow">Quality receipt</div>
                <h1 id="review-title">Review what will be analyzed.</h1>
                <p>{analysis.receipt.filename}</p>
              </div>
            </div>

            <div className="receipt-grid">
              <ReceiptItem
                label="Original rows"
                value={formatNumber(analysis.receipt.original_rows)}
              />
              <ReceiptItem
                label="Rows analyzed"
                value={formatNumber(analysis.receipt.analyzed_rows)}
              />
              <ReceiptItem
                label="Duplicate rows excluded"
                value={formatNumber(analysis.receipt.excluded_duplicate_rows)}
              />
              <ReceiptItem
                label="Invalid rows excluded"
                value={formatNumber(analysis.receipt.excluded_invalid_rows)}
              />
            </div>

            <div className="review-columns">
              <div className="review-panel">
                <h2>Checks and calculations</h2>
                <dl className="check-list">
                  <div>
                    <dt>Possible duplicate rows</dt>
                    <dd>{formatNumber(analysis.receipt.duplicate_candidates)}</dd>
                  </div>
                  <div>
                    <dt>Invalid transaction dates</dt>
                    <dd>{formatNumber(analysis.receipt.invalid_date_rows)}</dd>
                  </div>
                  <div>
                    <dt>Invalid sales values</dt>
                    <dd>{formatNumber(analysis.receipt.invalid_sales_rows)}</dd>
                  </div>
                </dl>
                <p>{analysis.receipt.sales_method}</p>
              </div>

              <div className="review-panel">
                <h2>Assumptions</h2>
                <ul>
                  {analysis.receipt.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="notice notice--info">
              <strong>First implementation slice</strong>
              <span>
                Weekly sales is available. Product, store, channel, discount, and
                profit analysis will be added only after this core result is verified.
              </span>
            </div>

            <div className="actions">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => setStep(2)}
              >
                Back to mapping
              </button>
              <button
                className="button button--primary"
                type="button"
                onClick={() => {
                  setStep(4)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              >
                Continue to report
              </button>
            </div>
          </section>
        )}

        {step === 4 && analysis && (
          <section aria-labelledby="report-title">
            <div className="page-heading">
              <div>
                <div className="eyebrow">Weekly sales report</div>
                <h1 id="report-title">
                  Week of{' '}
                  {formatDateRange(
                    analysis.report.week_start,
                    analysis.report.week_end,
                  )}
                </h1>
                <p>
                  Latest complete Monday-through-Sunday period in the uploaded file.
                </p>
              </div>
              <button
                className="button button--quiet"
                type="button"
                onClick={() => setStep(3)}
              >
                View upload receipt
              </button>
            </div>

            <article className="metric-card">
              <span className="metric-card__label">Total sales</span>
              <strong>
                {formatCurrency(analysis.report.sales_total, analysis.report.currency)}
              </strong>
              <span>
                {formatNumber(analysis.report.sales_rows)} valid sales rows
              </span>
              {analysis.report.prior_sales_total === null ? (
                <p>No complete prior week is available for comparison.</p>
              ) : (
                <p>
                  {analysis.report.absolute_change! >= 0 ? 'Increased' : 'Decreased'}{' '}
                  {formatCurrency(
                    Math.abs(analysis.report.absolute_change!),
                    analysis.report.currency,
                  )}{' '}
                  {analysis.report.percentage_change === null
                    ? ''
                    : `(${Math.abs(analysis.report.percentage_change).toFixed(1)}%)`}{' '}
                  from{' '}
                  {formatDateRange(
                    analysis.report.prior_week_start,
                    analysis.report.prior_week_end,
                  )}
                  .
                </p>
              )}
            </article>

            <div className="notice notice--success">
              <strong>The first result is working.</strong>
              <span>
                This total was calculated from the mapped fields and approved cleanup
                choices in a temporary DuckDB analysis table.
              </span>
            </div>

            <div className="actions">
              <button className="button button--secondary" type="button" onClick={reset}>
                Analyze another file
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

type MappingRowProps = {
  id: string
  label: string
  value: string
  columns: string[]
  onChange: (value: string) => void
  required?: boolean
  hint?: string
}

function MappingRow({
  id,
  label,
  value,
  columns,
  onChange,
  required = false,
  hint,
}: MappingRowProps) {
  return (
    <div className="mapping-row">
      <div>
        <label htmlFor={id}>
          {label}
          {required && <span className="required">Required</span>}
        </label>
        {hint && <small>{hint}</small>}
      </div>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Not provided</option>
        {columns.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </select>
      <span className={`mapping-status ${value ? 'is-confirmed' : ''}`}>
        {value ? 'Mapped' : required ? 'Needs attention' : 'Optional'}
      </span>
    </div>
  )
}

function ReceiptItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="receipt-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default App
