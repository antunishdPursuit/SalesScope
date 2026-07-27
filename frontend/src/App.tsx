import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import './index.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type MappingKey =
  | 'date'
  | 'sales'
  | 'quantity'
  | 'unit_price'
  | 'product'
  | 'category'
  | 'store'
  | 'channel'
  | 'region'
  | 'discount'
  | 'cost'
  | 'profit'

type Suggestions = Record<MappingKey, string | null>
type Mappings = Record<MappingKey, string>

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

type Metric = {
  current: number | null
  prior: number | null
  absolute_change: number | null
  percentage_change: number | null
}

type TrendRow = {
  week_start: string
  week_end: string
  sales: number
  profit: number | null
  units: number | null
}

type BreakdownRow = {
  label: string
  current_sales: number
  prior_sales: number
  sales_change: number
  sales_change_pct: number | null
  current_profit: number | null
  margin_pct: number | null
  current_units: number | null
}

type CoverageItem = {
  key: string
  label: string
  status: 'available' | 'limited' | 'unavailable'
  reason: string
}

type Report = {
  currency: string
  week_start: string
  week_end: string
  prior_week_start: string
  prior_week_end: string
  metrics: {
    sales: Metric
    profit: Metric
    margin: Metric
    units: Metric
    sales_rows: Metric
  }
  trend: TrendRow[]
  breakdowns: Record<string, BreakdownRow[]>
  drivers: Record<
    string,
    { increases: BreakdownRow[]; declines: BreakdownRow[] }
  >
  discount_summary: {
    discounted_sales: number
    discounted_sales_share_pct: number | null
    average_discount_pct: number | null
    high_discount_rows: number
  } | null
  risks: Array<{
    key: string
    severity: 'warning' | 'info'
    title: string
    detail: string
  }>
  manager_summary: string[]
  coverage: CoverageItem[]
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
  sales_formula: string
  profit_method: string | null
  profit_formula: string | null
  profit_coverage_pct: number
  quantity_coverage_pct: number
  assumptions: string[]
}

type VerificationFormula = {
  key: string
  label: string
  formula: string
  explanation: string
  current_value: number | null
  prior_value: number | null
}

type Verification = {
  currency: string
  filename: string
  mappings: Record<MappingKey, string | null>
  week_start: string
  week_end: string
  prior_week_start: string
  prior_week_end: string
  row_reconciliation: {
    original_rows: number
    analyzed_rows: number
    duplicate_candidates: number
    excluded_duplicate_rows: number
    excluded_invalid_rows: number
    current_period_rows: number
    prior_period_rows: number
  }
  assumptions: string[]
  formulas: VerificationFormula[]
  spreadsheet_steps: string[]
}

type Analysis = {
  receipt: Receipt
  report: Report
  verification: Verification
}

type View = 'prepare' | 'report' | 'verify'

const emptyMappings: Mappings = {
  date: '',
  sales: '',
  quantity: '',
  unit_price: '',
  product: '',
  category: '',
  store: '',
  channel: '',
  region: '',
  discount: '',
  cost: '',
  profit: '',
}

const coreFields: Array<{
  key: MappingKey
  label: string
  hint?: string
  required?: boolean
}> = [
  { key: 'date', label: 'Transaction date', required: true },
  {
    key: 'sales',
    label: 'Sales amount',
    hint: 'Optional only when quantity and unit price are both mapped.',
  },
  { key: 'quantity', label: 'Quantity' },
  { key: 'unit_price', label: 'Unit price' },
]

const analysisFields: Array<{
  key: MappingKey
  label: string
  hint: string
}> = [
  { key: 'product', label: 'Product', hint: 'Product rankings and change drivers' },
  { key: 'category', label: 'Category', hint: 'Category performance' },
  { key: 'store', label: 'Store or location', hint: 'Location performance' },
  { key: 'channel', label: 'Sales channel', hint: 'Channel mix' },
  { key: 'region', label: 'Region', hint: 'Regional performance' },
  { key: 'discount', label: 'Discount', hint: 'Discount levels and risks' },
  { key: 'cost', label: 'Unit cost', hint: 'Profit when quantity is available' },
  { key: 'profit', label: 'Profit', hint: 'Direct profit and margin reporting' },
]

function formatNumber(value: number, maximumFractionDigits = 0) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits }).format(value)
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
    year: 'numeric',
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
  const [view, setView] = useState<View>('prepare')
  const [file, setFile] = useState<File | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [sheetName, setSheetName] = useState('')
  const [mappings, setMappings] = useState<Mappings>(emptyMappings)
  const [currency, setCurrency] = useState('USD')
  const [excludeDuplicates, setExcludeDuplicates] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const canAnalyze = Boolean(
    mappings.date &&
      (mappings.sales || (mappings.quantity && mappings.unit_price)),
  )

  const mappedAnalysisCount = useMemo(
    () =>
      analysisFields.filter(({ key }) => Boolean(mappings[key])).length,
    [mappings],
  )

  async function readError(response: Response) {
    const body = await response.json().catch(() => null)
    return body?.detail ?? 'SalesScope could not process this file.'
  }

  async function profileFile(selectedFile: File, selectedSheet = '') {
    const form = new FormData()
    form.append('file', selectedFile)
    if (selectedSheet) form.append('sheet_name', selectedSheet)

    const response = await fetch(`${API_URL}/api/profile`, {
      method: 'POST',
      body: form,
    })
    if (!response.ok) throw new Error(await readError(response))

    const nextProfile: Profile = await response.json()
    setProfile(nextProfile)
    setSheetName(nextProfile.selected_sheet ?? '')
    setMappings(
      Object.fromEntries(
        Object.entries(nextProfile.suggestions).map(([key, value]) => [
          key,
          value ?? '',
        ]),
      ) as Mappings,
    )
    setExcludeDuplicates(false)
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return

    setIsLoading(true)
    setError('')
    setAnalysis(null)
    setView('prepare')
    setFile(selectedFile)
    try {
      await profileFile(selectedFile)
    } catch (caughtError) {
      setFile(null)
      setProfile(null)
      setError(getErrorMessage(caughtError))
    } finally {
      setIsLoading(false)
      event.target.value = ''
    }
  }

  async function handleSheetChange(event: ChangeEvent<HTMLSelectElement>) {
    if (!file) return
    const selectedSheet = event.target.value
    setSheetName(selectedSheet)
    setIsLoading(true)
    setError('')
    try {
      await profileFile(file, selectedSheet)
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
    } finally {
      setIsLoading(false)
    }
  }

  function buildAnalysisForm() {
    if (!file) throw new Error('Choose a file before generating a report.')
    const form = new FormData()
    form.append('file', file)
    if (sheetName) form.append('sheet_name', sheetName)
    form.append('currency', currency)
    form.append('exclude_exact_duplicates', String(excludeDuplicates))
    Object.entries(mappings).forEach(([key, value]) => {
      if (value) form.append(`${key}_column`, value)
    })
    return form
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canAnalyze) {
      setError(
        'Map a transaction date and either a sales amount or both quantity and unit price.',
      )
      return
    }

    setIsLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        body: buildAnalysisForm(),
      })
      if (!response.ok) throw new Error(await readError(response))
      const nextAnalysis: Analysis = await response.json()
      setAnalysis(nextAnalysis)
      setView('report')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
    } finally {
      setIsLoading(false)
    }
  }

  function updateMapping(key: MappingKey, value: string) {
    setMappings((current) => ({ ...current, [key]: value }))
  }

  function reset() {
    setView('prepare')
    setFile(null)
    setProfile(null)
    setAnalysis(null)
    setSheetName('')
    setMappings(emptyMappings)
    setCurrency('USD')
    setExcludeDuplicates(false)
    setError('')
    fileInput.current?.focus()
  }

  return (
    <div className="app-shell" id="top">
      <header className="site-header">
        <button className="brand-button" type="button" onClick={reset}>
          SalesScope
        </button>
        <span className="header-note">Transparent weekly sales reporting</span>
      </header>

      {view === 'prepare' && (
        <main className="main-content prepare-page">
          <section className="prepare-intro" aria-labelledby="prepare-title">
            <div className="eyebrow">Prepare weekly report</div>
            <h1 id="prepare-title">Turn a sales file into answers your manager can use.</h1>
            <p className="intro">
              Upload one CSV or Excel sheet. SalesScope will recognize common
              columns, show what the file can support, and explain every cleanup
              choice before creating the report.
            </p>
          </section>

          {error && (
            <div className="notice notice--error" role="alert">
              <strong>We could not continue.</strong>
              <span>{error}</span>
            </div>
          )}

          {!profile ? (
            <section className="upload-card" aria-labelledby="upload-title">
              <div className="requirements">
                <h2 id="upload-title">What your file needs</h2>
                <p>
                  At minimum, include a <strong>transaction date</strong> and a{' '}
                  <strong>sales amount</strong>. Quantity and unit price can be used
                  to calculate sales when no total is provided.
                </p>
                <details>
                  <summary>Fields that unlock a fuller report</summary>
                  <p>
                    Quantity, product, category, store or location, channel,
                    discount, and cost or profit.
                  </p>
                </details>
              </div>

              <div className="upload-zone">
                <label htmlFor="sales-file">Upload sales file</label>
                <p>Choose one CSV or Excel (.xlsx) file, up to 100 MB.</p>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  disabled={isLoading}
                >
                  {isLoading ? 'Reading file…' : 'Choose file'}
                </button>
                <input
                  ref={fileInput}
                  id="sales-file"
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={handleFileChange}
                />
              </div>

              <p className="privacy-note">
                Your original file stays unchanged. This MVP processes uploads
                temporarily and does not save report history.
              </p>
            </section>
          ) : (
            <form onSubmit={handleAnalyze}>
              <section className="file-summary" aria-label="Uploaded file">
                <div>
                  <span className="status-dot" aria-hidden="true" />
                  <div>
                    <strong>{profile.filename}</strong>
                    <span>
                      {formatNumber(profile.row_count)} rows ·{' '}
                      {formatNumber(profile.column_count)} columns
                    </span>
                  </div>
                </div>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => fileInput.current?.click()}
                >
                  Replace file
                </button>
                <input
                  ref={fileInput}
                  className="sr-only"
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={handleFileChange}
                />
              </section>

              {profile.sheet_names.length > 1 && (
                <div className="form-field sheet-field">
                  <label htmlFor="sheet-name">Sales sheet</label>
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

              <section className="workspace-section" aria-labelledby="core-mapping-title">
                <div className="section-heading">
                  <div>
                    <span className="section-number">1</span>
                    <div>
                      <h2 id="core-mapping-title">Confirm the core fields</h2>
                      <p>These fields determine whether a weekly report can be created.</p>
                    </div>
                  </div>
                  <span className={`status-badge ${canAnalyze ? 'is-ready' : 'needs-attention'}`}>
                    {canAnalyze ? 'Ready' : 'Needs attention'}
                  </span>
                </div>

                <div className="mapping-card">
                  {coreFields.map((field) => (
                    <MappingRow
                      key={field.key}
                      field={field}
                      value={mappings[field.key]}
                      columns={profile.columns}
                      onChange={(value) => updateMapping(field.key, value)}
                    />
                  ))}
                </div>
              </section>

              <section className="workspace-section" aria-labelledby="fuller-report-title">
                <div className="section-heading">
                  <div>
                    <span className="section-number">2</span>
                    <div>
                      <h2 id="fuller-report-title">Choose the deeper analysis</h2>
                      <p>
                        SalesScope recognized {mappedAnalysisCount} of 8 optional
                        analysis fields.
                      </p>
                    </div>
                  </div>
                </div>

                <details className="mapping-details">
                  <summary>Review optional report fields</summary>
                  <div className="mapping-card">
                    {analysisFields.map((field) => (
                      <MappingRow
                        key={field.key}
                        field={field}
                        value={mappings[field.key]}
                        columns={profile.columns}
                        onChange={(value) => updateMapping(field.key, value)}
                      />
                    ))}
                  </div>
                </details>
              </section>

              <section className="workspace-section" aria-labelledby="review-choices-title">
                <div className="section-heading">
                  <div>
                    <span className="section-number">3</span>
                    <div>
                      <h2 id="review-choices-title">Review report choices</h2>
                      <p>Confirm how SalesScope should interpret this file.</p>
                    </div>
                  </div>
                </div>

                <div className="choice-grid">
                  <div className="form-field">
                    <label htmlFor="currency">Currency</label>
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
                      row matches. Without a reliable transaction-line ID, they may be
                      separate real sales.
                    </p>
                    <label>
                      <input
                        type="checkbox"
                        checked={excludeDuplicates}
                        onChange={(event) =>
                          setExcludeDuplicates(event.target.checked)
                        }
                        disabled={profile.exact_duplicate_candidates === 0}
                      />
                      Exclude these rows from this report
                    </label>
                  </fieldset>
                </div>
              </section>

              <section
                className={`readiness-card ${canAnalyze ? 'is-ready' : ''}`}
                aria-live="polite"
              >
                <div>
                  <span className="readiness-icon" aria-hidden="true">
                    {canAnalyze ? '✓' : '!'}
                  </span>
                  <div>
                    <h2>
                      {canAnalyze
                        ? 'Ready to generate the weekly report'
                        : 'The report still needs required fields'}
                    </h2>
                    <p>
                      {canAnalyze
                        ? 'SalesScope will validate every row, calculate the latest complete week, and show only the analyses this file supports.'
                        : 'Map a date and either sales amount or both quantity and unit price.'}
                    </p>
                  </div>
                </div>
                <button
                  className="button button--primary button--large"
                  type="submit"
                  disabled={!canAnalyze || isLoading}
                >
                  {isLoading ? 'Analyzing file…' : 'Generate weekly report'}
                </button>
              </section>
            </form>
          )}
        </main>
      )}

      {view === 'report' && analysis && (
        <main className="main-content report-page">
          <div className="page-heading">
            <div>
              <div className="eyebrow">Weekly sales report</div>
              <h1>
                {formatDateRange(
                  analysis.report.week_start,
                  analysis.report.week_end,
                )}
              </h1>
              <p>
                Latest complete Monday-through-Sunday period in{' '}
                {analysis.receipt.filename}.
              </p>
            </div>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setView('prepare')}
            >
              Review data setup
            </button>
          </div>

          <div className="metric-card">
            <span className="metric-card__label">Total sales</span>
            <strong>
              {formatCurrency(
                analysis.report.metrics.sales.current ?? 0,
                analysis.report.currency,
              )}
            </strong>
            <p>
              {formatNumber(analysis.report.metrics.sales_rows.current ?? 0)} sales
              rows were included.
            </p>
          </div>

          <div className="notice notice--info">
            <strong>Detailed report is next.</strong>
            <span>
              The preparation workflow now leads directly to a valid result. The
              report dashboard will be added in the next focused commit.
            </span>
          </div>
        </main>
      )}
    </div>
  )
}

function MappingRow({
  field,
  value,
  columns,
  onChange,
}: {
  field: {
    key: MappingKey
    label: string
    hint?: string
    required?: boolean
  }
  value: string
  columns: string[]
  onChange: (value: string) => void
}) {
  const id = `mapping-${field.key}`
  return (
    <div className="mapping-row">
      <div>
        <label htmlFor={id}>
          {field.label}
          {field.required && <span className="required">Required</span>}
        </label>
        {field.hint && <small>{field.hint}</small>}
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
        {value ? 'Mapped' : field.required ? 'Needs attention' : 'Not available'}
      </span>
    </div>
  )
}

export default App
