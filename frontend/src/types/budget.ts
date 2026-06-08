export interface BudgetBreakdown {
  flights: number
  accommodation: number
  food: number
  local_transport: number
  activities: number
  buffer: number
}

export interface BudgetEstimate {
  total_estimated_cost: number
  per_person_estimated_cost: number
  breakdown: BudgetBreakdown
  currency: string
  confidence: string
  budget_warnings: string[]
  assumptions: string[]
}
