import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createLLMAnswer } from '../api/llm'
import type { LLMAnswerResponse } from '../types/llm'
import { HomePage } from './HomePage'

vi.mock('../api/llm', () => ({
  createLLMAnswer: vi.fn(),
}))

const llmResponse: LLMAnswerResponse = {
  answer:
    '삿포로 항공권 조건은 7월 초~중순, 가는 편 오전 출발, 오는 편 오후 출발로 보면 됩니다.',
  answer_kind: 'answer',
  interpreted_request: '항공 검색: 서울 -> Sapporo, 2026-07-03 ~ 2026-07-15',
  source_attempts: [
    {
      domain: 'flights',
      agent_name: 'FlightSearchAnswerAgent',
      provider: 'naver_flight',
      title: '네이버 항공권',
      source_url: 'https://flight.naver.com/test',
      status: 'requires_browser_network',
      summary: '검색 조건은 확인했지만 실시간 운임은 사이트 화면에서 확인해야 합니다.',
      evidence: ['verdict=weak_ok'],
      fare_options_found: false,
    },
  ],
  blockers: ['실시간 항공권 후보를 자동 확정하지 못했습니다.'],
  agent_runs: [
    {
      agent_name: 'FlightSearchAnswerAgent',
      title: '항공권 검색 agent',
      status: 'completed',
      summary: '항공권 검색 출처를 확인했습니다.',
      evidence: [],
    },
  ],
}

function renderHome() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('HomePage', () => {
  beforeEach(() => {
    vi.mocked(createLLMAnswer).mockReset()
  })

  it('renders the direct LLM answer on home', async () => {
    vi.mocked(createLLMAnswer).mockResolvedValue(llmResponse)

    renderHome()

    await userEvent.type(
      screen.getByLabelText('여행 요청'),
      '삿포로 여행갈건데 기간은 7월 초 중순 사이고 오전출발 비행기 돌아오는건 오후출발 비행기 항공권 찾아줘',
    )
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    await waitFor(() => expect(screen.getByText(/삿포로 항공권 조건은/)).toBeInTheDocument())
    expect(screen.queryByText('검색 답변')).not.toBeInTheDocument()
    const chatPanel = screen.getByRole('region', { name: '여행 agent 대화' })
    const inspectorPanel = screen.getByRole('complementary', { name: 'agent 상태' })
    expect(within(chatPanel).queryByText('해석한 검색 조건')).not.toBeInTheDocument()
    expect(within(chatPanel).queryByText('현재 막힌 부분')).not.toBeInTheDocument()
    expect(inspectorPanel).toHaveTextContent('항공권 검색 agent')
    expect(inspectorPanel).toHaveTextContent('해석한 검색 조건')
    expect(inspectorPanel).toHaveTextContent('현재 막힌 부분')
    expect(screen.getByText('항공 검색: 서울 -> Sapporo, 2026-07-03 ~ 2026-07-15')).toBeInTheDocument()
    expect(screen.getByText('네이버 항공권')).toBeInTheDocument()
    expect(screen.getByText(/브라우저 확인 필요/)).toBeInTheDocument()
    expect(screen.queryByText(/requires_browser_network/)).not.toBeInTheDocument()
    expect(
      screen.getByText('실시간 항공권 후보를 자동 확정하지 못했습니다.'),
    ).toBeInTheDocument()
    expect(createLLMAnswer).toHaveBeenCalledWith(
      expect.objectContaining({
        message:
          '삿포로 여행갈건데 기간은 7월 초 중순 사이고 오전출발 비행기 돌아오는건 오후출발 비행기 항공권 찾아줘',
      }),
      expect.anything(),
    )
  })

  it('renders legacy LLM answer responses without source fields', async () => {
    vi.mocked(createLLMAnswer).mockResolvedValue({
      answer: '조건을 확인했습니다. 항공권 검색 조건을 기준으로 답변합니다.',
    })

    renderHome()

    await userEvent.type(screen.getByLabelText('여행 요청'), '삿포로 항공권 찾아줘')
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    await waitFor(() => {
      expect(screen.getByText(/조건을 확인했습니다/)).toBeInTheDocument()
    })
    expect(screen.queryByText('확인한 검색 출처')).not.toBeInTheDocument()
    expect(screen.queryByText('현재 막힌 부분')).not.toBeInTheDocument()
  })

  it('does not render blocked extraction output as a final chat answer', async () => {
    vi.mocked(createLLMAnswer).mockResolvedValue({
      answer: '항공권 후보를 아직 찾지 못했습니다.',
      answer_kind: 'blocked',
      interpreted_request: '항공 검색: 서울 -> Sapporo, 2026-07-03',
      blockers: ['실시간 항공권 후보를 자동 확정하지 못했습니다.'],
      source_attempts: [],
      agent_runs: [],
    })

    renderHome()

    await userEvent.type(screen.getByLabelText('여행 요청'), '삿포로 항공권 찾아줘')
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    await waitFor(() => {
      expect(screen.getByText('실시간 후보 추출 필요')).toBeInTheDocument()
    })
    expect(screen.queryByRole('region', { name: 'agent 답변' })).not.toBeInTheDocument()
    expect(screen.queryByText('항공권 후보를 아직 찾지 못했습니다.')).not.toBeInTheDocument()
  })
})
