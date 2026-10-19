type Props = { name: string; icon: string; ready: boolean | null; detail: string; explanation?: string }

export default function ReadinessCard({name, icon, ready, detail, explanation}: Props) {
  return <div className={`readiness-item ${ready === true ? 'is-ready' : ready === false ? 'needs-setup' : 'is-checking'}`} title={explanation}>
    <span className="readiness-icon" aria-hidden="true">{icon}</span>
    <div className="readiness-copy"><strong>{name}</strong><span>{detail}</span>
      {explanation && <small>{explanation}</small>}</div>
    <span className={`readiness-mark ${ready === true ? 'mark-ready' : ready === false ? 'mark-down' : 'mark-checking'}`}
      role="img" aria-label={ready === true ? 'Ready' : ready === false ? 'Unavailable or needs attention' : 'Checking'}>{ready === true ? '✓' : ready === false ? '×' : '…'}</span>
  </div>
}
