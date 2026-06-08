import type { CriticFinding } from '../types/common'
import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'

const severityLabels: Record<CriticFinding['severity'], string> = {
  info: '안내',
  warning: '주의',
  blocking: '차단',
}

export function RiskFindingsPanel({ findings }: { findings: CriticFinding[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">입국/안전</p>
          <h2>리스크</h2>
        </div>
      </div>
      {findings.length === 0 ? (
        <EmptyState message="아직 리스크 확인 결과가 없습니다." />
      ) : (
        <FindingList findings={findings} />
      )}
    </section>
  )
}

export function FindingList({ findings }: { findings: CriticFinding[] }) {
  return (
    <ul className="finding-list">
      {findings.map((finding, index) => (
        <li className={`finding severity-${finding.severity}`} key={`${finding.category}-${index}`}>
          <span>{severityLabels[finding.severity]}</span>
          <strong>{cleanDisplayText(finding.message)}</strong>
          {finding.suggested_fix && <p>{cleanDisplayText(finding.suggested_fix)}</p>}
        </li>
      ))}
    </ul>
  )
}
