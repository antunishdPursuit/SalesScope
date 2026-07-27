import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import './index.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const configuredMaxUploadMb = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 100)
const MAX_UPLOAD_MB =
  Number.isFinite(configuredMaxUploadMb) && configuredMaxUploadMb > 0
    ? configuredMaxUploadMb
    : 100
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

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

function formatCompactCurrency(value: number, currency: string) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function formatPercent(value: number) {
  return `${formatNumber(value, 1)}%`
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
  if (
    error instanceof Error &&
    /networkerror|failed to fetch|load failed/i.test(error.message)
  ) {
    return (
      'The analysis service became unavailable while processing this file. ' +
      'Try the representative demo file or a smaller upload.'
    )
  }
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
  const [activeDimension, setActiveDimension] = useState('category')
  const [copyStatus, setCopyStatus] = useState('')
  const [isDownloading, setIsDownloading] = useState(false)
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

    if (selectedFile.size > MAX_UPLOAD_BYTES) {
      setFile(null)
      setProfile(null)
      setAnalysis(null)
      setError(`Choose a file smaller than ${MAX_UPLOAD_MB} MB.`)
      event.target.value = ''
      return
    }

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
      setActiveDimension(
        ['category', 'store', 'product', 'channel', 'region'].find(
          (dimension) => nextAnalysis.report.breakdowns[dimension]?.length,
        ) ?? '',
      )
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
    setActiveDimension('category')
    setCopyStatus('')
    setIsDownloading(false)
    setError('')
    fileInput.current?.focus()
  }

  async function copyManagerSummary() {
    if (!analysis) return
    try {
      await navigator.clipboard.writeText(
        analysis.report.manager_summary.join(' '),
      )
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Copy failed')
    }
  }

  async function downloadVerificationCsv() {
    if (!analysis) return
    setIsDownloading(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/verification.csv`, {
        method: 'POST',
        body: buildAnalysisForm(),
      })
      if (!response.ok) throw new Error(await readError(response))
      const blob = await response.blob()
      const downloadUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = downloadUrl
      anchor.download = 'salescope-verification.csv'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(downloadUrl)
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
    } finally {
      setIsDownloading(false)
    }
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
                <p>
                  Choose one CSV or Excel (.xlsx) file, up to {MAX_UPLOAD_MB} MB.
                </p>
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
                temporarily and does not save report history. On the public
                demo, use sample or non-sensitive data only.
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
          <div className="report-heading">
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
            <div className="report-heading__actions">
              <button
                className="button button--primary"
                type="button"
                onClick={() => {
                  setView('verify')
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              >
                Verify calculations
              </button>
              <button
                className="button button--secondary"
                type="button"
                onClick={() => setView('prepare')}
              >
                Review data setup
              </button>
              <button className="button button--secondary" type="button" onClick={reset}>
                Analyze another file
              </button>
            </div>
          </div>

          <section className="kpi-grid" aria-label="Weekly performance summary">
            <KpiCard
              label="Total sales"
              metric={analysis.report.metrics.sales}
              format={(value) => formatCurrency(value, analysis.report.currency)}
            />
            {analysis.report.metrics.profit.current !== null && (
              <KpiCard
                label="Profit"
                metric={analysis.report.metrics.profit}
                format={(value) => formatCurrency(value, analysis.report.currency)}
              />
            )}
            {analysis.report.metrics.margin.current !== null && (
              <KpiCard
                label="Profit margin"
                metric={analysis.report.metrics.margin}
                format={formatPercent}
                changeAsPoints
              />
            )}
            {analysis.report.metrics.units.current !== null && (
              <KpiCard
                label="Units sold"
                metric={analysis.report.metrics.units}
                format={(value) => formatNumber(value)}
              />
            )}
          </section>

          <section className="summary-card" aria-labelledby="manager-summary-title">
            <div className="section-title-row">
              <div>
                <div className="eyebrow">Manager-ready summary</div>
                <h2 id="manager-summary-title">What changed this week</h2>
              </div>
              <button
                className="button button--secondary"
                type="button"
                onClick={copyManagerSummary}
              >
                {copyStatus || 'Copy summary'}
              </button>
            </div>
            <div className="summary-text">
              {analysis.report.manager_summary.map((sentence) => (
                <p key={sentence}>{sentence}</p>
              ))}
            </div>
          </section>

          {analysis.report.trend.length > 1 && (
            <section className="report-section" aria-labelledby="trend-title">
              <div className="section-title-row">
                <div>
                  <div className="eyebrow">Movement</div>
                  <h2 id="trend-title">Eight-week sales trend</h2>
                  <p>Complete Monday-through-Sunday reporting periods.</p>
                </div>
              </div>
              <TrendChart
                rows={analysis.report.trend}
                currency={analysis.report.currency}
              />
            </section>
          )}

          {Object.keys(analysis.report.breakdowns).length > 0 && activeDimension && (
            <section className="report-section" aria-labelledby="drivers-title">
              <div className="section-title-row">
                <div>
                  <div className="eyebrow">Performance drivers</div>
                  <h2 id="drivers-title">What moved sales</h2>
                  <p>
                    Compare the current report week with the preceding complete week.
                  </p>
                </div>
              </div>

              <div className="dimension-tabs" role="tablist" aria-label="Sales breakdown">
                {Object.keys(analysis.report.breakdowns).map((dimension) => (
                  <button
                    key={dimension}
                    className={activeDimension === dimension ? 'is-active' : ''}
                    type="button"
                    role="tab"
                    aria-selected={activeDimension === dimension}
                    onClick={() => setActiveDimension(dimension)}
                  >
                    {dimensionLabel(dimension)}
                  </button>
                ))}
              </div>

              <div className="driver-grid">
                <DriverList
                  title="Largest increases"
                  rows={
                    analysis.report.drivers[activeDimension]?.increases ?? []
                  }
                  currency={analysis.report.currency}
                  emptyText="No increases were found for this breakdown."
                />
                <DriverList
                  title="Largest declines"
                  rows={analysis.report.drivers[activeDimension]?.declines ?? []}
                  currency={analysis.report.currency}
                  emptyText="No declines were found for this breakdown."
                  decline
                />
              </div>

              <BreakdownTable
                dimension={activeDimension}
                rows={analysis.report.breakdowns[activeDimension] ?? []}
                currency={analysis.report.currency}
              />
            </section>
          )}

          {(analysis.report.discount_summary || analysis.report.risks.length > 0) && (
            <section className="report-section" aria-labelledby="risk-title">
              <div className="section-title-row">
                <div>
                  <div className="eyebrow">Margin and discount review</div>
                  <h2 id="risk-title">Items that need attention</h2>
                  <p>
                    Transparent checks based on the mapped discount and profit fields.
                  </p>
                </div>
              </div>

              {analysis.report.discount_summary && (
                <div className="supporting-metrics">
                  <div>
                    <span>Discounted sales share</span>
                    <strong>
                      {analysis.report.discount_summary.discounted_sales_share_pct ===
                      null
                        ? 'Unavailable'
                        : formatPercent(
                            analysis.report.discount_summary
                              .discounted_sales_share_pct,
                          )}
                    </strong>
                  </div>
                  <div>
                    <span>Average discount</span>
                    <strong>
                      {analysis.report.discount_summary.average_discount_pct === null
                        ? 'Unavailable'
                        : formatPercent(
                            analysis.report.discount_summary.average_discount_pct,
                          )}
                    </strong>
                  </div>
                  <div>
                    <span>High-discount rows</span>
                    <strong>
                      {formatNumber(
                        analysis.report.discount_summary.high_discount_rows,
                      )}
                    </strong>
                  </div>
                </div>
              )}

              {analysis.report.risks.length > 0 ? (
                <div className="risk-list">
                  {analysis.report.risks.map((risk) => (
                    <article className={`risk-item risk-item--${risk.severity}`} key={risk.key}>
                      <h3>{risk.title}</h3>
                      <p>{risk.detail}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="empty-message">
                  No negative-profit or high-discount warnings were found.
                </p>
              )}
            </section>
          )}

          <section className="report-section" aria-labelledby="coverage-title">
            <div className="section-title-row">
              <div>
                <div className="eyebrow">Analysis coverage</div>
                <h2 id="coverage-title">What this file could answer</h2>
              </div>
            </div>
            <div className="coverage-list">
              {analysis.report.coverage.map((item) => (
                <div className="coverage-item" key={item.key}>
                  <span className={`coverage-status coverage-status--${item.status}`}>
                    {item.status}
                  </span>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <details className="quality-details">
            <summary>Data quality and report assumptions</summary>
            <div className="quality-grid">
              <dl>
                <div>
                  <dt>Original rows</dt>
                  <dd>{formatNumber(analysis.receipt.original_rows)}</dd>
                </div>
                <div>
                  <dt>Rows analyzed</dt>
                  <dd>{formatNumber(analysis.receipt.analyzed_rows)}</dd>
                </div>
                <div>
                  <dt>Possible duplicates</dt>
                  <dd>{formatNumber(analysis.receipt.duplicate_candidates)}</dd>
                </div>
                <div>
                  <dt>Invalid rows excluded</dt>
                  <dd>{formatNumber(analysis.receipt.excluded_invalid_rows)}</dd>
                </div>
              </dl>
              <ul>
                {analysis.receipt.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </div>
          </details>
        </main>
      )}

      {view === 'verify' && analysis && (
        <main className="main-content verification-page">
          <div className="report-heading">
            <div>
              <div className="eyebrow">Calculation transparency</div>
              <h1>Verify this report yourself.</h1>
              <p>
                Recreate the headline results in Excel or Google Sheets using your
                original file.
              </p>
            </div>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setView('report')}
            >
              Back to weekly report
            </button>
          </div>

          {error && (
            <div className="notice notice--error" role="alert">
              <strong>We could not create the verification download.</strong>
              <span>{error}</span>
            </div>
          )}

          <section className="verification-intro" aria-labelledby="verification-source-title">
            <div>
              <div className="eyebrow">What SalesScope used</div>
              <h2 id="verification-source-title">Report inputs and choices</h2>
              <p>
                These are the exact fields, periods, and cleanup choices behind the
                report.
              </p>
            </div>
            <dl className="verification-facts">
              <div>
                <dt>File</dt>
                <dd>{analysis.receipt.filename}</dd>
              </div>
              <div>
                <dt>Report period</dt>
                <dd>
                  {formatDateRange(
                    analysis.verification.week_start,
                    analysis.verification.week_end,
                  )}
                </dd>
              </div>
              <div>
                <dt>Comparison period</dt>
                <dd>
                  {formatDateRange(
                    analysis.verification.prior_week_start,
                    analysis.verification.prior_week_end,
                  )}
                </dd>
              </div>
              <div>
                <dt>Date column</dt>
                <dd><code>{analysis.verification.mappings.date}</code></dd>
              </div>
              <div>
                <dt>Sales calculation</dt>
                <dd><code>{analysis.receipt.sales_formula}</code></dd>
              </div>
              <div>
                <dt>Duplicate choice</dt>
                <dd>
                  {analysis.receipt.excluded_duplicate_rows
                    ? `${formatNumber(analysis.receipt.excluded_duplicate_rows)} excluded`
                    : `${formatNumber(analysis.receipt.duplicate_candidates)} kept`}
                </dd>
              </div>
            </dl>
          </section>

          <section className="report-section" aria-labelledby="reconciliation-title">
            <div className="section-title-row">
              <div>
                <div className="eyebrow">Row reconciliation</div>
                <h2 id="reconciliation-title">From source file to report</h2>
                <p>Use these counts to confirm which records reached the calculation.</p>
              </div>
            </div>
            <div className="reconciliation-grid">
              <ReconciliationItem
                label="Original file"
                value={analysis.verification.row_reconciliation.original_rows}
              />
              <ReconciliationItem
                label="Rows analyzed"
                value={analysis.verification.row_reconciliation.analyzed_rows}
              />
              <ReconciliationItem
                label="Current report week"
                value={analysis.verification.row_reconciliation.current_period_rows}
              />
              <ReconciliationItem
                label="Prior report week"
                value={analysis.verification.row_reconciliation.prior_period_rows}
              />
              <ReconciliationItem
                label="Possible duplicates"
                value={analysis.verification.row_reconciliation.duplicate_candidates}
              />
              <ReconciliationItem
                label="Invalid rows excluded"
                value={analysis.verification.row_reconciliation.excluded_invalid_rows}
              />
            </div>
          </section>

          <section className="report-section" aria-labelledby="formula-title">
            <div className="section-title-row">
              <div>
                <div className="eyebrow">Metric definitions</div>
                <h2 id="formula-title">How each number was calculated</h2>
              </div>
            </div>
            <div className="formula-list">
              {analysis.verification.formulas.map((formula) => (
                <article className="formula-card" key={formula.key}>
                  <div>
                    <h3>{formula.label}</h3>
                    <code>{formula.formula}</code>
                    <p>{formula.explanation}</p>
                  </div>
                  <dl>
                    <div>
                      <dt>Current result</dt>
                      <dd>
                        {formatVerificationValue(
                          formula,
                          formula.current_value,
                          analysis.report.currency,
                        )}
                      </dd>
                    </div>
                    {formula.prior_value !== null && (
                      <div>
                        <dt>Prior result</dt>
                        <dd>
                          {formatVerificationValue(
                            formula,
                            formula.prior_value,
                            analysis.report.currency,
                          )}
                        </dd>
                      </div>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          </section>

          <section className="report-section" aria-labelledby="spreadsheet-title">
            <div className="section-title-row">
              <div>
                <div className="eyebrow">Independent check</div>
                <h2 id="spreadsheet-title">Recreate it in your spreadsheet</h2>
                <p>
                  Follow these steps in the original CSV opened in Excel or Google
                  Sheets.
                </p>
              </div>
            </div>
            <ol className="verification-steps">
              {analysis.verification.spreadsheet_steps.map((step, index) => (
                <li key={step}>
                  <span>{index + 1}</span>
                  <p>{step}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="verification-download" aria-labelledby="download-title">
            <div>
              <div className="eyebrow">Download evidence</div>
              <h2 id="download-title">Inspect the rows behind both weeks</h2>
              <p>
                The verification CSV includes source-row numbers, mapped values,
                derived sales and profit, report period, and inclusion status. It
                contains only the current and prior report periods.
              </p>
            </div>
            <button
              className="button button--primary button--large"
              type="button"
              onClick={downloadVerificationCsv}
              disabled={isDownloading}
            >
              {isDownloading ? 'Preparing CSV…' : 'Download verification CSV'}
            </button>
          </section>

          <div className="verification-note">
            <strong>This is a reproducibility guide, not an audit certification.</strong>
            <span>
              SalesScope does not modify your original file or hide unsupported
              analyses. Differences should be investigated using the mappings,
              filters, and source-row numbers shown here.
            </span>
          </div>
        </main>
      )}
    </div>
  )
}

function dimensionLabel(dimension: string) {
  const labels: Record<string, string> = {
    category: 'Category',
    store: 'Store',
    product: 'Product',
    channel: 'Channel',
    region: 'Region',
  }
  return labels[dimension] ?? dimension
}

function formatVerificationValue(
  formula: VerificationFormula,
  value: number | null,
  currency: string,
) {
  if (value === null) return 'Not available'
  if (formula.key === 'margin' || formula.key === 'sales_change_pct') {
    return formatPercent(value)
  }
  return formatCurrency(value, currency)
}

function ReconciliationItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="reconciliation-item">
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
      <small>rows</small>
    </div>
  )
}

function KpiCard({
  label,
  metric,
  format,
  changeAsPoints = false,
}: {
  label: string
  metric: Metric
  format: (value: number) => string
  changeAsPoints?: boolean
}) {
  const change = changeAsPoints
    ? metric.absolute_change
    : metric.percentage_change
  return (
    <article className="kpi-card">
      <span>{label}</span>
      <strong>{format(metric.current ?? 0)}</strong>
      {change === null ? (
        <small>No complete prior-week comparison</small>
      ) : (
        <small className={change >= 0 ? 'is-positive' : 'is-negative'}>
          {change >= 0 ? '↑' : '↓'} {formatNumber(Math.abs(change), 1)}
          {changeAsPoints ? ' pts' : '%'} from prior week
        </small>
      )}
    </article>
  )
}

function TrendChart({ rows, currency }: { rows: TrendRow[]; currency: string }) {
  const width = 760
  const height = 240
  const left = 54
  const right = 20
  const top = 22
  const bottom = 44
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom
  const values = rows.flatMap((row) =>
    row.profit === null ? [row.sales] : [row.sales, row.profit],
  )
  const maximum = Math.max(...values, 1)
  const point = (value: number, index: number) => {
    const x =
      left + (rows.length === 1 ? 0 : (index / (rows.length - 1)) * chartWidth)
    const y = top + chartHeight - (value / maximum) * chartHeight
    return { x, y }
  }
  const salesPath = rows
    .map((row, index) => {
      const { x, y } = point(row.sales, index)
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
  const profitRows = rows.filter((row) => row.profit !== null)
  const profitPath =
    profitRows.length === rows.length
      ? rows
          .map((row, index) => {
            const { x, y } = point(row.profit ?? 0, index)
            return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
          })
          .join(' ')
      : ''

  return (
    <div className="trend-chart">
      <div className="chart-legend" aria-hidden="true">
        <span><i className="sales-line" />Sales</span>
        {profitPath && <span><i className="profit-line" />Profit</span>}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Weekly sales trend from ${formatDateRange(
          rows[0].week_start,
          rows[rows.length - 1].week_end,
        )}`}
      >
        {[0, 0.5, 1].map((ratio) => {
          const y = top + chartHeight - ratio * chartHeight
          return (
            <g key={ratio}>
              <line className="chart-gridline" x1={left} x2={width - right} y1={y} y2={y} />
              <text className="chart-axis-label" x={left - 8} y={y + 4} textAnchor="end">
                {formatCompactCurrency(maximum * ratio, currency)}
              </text>
            </g>
          )
        })}
        <path className="chart-line chart-line--sales" d={salesPath} />
        {profitPath && <path className="chart-line chart-line--profit" d={profitPath} />}
        {rows.map((row, index) => {
          const salesPoint = point(row.sales, index)
          return (
            <g key={row.week_start}>
              <circle className="chart-point chart-point--sales" cx={salesPoint.x} cy={salesPoint.y} r="4">
                <title>{`${formatDateRange(row.week_start, row.week_end)}: ${formatCurrency(row.sales, currency)} sales`}</title>
              </circle>
              {row.profit !== null && (
                <circle
                  className="chart-point chart-point--profit"
                  cx={point(row.profit, index).x}
                  cy={point(row.profit, index).y}
                  r="4"
                >
                  <title>{`${formatDateRange(row.week_start, row.week_end)}: ${formatCurrency(row.profit, currency)} profit`}</title>
                </circle>
              )}
              {(index === 0 || index === rows.length - 1) && (
                <text
                  className="chart-axis-label"
                  x={salesPoint.x}
                  y={height - 14}
                  textAnchor={index === 0 ? 'start' : 'end'}
                >
                  {new Intl.DateTimeFormat('en-US', {
                    month: 'short',
                    day: 'numeric',
                    timeZone: 'UTC',
                  }).format(new Date(`${row.week_start}T00:00:00Z`))}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function DriverList({
  title,
  rows,
  currency,
  emptyText,
  decline = false,
}: {
  title: string
  rows: BreakdownRow[]
  currency: string
  emptyText: string
  decline?: boolean
}) {
  return (
    <article className="driver-card">
      <h3>{title}</h3>
      {rows.length ? (
        <ol>
          {rows.slice(0, 5).map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <strong className={decline ? 'is-negative' : 'is-positive'}>
                {decline ? '−' : '+'}
                {formatCurrency(Math.abs(row.sales_change), currency)}
              </strong>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-message">{emptyText}</p>
      )}
    </article>
  )
}

function BreakdownTable({
  dimension,
  rows,
  currency,
}: {
  dimension: string
  rows: BreakdownRow[]
  currency: string
}) {
  const maximumSales = Math.max(...rows.map((row) => row.current_sales), 1)
  const hasProfit = rows.some((row) => row.current_profit !== null)
  return (
    <div className="table-wrap">
      <table>
        <caption>Top {dimensionLabel(dimension).toLowerCase()} results by current sales</caption>
        <thead>
          <tr>
            <th scope="col">{dimensionLabel(dimension)}</th>
            <th scope="col">Current sales</th>
            <th scope="col">Prior sales</th>
            <th scope="col">Change</th>
            {hasProfit && <th scope="col">Profit</th>}
            {hasProfit && <th scope="col">Margin</th>}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 10).map((row) => (
            <tr key={row.label}>
              <th scope="row">
                <span>{row.label}</span>
                <i
                  className="value-bar"
                  style={{ width: `${(row.current_sales / maximumSales) * 100}%` }}
                  aria-hidden="true"
                />
              </th>
              <td>{formatCurrency(row.current_sales, currency)}</td>
              <td>{formatCurrency(row.prior_sales, currency)}</td>
              <td className={row.sales_change >= 0 ? 'is-positive' : 'is-negative'}>
                {row.sales_change >= 0 ? '+' : '−'}
                {formatCurrency(Math.abs(row.sales_change), currency)}
              </td>
              {hasProfit && (
                <td>
                  {row.current_profit === null
                    ? '—'
                    : formatCurrency(row.current_profit, currency)}
                </td>
              )}
              {hasProfit && (
                <td>{row.margin_pct === null ? '—' : formatPercent(row.margin_pct)}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
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
