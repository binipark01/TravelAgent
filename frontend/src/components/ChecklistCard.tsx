import type { PrepChecklist } from '../types/trip'
import { cleanDisplayText } from '../utils/format'

/** 출발 전 준비물 체크리스트: 전압·유심·환전·옷차림 등을 카테고리별로. */
export function ChecklistCard({ checklist }: { checklist?: PrepChecklist | null }) {
  if (!checklist || checklist.groups.length === 0) return null
  return (
    <section className="card checklist-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">출발 전 준비물</p>
          <h2>{cleanDisplayText(checklist.destination)} 체크리스트</h2>
        </div>
      </div>

      <p className="visa-summary">{cleanDisplayText(checklist.summary)}</p>

      <div className="checklist-grid">
        {checklist.groups.map((group) => (
          <div key={group.title} className="checklist-group">
            <h3>{cleanDisplayText(group.title)}</h3>
            <ul>
              {group.items.map((item) => (
                <li key={item}>{cleanDisplayText(item)}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <p className="card-footnote">LLM 종합 · 출발 전 최신 정보(비자·날씨)는 한 번 더 확인</p>
    </section>
  )
}
