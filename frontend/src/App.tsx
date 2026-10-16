
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

function App() {
  const [graph, setGraph] = useState<EvidenceGraphData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)

  const [repositories, setRepositories] = useState<Repository[]>([])
  const [selectedRepository, setSelectedRepository] = useState('')
  const [repositoriesLoading, setRepositoriesLoading] = useState(true)

  // Prevent outdated requests from displaying results after a selection change.
  const selectionVersion = useRef(0)

  // Load repository options only. Do not load any previous investigation.
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

  // Clear all displayed investigation data when changing repositories.
  function handleRepositoryChange(repositoryId: string) {
    if (running) return

    selectionVersion.current += 1

    setSelectedRepository(repositoryId)
    setGraph(null)
    setError(null)
    setSuccess(null)
  }

  // Run a new investigation only when explicitly requested.
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
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch('/api/run-investigation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          repository_id: repositoryId,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)

        throw new Error(
          typeof errorData?.detail === 'string'
            ? errorData.detail
            : errorData?.detail?.message ??
              `Investigation failed (${response.status})`
        )
      }

      // Load the new graph only after this investigation completes.
      const graphResponse = await fetch('/api/graph', {
        cache: 'no-store',
      })

      if (!graphResponse.ok) {
        throw new Error(
          'Investigation completed, but the Evidence Graph could not be loaded.'
        )
      }

      const updatedGraph: EvidenceGraphData =
        await graphResponse.json()

      // Ignore results if the repository selection changed.
      if (selectionVersion.current !== currentVersion) {
        return
      }

      setGraph(updatedGraph)

      const repositoryName =
        repositories.find(
          repository => repository.id === repositoryId
        )?.name ?? repositoryId

      setSuccess(
        `${repositoryName} investigation completed. Evidence Graph updated.`
      )
    } catch (err) {
      if (selectionVersion.current === currentVersion) {
        setGraph(null)
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

  return (
    <main className="dashboard">
      <header className="header">
        <div>
          <p className="eyebrow">
            AI-POWERED REGRESSION INVESTIGATION
          </p>

          <h1>CausalTrace</h1>

          <p className="subtitle">
            Don't guess why software failed. Investigate the evidence.
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
                {experiment?.data.verified === true
                  ? 'VERIFIED'
                  : 'INCONCLUSIVE'}
              </strong>
            </article>
          </section>

          <section className="panel">
            <h2>Regression Investigation</h2>

            <p>
              <b>Suspected commit:</b>{' '}
              {String(commit?.data.hash ?? 'Unknown')}
            </p>

            <p>
              <b>Test status:</b>{' '}
              {failure ? 'FAILED' : 'Unknown'}
            </p>

            <p>
              <b>Verification:</b>{' '}
              {experiment?.data.verified === true
                ? 'Reversal restored passing tests'
                : 'Not verified'}
            </p>
          </section>

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
