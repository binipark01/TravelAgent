import { apiRequest } from './client'
import type { LLMAnswerRequest, LLMAnswerResponse } from '../types/llm'

export function createLLMAnswer(payload: LLMAnswerRequest): Promise<LLMAnswerResponse> {
  return apiRequest<LLMAnswerResponse>('/llm/answer', { method: 'POST', body: payload })
}
