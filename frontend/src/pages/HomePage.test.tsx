import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { addAgentRunMessage, createAgentRun, getAgentRun } from '../api/agent'
import type { AgentRunDetailResponse, AgentRunResponse } from '../types/agent'
import { HomePage } from './HomePage'

vi.mock('../api/agent', () => ({
  createAgentRun: vi.fn(),
  getAgentRun: vi.fn(),
  addAgentRunMessage: vi.fn(),
  listAgentRuns: vi.fn(),
}))

const RUN_ID = 'run_test1'

// POST는 run_id만 즉시 반환(아직 실행 전).
const queued = {
  trip_id: 'trip_test1',
  run_id: RUN_ID,
  status: 'queued',
  steps: [],
  missing_fields: [],
  questions: [],
  state_summary: null,
  partial_plan: null,
  events: [],
} as unknown as AgentRunResponse

// 폴링(GET)이 받는 완료 상태 — 항공 후보 1개 + 목적지.
const completedDetail = {
  run: {
    run_id: RUN_ID,
    trip_id: 'trip_test1',
    status: 'completed',
    started_at: '2026-06-18T00:00:00Z',
  },
  steps: [
    {
      step_id: 's1',
      run_id: RUN_ID,
      agent_name: 'FlightAgent',
      status: 'completed',
      input_summary: '',
      tool_calls: [],
    },
  ],
  events: [
    {
      event_id: 'e1',
      run_id: RUN_ID,
      trip_id: 'trip_test1',
      type: 'user_message',
      message: '',
      payload: { message: '삿포로 항공권 찾아줘' },
      created_at: '',
    },
  ],
  state_summary: {
    destination: 'Sapporo',
    origin: null,
    date_range: null,
    travelers: null,
    budget_total: null,
    budget_per_person: null,
    status: 'completed',
    missing_fields: [],
    assumptions: [],
  },
  state: {
    trip_id: 'trip_test1',
    selected_destination: 'Sapporo',
    transport_options: [
      {
        option_id: 'f1',
        airline: 'JAL',
        origin: '서울',
        destination: 'Sapporo',
        departure_time: '2026-07-03T09:30:00',
        arrival_time: '2026-07-03T12:00:00',
        price: { amount: 500000, currency: 'KRW' },
        refundable: false,
        booking_required: false,
        metadata: {
          provider_name: 'naver_flight',
          retrieved_at: '',
          source_ref: { is_mock: false },
          is_mock: false,
        },
        notes: [],
      },
    ],
    accommodation_options: [],
    poi_candidates: [],
    activity_options: [],
  },
} as unknown as AgentRunDetailResponse

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
    vi.mocked(createAgentRun).mockReset()
    vi.mocked(getAgentRun).mockReset()
    vi.mocked(addAgentRunMessage).mockReset()
    localStorage.clear()
  })

  it('요청을 보내면 createAgentRun을 호출하고 사용자 메시지를 띄운다', async () => {
    vi.mocked(createAgentRun).mockResolvedValue(queued)
    vi.mocked(getAgentRun).mockResolvedValue(completedDetail)

    renderHome()

    await userEvent.type(screen.getByLabelText('여행 요청'), '삿포로 항공권 찾아줘')
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    await waitFor(() => expect(createAgentRun).toHaveBeenCalled())
    expect(createAgentRun).toHaveBeenCalledWith(
      expect.objectContaining({ message: '삿포로 항공권 찾아줘' }),
    )
    // 채팅 말풍선 + '최근 요청' 사이드바 양쪽에 표시되므로 1개 이상이면 OK.
    await waitFor(() =>
      expect(screen.getAllByText('삿포로 항공권 찾아줘').length).toBeGreaterThan(0),
    )
  })

  it('run이 완료되면 폴링 결과(목적지)를 캔버스에 보여준다', async () => {
    vi.mocked(createAgentRun).mockResolvedValue(queued)
    vi.mocked(getAgentRun).mockResolvedValue(completedDetail)

    renderHome()

    await userEvent.type(screen.getByLabelText('여행 요청'), '삿포로 항공권 찾아줘')
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    await waitFor(() => expect(getAgentRun).toHaveBeenCalledWith(RUN_ID))
    await waitFor(() => expect(screen.getAllByText(/Sapporo/).length).toBeGreaterThan(0))
  })
})
