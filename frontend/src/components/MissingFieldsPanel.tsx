import { fieldLabel } from '../utils/format'
import { EmptyState } from './EmptyState'

const missingReasons: Record<string, string> = {
  origin: '항공/이동 후보를 찾으려면 출발지가 필요합니다.',
  destinations: '일정과 숙소 후보를 만들려면 목적지가 필요합니다.',
  start_date: '항공, 숙소, 운영시간 확인을 위해 출발일이 필요합니다.',
  end_date: '숙박 수와 귀국 이동을 계산하려면 귀국일이 필요합니다.',
  travelers: '예산과 객실/좌석 수를 계산하려면 인원이 필요합니다.',
  passport_country: '입국 요건과 비자 리스크 확인에 필요합니다.',
}

export function MissingFieldsPanel({ fields }: { fields: string[] }) {
  return (
    <section className="card">
      <h2>누락 정보</h2>
      {fields.length === 0 ? (
        <EmptyState message="누락된 필수 정보가 없습니다." />
      ) : (
        <ul className="missing-field-list">
          {fields.map((field) => (
            <li key={field}>
              <strong>{fieldLabel(field)}</strong>
              <p>{missingReasons[field] ?? '정확한 계획 생성을 위해 필요한 정보입니다.'}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
