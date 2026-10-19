
import { useEffect, useState } from 'react'
import './RegressionTimeline.css'

type TimelineCommit = {
  hash: string
  short_hash: string
  message: string
  date: string
  test_status: string
}

type TimelineResponse = {
  repository_id: string
  history_type?: string
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

  const selectedCommit = commits.find(commit => commit.hash === selected)

  return (
    <section className="panel">
      <div className="timeline-heading">
        <div>
          <h2>Git Regression Timeline</h2>
          <p className="subtitle">
            {historyType === 'upstream' ? 'Original upstream commits and author dates, displayed in your local time zone.' : 'Synthetic demo history; these commits were created for the demonstration.'}
            Untested commits are not classified as passing or failing.
          </p>
        </div>
        <span className="timeline-count">{commits.length} commits</span>
      </div>

      {loading && <p role="status">Loading Git history...</p>}
      {error && <p role="alert" className="error">{error}</p>}

      {!loading && !error && commits.length === 0 && (
        <p>No commits available.</p>
      )}

      {!loading && !error && commits.length > 0 && (
        <>
          <div className="timeline-list">
            {commits.map(commit => {
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
                  className={`timeline-item ${
                    suspected ? 'timeline-suspected' : ''
                  } ${selected === commit.hash ? 'timeline-selected' : ''}`}
                  onClick={() => setSelected(commit.hash)}
                  aria-pressed={selected === commit.hash}
                >
                  <span className="timeline-node" aria-hidden="true" />
                  <span className="timeline-item-content">
                    <span className="timeline-item-top">
                      <code>{commit.short_hash}</code>
                      {suspected && (
                        <span className="timeline-badge">
                          {verified ? 'VERIFIED REGRESSION' : 'SUSPECTED'}
                        </span>
                      )}
                      {!suspected && (
                        <span className="timeline-untested">{commit.test_status.replaceAll('_', ' ').toUpperCase()}</span>
                      )}
                    </span>
                    <span className="timeline-message">{commit.message}</span>
                    {historyType === 'upstream' ? <time dateTime={commit.date}>
                      Author date: {new Date(commit.date).toLocaleString()}
                    </time> : <span>Generated demo commit</span>}
                  </span>
                </button>
              )
            })}
          </div>

          {selectedCommit && (
            <div className="timeline-detail">
              <h3>Selected Commit</h3>
              <p><strong>Commit:</strong> <code>{selectedCommit.hash}</code></p>
              <p><strong>Message:</strong> {selectedCommit.message}</p>
              <p>
                <strong>Historical test status:</strong> {selectedCommit.test_status.replaceAll('_', ' ')}
              </p>
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
