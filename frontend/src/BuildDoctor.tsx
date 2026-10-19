import { useEffect, useState } from 'react'

import './BuildDoctor.css'

type Source = {
  path: string
  content: string
}

type Demo = {
  id: string
  name: string
  log: string
  files: Source[]
}

type Check = {
  return_code: number
  output: string
}

type Verification = {
  status: string
  reason?: string
  before?: Check
  after?: Check | null
}

type Report = {
  id: string
  model: string
  provider: string
  patch: string
  patch_error: string | null

  diagnosis: {
    category: string
    summary: string
    evidence: string[]
    recommended_steps: string[]
  }

  verification: Verification
}

async function readResponse(response: Response) {
  const body = await response.json()

  if (!response.ok) {
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail)
    )
  }

  return body
}

export default function BuildDoctor() {
  const [demos, setDemos] = useState<Demo[]>([])
  const [log, setLog] = useState('')
  const [diff, setDiff] = useState('')

  const [files, setFiles] = useState<Source[]>([
    {
      path: 'app.py',
      content: '',
    },
  ])

  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/build/demos', {
      signal: controller.signal,
    })
      .then(readResponse)
      .then(data => setDemos(data.demos))
      .catch(error => {
        if (!controller.signal.aborted) {
          setError(String(error))
        }
      })

    return () => controller.abort()
  }, [])

  function reset() {
    setReport(null)
    setError('')
  }

  function changeFile(
    index: number,
    update: Partial<Source>
  ) {
    reset()

    setFiles(
      files.map((file, currentIndex) =>
        currentIndex === index
          ? { ...file, ...update }
          : file
      )
    )
  }

  async function analyze() {
    reset()
    setBusy('Asking Nemotron to investigate…')

    try {
      const result: Report = await fetch(
        '/api/build/analyze',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            log,
            files,
            diff,
          }),
        }
      ).then(readResponse)

      setReport(result)
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Analysis failed'
      )
    } finally {
      setBusy('')
    }
  }

  async function verify() {
    if (!report) return

    setBusy(
      'Reproducing failure and testing the patch in Docker…'
    )
    setError('')

    try {
      const verification: Verification = await fetch(
        `/api/build/${report.id}/verify`,
        {
          method: 'POST',
        }
      ).then(readResponse)

      setReport({
        ...report,
        verification,
      })
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Verification failed'
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <main className="doctor">
      <header className="doctor-hero">
        <p className="doctor-kicker">
          CAUSALTRACE / BUILD DOCTOR
        </p>

        <h1>
          Failed build.
          <br />
          <span>Follow the evidence.</span>
        </h1>

        <p>
          Investigate Python CI failures, propose a repair,
          and test whether it works.
        </p>

        <div className="doctor-flow">
          01 Collect evidence → 02 Diagnose →
          03 Propose repair → 04 Verify
        </div>
      </header>

      <div className="doctor-layout">
        <section className="doctor-panel">
          <h2>01 / Evidence workspace</h2>

          <fieldset disabled={Boolean(busy)}>
            <label>
              Try a reproducible scenario

              <select
                defaultValue=""
                onChange={event => {
                  const demo = demos.find(
                    item => item.id === event.target.value
                  )

                  if (demo) {
                    reset()
                    setLog(demo.log)
                    setFiles(demo.files)
                    setDiff('')
                  }
                }}
              >
                <option value="" disabled>
                  Choose a scenario
                </option>

                {demos.map(demo => (
                  <option key={demo.id} value={demo.id}>
                    {demo.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Failed workflow log

              <textarea
                rows={7}
                maxLength={40000}
                value={log}
                placeholder="Paste the traceback or failed CI log…"
                onChange={event => {
                  reset()
                  setLog(event.target.value)
                }}
              />
            </label>

            <p className="doctor-note">
              Selected logs and files go to Nebius for
              analysis. Remove credentials and private
              data before submitting.
            </p>

            <h3>Relevant source and tests</h3>

            {files.map((file, index) => (
              <div className="doctor-file" key={index}>
                <label>
                  Relative file path

                  <input
                    value={file.path}
                    onChange={event =>
                      changeFile(index, {
                        path: event.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  File content

                  <textarea
                    rows={6}
                    maxLength={30000}
                    value={file.content}
                    spellCheck={false}
                    onChange={event =>
                      changeFile(index, {
                        content: event.target.value,
                      })
                    }
                  />
                </label>

                {files.length > 1 && (
                  <button
                    type="button"
                    className="doctor-secondary"
                    onClick={() => {
                      reset()

                      setFiles(
                        files.filter(
                          (_, currentIndex) =>
                            currentIndex !== index
                        )
                      )
                    }}
                  >
                    Remove file
                  </button>
                )}
              </div>
            ))}

            <button
              type="button"
              className="doctor-secondary"
              disabled={files.length >= 12}
              onClick={() => {
                reset()

                setFiles([
                  ...files,
                  {
                    path: '',
                    content: '',
                  },
                ])
              }}
            >
              + Add file
            </button>

            <label>
              Recent Git diff (optional)

              <textarea
                rows={3}
                maxLength={20000}
                value={diff}
                onChange={event => {
                  reset()
                  setDiff(event.target.value)
                }}
              />
            </label>

            <button
              type="button"
              className="doctor-primary"
              disabled={
                log.trim().length < 5 ||
                files.some(file => !file.path.trim())
              }
              onClick={() => void analyze()}
            >
              Investigate with Nemotron →
            </button>
          </fieldset>
        </section>

        <section
          className="doctor-panel doctor-results"
          aria-live="polite"
        >
          <h2>02 / Investigation</h2>

          {busy && <p role="status">{busy}</p>}

          {error && (
            <p className="doctor-error" role="alert">
              {error}
            </p>
          )}

          {!report && !busy && (
            <div className="doctor-empty">
              <h3>Evidence before conclusions.</h3>

              <p>
                Load a demo or paste a real failure.
                Nemotron will reason over the log and
                supplied files.
              </p>

              <p>
                Repairs remain proposals until a failing
                baseline becomes a passing test run.
              </p>
            </div>
          )}

          {report && (
            <>
              <span className="doctor-badge">
                {report.diagnosis.category}
              </span>

              <h3>{report.diagnosis.summary}</h3>

              <p className="doctor-note">
                {report.provider} · {report.model} ·
                AI hypothesis
              </p>

              <h3>Supporting evidence</h3>

              <ul>
                {report.diagnosis.evidence.map(
                  (item, index) => (
                    <li key={index}>{item}</li>
                  )
                )}
              </ul>

              <h3>Recommended steps</h3>

              <ol>
                {report.diagnosis.recommended_steps.map(
                  (item, index) => (
                    <li key={index}>{item}</li>
                  )
                )}
              </ol>

              <h3>03 / Proposed patch</h3>

              {report.patch_error && (
                <p className="doctor-error">
                  Patch rejected: {report.patch_error}
                </p>
              )}

              {report.patch ? (
                <pre>{report.patch}</pre>
              ) : (
                <p>
                  No applicable patch. Follow the
                  recommendations or supply more evidence.
                </p>
              )}

              <h3>
                04 / Verification{' '}
                <span className="doctor-badge">
                  {report.verification.status.replaceAll(
                    '_',
                    ' '
                  )}
                </span>
              </h3>

              <p className="doctor-note">
                Runs supplied Python tests in temporary,
                restricted Docker containers. No network
                or dependency installation. Your source
                files stay unchanged.
              </p>

              <button
                type="button"
                className="doctor-primary"
                disabled={Boolean(busy) || !report.patch}
                onClick={() => void verify()}
              >
                Test proposed repair in Docker
              </button>

              {report.verification.reason && (
                <p>{report.verification.reason}</p>
              )}

              {(['before', 'after'] as const).map(stage => {
                const check = report.verification[stage]

                return (
                  check && (
                    <details key={stage} open>
                      <summary>
                        {stage === 'before'
                          ? 'Before patch'
                          : 'After patch'}
                        {' · '}exit {check.return_code}
                      </summary>

                      <pre>{check.output}</pre>
                    </details>
                  )
                )
              })}

              {report.verification.status ===
                'verified' && (
                <p className="doctor-note">
                  Verified for the supplied tests only.
                  Review the patch and run your complete
                  suite before merging.
                </p>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  )
}