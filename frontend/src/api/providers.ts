import type { ProviderStatus } from '../types/provider'
import { apiRequest } from './client'

export function getProviderStatus(): Promise<ProviderStatus[]> {
  return apiRequest<ProviderStatus[]>('/providers/status')
}
