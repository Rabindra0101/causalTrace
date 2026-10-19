
import { useEffect, useMemo, useRef, useState } from 'react'
import './RegressionTimeline.css'

type TimelineCommit = {
  hash: string
  short_hash: string
  message: string
  date: string
  test_status: string
  result?: { status: string; return_code: number; output: string; counts?: { test: number; passed: number; failed: number; skipped: number } }
}

type TimelineResponse = {
  repository_id: string
  history_type?: string
  latest_pass?: string | null
  latest_fail?: string | null
  latest_pass_with_skips?: string | null
  latest_error?: string | null
  complete?: boolean
  reason?: string
  commits: TimelineCommit[]
}

type Props = {
  repositoryId: string
  reportId?: string
  suspectedCommit?: string
  verified?: boolean
}

export default function RegressionTimeline({
  repositoryId,
  reportId,
  suspectedCommit,
  verified = false,
}: Props) {
  const [commits, setCommits] = useState<TimelineCommit[]>([])
  const [historyType, setHistoryType] = useState('synthetic')
  const [summary, setSummary] = useState<TimelineResponse | null>(null)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const detail = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadTimeline() {
      setLoading(true)
      setError(null)
      setCommits([])
      setSelected(null)
      setSummary(null)
      setFilter('all')
      setQuery('')

      try {
        const response = await fetch(
          `/api/repositories/${encodeURIComponent(repositoryId)}/timeline${reportId ? '?report_id=' + reportId : ''}`,
          { signal: controller.signal, cache: 'no-store' }
        )

        if (!response.ok) {
          throw new Error(`Unable to load Git history (${response.status})`)
        }

        const data: TimelineResponse = await response.json()

        if (!controller.signal.aborted) {
          setSummary(data)
          setCommits(data.commits)
          setHistoryType(data.history_type ?? 'synthetic')
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error ? err.message : 'Unable to load timeline'
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadTimeline()
    return () => controller.abort()
  }, [repositoryId, reportId])

  const category = (status: string) => ['fail', 'collection_error'].includes(status) ? 'failed' : status === 'pass' ? 'passed' : status === 'pass_with_skips' ? 'incomplete' : status === 'not_tested' ? 'untested' : 'errors'
  const visible = useMemo(() => commits.filter(commit =>
    (filter === 'all' || category(commit.test_status) === filter)
    && (commit.hash + ' ' + commit.message).toLowerCase().includes(query.toLowerCase())), [commits, filter, query])
  const selectedCommit = commits.find(commit => commit.hash === selected)

  return (
    <section className="panel">
      <div className="timeline-heading">
        <div>
          <h2>Git Regression Timeline</h2>
          <p className="subtitle">
            {historyType !== 'synthetic' ? 'Original Git commits and author dates, displayed in your local time zone. ' : 'Synthetic demo history; these commits were created for the demonstration.'}
            Untested commits are not classified as passing or failing.
          </p>
        </div>
        <span className="timeline-count">{commits.length} {commits.length === 1 ? 'commit' : 'commits'}</span>
      </div>

      {summary?.reason && <p role="status">{summary.reason}</p>}
      {summary && ('latest_pass' in summary || 'latest_fail' in summary) && <p><strong>Most recent passing commit:</strong> <code>{summary.latest_pass?.slice(0, 8) ?? 'No fully passing run found'}</code><br /><strong>Most recent failing commit:</strong> <code>{summary.latest_fail?.slice(0, 8) ?? 'Not found in tested history'}</code></p>}
      {summary?.latest_pass_with_skips && <p className="timeline-caution"><strong>Latest passing run with skipped tests:</strong> <code>{summary.latest_pass_with_skips.slice(0,8)}</code>. Executed tests passed; skipped coverage is not verified.</p>}
      {summary?.latest_error && <p className="timeline-caution"><strong>Latest runner error:</strong> <code>{summary.latest_error.slice(0,8)}</code>. Its output is retained below; it is not labeled as a regression.</p>}
      {!loading && !error && commits.length > 0 && <div className="timeline-tools">
        <label className="timeline-search"><span>Find a commit</span><input type="search" value={query} placeholder="Search commit ID or message?" onChange={e => setQuery(e.target.value)} /></label>
        <div className="timeline-filters" role="group" aria-label="Filter commit results">{[['all','All results'],['failed','Failed'],['passed','Passed'],['incomplete','With skips'],['errors','Runner errors']].map(([key,label]) => <button key={key} type="button" aria-pressed={filter===key} onClick={() => {setFilter(key);setSelected(null)}}>{label} <strong>{key==='all' ? commits.length : commits.filter(c => category(c.test_status)===key).length}</strong></button>)}</div>
        <p role="status">Showing {visible.length} of {commits.length} commits. Select a commit to inspect its output.</p>
      </div>}
      {loading && <p role="status">Loading Git history...</p>}
      {error && <p role="alert" className="error">{error}</p>}

      {!loading && !error && commits.length === 0 && (
        <p>No commits available.</p>
      )}

      {!loading && !error && commits.length > 0 && (
        <>
          <div className="timeline-list">
            {visible.map(commit => {
              const suspected = Boolean(
                suspectedCommit &&
                (commit.hash === suspectedCommit ||
                  commit.hash.startsWith(suspectedCommit) ||
                  suspectedCommit.startsWith(commit.hash))
              )

              return (
                <button
                  key={commit.hash}
                  type="button"
                  data-status={commit.test_status}
                  className={`timeline-item ${
                    suspected ? 'timeline-suspected' : ''
                  } ${selected === commit.hash ? 'timeline-selected' : ''}`}
                  onClick={() => { setSelected(commit.hash); requestAnimationFrame(() => detail.current?.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })) }}
                  aria-pressed={selected === commit.hash}
                >
                  <span className="timeline-node" aria-hidden="true" />
                  <span className="timeline-item-content">
                    <span className="timeline-item-top">
                      <code>{commit.short_hash}</code>
                      {commit.hash === summary?.latest_pass && <span className="timeline-badge">LATEST PASS</span>}
                      {commit.hash === summary?.latest_fail && <span className="timeline-badge">LATEST FAIL</span>}
                      {suspected && (
                        <span className="timeline-badge">
                          {verified ? 'VERIFIED REGRESSION' : 'SUSPECTED'}
                        </span>
                      )}
                      {!suspected && (
                        <span className="timeline-untested">{commit.test_status.replaceAll('_', ' ').toUpperCase()}</span>
                      )}
                    </span>
                    {commit.result?.counts && <span className="timeline-test-counts">{commit.result.counts.passed} passed ? {commit.result.counts.failed} failed ? {commit.result.counts.skipped} skipped</span>}
                    <span className="timeline-message">{commit.message}</span>
                    {historyType !== 'synthetic' ? <time dateTime={commit.date}>
                      Author date: {new Date(commit.date).toLocaleString()}
                    </time> : <span>Generated demo commit</span>}
                  </span>
                </button>
              )
            })}
          </div>

          {selectedCommit && (
            <div className="timeline-detail" ref={detail} tabIndex={-1}>
              <h3>Commit evidence</h3>
              <p><strong>Commit:</strong> <code>{selectedCommit.hash}</code></p>
              <p><strong>Message:</strong> {selectedCommit.message}</p>
              <p>
                <strong>Historical test status:</strong> {selectedCommit.test_status.replaceAll('_', ' ')}
              </p>
              {selectedCommit.result && <details open><summary>Test output ? exit {selectedCommit.result.return_code}</summary><pre className="run-output">{selectedCommit.result.output}</pre></details>}
              {suspectedCommit &&
                (selectedCommit.hash === suspectedCommit ||
                  selectedCommit.hash.startsWith(suspectedCommit) ||
                  suspectedCommit.startsWith(selectedCommit.hash)) && (
                  <p>
                    <strong>Reversal evidence:</strong>{' '}
                    {verified
                      ? 'Reversing this commit restored passing tests.'
                      : 'The investigation identified this commit, but verification is not confirmed.'}
                  </p>
                )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
