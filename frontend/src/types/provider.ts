export interface ProviderStatus {
  readonly domain: string
  readonly name: string
  readonly source_type: string
  readonly connector: string
  readonly configured: boolean
  readonly enabled: boolean
  readonly missing_credentials: boolean
  readonly fallback_to_mock: boolean
  readonly status: string
  readonly reason: string
}
