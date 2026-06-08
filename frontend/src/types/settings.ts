export interface RuntimeSettings {
  readonly enable_live_llm: boolean
  readonly enable_flight_source_probes: boolean
  readonly codex_reasoning_effort: string
}

export type RuntimeSettingsUpdate = Partial<RuntimeSettings>
