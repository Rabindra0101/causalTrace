import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import EvidenceGraph from './EvidenceGraph'
import RegressionTimeline from './RegressionTimeline'
import BuildDoctor from './BuildDoctor'
import './InvestigationDashboard.css'

type TestRun = { status: string; return_code: number; output: string; preparation?: TestRun }
type Experiment = {
  commit: string; outcome: string; reason: string
  before?: TestRun; after?: TestRun
}
type Repair = {
  model: string; patch: string; patch_error: string | null
  diagnosis: { summary: string; evidence: string[]; recommended_steps: string[] }
  verification: { status: string; reason?: string; before?: TestRun; after?: TestRun | null }
}
type Report = {
  id: string; repository_id: string; status: string; reason: string; investigation_type?: string; test_runner?: string
  baseline_revision: string; baseline: TestRun; candidate_diff?: string
  regression?: { confirmed: boolean; suspected_commit?: string; parent_revision?: string }
  experiments: { commit_reversal?: Experiment; alternative_reversal?: Experiment }
  ai_analysis: { status: string; model?: string; hypothesis?: string; reason?: string }
  repair?: Repair | null
  source_evidence?: { path: string; content: string }[]
  setup_issues?: { code: string; message: string; action: string }[]
  evidence_graph?: {
    nodes: { id: string; type: string; data: Record<string, unknown> }[]
    edges: { source: string; target: string; relationship: string }[]
  }
}
type Health = {
  git_available: boolean; nebius_configured: boolean
  docker: { ready: boolean; available?: boolean; reason: string }
}

async function jsonResponse(response: Response) {
  const text = await response.text()
  let data
  try { data = JSON.parse(text) }
  catch { throw new Error('Backend unavailable. Start the backend on port 8000 and try again.') }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed')
  return data
}

function Output({ title, run }: { title: string; run?: TestRun | null }) {
  if (!run) return null
  return <details className="run-receipt"><summary>{title} · {run.status ?? 'test run'} · exit {run.return_code}</summary>
    <pre className="run-output">{run.output}</pre></details>
}

function ExperimentCard({ title, experiment }: { title: string; experiment?: Experiment }) {
  if (!experiment) return null
  return <article className="experiment-card"><h3>{title}</h3>
    <span className="run-badge">{experiment.outcome.replaceAll('_', ' ')}</span>
    <p><code>{experiment.commit.slice(0, 8)}</code></p><p>{experiment.reason}</p>
    <Output title="Before reversal" run={experiment.before} />
    <Output title="After reversal" run={experiment.after} />
  </article>
}

export default function InvestigationDashboard() {
  const [repositories, setRepositories] = useState<{ id: string; name: string }[]>([])
  const [repository, setRepository] = useState('config')
  const [repositoryPath, setRepositoryPath] = useState('')
  const [testDirectory, setTestDirectory] = useState('.')
  const [investigationType, setInvestigationType] = useState('full')
  const [testRunner, setTestRunner] = useState('auto')
  const [runnerImage, setRunnerImage] = useState('')
  const [installDependencies, setInstallDependencies] = useState(false)
  const [buildFrontend, setBuildFrontend] = useState(false)
  const [frontendDirectory, setFrontendDirectory] = useState('frontend')
  const [health, setHealth] = useState<Health | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      fetch('/api/repositories', { signal: controller.signal }).then(jsonResponse),
      fetch('/api/health', { signal: controller.signal }).then(jsonResponse),
    ]).then(([catalog, status]) => {
      setRepositories(catalog.repositories); setHealth(status)
    }).catch(e => { if (!controller.signal.aborted) setError(String(e)) })
    return () => controller.abort()
  }, [])

  async function refresh() {
    setChecking(true); setError('')
    try { setHealth(await fetch('/api/health').then(jsonResponse)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to check setup') }
    finally { setChecking(false) }
  }

  async function run() {
    setRunning(true); setError(''); setReport(null)
    try {
      const data = await fetch('/api/run-investigation', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repository_id: repository, repository_path: repositoryPath,
          test_directory: testDirectory, investigation_type: investigationType,
          test_runner: repository === 'local' ? testRunner : 'pytest',
          runner_image: repository === 'local' ? runnerImage.trim() || null : null,
          install_dependencies: repository === 'local' && installDependencies,
          build_frontend: repository === 'local' && buildFrontend,
          frontend_directory: frontendDirectory }),
      }).then(jsonResponse)
      setReport(data.report)
    } catch (e) { setError(e instanceof Error ? e.message : 'Investigation failed') }
    finally { setRunning(false) }
  }

  return <main className="dashboard">
    <header className="header"><div>
      <p className="eyebrow">EVIDENCE-DRIVEN REGRESSION INVESTIGATION</p>
      <h1>CausalTrace</h1>
      <p className="subtitle">Find the breaking change. Explain it. Test the repair.</p>
    </div><div className="header-actions">
      <label className="repository-selector"><span>Repository</span>
        <select value={repository} disabled={running || !repositories.length}
          onChange={e => { setRepository(e.target.value); setReport(null); setError('') }}>
          {repositories.map(repo => <option value={repo.id} key={repo.id}>{repo.name}</option>)}
          <option value="local">Local Git repository</option>
        </select>
      </label>
      {repository === 'local' && <>
        <label className="repository-selector"><span>Test runner</span>
          <select value={testRunner} disabled={running} onChange={e => { setTestRunner(e.target.value); setReport(null) }}>
            <option value="auto">Detect from committed project files</option>
            <option value="pytest">Python — pytest</option>
            <option value="node">JavaScript — Node test runner</option>
            <option value="vitest">JavaScript / TypeScript — Vitest</option>
            <option value="jest">JavaScript / TypeScript — Jest</option>
            <option value="maven">Java — Maven / Surefire</option>
            <option value="go">Go — go test</option>
          </select></label>
        <label className="repository-selector"><span>Prepared runner image (optional)</span>
          <input value={runnerImage} disabled={running} placeholder="Default image for selected runner"
            onChange={e => { setRunnerImage(e.target.value); setReport(null) }} /></label>
        <label className="repository-selector"><span>Absolute repository path</span>
          <input value={repositoryPath} disabled={running} placeholder="C:\\projects\\my-repo"
            onChange={e => { setRepositoryPath(e.target.value); setReport(null) }} /></label>
        <label className="repository-selector"><span>Project / test directory (relative to repository)</span>
          <input value={testDirectory} disabled={running} placeholder="."
            onChange={e => { setTestDirectory(e.target.value); setReport(null) }} /></label>
        <fieldset className="preparation-options" disabled={running}>
          <legend>Project preparation (optional)</legend>
          <label><input type="checkbox" checked={installDependencies} onChange={e => setInstallDependencies(e.target.checked)} /> Download project dependencies</label>
          <p>Allows network access during preparation, including dependency install scripts. Actual tests run offline. Use only with repositories you trust.</p>
          <label><input type="checkbox" checked={buildFrontend} onChange={e => setBuildFrontend(e.target.checked)} /> Build frontend assets before testing</label>
          {buildFrontend && <label className="repository-selector"><span>Frontend directory (relative to project)</span>
            <input value={frontendDirectory} placeholder="frontend" onChange={e => setFrontendDirectory(e.target.value)} /></label>}
          <p>Preparation and builds use a disposable copy for each tested revision. Your repository is not modified. Python uses prepared images instead.</p>
        </fieldset>
      </>}
      <label className="repository-selector"><span>Investigation type</span>
        <select value={investigationType} disabled={running}
          onChange={e => { setInvestigationType(e.target.value); setReport(null) }}>
          <option value="full">Full investigation and repair</option>
          <option value="regression">Git regression and reversal</option>
          <option value="reproduce">Reproduce failure only</option>
        </select>
      </label>
      <button className="run-button" disabled={running || !repositories.length || !health?.git_available || !(health?.docker.ready || (repository === 'local' && health?.docker.available)) || (repository === 'local' && !repositoryPath.trim())}
        onClick={() => void run()}>{running ? 'Investigating…' : 'Run investigation'}</button>
    </div></header>

    <section className="panel setup-panel"><h2>Readiness</h2>
      {health ? <><p>Git: {health.git_available ? 'ready' : 'missing'} · Docker: {health.docker.ready ? 'ready' : 'setup needed'} · Nebius key: {health.nebius_configured ? 'configured' : 'missing'}</p>
        {!health.docker.ready && <p role="status">{health.docker.reason}</p>}
        {repository === 'local' && <p>The selected test runner image and dependencies are checked when you run the investigation.</p>}
        {!health.nebius_configured && <p>Set NEBIUS_API_KEY in .env for model analysis and proposed repairs. Git evidence can still be collected when Docker is ready.</p>}
      </> : <p>Checking backend setup…</p>}
      <button className="doctor-secondary" disabled={checking || running} onClick={() => void refresh()}>{checking ? 'Checking…' : 'Check setup again'}</button>
    </section>

    {running && <p role="status" className="investigation-progress">{investigationType === 'reproduce'
      ? 'Testing committed HEAD in Docker.'
      : investigationType === 'regression' ? 'Reproducing the failure, testing Git history and running reversal experiments.'
      : 'Reproducing the failure, testing Git history, running reversal experiments and requesting a tested Nemotron repair.'} This may take several minutes.</p>}
    {error && <p role="alert" className="error">{error}</p>}

    {!report && !running && <section className="panel"><h2>Start with the configuration regression</h2>
      <p>Each bundled demo has a passing commit, a breaking commit, and an unrelated documentation commit. CausalTrace runs the tests and investigates the history from those source files.</p>
      <p className="subtitle">Choose a bundled demo or a local Git repository with Python, JavaScript/TypeScript, Java or Go tests. Local investigations use an independent snapshot of committed HEAD and history; uncommitted edits are ignored. The original files, .env and Git worktree metadata are not modified. Select the project directory containing its manifest, sources and tests. Preparation and tests run on disposable copies.</p>
      <p>Full investigations send committed source, logs and the candidate diff to Nebius. Review your source for secrets first. The other investigation types run without model requests.</p>
    </section>}

    {report && <>
      <section className="panel"><h2>Run result <span className="run-badge">{report.status.replaceAll('_', ' ')}</span></h2>
        <p>{report.reason}</p><p className="subtitle">Investigation {report.id.slice(0, 8)} · committed HEAD {report.baseline_revision.slice(0, 8)}</p>
        {report.test_runner && <p>Test runner: <strong>{report.test_runner}</strong></p>}
        <a className="report-download" href={`/api/investigation?report_id=${report.id}`} download={`causaltrace-${report.id}.json`}>Download this evidence report</a>
      </section>
      {Boolean(report.setup_issues?.length) && <section className="panel"><h2>Setup needs attention</h2>
        {report.setup_issues?.map(issue => <article key={issue.code}><h3>{issue.message}</h3><p>{issue.action}</p></article>)}
      </section>}
      <section className="panel"><h2>1. Baseline tests</h2>
        <Output title="Project preparation output" run={report.baseline.preparation} />
        <Output title="Baseline test output" run={report.baseline} /></section>
      {report.regression && <section className="panel"><h2>2. Regression boundary</h2>
        <p>Boundary: {report.regression.confirmed ? 'confirmed by historical tests' : 'inconclusive'}</p>
        {report.regression.suspected_commit && <p>Breaking commit: <code>{report.regression.suspected_commit}</code></p>}
        {report.regression.parent_revision && <p>Passing parent: <code>{report.regression.parent_revision}</code></p>}
        {report.candidate_diff && <details><summary>Candidate Git diff</summary><pre className="run-output">{report.candidate_diff}</pre></details>}
      </section>}
      {report.repository_id !== 'local' && <RegressionTimeline key={report.id} repositoryId={report.repository_id} reportId={report.id}
        suspectedCommit={report.regression?.suspected_commit}
        verified={report.experiments.commit_reversal?.outcome === 'verified'} />}
      {report.experiments.commit_reversal && <section className="panel"><h2>3. Reversal experiments</h2>
        <div className="experiment-grid"><ExperimentCard title="Suspected breaking change" experiment={report.experiments.commit_reversal} />
          <ExperimentCard title="Alternative: latest commit" experiment={report.experiments.alternative_reversal} /></div>
      </section>}
      {(!report.investigation_type || report.investigation_type === 'full') && report.ai_analysis.status !== 'not_run' && <><section className="panel"><h2>4. Nemotron analysis <span className="run-badge">{report.ai_analysis.status}</span></h2>
        {report.ai_analysis.reason && <p role="status">{report.ai_analysis.reason}</p>}
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.ai_analysis.hypothesis ?? 'No model analysis was performed for this run.'}</ReactMarkdown>
        {report.source_evidence && <details><summary>Source files supplied to Nemotron</summary>{report.source_evidence.map(file => <div key={file.path}><h3>{file.path}</h3><pre className="run-output">{file.content}</pre></div>)}</details>}
      </section>
      <section className="panel"><h2>5. Proposed repair and test result</h2>
        {report.repair ? <>
          {report.repair.patch_error && <p className="error">Patch rejected: {report.repair.patch_error}</p>}
          {report.repair.patch ? <pre className="run-output">{report.repair.patch}</pre> : <p>No applicable source patch was proposed.</p>}
          <span className="run-badge">{report.repair.verification.status.replaceAll('_', ' ')}</span>
          <p>{report.repair.verification.reason}</p>
          <Output title="Before repair" run={report.repair.verification.before} />
          <Output title="After repair" run={report.repair.verification.after} />
          <p className="subtitle">Verification covers the supplied tests. Original repository files are unchanged.</p>
        </> : <p>No proposed repair is available for this run.</p>}
      </section></>}
      {report.evidence_graph && <section className="panel"><h2>Evidence graph</h2><EvidenceGraph nodes={report.evidence_graph.nodes} edges={report.evidence_graph.edges} /></section>}
    </>}
    <details className="advanced-workspace"><summary>Advanced: investigate pasted logs and Python files</summary><BuildDoctor /></details>
  </main>
}
