import type { CriticFinding } from '../types/common'
import { EmptyState } from './EmptyState'
import { FindingList } from './RiskFindingsPanel'

export function CriticFindingsPanel({ findings }: { findings: CriticFinding[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">검토</p>
          <h2>검증 결과</h2>
        </div>
      </div>
      {findings.length === 0 ? (
        <EmptyState message="아직 검증 결과가 없습니다." />
      ) : (
        <FindingList findings={findings} />
      )}
    </section>
  )
}
