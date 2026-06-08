import type { RuntimeSettings, RuntimeSettingsUpdate } from '../types/settings'
import { apiRequest } from './client'

export function getSettings(): Promise<RuntimeSettings> {
  return apiRequest<RuntimeSettings>('/settings')
}

export function updateSettings(payload: RuntimeSettingsUpdate): Promise<RuntimeSettings> {
  return apiRequest<RuntimeSettings>('/settings', { method: 'POST', body: payload })
}
