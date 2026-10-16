
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useEffect, useRef, useState } from 'react'
import './App.css'
import EvidenceGraph from './EvidenceGraph'

type EvidenceNode = {
  id: string
  type: string
  data: Record<string, unknown>
}

type EvidenceEdge = {
  source: string
  target: string
  relationship: string
}

type EvidenceGraphData = {
  created_at: string
  nodes: EvidenceNode[]
  edges: EvidenceEdge[]
}

type Repository = {
  id: string
  name: string
}

type ReversalOutcome =
  | 'verified'
  | 'not_supported'
  | 'inconclusive'

type ReversalExperiment = {
  commit?: string
  verified: boolean
  outcome?: ReversalOutcome
  reason?: string
  before_return_code: number | null
  after_return_code: number | null
}

type InvestigationReport = {
  experiments: {
    commit_reversal: ReversalExperiment
    alternative_reversal?: ReversalExperiment
  }
}

function testStatus(returnCode: number | null | undefined) {
  if (returnCode === 0) return 'PASS'
  if (returnCode === 1) return 'FAIL'
  return 'UNKNOWN'
}

function getOutcome(
  experiment: ReversalExperiment
): ReversalOutcome {
  if (
    experiment.outcome === 'verified' ||
    experiment.outcome === 'not_supported' ||
    experiment.outcome === 'inconclusive'
  ) {
    return experiment.outcome
  }

  // Compatibility with reports created before the
  // backend introduced structured outcomes.
  if (
    experiment.verified &&
    experiment.before_return_code === 1 &&
    experiment.after_return_code === 0
  ) {
    return 'verified'
  }

  if (
    experiment.before_return_code === 1 &&
    experiment.after_return_code === 1
  ) {
    return 'not_supported'
  }

  return 'inconclusive'
}

function outcomeLabel(outcome: ReversalOutcome) {
  switch (outcome) {
    case 'verified':
      return 'VERIFIED'
    case 'not_supported':
      return 'NOT SUPPORTED'
    default:
      return 'INCONCLUSIVE'
  }
}

function outcomeExplanation(
  experiment: ReversalExperiment
) {
  if (experiment.reason) {
    return experiment.reason
  }

  switch (getOutcome(experiment)) {
    case 'verified':
      return 'Reverting this commit restored passing tests, supporting the causal hypothesis.'
    case 'not_supported':
      return 'Tests still failed after reversal. Undoing this commit did not resolve the observed failure.'
    default:
      return 'The reversal experiment could not establish a reliable conclusion.'
  }
}

function ExperimentCard({
  title,
  description,
  experiment,
}: {
  title: string
  description: string
  experiment: ReversalExperiment
}) {
  const before = testStatus(experiment.before_return_code)
  const after = testStatus(experiment.after_return_code)
  const outcome = getOutcome(experiment)

  return (
    <article className="experiment-card">
      <div className="experiment-card-header">
        <div>
          <h3>{title}</h3>

          <p className="experiment-description">
            {description}
          </p>
        </div>

        <span
          className={`experiment-badge ${
            outcome === 'verified'
              ? 'experiment-badge-success'
              : 'experiment-badge-neutral'
          }`}
        >
          {outcomeLabel(outcome)}
        </span>
      </div>

      <div className="experiment-commit">
        <span>Commit</span>

        <code title={experiment.commit ?? 'Unknown'}>
          {experiment.commit?.slice(0, 7) ?? 'Unknown'}
        </code>
      </div>

      <div className="experiment-transition">
        <div className="experiment-test">
          <span>Before reversal</span>

          <strong
            className={
              before === 'PASS'
                ? 'experiment-pass'
                : before === 'FAIL'
                  ? 'experiment-fail'
                  : ''
            }
          >
            {before}
          </strong>
        </div>

        <span
          className="experiment-arrow"
          aria-hidden="true"
        >
          →
        </span>

        <div className="experiment-test">
          <span>After reversal</span>

          <strong
            className={
              after === 'PASS'
                ? 'experiment-pass'
                : after === 'FAIL'
                  ? 'experiment-fail'
                  : ''
            }
          >
            {after}
          </strong>
        </div>
      </div>

      <p className="experiment-conclusion">
        {outcomeExplanation(experiment)}
      </p>
    </article>
  )
}

function App() {
  const [graph, setGraph] =
    useState<EvidenceGraphData | null>(null)

  const [report, setReport] =
    useState<InvestigationReport | null>(null)

  const [error, setError] =
    useState<string | null>(null)

  const [running, setRunning] = useState(false)

  const [success, setSuccess] =
    useState<string | null>(null)

  const [repositories, setRepositories] =
    useState<Repository[]>([])

  const [selectedRepository, setSelectedRepository] =
    useState('')

  const [repositoriesLoading, setRepositoriesLoading] =
    useState(true)

  // Prevent outdated requests from displaying results
  // after the selected repository changes.
  const selectionVersion = useRef(0)

  // Load repository options only.
  // Do not automatically load previous investigations.
  useEffect(() => {
    const controller = new AbortController()

    async function loadRepositories() {
      try {
        const response = await fetch('/api/repositories', {
          cache: 'no-store',
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(
            `Unable to load repositories (${response.status})`
          )
        }

        const data: { repositories: Repository[] } =
          await response.json()

        if (!controller.signal.aborted) {
          setRepositories(data.repositories)
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load repositories'
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setRepositoriesLoading(false)
        }
      }
    }

    void loadRepositories()

    return () => controller.abort()
  }, [])

  function handleRepositoryChange(repositoryId: string) {
    if (running) return

    selectionVersion.current += 1

    setSelectedRepository(repositoryId)
    setGraph(null)
    setReport(null)
    setError(null)
    setSuccess(null)
  }

  async function runInvestigation() {
    if (
      running ||
      repositoriesLoading ||
      !selectedRepository
    ) {
      return
    }

    const repositoryId = selectedRepository
    const currentVersion = selectionVersion.current

    setRunning(true)
    setGraph(null)
    setReport(null)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        '/api/run-investigation',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            repository_id: repositoryId,
          }),
        }
      )

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => null)

        throw new Error(
          typeof errorData?.detail === 'string'
            ? errorData.detail
            : errorData?.detail?.message ??
              `Investigation failed (${response.status})`
        )
      }

      // Fetch both outputs after the investigation finishes.
      const [graphResponse, reportResponse] =
        await Promise.all([
          fetch('/api/graph', {
            cache: 'no-store',
          }),
          fetch('/api/investigation', {
            cache: 'no-store',
          }),
        ])

      if (!graphResponse.ok) {
        throw new Error(
          'Investigation completed, but the Evidence Graph could not be loaded.'
        )
      }

      if (!reportResponse.ok) {
        throw new Error(
          'Investigation completed, but the experiment report could not be loaded.'
        )
      }

      const updatedGraph: EvidenceGraphData =
        await graphResponse.json()

      const updatedReport: InvestigationReport =
        await reportResponse.json()

      if (!updatedReport.experiments?.commit_reversal) {
        throw new Error(
          'The investigation report is missing the reversal experiment.'
        )
      }

      if (selectionVersion.current !== currentVersion) {
        return
      }

      setGraph(updatedGraph)
      setReport(updatedReport)

      const repositoryName =
        repositories.find(
          repository => repository.id === repositoryId
        )?.name ?? repositoryId

      setSuccess(
        `${repositoryName} investigation completed. Evidence Graph and reversal experiments updated.`
      )
    } catch (err) {
      if (selectionVersion.current === currentVersion) {
        setGraph(null)
        setReport(null)

        setError(
          err instanceof Error
            ? err.message
            : 'Investigation failed'
        )
      }
    } finally {
      setRunning(false)
    }
  }

  const failure = graph?.nodes.find(
    node => node.type === 'test_failure'
  )

  const commit = graph?.nodes.find(
    node => node.type === 'git_commit'
  )

  const hypothesis = graph?.nodes.find(
    node => node.type === 'ai_hypothesis'
  )

  const experiment = graph?.nodes.find(
    node => node.type === 'experiment'
  )

  const primaryReversal =
    report?.experiments.commit_reversal

  const alternativeReversal =
    report?.experiments.alternative_reversal

  const primaryOutcome: ReversalOutcome =
    primaryReversal
      ? getOutcome(primaryReversal)
      : experiment?.data.verified === true
        ? 'verified'
        : 'inconclusive'

  return (
    <main className="dashboard">
      <header className="header">
        <div>
          <p className="eyebrow">
            AI-POWERED REGRESSION INVESTIGATION
          </p>

          <h1>CausalTrace</h1>

          <p className="subtitle">
            Don't guess why software failed.
            Investigate the evidence.
          </p>
        </div>

        <div className="header-actions">
          <label className="repository-selector">
            <span>Repository</span>

            <select
              value={selectedRepository}
              onChange={event =>
                handleRepositoryChange(event.target.value)
              }
              disabled={running || repositoriesLoading}
            >
              <option value="">
                {repositoriesLoading
                  ? 'Loading repositories...'
                  : 'Select a repository'}
              </option>

              {repositories.map(repository => (
                <option
                  key={repository.id}
                  value={repository.id}
                >
                  {repository.name}
                </option>
              ))}
            </select>
          </label>

          <span className="status">
            Investigation Dashboard
          </span>

          <button
            type="button"
            className="run-button"
            onClick={() => void runInvestigation()}
            disabled={
              running ||
              repositoriesLoading ||
              !selectedRepository
            }
          >
            {running
              ? 'Investigating...'
              : 'Run Investigation'}
          </button>
        </div>
      </header>

      {running && (
        <p
          role="status"
          className="investigation-progress"
        >
          Running tests, examining Git history, generating
          the NVIDIA Nemotron hypothesis, and verifying
          the suspected regression...
        </p>
      )}

      {error && (
        <p role="alert" className="error">
          Error: {error}
        </p>
      )}

      {success && (
        <p
          role="status"
          className="investigation-success"
        >
          {success}
        </p>
      )}

      {!graph && !running && !error && (
        <section className="panel">
          <h2>No Investigation Selected</h2>

          <p className="subtitle">
            {selectedRepository
              ? 'Click Run Investigation to analyze the selected repository.'
              : 'Select a repository and click Run Investigation to generate a new evidence report.'}
          </p>
        </section>
      )}

      {graph && (
        <>
          <section className="stats">
            <article className="card">
              <h3>Evidence Nodes</h3>
              <strong>{graph.nodes.length}</strong>
            </article>

            <article className="card">
              <h3>Evidence Connections</h3>
              <strong>{graph.edges.length}</strong>
            </article>

            <article className="card">
              <h3>Reversal Verification</h3>
              <strong>
                {outcomeLabel(primaryOutcome)}
              </strong>
            </article>
          </section>

          <section className="panel">
            <h2>Regression Investigation</h2>

            <p>
              <b>Suspected commit:</b>{' '}
              {String(
                primaryReversal?.commit ??
                commit?.data.hash ??
                'Unknown'
              )}
            </p>

            <p>
              <b>Test status:</b>{' '}
              {failure ? 'FAILED' : 'Unknown'}
            </p>

            <p>
              <b>Verification:</b>{' '}
              {primaryReversal
                ? outcomeExplanation(primaryReversal)
                : primaryOutcome === 'verified'
                  ? 'Reversal restored passing tests'
                  : 'Investigation was inconclusive'}
            </p>
          </section>

          {primaryReversal && (
            <section className="panel">
              <h2>Reversal Experiment Comparison</h2>

              <p className="subtitle">
                Compare the effects of reversing different
                commits to determine which hypothesis is
                supported by test evidence.
              </p>

              <div className="experiment-grid">
                {alternativeReversal && (
                  <ExperimentCard
                    title="Alternative Hypothesis"
                    description="Reversal of the latest commit"
                    experiment={alternativeReversal}
                  />
                )}

                <ExperimentCard
                  title="Regression Hypothesis"
                  description="Reversal of the identified regression commit"
                  experiment={primaryReversal}
                />
              </div>
            </section>
          )}

          <section className="panel">
            <h2>NVIDIA Nemotron Root-Cause Analysis</h2>

            <div className="analysis">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
              >
                {String(
                  hypothesis?.data.explanation ??
                  'No analysis available'
                )}
              </ReactMarkdown>
            </div>
          </section>

          <section className="panel">
            <h2>Evidence Graph</h2>

            <EvidenceGraph
              nodes={graph.nodes}
              edges={graph.edges}
            />
          </section>
        </>
      )}
    </main>
  )
}

export default App
