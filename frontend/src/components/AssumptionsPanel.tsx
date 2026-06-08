import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'

export function AssumptionsPanel({ assumptions }: { assumptions: string[] }) {
  return (
    <section className="card">
      <h2>현재 반영한 가정</h2>
      {assumptions.length === 0 ? (
        <EmptyState message="추가 가정 없이 입력값을 반영했습니다." />
      ) : (
        <ul className="text-list">
          {assumptions.map((assumption) => (
            <li key={assumption}>{cleanDisplayText(assumption)}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
