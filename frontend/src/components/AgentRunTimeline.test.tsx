import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AgentRunTimeline } from './AgentRunTimeline'
import type { AgentStep } from '../types/agent'

const steps: AgentStep[] = [
  {
    step_id: 'step_1',
    run_id: 'run_1',
    agent_name: 'IntakeAgent',
    status: 'completed',
    input_summary: '요청 분석',
    output_summary: '목적지 Japan, 누락 3개',
    started_at: '2026-06-03T00:00:00Z',
    completed_at: '2026-06-03T00:00:01Z',
    tool_calls: [],
  },
]

describe('AgentRunTimeline', () => {
  it('renders agent steps', () => {
    render(<AgentRunTimeline steps={steps} />)

    expect(screen.getByText('요청 분석')).toBeInTheDocument()
    expect(screen.getByText('목적지 일본, 누락 3개')).toBeInTheDocument()
    expect(screen.queryByText('목적지 후보 탐색')).not.toBeInTheDocument()
  })
})
