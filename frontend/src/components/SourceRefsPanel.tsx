import { useState } from 'react'
import type { SourceRef } from '../types/common'
import { cleanDisplayText, formatDateTime } from '../utils/format'
import { EmptyState } from './EmptyState'

export function SourceRefsPanel({ sourceRefs }: { sourceRefs: SourceRef[] }) {
  const [open, setOpen] = useState(false)

  return (
    <section className="card">
      <button
        className="source-toggle"
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>
          <strong>출처와 데이터 확인</strong>
          <small>{sourceRefs.length}개 항목</small>
        </span>
        <span>{open ? '접기' : '펼치기'}</span>
      </button>
      {open &&
        (sourceRefs.length === 0 ? (
          <EmptyState message="아직 확인 가능한 출처가 없습니다." />
        ) : (
          <div className="source-list">
            {sourceRefs.map((ref) => (
              <article key={ref.source_id} className="source-row">
                <div className="source-row-header">
                  <strong>{cleanDisplayText(ref.title)}</strong>
                  <span className={`small-badge source-kind-${ref.is_mock ? 'mock' : 'live'}`}>
                    {ref.is_mock ? 'mock' : 'live'}
                  </span>
                </div>
                <p>
                  {cleanDisplayText(ref.provider)} · {cleanDisplayText(ref.source_type)}
                </p>
                <p>확인 시각: {formatDateTime(ref.retrieved_at)}</p>
                <p className="fine-print">{cleanDisplayText(ref.freshness_note)}</p>
              </article>
            ))}
          </div>
        ))}
    </section>
  )
}
