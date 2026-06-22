import { Send, Square } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { LLMAnswerRequest } from '../types/llm'

interface AgentCommandBoxProps {
  isSubmitting: boolean
  onSubmit: (payload: LLMAnswerRequest) => void
  onCancel?: () => void
}

// 트리플의 '나를 아는' 맞춤 입력을 본떠, 동행자·페이스·취향을 칩으로 골라 개인화한다.
const WHO = ['혼자', '친구', '연인', '가족', '아이와', '부모님']
const PACE = ['빡빡하게', '적당히', '여유롭게']
const TAGS = ['맛집', '쇼핑', '자연·힐링', 'SNS핫플', '유명관광지', '체험·액티비티', '문화·역사', '온천']

export function AgentCommandBox({ isSubmitting, onSubmit, onCancel }: AgentCommandBoxProps) {
  const [message, setMessage] = useState('')
  const [who, setWho] = useState<string | null>(null)
  const [pace, setPace] = useState<string | null>(null)
  const [tags, setTags] = useState<string[]>([])

  const toggleTag = (tag: string) =>
    setTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]))

  function buildMessage(trimmed: string): string {
    // 고른 칩을 구조화 텍스트로 덧붙여, intake가 동행자·페이스·취향을 정확히 잡게 한다.
    const parts: string[] = []
    if (who) parts.push(`동행: ${who}`)
    if (pace) parts.push(`페이스: ${pace}`)
    if (tags.length) parts.push(`취향: ${tags.join(', ')}`)
    return parts.length ? `${trimmed} [${parts.join(' · ')}]` : trimmed
  }

  function submitMessage() {
    const trimmedMessage = message.trim()
    if (!trimmedMessage || isSubmitting) return

    onSubmit({
      message: buildMessage(trimmedMessage),
      locale: 'ko-KR',
      currency: 'KRW',
      timezone: 'Asia/Seoul',
    })
    setMessage('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submitMessage()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return

    event.preventDefault()
    submitMessage()
  }

  return (
    <form className="agent-command-box" onSubmit={handleSubmit}>
      <label htmlFor="agent-request" className="composer-label">
        여행 요청
      </label>

      <div className="pref-chips" aria-label="여행 취향 선택">
        <div className="pref-group">
          <span className="pref-group__label">동행</span>
          {WHO.map((w) => (
            <button
              key={w}
              type="button"
              className={`pref-chip${who === w ? ' pref-chip--on' : ''}`}
              onClick={() => setWho((cur) => (cur === w ? null : w))}
            >
              {w}
            </button>
          ))}
        </div>
        <div className="pref-group">
          <span className="pref-group__label">페이스</span>
          {PACE.map((p) => (
            <button
              key={p}
              type="button"
              className={`pref-chip${pace === p ? ' pref-chip--on' : ''}`}
              onClick={() => setPace((cur) => (cur === p ? null : p))}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="pref-group">
          <span className="pref-group__label">취향</span>
          {TAGS.map((t) => (
            <button
              key={t}
              type="button"
              className={`pref-chip${tags.includes(t) ? ' pref-chip--on' : ''}`}
              onClick={() => toggleTag(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="composer-row">
        <textarea
          id="agent-request"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="여행 요청을 입력하세요 (예: 오사카 3박4일)"
          rows={3}
          required
        />
        {isSubmitting ? (
          <button
            className="composer-submit composer-stop"
            type="button"
            onClick={onCancel}
            title="실행 중지"
          >
            <Square aria-hidden="true" />
            중지
          </button>
        ) : (
          <button
            className="primary-button composer-submit"
            type="submit"
            disabled={!message.trim()}
          >
            <Send aria-hidden="true" />
            보내기
          </button>
        )}
      </div>
    </form>
  )
}
