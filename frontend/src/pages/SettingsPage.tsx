import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getSettings, updateSettings } from '../api/settings'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import type { RuntimeSettings } from '../types/settings'
import { errorMessage } from '../utils/errors'

const EFFORTS = ['minimal', 'low', 'medium', 'high'] as const

const rowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 16,
  padding: '14px 0',
  borderTop: '1px solid #ececec',
} as const

export function SettingsPage() {
  const query = useQuery({ queryKey: ['settings'], queryFn: getSettings })

  if (query.isLoading) return <LoadingState label="설정을 불러오는 중입니다." />
  if (query.error || !query.data) return <ErrorState message={errorMessage(query.error)} />

  return <SettingsForm initial={query.data} />
}

function SettingsForm({ initial }: { initial: RuntimeSettings }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<RuntimeSettings>(initial)

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      setForm(data)
      queryClient.setQueryData(['settings'], data)
    },
  })

  return (
    <div className="workspace" style={{ maxWidth: 720, margin: '0 auto' }}>
      <section className="card">
        <h1>설정</h1>
        <p className="fine-print">
          변경은 저장 즉시 다음 요청부터 적용됩니다. (서버 재시작 시 기본값으로 초기화)
        </p>

        <label style={rowStyle}>
          <div>
            <strong>AI 추론(LLM) 사용</strong>
            <p className="fine-print">
              켜면 요청을 LLM이 정확히 해석합니다(날짜·인원·선호 등). 대신 요청당 수십 초 느려집니다.
            </p>
          </div>
          <input
            type="checkbox"
            checked={form.enable_live_llm}
            onChange={(event) => setForm({ ...form, enable_live_llm: event.target.checked })}
          />
        </label>

        <label style={rowStyle}>
          <div>
            <strong>실시간 항공/숙소 검색</strong>
            <p className="fine-print">
              켜면 네이버 화면을 브라우저로 분석해 실제 데이터를 가져옵니다(느림). 끄면 결과가 비어
              있습니다(mock은 표시하지 않음).
            </p>
          </div>
          <input
            type="checkbox"
            checked={form.enable_flight_source_probes}
            onChange={(event) =>
              setForm({ ...form, enable_flight_source_probes: event.target.checked })
            }
          />
        </label>

        <label style={rowStyle}>
          <div>
            <strong>추론 강도</strong>
            <p className="fine-print">낮을수록 빠르고, 높을수록 정확합니다. (추천: low)</p>
          </div>
          <select
            value={form.codex_reasoning_effort}
            onChange={(event) => setForm({ ...form, codex_reasoning_effort: event.target.value })}
          >
            {EFFORTS.map((effort) => (
              <option key={effort} value={effort}>
                {effort}
              </option>
            ))}
          </select>
        </label>

        {mutation.error && <ErrorState message={errorMessage(mutation.error)} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
          <button
            className="primary-button"
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(form)}
          >
            {mutation.isPending ? '저장 중...' : '저장'}
          </button>
          {mutation.isSuccess && <span className="fine-print">✅ 저장되었습니다.</span>}
        </div>
      </section>
    </div>
  )
}
