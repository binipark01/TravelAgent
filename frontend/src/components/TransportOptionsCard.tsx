import type { FlightOption } from '../types/trip'
import { cleanDisplayText, formatMoney } from '../utils/format'
import { EmptyState } from './EmptyState'

// 스크래핑에서 새어든 광고/중복 노이즈(적립·할인·표시운임)는 화면에서 숨긴다.
const NOISE = /적립|할인|쿠폰|최대|표시\s*운임/
const isDisclaimer = (note: string) => /추출|재확인/.test(note)

const city = (value: string) => cleanDisplayText(value).split(',')[0].trim()
const md = (value?: string | null) => {
  const m = value?.match(/(\d{4})-(\d{2})-(\d{2})/)
  return m ? `${Number(m[2])}/${Number(m[3])}` : ''
}
const hm = (value?: string | null) => {
  const m = value?.match(/[T ](\d{2}):(\d{2})/)
  return m ? `${m[1]}:${m[2]}` : ''
}

export function TransportOptionsCard({ options }: { options: FlightOption[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">이동</p>
          <h2>항공/이동 후보</h2>
        </div>
      </div>
      {options.length === 0 ? (
        <EmptyState message="아직 항공 후보가 없습니다." />
      ) : (
        <div className="flight-list">
          {options.map((option, index) => {
            const chips = option.notes
              .filter((note) => !NOISE.test(note) && !isDisclaimer(note))
              .map(cleanDisplayText)
            const disclaimer = option.notes.find(isDisclaimer)
            return (
              <article className="flight-option" key={option.option_id}>
                <div className="flight-option__head">
                  <span className="flight-airline">{displayAirline(option.airline, index)}</span>
                  <strong className="flight-price">{formatMoney(option.price)}</strong>
                </div>
                <p className="flight-route">
                  {city(option.origin)} → {city(option.destination)}
                </p>
                <p className="flight-legs">
                  <span>
                    가는{' '}
                    <b>
                      {md(option.departure_time)} {hm(option.departure_time)}→
                      {hm(option.arrival_time)}
                    </b>
                  </span>
                  {option.return_departure_time && (
                    <span>
                      오는{' '}
                      <b>
                        {md(option.return_departure_time)} {hm(option.return_departure_time)}→
                        {hm(option.return_arrival_time)}
                      </b>
                    </span>
                  )}
                </p>
                {chips.length > 0 && (
                  <div className="flight-chips">
                    {chips.map((chip) => (
                      <span className="flight-chip" key={chip}>
                        {chip}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flight-option__foot">
                  {option.metadata.source_ref.source_url && (
                    <a
                      href={option.metadata.source_ref.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      예약 ↗
                    </a>
                  )}
                  {disclaimer && <span className="flight-disclaimer">{cleanDisplayText(disclaimer)}</span>}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function displayAirline(airline: string, index: number): string {
  return /\bmock\b/i.test(airline) ? `항공 후보 ${index + 1}` : cleanDisplayText(airline)
}
