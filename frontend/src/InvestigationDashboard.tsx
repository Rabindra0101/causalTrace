import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import EvidenceGraph from './EvidenceGraph'
import RegressionTimeline from './RegressionTimeline'

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
  id: string; generated_at?: string; repository_id: string; status: string; reason: string; investigation_type?: string; test_runner?: string
  baseline_revision: string; baseline: TestRun; candidate_diff?: string
  regression?: { confirmed: boolean; suspected_commit?: string; parent_revision?: string }
  experiments: { commit_reversal?: Experiment; alternative_reversal?: Experiment }
  ai_analysis: { status: string; model?: string; hypothesis?: string; reason?: string }
  repair?: Repair | null
  tested_history?: { commits: { hash: string }[] }
  release_range?: { good_ref: string; bad_ref: string; good_commit: string; bad_commit: string; commits_in_range: number; assumption: string }
  working_baseline?: TestRun
  failure_groups?: { test_id: string; confirmed: boolean; reason: string; suspected_commit?: string; commit_date?: string; commit_message?: string; resolved_after_repair?: boolean; reversal?: { outcome: string; reason: string } }[]
  repair_session?: { status: string; reason: string; final_tests: TestRun; attempts: { number: number; accepted: boolean; reason: string; proposal?: Repair; verification?: { status: string; before?: TestRun; after?: TestRun } }[] }
  unsearched_failures?: number
  repair_patch_url?: string
  source_context?: { selected_files: string[]; omitted_files: string[]; scope: string }
  source_evidence?: { path: string; content: string }[]
  provenance?: { name: string; source: string; upstream_fixed?: string; upstream_revision?: string; history_type?: string; note: string }
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
    <span className={`run-badge outcome-${experiment.outcome}`}>{experiment.outcome.replaceAll('_', ' ')}</span>
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
  const [historyLimit, setHistoryLimit] = useState(64)
  const [goodRef, setGoodRef] = useState('')
  const [badRef, setBadRef] = useState('HEAD')
  const [maxRepairAttempts, setMaxRepairAttempts] = useState(3)
  const [shareWithNebius, setShareWithNebius] = useState(false)
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
  const [elapsed, setElapsed] = useState(0)
  const controlId = useRef<string | null>(null)
  const [controlState, setControlState] = useState('running')
  const [controlBusy, setControlBusy] = useState(false)
  const [controlMessage, setControlMessage] = useState('')
  useEffect(() => {
    if (!running) return
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now()-started)/1000)), 1000)
    return () => window.clearInterval(timer)
  }, [running])

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
    controlId.current = crypto.randomUUID().replaceAll('-', '')
    setControlState('running'); setControlMessage('')
    setElapsed(0); setRunning(true); setError(''); setReport(null)
    try {
      const data = await fetch('/api/run-investigation', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ control_id: controlId.current, repository_id: repository, repository_path: repositoryPath,
          test_directory: testDirectory, investigation_type: investigationType,
          share_with_nebius: shareWithNebius, history_limit: historyLimit,
          good_ref: goodRef.trim() || null, bad_ref: badRef.trim() || 'HEAD', max_repair_attempts: maxRepairAttempts,
          test_runner: repository === 'local' ? testRunner : 'pytest',
          runner_image: repository === 'local' ? runnerImage.trim() || null : null,
          install_dependencies: repository === 'local' && installDependencies,
          build_frontend: repository === 'local' && buildFrontend,
          frontend_directory: frontendDirectory }),
      }).then(jsonResponse)
      setReport(data.report)
    } catch (e) { setError(e instanceof Error ? e.message : 'Investigation failed') }
    finally { setRunning(false); controlId.current = null; setControlMessage('') }
  }

  async function control(action: 'pause' | 'resume' | 'stop') {
    const id = controlId.current
    if (!id) return
    setControlBusy(true)
    try {
      const result = await fetch(`/api/investigation-control/${id}`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action}),
      }).then(jsonResponse)
      if (controlId.current !== id) return
      setControlState(result.state)
      setControlMessage(action === 'resume' ? 'Investigation resumed.' : action === 'pause'
        ? 'Pause requested. The current operation finishes first; then work waits until you resume.'
        : 'Stop requested. Finishing the current operation and saving completed test results.')
    } catch (e) {
      if (controlId.current === id) setControlMessage(e instanceof Error ? e.message : 'Unable to control investigation')
    } finally { setControlBusy(false) }
  }

  return <main className="dashboard">
    <a className="skip-link" href="#investigation">Skip to investigation controls</a>
    <nav className="workspace-nav" aria-label="Workspace navigation">
      <a className="workspace-brand" href="#top"><span className="brand-symbol" aria-hidden="true">⌘</span>CausalTrace<span className="brand-tag">LAB</span></a>
      <div><a href="#investigation">Investigate</a><a href="#readiness">Readiness</a><span className="local-label">Local workspace</span></div>
    </nav>
    <header className="header" id="top"><div className="hero-copy">
      <p className="eyebrow"><span aria-hidden="true" /> EVIDENCE, NOT GUESSWORK</p>
      <h1>Find the change.<br /><span>Prove the fix.</span></h1>
      <p className="subtitle">Turn a failing test into a clear trail of evidence.<br className="desktop-break" /> Trace the regression, challenge the cause, and test the repair.</p>
      <div className="language-chips" aria-label="Supported languages"><span>Python</span><span>JavaScript / TS</span><span>Java</span><span>Go</span></div>
    </div>
    <div className="trace-art" aria-hidden="true">
      <div className="trace-orbit orbit-one" /><div className="trace-orbit orbit-two" />
      <svg className="trace-lines" viewBox="0 0 400 260" fill="none"><path d="M65 50V145Q65 180 100 180H300" stroke="#009b87" strokeWidth="3" /><path d="M65 85H210Q245 85 245 120V215" stroke="#8660cf" strokeWidth="3" strokeDasharray="6 7" /><circle cx="65" cy="50" r="8" fill="#009b87" /><circle cx="245" cy="215" r="8" fill="#8660cf" /><circle cx="300" cy="180" r="8" fill="#ef875e" /></svg>
      <div className="trace-note note-source"><span>01 / REPRODUCE</span><strong>Start with the failure.</strong><code>test → evidence</code></div>
      <div className="trace-note note-verify"><span>02 / INVESTIGATE</span><strong>Follow the change.</strong><code>commit → experiment</code></div>
      <div className="trace-caption">A better answer starts with proof.</div>
    </div></header>

    <section className="investigation-launch" id="investigation" tabIndex={-1}>
      <div className="launch-heading"><div><p className="section-kicker">YOUR NEXT INVESTIGATION</p><h2>Let’s follow the evidence.</h2></div><span className="workspace-pill">Isolated experiments</span></div>
      <div className="header-actions">
      <label className="repository-selector"><span>Repository</span>
        <select value={repository} disabled={running || !repositories.length}
          onChange={e => { setRepository(e.target.value); setShareWithNebius(false); setReport(null); setError('') }}>
          {repositories.map(repo => <option value={repo.id} key={repo.id}>{repo.name}</option>)}
          <option value="local">Local Git repository</option>
        </select>
      </label>
      {['humanize', 'pysnooper', 'cookiecutter', 'commons_csv'].includes(repository) && <p role="note">Full upstream repository at a pinned historical revision. Original tests, commit IDs and author dates are preserved. Tests run in disposable containers.</p>}
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
            onChange={e => { setRepositoryPath(e.target.value); setShareWithNebius(false); setReport(null) }} /></label>
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
      <fieldset className="mode-picker" disabled={running}><legend>What would you like to investigate?</legend><div className="mode-grid">{[
        ['full', 'Find the breaking change', 'Trace history, challenge the cause and test an AI repair.'],
        ['release', 'Repair a broken update', 'Compare working and broken releases; iterate on fixes.'],
        ['diagnose', 'Explain an error', 'Get AI suggestions for errors, setup or code improvements.'],
        ['regression', 'Check Git causes', 'Test history and reverse candidates without AI.'],
        ['reproduce', 'Explore test history', 'Run tests and find recent passing and failing commits.'],
      ].map(([value,title,description]) => <label key={value} className={`mode-card ${investigationType===value ? 'is-selected' : ''}`}><input type="radio" name="investigation-type" value={value} checked={investigationType===value} onChange={() => {setInvestigationType(value);setReport(null);setError('')}} /><span><strong>{title}</strong><span>{description}</span></span></label>)}</div></fieldset>
      <label className="repository-selector"><span>Maximum historical commits to test</span><select value={historyLimit} disabled={running} onChange={e => setHistoryLimit(Number(e.target.value))}>{[16,32,64,128,256,512,1024,2048].map(n => <option key={n} value={n}>{n}</option>)}</select><span>Starts at the selected revision and stops at the most recent passing/failing transition. Keeps skipped/error results visible and continues past them, up to this limit. The same search applies to every investigation type.</span></label>
      {investigationType === 'release' && <>
        <label className="repository-selector"><span>Last working release (tag or commit)</span><input value={goodRef} disabled={running} placeholder="v1.0.0 or commit ID" onChange={e => setGoodRef(e.target.value)} /></label>
        <label className="repository-selector"><span>Broken release (tag or commit)</span><input value={badRef} disabled={running} placeholder="HEAD" onChange={e => setBadRef(e.target.value)} /></label>
        <label className="repository-selector"><span>Maximum AI repair attempts</span><select value={maxRepairAttempts} disabled={running} onChange={e => setMaxRepairAttempts(Number(e.target.value))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
        <p>Searches backward from the broken release to the most recent passing/failing transition. Also checks your working release separately, then analyzes the tested interval and tries repairs in an independent snapshot.</p>
      </>}
      {(investigationType === 'full' || investigationType === 'diagnose' || investigationType === 'release') && <fieldset className="preparation-options" disabled={running}>
        <legend>AI analysis with Nebius / Nemotron</legend>
        <label><input type="checkbox" checked={shareWithNebius} onChange={e => setShareWithNebius(e.target.checked)} /> Share selected evidence with Nebius for this run</label>
        <p>Sends up to 12 committed source/config files (100,000 characters total), test logs and the candidate diff to Nebius Token Factory. This is a source-context limit, not a commit limit. Check your committed source for sensitive information before sharing. Environment files are excluded.</p>
        {investigationType === 'diagnose' && <p>Uses the same recent passing/failing history search before AI diagnosis. Every attempted result remains visible; it does not scan the entire repository history.</p>}
        <p>AI diagnosis explains errors and suggests fixes, tests and improvements. It can run without proving a Git regression. Suggestions stay unverified until unchanged tests pass after a source repair.</p>
      </fieldset>}
      <div className="investigation-actions"><button className="run-button" disabled={running || (investigationType === 'release' && !goodRef.trim()) || !repositories.length || !health?.git_available || !(health?.docker.ready || (repository === 'local' && health?.docker.available)) || (repository === 'local' && !repositoryPath.trim())}
        onClick={() => void run()}>{running ? 'Investigating…' : ({full:'Find breaking change', release:'Run repair agent', diagnose:'Get AI suggestions', regression:'Test Git causes', reproduce:'Explore tested history'}[investigationType] ?? 'Run investigation')}<span aria-hidden="true">↗</span></button>
        {running && <><button className="control-button" disabled={controlBusy || controlState === 'stopping'} onClick={() => void control(controlState === 'paused' ? 'resume' : 'pause')}>{controlState === 'paused' ? 'Resume' : 'Pause'}</button>
          <button className="control-button stop-button" disabled={controlBusy || controlState === 'stopping'} onClick={() => void control('stop')}>{controlState === 'stopping' ? 'Stopping…' : 'Stop'}</button></>}
      </div>
      {running && controlMessage && <p className="control-message" role="status" aria-live="polite">{controlMessage}</p>}
    </div></section>

    <section className="panel setup-panel" id="readiness"><div className="setup-heading"><div><p className="section-kicker">BEFORE YOU BEGIN</p><h2>Workspace readiness</h2></div>
      <button className="setup-refresh" disabled={checking || running} onClick={() => void refresh()}>{checking ? 'Checking…' : '↻ Check again'}</button></div>
      {health ? <><div className="readiness-grid">
        <div className={`readiness-item ${health.git_available ? 'is-ready' : 'needs-setup'}`}><span className="readiness-icon" aria-hidden="true">⌘</span><div><strong>Git history</strong><span>{health.git_available ? 'Ready to trace' : 'Git is missing'}</span></div><span className="readiness-dot" aria-hidden="true" /></div>
        <div className={`readiness-item ${health.docker.ready ? 'is-ready' : 'needs-setup'}`}><span className="readiness-icon" aria-hidden="true">◇</span><div><strong>Docker runner</strong><span>{health.docker.ready ? 'Ready to experiment' : 'Setup needed'}</span></div><span className="readiness-dot" aria-hidden="true" /></div>
        <div className={`readiness-item ${health.nebius_configured ? 'is-ready' : 'needs-setup'}`}><span className="readiness-icon" aria-hidden="true">✧</span><div><strong>Nebius / Nemotron</strong><span>{health.nebius_configured ? 'Key configured' : 'API key needed'}</span></div><span className="readiness-dot" aria-hidden="true" /></div>
      </div>
        {!health.docker.ready && <p role="status">{health.docker.reason}</p>}
        {repository === 'local' && <p>The selected test runner image and dependencies are checked when you run the investigation.</p>}
        {!health.nebius_configured && <p>Set NEBIUS_API_KEY in .env for model analysis and proposed repairs. Git evidence can still be collected when Docker is ready.</p>}
      </> : <p>Checking backend setup…</p>}
    </section>

    {running && <p role="status" className="investigation-progress" aria-live="polite">{investigationType === 'reproduce'
      ? 'Testing HEAD and each historical commit through the most recent passing/failing transition.'
      : investigationType === 'release' ? 'Searching the most recent passing/failing transition, checking release endpoints and testing bounded repair attempts.'
      : investigationType === 'diagnose' ? 'Searching the most recent passing/failing transition before preparing AI suggestions.'
      : investigationType === 'regression' ? 'Reproducing the failure, testing Git history and running reversal experiments.'
      : 'Reproducing the failure, testing Git history, running reversal experiments and requesting a tested Nemotron repair.'} Elapsed: {elapsed}s. Each result comes from actual tests; longer histories may take several minutes.</p>}
    {error && <p role="alert" className="error">{error}</p>}

    {!report && !running && <section className="panel getting-started"><p className="section-kicker">SMALL DEMO. REAL EVIDENCE.</p><h2>Meet your next “aha” moment.</h2>
      <div className="workflow-strip"><div><span>01</span><strong>Reproduce</strong><p>See the failure as it happened.</p></div><div><span>02</span><strong>Investigate</strong><p>Find the change. Test the cause.</p></div><div><span>03</span><strong>Verify</strong><p>Let unchanged tests judge the repair.</p></div></div>
      <p>Each bundled demo has a passing commit, a breaking commit, and an unrelated documentation commit. CausalTrace runs the tests and investigates the history from those source files.</p>
      <p className="subtitle">Choose a bundled demo or a local Git repository with Python, JavaScript/TypeScript, Java or Go tests. Local investigations use an independent snapshot of committed HEAD and history; uncommitted edits are ignored. The original files, .env and Git worktree metadata are not modified. Select the project directory containing its manifest, sources and tests. Preparation and tests run on disposable copies.</p>
      <p>Enable evidence sharing for AI diagnosis or full investigations. Git regression and reproduce-only modes run without model requests. Use AI diagnosis for setup/build/import errors or optional improvements even when history cannot prove a regression.</p>
    </section>}

    {report && <>
      <section className="panel result-panel"><p className="section-kicker">THE EVIDENCE IS IN</p><h2>Investigation results <span className={`run-badge status-${report.status}`}>{report.status.replaceAll('_', ' ')}</span></h2>
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
      {report.release_range && <section className="panel"><h2>Release comparison</h2><p>Working: <code>{report.release_range.good_ref}</code> ? broken: <code>{report.release_range.bad_ref}</code> ({report.release_range.commits_in_range} commits).</p><p>{report.release_range.assumption}</p><Output title="Working release tests" run={report.working_baseline} />{report.candidate_diff && <details><summary>Diff between selected releases</summary><pre className="run-output">{report.candidate_diff}</pre></details>}</section>}
      {report.failure_groups && <section className="panel"><h2>Failing tests and regression boundaries</h2><p>Multiple tests can share one underlying bug. Each boundary is assessed separately.</p>{Boolean(report.unsearched_failures) && <p>{report.unsearched_failures} additional failures were not bisected because the grouping limit was reached.</p>}{report.failure_groups.map(group => <article key={group.test_id}><h3><code>{group.test_id}</code></h3><p>{group.reason}</p>{group.suspected_commit && <p>Candidate: <code>{group.suspected_commit}</code> ? {group.commit_message}{group.commit_date && <> ? {new Date(group.commit_date).toLocaleString()}</>}</p>}<p>Reversal: {group.reversal?.outcome.replaceAll('_', ' ')}. {group.reversal?.reason}</p><p>{group.resolved_after_repair ? 'Passing after repair' : 'Unresolved'}</p></article>)}</section>}
      {report.repair_session && <section className="panel"><h2>Iterative repair experiments <span className="run-badge">{report.repair_session.status.replaceAll('_', ' ')}</span></h2><p>{report.repair_session.reason}</p>{report.repair_session.attempts.map(attempt => <article key={attempt.number}><h3>Attempt {attempt.number}: {attempt.accepted ? 'accepted in isolated snapshot' : 'not accepted'}</h3><p>{attempt.reason}</p>{attempt.proposal && <><p>{attempt.proposal.diagnosis.summary}</p><ul>{attempt.proposal.diagnosis.recommended_steps.map((step,i) => <li key={i}>{step}</li>)}</ul><details><summary>Proposed patch</summary><pre className="run-output">{attempt.proposal.patch}</pre></details></>}<Output title="Candidate tests" run={attempt.verification?.after} /></article>)}<Output title="Final complete test suite" run={report.repair_session.final_tests} />{report.repair_patch_url && <a className="report-download" href={report.repair_patch_url} download>Download cumulative repair patch</a>}<p>Original repository unchanged. Review the patch before applying it. Passing tests cover tested behavior, not every possible bug.</p></section>}
      {report.regression && !report.release_range && <section className="panel"><h2>2. Regression boundary</h2>
        <p>Boundary: {report.regression.confirmed ? 'confirmed by historical tests' : 'inconclusive'}</p>
        {report.regression.suspected_commit && <p>Breaking commit: <code>{report.regression.suspected_commit}</code></p>}
        {report.regression.parent_revision && <p>Passing parent: <code>{report.regression.parent_revision}</code></p>}
        {report.candidate_diff && <details><summary>Candidate Git diff</summary><pre className="run-output">{report.candidate_diff}</pre></details>}
      </section>}
      {report.generated_at && <p>Investigation started: <time dateTime={report.generated_at}>{new Date(report.generated_at).toLocaleString()}</time></p>}
      {report.provenance && <section className="result-card"><h2>Public source provenance</h2><p>{report.provenance.note}</p><a href={report.provenance.source}>Pinned upstream source</a><p>Upstream revision: <code>{report.provenance.upstream_revision ?? report.provenance.upstream_fixed}</code></p></section>}
      {(report.repository_id !== 'local' || report.tested_history) && <RegressionTimeline key={report.id} repositoryId={report.repository_id} reportId={report.id}
        suspectedCommit={report.regression?.suspected_commit}
        verified={report.experiments.commit_reversal?.outcome === 'verified'} />}
      {report.experiments.commit_reversal && <section className="panel"><h2>3. Reversal experiments</h2>
        <div className="experiment-grid"><ExperimentCard title="Suspected breaking change" experiment={report.experiments.commit_reversal} />
          <ExperimentCard title="Alternative: latest commit" experiment={report.experiments.alternative_reversal} /></div>
      </section>}
      {(!report.investigation_type || report.investigation_type === 'full' || report.investigation_type === 'diagnose') && report.ai_analysis.status !== 'not_run' && <><section className="panel"><h2>4. Nemotron diagnosis and suggestions <span className="run-badge">{report.ai_analysis.status}</span></h2>
        {report.ai_analysis.reason && <p role="status">{report.ai_analysis.reason}</p>}
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.ai_analysis.hypothesis ?? 'No model analysis was performed for this run.'}</ReactMarkdown>
        {report.source_context && <p>{report.source_context.selected_files.length} selected files analyzed; {report.source_context.omitted_files.length} files omitted by context limits. {report.source_context.scope}</p>}
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

    <footer className="workspace-footer"><span>CausalTrace <span aria-hidden="true">✧</span> Built around evidence.</span><span>Reproduce. Investigate. Verify.</span></footer>
  </main>
}
