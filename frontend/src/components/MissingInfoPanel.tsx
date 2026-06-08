import { fieldLabel } from '../utils/format'
import { EmptyState } from './EmptyState'

const missingReasons: Record<string, string> = {
  origin: '항공/이동 후보 탐색에 필요합니다.',
  destinations: '목적지 후보와 일정을 만들기 위해 필요합니다.',
  start_date: '항공, 숙소, 운영시간 확인에 필요합니다.',
  end_date: '숙박 수와 귀국 동선을 계산하기 위해 필요합니다.',
  travelers: '예산과 숙소/좌석 수 계산에 필요합니다.',
  passport_country: '입국 리스크 확인에 필요합니다.',
}

export function MissingInfoPanel({ fields }: { fields: string[] }) {
  return (
    <section className="card">
      <h2>부족 정보</h2>
      {fields.length === 0 ? (
        <EmptyState message="현재 에이전트 실행을 막는 부족 정보가 없습니다." />
      ) : (
        <ul className="missing-field-list">
          {fields.map((field) => (
            <li key={field}>
              <strong>{fieldLabel(field)}</strong>
              <p>{missingReasons[field] ?? '계획을 계속 진행하기 위해 필요합니다.'}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
